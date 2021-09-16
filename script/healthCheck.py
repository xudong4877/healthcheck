#!/usr/bin/python
# -*- coding: utf-8 -*-

# @Time    : 2020-11-20
# @Author  : xudong
# @Desc    : 针对supervisor的应用进行健康检查
# @Version : 1.0


import os
import sys
import time
import json
import yaml
import base64
import socket
import signal
import smtplib
import datetime
import platform
import threading
import subprocess
import psutil
import argparse
from email.header import Header
from email.mime.text import MIMEText
from collections import namedtuple
from supervisor.xmlrpc import SupervisorTransport

PSUTIL_CHECK_INTERVAL = 3.0
PY3 = sys.version_info[0] == 3
Version = '__version__'

if PY3:
    import http.client as httplib
    from xmlrpc.client import Transport, ServerProxy, Fault


    def iterkeys(d, **kw):
        return iter(d.keys(**kw))


    def iteritems(d, **kw):
        return iter(d.items(**kw))
else:
    import httplib
    from xmlrpclib import Transport, ServerProxy, Fault


    def iterkeys(d, **kw):
        return d.iterkeys(**kw)


    def iteritems(d, **kw):
        return d.iteritems(**kw)


def get_version():
    return Version

def shell(cmd):
    """
    执行系统命令
    :param cmd:
    :return: (exitcode, stdout, stderr)
    """
    # with os.popen(cmd) as f:
    #     return f.read()
    env_to_pass = dict(os.environ)
    proc = subprocess.Popen(cmd,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            env=env_to_pass)
    proc.wait()
    return (proc.returncode,) + proc.communicate()


def get_proc_cpu(pid):
    """
    获取进程CPU使用率
    :param pid:
    :return:
    """
    result=True
    data=0
    err=''
    try:
        if pid == 0: # 系统cpu使用率
            data = psutil.cpu_percent(PSUTIL_CHECK_INTERVAL)
        else: # 进程cpu使用率
            data = psutil.Process(pid).cpu_percent(PSUTIL_CHECK_INTERVAL)
    except Exception as e:
        result=False
        err=e
    return result, data, err

def get_proc_mem(pid, type="rss"):
    """
    获取进程内存使用
    :param pid:
    :param type:
    :return:
    """
    result=True
    data=0
    err=''
    try:
        if pid == 0: # 系统内存使用
            mem = psutil.virtual_memory()
            data = mem.used
        else: # 进程内存使用
            if type == "rss":
                data = psutil.Process(pid).memory_full_info().rss
            elif type == "pss":
                data = psutil.Process(pid).memory_full_info().pss
            elif type == "uss":
                data = psutil.Process(pid).memory_full_info().uss

        data = data / 1024 / 1024 # 单位是 Byte,这里返回MB单位
        # print("pid %s get_proc_mem end, mem %s" % (pid, psutil.Process(pid).memory_full_info()))
    except Exception as e:
        result=False
        err=e
    
    return result, int(data), err


class WorkerThread(threading.Thread):
    """
    自定义Thread, 记录线程的异常信息
    """

    def __init__(self, target=None, args=(), kwargs={}, name=None):
        super(WorkerThread, self).__init__(target=target, args=args, kwargs=kwargs, name=name)
        self._target = target
        self._args = args
        self._kwargs = kwargs

        self.exception = None

    def run(self):
        try:
            if self._target:
                self._target(*self._args, **self._kwargs)
        except Exception as e:
            # 记录线程异常
            self.exception = sys.exc_info()
        finally:
            del self._target, self._args, self._kwargs

    def get_exception(self):
        return self.exception


class HealthCheck(object):
    def __init__(self, config):
        """
        初始化配置
        :param config:
        """

        self.mail_config = None
        self.supervisord_url = 'unix:///var/run/supervisor/supervisor.sock'

        if 'config' in config:
            self.mail_config = config['config'].get('mail')
            self.supervisord_url = config['config'].get('supervisordUrl', self.supervisord_url)
            self.supervisord_user = config['config'].get('supervisordUser', None)
            self.supervisord_pass = config['config'].get('supervisordPass', None)
            config.pop('config')

        self.program_config = config

        # 只保留通知action
        self.notice_action = ['email']

        self.mincontinueRun = 8*60*60
        self.periodSeconds = 5
        self.failureThreshold = 3
        self.successThreshold = 1
        self.initialDelaySeconds = 1
        self.sendResolved = False

        self.mem_type = 'rss'
        self.max_mem = 1024
        self.max_cpu = 90

    def get_supervisord_conn(self):
        """
        获取supervisor的连接
        :return:
        """
        transport = SupervisorTransport(self.supervisord_user, self.supervisord_pass, self.supervisord_url)
        s = ServerProxy('http://127.0.0.1', transport=transport)

        return s

    def get_pid(self, program, kind, pid_file):
        """
        获取进程pid
        :param program:
        :param kind:
        :param pid_file:
        :return:
        """
        pid = 0
        starttime = 0
        err = ''

        if kind == 'supervisor':
            # 通过supervisor程序获取pid
            try:
                s = self.get_supervisord_conn()
                info = s.supervisor.getProcessInfo(program)
                pid = info.get('pid')
                starttime = info.get('start')
                err = info.get('description')
            except Exception as e:
                self.log(program, "PID: Can't get pid from supervisor %s ", e)

        elif kind == 'name':
            # 通过进程名称获取pid
            pscommand = "ps -A -o pid,cmd | grep '[%s]%s' | awk '{print $1}' | head -1"
            exitcode, stdout, stderr = shell(pscommand % (program[0], program[1:]))
            if exitcode == 0:
                if stdout.decode() != '':
                    pid = int(stdout.strip())
                else:
                    pid = 0
            else:
                err = stderr.decode()
                self.log(program, "PID: Can't get pid from name %s ", err)
                pid = 0

        elif kind == 'file':
            # 通过文件获取pid
            if pid_file:
                try:
                    with open(pid_file) as f:
                        pid = f.read().strip()
                except Exception as e:
                    self.log(program, "PID: Can't get pid from file %s ", e)
                    err = "Can't get pid from file"
            else:
                err = "PID: pid file not set."
                self.log(program, err)

        if not pid:
            pid = 0

        return pid, err

    def log(self, program, msg, *args):
        """
        写信息到 STDERR.
        :param program:
        :param msg:
        :param args:
        :return:
        """

        curr_dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sys.stderr.write(
            '%s [%s] %s\n' % (curr_dt, program, msg % args,))

        sys.stderr.flush()

    def check(self, config):
        """
        检查主函数
        :param config:
        :return:
        """
        check_state = {}

        program = config.get('program')
        mincontinueRun = config.get('mincontinueRun', self.mincontinueRun)
        periodSeconds = config.get('periodSeconds', self.periodSeconds)
        failureThreshold = config.get('failureThreshold', self.failureThreshold)
        successThreshold = config.get('successThreshold', self.successThreshold)
        initialDelaySeconds = config.get('initialDelaySeconds', self.initialDelaySeconds)
        sendResolved = config.get('sendResolved', self.sendResolved)

        action_type = config.get('action', 'restart')
        check_type = config.get('type', 'http').lower()

        if check_type == 'http':
            check_method = self.http_check
        elif check_type == 'tcp':
            check_method = self.tcp_check
        elif check_type == 'mem':
            check_method = self.mem_check
        elif check_type == 'cpu':
            check_method = self.cpu_check
        elif check_type == 'restart':
            # 使用重启次数方式监控,默认将连续成功阈值设置为最小持续运行时长/检查频率
            successThreshold = mincontinueRun/periodSeconds
            check_method = self.restart_check
        elif check_type == 'command':
            check_method = self.cmd_check

        while 1:
            if program not in check_state:
                check_state[program] = {
                    'periodSeconds': 1,
                    'pid': 0,
                    'failure': 0,
                    'success': 0,
                    'unstart': 0,
                    'action': False
                }
                self.log(program, '[CONFIG]: %s', config)
                time.sleep(initialDelaySeconds)

            # self.log(program, '%s check state: %s', check_type, json.dumps(check_state[program]))
            if check_state[program]['periodSeconds'] % periodSeconds == 0:
                check_result = check_method(config, check_state[program]['pid'])
                check_status = check_result.get('status', None)
                check_state[program]['pid'] = check_result.get('pid', 0)
                check_info = check_result.get('info', '')
                self.log(program, '[%s check]: info(%s) state(%s) count(%s)', check_type.upper(), check_info, check_status, check_state[program][check_status])

                if check_status == 'failure':
                    check_state[program]['failure'] += 1
                    # 只要失败一次就清零成功计数
                    check_state[program]['success'] = 0
                elif check_status == 'success':
                    check_state[program]['success'] += 1
                elif check_status == 'unstart':
                    check_state[program]['success'] = 0
                    check_state[program]['failure'] = 0

                # 先判断成功次数
                if check_state[program]['success'] >= successThreshold:
                    # 只有开启恢复通知和检测失败并且执行操作后,才可以发送恢复通知
                    if sendResolved and check_state[program]['action']:
                        send_action = ','.join(list(set(action_type.split(',')) & set(self.notice_action)))
                        self.log(program, '[Resolved] Use %s.', send_action)
                        action_param = {
                            'check_status': check_status,
                            'action_type': send_action,
                            'msg': check_result.get('msg', '')
                        }
                        self.action(program, **action_param)

                    # 成功后,将项目状态初始化
                    check_state[program]['failure'] = 0
                    check_state[program]['success'] = 0
                    check_state[program]['action'] = False

                # 再判断失败次数
                if check_state[program]['failure'] >= failureThreshold:
                    action_param = {
                        'config': config,
                        'action_type': action_type,
                        'check_status': check_status,
                        'msg': check_result.get('msg', '')
                    }
                    self.action(program, **action_param)
                    check_state[program]['action'] = True
                    # 失败后,将项目状态初始化
                    check_state[program]['failure'] = 0

                # 间隔时间清零
                check_state[program]['periodSeconds'] = 0

            time.sleep(1)
            check_state[program]['periodSeconds'] += 1

    def http_check(self, config, prepid):
        """
        用于检查http连接
        :param config:
        :return: dict
        """
        program = config.get('program')
        config_host = config.get('host', 'localhost')
        config_path = config.get('path', '/')
        config_port = config.get('port', '80')

        config_method = config.get('method', 'GET')
        config_timeoutSeconds = config.get('timeoutSeconds', 3)
        config_body = config.get('body', '')
        config_json = config.get('json', '')
        config_headers = config.get('headers', '')

        config_username = config.get('username', '')
        config_password = config.get('password', '')

        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        local_proc = config.get('localProc', 1)

        HEADERS = {'User-Agent': 'meichuang http_check'}

        headers = HEADERS.copy()
        if config_headers:
            try:
                headers.update(json.loads(config_headers))
            except Exception as e:
                self.log(program, '[http_check]: config_headers not loads: %s , %s', config_headers, e)
            if config_json:
                headers['Content-Type'] = 'application/json'

        if config_username and config_password:
            auth_str = '%s:%s' % (config_username, config_password)
            headers['Authorization'] = 'Basic %s' % base64.b64encode(auth_str.encode()).decode()

        if config_json:
            try:
                config_body = json.dumps(config_json)
            except Exception as e:
                self.log(program, '[http_check]: config_json not loads: %s , %s', json, e)

        check_info = '%s %s %s %s %s %s' % (config_host, config_port, config_path, config_method,
                                            config_body, headers)

        if local_proc == 1:
            pid, err = self.get_pid(program, pid_get, pid_file)
            if pid == 0:
                self.log(program, '[http_check]: check error, program not starting.')
                return {'status': 'unstart',
                        'msg': '[http_check] program not starting, message: %s.' % err,
                        'info': check_info}

        try:
            httpClient = httplib.HTTPConnection(config_host, config_port, timeout=config_timeoutSeconds)
            httpClient.request(config_method, config_path, config_body, headers=headers)
            res = httpClient.getresponse()
        except Exception as e:
            self.log(program, '[http_check]: conn error, %s', e)
            return {'status': 'failure', 'msg': '[http_check] %s' % e, 'info': check_info}
        finally:
            if httpClient:
                httpClient.close()

        if res.status != httplib.OK:
            return {'status': 'failure', 'msg': '[http_check] return code %s' % res.status, 'info': check_info}

        return {'status': 'success', 'msg': '[http_check] return code %s' % res.status, 'info': check_info}

    def tcp_check(self, config, prepid):
        """
        用于检查TCP连接
        :param config:
        :return: dict
        """
        program = config.get('program')
        host = config.get('host', 'localhost')
        port = config.get('port', 80)
        timeoutSeconds = config.get('timeoutSeconds', 3)
        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        local_proc = config.get('localProc', 1)
        check_info = '%s %s' % (host, port)

        if local_proc == 1:
            pid, err = self.get_pid(program, pid_get, pid_file)
            if pid == 0:
                self.log(program, '[tcp_check]: check error, program not starting.')
                return {'status': 'unstart',
                        'msg': '[tcp_check] program not starting, message: %s.' % err,
                        'info': check_info}

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeoutSeconds)
            sock.connect((host, port))
            sock.close()
        except Exception as e:
            self.log(program, '[tcp_check]: conn error, %s', e)
            return {'status': 'failure', 'msg': '[tcp_check] %s' % e, 'info': check_info}
        return {'status': 'success', 'msg': '[tcp_check] connection succeeded', 'info': check_info}

    def mem_check(self, config, prepid):
        """
        用于检查进程内存
        :param config:
        :return: dict
        """
        program = config.get('program')
        max_mem = config.get('maxMem', self.max_mem)
        mem_type = config.get('memType', self.mem_type)
        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        check_info = 'max_mem:{max_mem}MB mem_type:{type}'.format(max_mem=max_mem, type=mem_type)

        if program == 'system':
            pid = 0
        else:
            pid, err = self.get_pid(program, pid_get, pid_file)
            if pid == 0:
                self.log(program, '[mem_check]: check error, program not starting.')
                return {'status': 'unstart',
                        'pid': pid,
                        'msg': '[mem_check] program not starting, message: {err}.'.format(err=err),
                        'info': check_info}
        result, now_mem, err = get_proc_mem(pid, mem_type)
        if not result:
            check_info = '{info} get_proc_mem failed, pid:{pid}, error:{err}'.format(info=check_info, pid=pid, err=err)
            return {'status': 'failure',
                    'pid': pid,
                    'msg': '[mem_check] max_mem({max_mem}MB) now_mem({now}MB)'.format(max_mem=max_mem, now=now_mem),
                    'info': check_info}
        check_info = '{info} now_mem:{now}MB pid:{pid}'.format(info=check_info, now=now_mem, pid=pid)
        if now_mem >= int(max_mem):
            return {'status': 'failure',
                    'pid': pid,
                    'msg': '[mem_check] max_mem({max_mem}MB) now_mem({now}MB)'.format(max_mem=max_mem, now=now_mem),
                    'info': check_info}

        return {'status': 'success',
                'pid': pid,
                'msg': '[mem_check] max_mem({max_mem}MB) now_mem({now}MB)'.format(max_mem=max_mem, now=now_mem),
                'info': check_info}

    def cpu_check(self, config, prepid):
        """
        用于检查进程CPU
        :param config:
        :return: dict
        """
        program = config.get('program')
        max_cpu = config.get('maxCpu', self.max_cpu)
        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        check_info = 'max_cpu:{cpu}%'.format(cpu=max_cpu)

        if program == 'system':
            pid = 0
        else:
            pid, err = self.get_pid(program, pid_get, pid_file)
            if pid == 0:
                self.log(program, '[cpu_check]: check error, program not starting.')
                return {'status': 'unstart',
                        'pid': pid,
                        'msg': '[cpu_check] program not starting, message: %s.' % err,
                        'info': check_info}
        result, now_cpu, err = get_proc_cpu(pid)
        if not result:
            check_info = '{info} get_proc_cpu failed, pid:{pid}, error:{err}'.format(info=check_info, pid=pid, err=err)
            return {'status': 'failure',
                    'pid': pid,
                    'msg': '[cpu_check] max_cpu({max_cpu}%) now_cpu({now}%)'.format(max_cpu=max_cpu, now=now_cpu),
                    'info': check_info}
        check_info = '{info} now_cpu:{now}% pid:{pid}'.format(info=check_info, now=now_cpu, pid=pid)
        if now_cpu >= max_cpu:
            return {'status': 'failure',
                    'pid': pid,
                    'msg': '[cpu_check] max_cpu({max_cpu}%) now_cpu({now}%)'.format(max_cpu=max_cpu, now=now_cpu),
                    'info': check_info}

        return {'status': 'success',
                'pid': pid,
                'msg': '[cpu_check] max_cpu({max_cpu}%) now_cpu({now}%)'.format(max_cpu=max_cpu, now=now_cpu),
                'info': check_info}
   
    def restart_check(self, config, prepid):
        """
        用于检查进程重启次数
        :param config:
        :return: dict
        """
        program = config.get('program')
        max_count = config.get('failureThreshold', self.failureThreshold)
        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        check_info = 'max_count:{count}'.format(count=max_count)

        pid, err = self.get_pid(program, pid_get, pid_file)
        if pid == 0:
            self.log(program, '[restart_check]: check error, program not starting.')
            if prepid:
                return {'status': 'failure',
                    'pid': pid,
                    'msg': '[restart_check] cur_pid({pid}) pre_pid({prepid})'.format(pid=pid, prepid=prepid),
                    'info': check_info}
            else:
                return {'status': 'unstart',
                        'pid': pid,
                        'msg': '[restart_check] program not starting, message: %s.' % err,
                        'info': check_info}
        check_info = '{info} pid:{pid}'.format(info=check_info, pid=pid)
        if prepid and prepid != pid:
            return {'status': 'failure',
                    'pid': pid,
                    'msg': '[restart_check] cur_pid({pid}) pre_pid({prepid})'.format(pid=pid, prepid=prepid),
                    'info': check_info}

        return {'status': 'success',
                'pid': pid,
                'msg': '[restart_check] cur_pid({pid}) pre_pid({prepid})'.format(pid=pid, prepid=prepid),
                'info': check_info}

    def cmd_check(self, config, prepid):
        """
        用于检查执行命令
        :param config:
        :return: dict
        """
        program = config.get('program')
        checkCmd = config.get('checkCmd', '')
        successValue = config.get('successValue', 0)
        pid_get = config.get('pidGet', 'supervisor')
        pid_file = config.get('pidFile', )
        local_proc = config.get('localProc', 1)
        check_info = '%s %s' % (checkCmd, successValue)

        if local_proc == 1:
            pid, err = self.get_pid(program, pid_get, pid_file)
            if pid == 0:
                self.log(program, '[cmd_check]: check error, program not starting.')
                return {'status': 'unstart',
                        'msg': '[cmd_check] program not starting, message: %s.' % err,
                        'info': check_info}

        exitcode, stdout, stderr = shell(checkCmd)
        if exitcode != successValue:
            err = stderr.decode()
            self.log(program, '[cmd_check]: exec(cmd:%s,return:%s) failed, %s', checkCmd, exitcode, err)
            return {'status': 'failure', 'msg': '[cmd_check] exec(cmd:%s,return:%s) failed, %s' % (checkCmd, exitcode, err), 'info': check_info}
        return {'status': 'success', 'msg': '[cmd_check] exec(cmd:%s) succeeded' % checkCmd, 'info': check_info}

    def action(self, program, **args):
        """
        执行动作
        :param program:
        :param args:
        :return: None
        """
        action_type = args.get('action_type')
        msg = args.get('msg')
        check_status = args.get('check_status')
        config = args.get('config')

        self.log(program, '[Action: %s]', action_type)
        action_list = action_type.split(',')

        if 'restart' in action_list:
            pid_get = config.get('pidGet', 'supervisor')
            pid_file = config.get('pidFile', )
            pid, err = self.get_pid(program, pid_get, pid_file)
            self.action_dump_stack(program, pid)
            restart_result = self.action_supervisor_restart(program)
            msg += '\r\nRestart: %s' % restart_result
        elif 'exec' in action_list:
            action_exec_cmd = config.get('execCmd')
            exec_result = self.action_exec(program, action_exec_cmd)
            msg += '\r\nExec: %s' % exec_result
        elif 'kill' in action_list:
            pid_get = config.get('pidGet', 'supervisor')
            pid_file = config.get('pidFile', )
            pid, err = self.get_pid(program, pid_get, pid_file)
            self.action_dump_stack(program, pid)
            kill_result = self.action_kill(program, pid)
            msg += '\r\nKill: %s' % kill_result

        if 'email' in action_list and self.mail_config:
            self.action_email(program, action_type, msg, check_status)

    def action_supervisor_restart(self, program):
        """
        通过supervisor的rpc接口重启进程
        :param program:
        :return:
        """
        result = 'success'
        try:
            s = self.get_supervisord_conn()
            info = s.supervisor.getProcessInfo(program)
        except Exception as e:
            result = 'Get %s ProcessInfo Error: %s' % (program, e)
            self.log(program, '[Action: restart] %s' % result)
            return result

        if info['state'] == 20:
            try:
                stop_result = s.supervisor.stopProcess(program)
                self.log(program, '[Action: restart] stop result %s', stop_result)
            except Fault as e:
                result = 'Failed to stop process %s, exiting: %s' % (program, e)
                self.log(program, '[Action: restart] stop error %s', result)
                return result

            time.sleep(1)
            info = s.supervisor.getProcessInfo(program)

        if info['state'] != 20:
            try:
                start_result = s.supervisor.startProcess(program)
                self.log(program, '[Action: restart] start result %s', start_result)
            except Fault as e:
                result = 'Failed to start process %s, exiting: %s' % (program, e)
                self.log(program, '[Action: restart] start error %s', result)
                return result

        return result

    def action_exec(self, program, cmd):
        """
        执行系统命令
        :param program:
        :param cmd:
        :return:
        """
        exitcode, stdout, stderr = shell(cmd)

        if exitcode == 0:
            self.log(program, "[Action: exec] cmd(%s) result success", cmd)
        else:
            result = 'Failed to exec cmd(%s), exiting: %s' % (cmd, exitcode)
            self.log(program, "[Action: exec] result %s", result)
            return False

        return True

    def action_kill(self, program, pid):
        """
        杀死进程
        :param program:
        :param pid:
        :return:
        """
        if int(pid) < 3:
            result='Failed to kill %s, pid: %s ' % (program, pid)
            self.log(program, "[Action: kill] result %s", result)
            return False

        cmd = "kill -9 %s" % pid
        exitcode, stdout, stderr = shell(cmd)

        if exitcode == 0:
            self.log(program, "[Action: kill] result success")
        else:
            result = 'Failed to kill %s, pid: %s exiting: %s' % (program, pid, exitcode)
            self.log(program, "[Action: kill] result %s", result)
            return False

        return True

    def action_email(self, program, action_type, msg, check_status):
        """
        发送email
        :param program:
        :param action_type:
        :param msg:
        :param check_status:
        :return:
        """

        ip = ""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception as e:
            self.log(program, '[Action: email] get ip error %s' % e)
        finally:
            s.close()

        hostname = platform.node().split('.')[0]
        system_platform = platform.platform()

        if check_status == 'success':
            subject = "[Supervisor] %s Health check successful" % program
        else:
            subject = "[Supervisor] %s Health check failed" % program
        curr_dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content = """
DateTime: {curr_dt}
Program: {program}
IP: {ip}
Hostname: {hostname}
Platfrom: {system_platform}
Action: {action}
Msg: {msg}
        """.format(curr_dt=curr_dt, program=program, ip=ip, hostname=hostname, system_platform=system_platform,
                   action=action_type, msg=msg)
        # self.log(program, '[Action: email] mail content %s', content)
        mail_port = self.mail_config.get('port', '')
        mail_host = self.mail_config.get('host', '')
        mail_user = self.mail_config.get('user', '')
        mail_pass = self.mail_config.get('pass', '')
        to_list = self.mail_config.get('to_list', [])

        msg = MIMEText(content, _subtype='plain', _charset='utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = mail_user
        msg['to'] = ",".join(to_list)
        try:
            s = smtplib.SMTP_SSL(mail_host, mail_port)
            s.login(mail_user, mail_pass)
            s.sendmail(mail_user, to_list, msg.as_string())
            s.quit()
        except Exception as e:
            self.log(program, '[Action: email] send error %s' % e)
            return False

        self.log(program, '[Action: email] send success.')
        return True

    def action_dump_stack(self, program, pid):
        """
        收集进程堆栈信息
        :param program:
        :param pid:
        :return:
        """
        if int(pid) <= 0:
            result = 'Failed to dump stack %s, pid: %s ' % (program, pid)
            self.log(program, "[Action: dump_stack] result %s", result)
            return False

        curr_dt = datetime.datetime.now().strftime('%Y%m%d%H%M%S')

        cmd = "pstack %s > %s-%s-%s.stack" % (pid, curr_dt, program, pid)
        exitcode, stdout, stderr = shell(cmd)

        if exitcode == 0:
            self.log(program, "[Action: dump_stack] result success")
        else:
            result = 'Failed to dump stack %s, pid: %s exiting: %s' % (program, pid, exitcode)
            self.log(program, "[Action: dump_stack] result %s", result)
            return False

        return True

    def start(self):
        """
        启动检测
        :return:
        """
        self.log('healthCheck', 'start, version:%s.', get_version())
        threads = []
        threads_data = {}

        for key, value in iteritems(self.program_config):
            item = value
            item['case'] = key
            t = WorkerThread(target=self.check, args=(item,), name=key)
            threads.append(t)
            threads_data[key] = item

        for t in threads:
            t.setDaemon(True)
            t.start()

        while 1:
            time.sleep(0.1)
            for i, t in enumerate(threads):
                if not t.isAlive():
                    thread_name = t.getName()
                    self.log('ERROR', 'Exception in %s (catch by main): %s' % (thread_name, t.get_exception()))
                    self.log('ERROR', 'Create new Thread!')
                    t = WorkerThread(target=self.check, args=(threads_data[thread_name],), name=thread_name)
                    t.setDaemon(True)
                    t.start()
                    threads[i] = t


if __name__ == '__main__':
    # 版本号处理
    parse = argparse.ArgumentParser()
    parse.add_argument('-v', '--version', action='version', version=get_version(), help='Display version')
    parse.parse_args()
    
    # 信号处理
    def sig_handler(signum, frame):
        print("Exit check!")
        sys.exit(0)


    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGQUIT, sig_handler)

    # 获取当前目录下的配置文件,没有的话就生成个模板
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
    if not os.path.exists(config_file):
        example_config = """
config:                                          # 脚本配置名称,请勿更改
  supervisordUrl: http://localhost:9001/RPC2     # supervisor的接口地址, 默认使用本地socket文件unix:///var/run/supervisor.sock
  supervisordUser: user                          # supervisor中设置的username, 没有设置可不填
  supervisordPass: 123                           # supervisor中设置的password, 没有设置可不填
  mail:                                          # 邮箱通知配置
#    host: 'smtp.test.com'
#    port: '465'
#    user: 'ops@test.com'
#    pass: '123456'
#    to_list: ['test@test.com']

# 内存方式监控
cat1:
  program: test1          # supervisor中配置的program名称
  type: mem               # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  maxMem: 1024            # 内存阈值, 超过则为检测失败. 单位MB, 默认: 1024
  memType: rss            # 内存使用分类: rss, pss, uss 默认: rss
  pidGet: supervisor      # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
  pidFile: /var/run/t.pid # 指定pid文件的路径, 只在pidGet为file的时候有用
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 1     # 失败后检查成功的最小连续成功次数, 默认: 1
  action: restart,email   # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: command        # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False

# cpu方式监控
cat2:
  program: test2          # supervisor中配置的program名称
  type: cpu               # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  maxCpu: 90              # CPU阈值, 超过则为检测失败. 单位% 默认: 90%
  pidGet: supervisor      # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
  pidFile: /var/run/t.pid # 指定pid文件的路径, 只在pidGet为file的时候有用
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 1     # 失败后检查成功的最小连续成功次数, 默认: 1
  action: restart,email   # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: command        # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False

# HTTP方式监控
cat3:
  program: test3          # supervisor中配置的program名称
  type: http              # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  localProc: 1            # 是否为本地进程: 0(不是本地进程),1(本地进程) 默认: 1
  method: GET             # http动作: POST,GET 默认: GET
  host: localhost         # 主机地址, 默认: localhost
  path: /                 # URI地址, 默认: /
  port: 80                # 检测端口, 默认: 80
  json: '{"a":"b"}'       # POST的json数据
  headers: '{"c":1}'      # http的hearder头部数据
  username: test          # 用于http的basic认证
  password: pass          # 用于http的basic认证
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  timeoutSeconds: 3       # 检查超时的秒数, 默认: 3
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 1     # 失败后检查成功的最小连续成功次数, 默认: 1
  action: restart,email   # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: command        # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False

# TCP方式监控
cat4:
  program: test4          # supervisor中配置的program名称
  type: tcp               # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  localProc: 1            # 是否为本地进程: 0(不是本地进程),1(本地进程) 默认: 1
  host: localhost         # 主机地址, 默认: localhost
  port: 80                # 检测端口, 默认: 80
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  timeoutSeconds: 3       # 检查超时的秒数, 默认: 3
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 1     # 失败后检查成功的最小连续成功次数, 默认: 1
  action: restart,email   # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: command        # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False

# 重启次数监控
cat5:
  program: test5          # supervisor中配置的program名称
  type: restart           # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  pidGet: supervisor      # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor(重启次数监控时仅支持supervisor)
  pidFile: /var/run/t.pid # 指定pid文件的路径, 只在pidGet为file的时候有用
  mincontinueRun: 28800   # 进程持续运行最小时长(以秒为单位,超过该时长才认为进程运行正常), 默认: 28800(8*60*60:8小时)
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 14400 # 失败后检查成功的最小连续成功次数, 默认: 1(重启次数监控时默认为最少连续运行时间/检查频率)
  action: exec            # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: echo '123456'  # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False

# command方式监控
cat6:
  program: test6          # supervisor中配置的program名称
  type: command           # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
  localProc: 1            # 是否为本地进程: 0(不是本地进程),1(本地进程) 默认: 1
  checkCmd: command       # check exec 的执行命令
  successValue: 0         # 成功返回结果, 默认: 0
  periodSeconds: 5        # 检查的频率(以秒为单位), 默认: 5
  initialDelaySeconds: 1  # 首次检查等待的时间(以秒为单位), 默认: 1
  timeoutSeconds: 3       # 检查超时的秒数, 默认: 3
  failureThreshold: 3     # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
  successThreshold: 1     # 失败后检查成功的最小连续成功次数, 默认: 1
  action: restart,email   # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
  execCmd: command        # action exec 的执行命令
  sendResolved: False     # 是否发送恢复通知,仅用作于email. 默认: False
"""
        with open(config_file, 'w') as f:
            f.write(example_config)

        print("\r\n\r\nThe configuration file has been initialized, please modify the file to start.")
        print("Config File: %s\r\n\r\n" % config_file)
        sys.exit(0)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    check = HealthCheck(config)
    check.start()

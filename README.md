# healthCheck

负责对管理的进程进行健康检查，检测到进程假死、占用资源（cpu/内存）过多时会触发一些动作，类似于故障治愈功能。

## 一、功能说明

主要可以提供以下功能：

- 提供对管理的进程进行 cpu 资源占用检测
- 提供对管理的进程进行内存资源占用检测
- 提供对管理的进程进行 http 检测
- 提供对管理的进程进行 tcp 检测
- 提供对管理的进程进行重启次数检测
- 提供对管理的进程执行命令检测
- 提供对管理的进程出现以上检测异常进行重启的功能
- 提供对管理的进程出现以上检测异常进行强杀的功能
- 提供对管理的进程出现以上检测异常执行外部命令的功能
- 提供对管理的进程出现以上检测异常进行邮件通知的功能
- 提供对管理的进程出现重启或强杀异常时收集进程堆栈信息的功能

## 二、安装与卸载

### 1. 安装

```bash
# 解压后进入目录执行安装脚本
bash install.sh
```

安装脚本会自动完成以下操作：

- 安装 python3、python3-devel、python36-PyYAML 依赖
- 安装 supervisor 和 psutil
- 配置 supervisord 服务（systemd）
- 部署 healthCheck 到 `/etc/supervisord.d/scripts/`
- 启动 supervisord 服务并设置开机自启

### 2. 卸载

```bash
bash /etc/supervisord.d/uninstall.sh
```

卸载脚本会停止所有 supervisor 管理的进程并清理相关文件。

### 3. 版本

当前版本：`1.1-r4`

查看已安装版本：

```bash
python3 /etc/supervisord.d/scripts/healthCheck -v
```

## 三、进程健康检查配置文件说明

**路径：** `/etc/supervisord.d/scripts/config.yaml`

### 配置说明

```yaml
config: # 脚本配置名称,请勿更改
    supervisordUrl: http://localhost:9001/RPC2      # supervisor的接口地址, 默认使用本地socket文件unix:///var/run/supervisor.sock
    supervisordUser: user                           # supervisor中设置的username, 没有设置可不填
    supervisordPass: 123                            # supervisor中设置的password, 没有设置可不填
    mail:                                           # 邮箱通知配置
        host: 'smtp.test.com'                       # 邮箱服务器地址
        port: '465'                                 # 邮箱服务器端口
        user: 'ops@test.com'                        # 发件人账号
        pass: '123456'                              # 发件人账号密码
        to_list: ['test@test.com']                  # 收件人列表
```

### 内存方式监控

```yaml
# 内存方式监控
cat1:
    program: test1               # supervisor中配置的program名称
    type: mem                    # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    maxMem: 1024                 # 内存阈值, 超过则为检测失败. 单位MB, 默认: 1024
    memType: rss                 # 内存使用分类: rss, pss, uss 默认: rss
    pidGet: supervisor           # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
    pidFile: /var/run/t.pid      # 指定pid文件的路径, 只在pidGet为file的时候有用
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1          # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email        # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command             # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

### CPU 方式监控

```yaml
# cpu方式监控
cat2:
    program: test2               # supervisor中配置的program名称
    type: cpu                    # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    maxCpu: 90                   # CPU阈值, 超过则为检测失败. 单位% 默认: 90%
    pidGet: supervisor           # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
    pidFile: /var/run/t.pid      # 指定pid文件的路径, 只在pidGet为file的时候有用
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1          # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email        # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command             # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

### HTTP 方式监控

```yaml
# HTTP方式监控
cat3:
    program: test3               # supervisor中配置的program名称
    type: http                   # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    localProc: 1                 # 是否为本地进程: 0(不是本地进程,不检查pid),1(本地进程,检查pid) 默认: 1
    mode: GET                    # http动作: POST,GET 默认: GET
    host: localhost              # 主机地址, 默认: localhost
    path: /                      # URI地址, 默认: /
    port: 80                     # 检测端口, 默认: 80
    json: '{"a":"b"}'            # POST的json数据
    headers: '{"c":1}'           # http的header头部数据
    username: test               # 用于http的basic认证
    password: pass               # 用于http的basic认证
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    timeoutSeconds: 3            # 检查超时的秒数, 默认: 3
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1          # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email        # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command             # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

### TCP 方式监控

```yaml
# TCP方式监控
cat4:
    program: test4               # supervisor中配置的program名称
    type: tcp                    # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    localProc: 1                 # 是否为本地进程: 0(不是本地进程,不检查pid),1(本地进程,检查pid) 默认: 1
    host: localhost              # 主机地址, 默认: localhost
    port: 80                     # 检测端口, 默认: 80
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    timeoutSeconds: 3            # 检查超时的秒数, 默认: 3
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1          # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email        # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command             # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

### 重启次数监控

```yaml
# 重启次数监控
cat5:
    program: test5               # supervisor中配置的program名称
    type: restart                # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    pidGet: supervisor           # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor(重启次数监控时仅支持supervisor)
    pidFile: /var/run/t.pid      # 指定pid文件的路径, 只在pidGet为file的时候有用
    mincontinueRun: 28800        # 进程持续运行最小时长(以秒为单位,超过该时长才认为进程运行正常), 默认: 28800(8*60*60:8小时)
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 14400      # 失败后检查成功的最小连续成功次数, 默认: 1(重启次数监控时默认为最少连续运行时间/检查频率)
    action: exec                 # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: echo '123456'       # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

### command 方式监控

```yaml
# command方式监控
cat6:
    program: test6               # supervisor中配置的program名称
    type: command                # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    localProc: 1                 # 是否为本地进程: 0(不是本地进程,不检查pid),1(本地进程,检查pid) 默认: 1
    checkCmd: command            # check exec 的执行命令
    successValue: 0              # 成功返回结果, 默认: 0
    periodSeconds: 5             # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1       # 首次检查等待的时间(以秒为单位), 默认: 1
    timeoutSeconds: 3            # 检查超时的秒数, 默认: 3
    failureThreshold: 3          # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1          # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email        # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command             # action exec 的执行命令
    sendResolved: False          # 是否发送恢复通知,仅用作于email. 默认: False
```

> 每个cat代表一个进程的一种类型检测，如果一个进程需要检测多种类型，则需要配置多个cat，需要注意cat不能重复。为什么一个进程多种检测类型需要配置多个cat，因为每种检测类型的参数可能会不相同，所以cat是以类型为单位而不是以进程为单位。

## 四、如何将一个进程加入到进程健康检查中？

以 gateway 进程为例，检测类型为内存、cpu 和重启次数(不发送邮件)，需要做如下操作：

### 1. 修改进程健康检查的配置文件

```bash
cat /etc/supervisord.d/scripts/config.yaml
```

```yaml
config: # 脚本配置名称,请勿更改
    supervisordUrl: http://localhost:9001/RPC2      # supervisor的接口地址, 默认使用本地socket文件unix:///var/run/supervisor.sock
    supervisordUser: user                           # supervisor中设置的username, 没有设置可不填
    supervisordPass: 123                            # supervisor中设置的password, 没有设置可不填
    mail:                                           # 邮箱通知配置
#        host: 'smtp.test.com'                       # 邮箱服务器地址
#        port: '465'                                 # 邮箱服务器端口
#        user: 'ops@test.com'                        # 发件人账号
#        pass: '123456'                              # 发件人账号密码
#        to_list: ['test@test.com']                  # 收件人列表

# 内存方式监控
cat1:
    program: gateway            # supervisor中配置的program名称
    type: mem                   # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    maxMem: 1024                # 内存阈值, 超过则为检测失败. 单位MB, 默认: 1024
    memType: rss                # 内存使用分类: rss, pss, uss 默认: rss
    pidGet: supervisor          # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
    pidFile: /var/run/t.pid     # 指定pid文件的路径, 只在pidGet为file的时候有用
    periodSeconds: 5            # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1      # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3         # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1         # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email       # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command            # action exec 的执行命令
    sendResolved: False         # 是否发送恢复通知,仅用作于email. 默认: False

# cpu方式监控
cat2:
    program: gateway            # supervisor中配置的program名称
    type: cpu                   # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    maxCpu: 90                  # CPU阈值, 超过则为检测失败. 单位% 默认: 90%
    pidGet: supervisor          # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor
    pidFile: /var/run/t.pid     # 指定pid文件的路径, 只在pidGet为file的时候有用
    periodSeconds: 5            # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1      # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3         # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 1         # 失败后检查成功的最小连续成功次数, 默认: 1
    action: restart,email       # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: command            # action exec 的执行命令
    sendResolved: False         # 是否发送恢复通知,仅用作于email. 默认: False

# HTTP方式监控
#cat3:
#    program: test3
#    type: http
#    localProc: 1
#    mode: GET
#    host: localhost
#    path: /
#    port: 80
#    json: '{"a":"b"}'
#    headers: '{"c":1}'
#    username: test
#    password: pass
#    periodSeconds: 5
#    initialDelaySeconds: 1
#    timeoutSeconds: 3
#    failureThreshold: 3
#    successThreshold: 1
#    action: restart,email
#    execCmd: command
#    sendResolved: False

# TCP方式监控
#cat4:
#    program: test4
#    type: tcp
#    localProc: 1
#    host: localhost
#    port: 80
#    periodSeconds: 5
#    initialDelaySeconds: 1
#    timeoutSeconds: 3
#    failureThreshold: 3
#    successThreshold: 1
#    action: restart,email
#    execCmd: command
#    sendResolved: False

# 重启次数监控
cat5:
    program: gateway            # supervisor中配置的program名称
    type: restart              # 检查类型: http,tcp,mem,cpu,restart,command 默认: http
    pidGet: supervisor          # 获取pid的方式: supervisor,name,file, 选择name时,按program名称搜索pid,选择file时,需指定pidFile 默认: supervisor(重启次数监控时仅支持supervisor)
    pidFile: /var/run/t.pid     # 指定pid文件的路径, 只在pidGet为file的时候有用
    mincontinueRun: 28800      # 进程持续运行最小时长(以秒为单位,超过该时长才认为进程运行正常), 默认: 28800(8*60*60:8小时)
    periodSeconds: 5            # 检查的频率(以秒为单位), 默认: 5
    initialDelaySeconds: 1      # 首次检查等待的时间(以秒为单位), 默认: 1
    failureThreshold: 3         # 检查成功后, 最少连续检查失败多少次才被认定为失败, 默认: 3
    successThreshold: 14400      # 失败后检查成功的最小连续成功次数, 默认: 1(重启次数监控时默认为最少连续运行时间/检查频率)
    action: exec                # 触发的动作: restart,kill,exec,email (restart,kill和exec三者互斥,同时设置时restart生效) 默认: restart,email
    execCmd: sh /capaa/gateway/tools/bypass_new.sh 1   # action exec 的执行命令
    sendResolved: False         # 是否发送恢复通知,仅用作于email. 默认: False
```

### 2. 配置完成后需要重启 healthCheck 进程

```bash
supervisorctl restart healthCheck
```

### 3. 查看 healthCheck 运行情况

```bash
supervisorctl status healthCheck
```

输出：

```
healthCheck                          RUNNING   pid 2630, uptime 0 days, 00:00:12
```

## 五、如何将一个进程从进程健康检查中移除？

以 gateway 进程为例，需要做如下操作：

### 1. 删除 gateway 在进程健康检查配置文件里的配置

### 2. 删除后需要重启 healthCheck 进程

```bash
supervisorctl restart healthCheck
```

### 3. 查看 healthCheck 运行情况

```bash
supervisorctl status healthCheck
```

输出：

```
healthCheck                          RUNNING   pid 2942, uptime 0 days, 00:00:09
```

## 六、检测机制说明

### 1. 检测流程

每个 cat 配置项会启动一个独立的守护线程进行检测，线程异常退出时会自动重启。

检测流程如下：

1. 首次启动时等待 `initialDelaySeconds` 秒
2. 每隔 `periodSeconds` 秒执行一次检测
3. 检测失败时 failure 计数 +1，success 计数清零
4. 检测成功时 success 计数 +1，failure 计数不清零
5. 连续失败次数达到 `failureThreshold` 时触发动作
6. 连续成功次数达到 `successThreshold` 时认为恢复正常（可发送恢复通知）

### 2. 检测状态

- `success`：检测成功
- `failure`：检测失败
- `unstart`：进程未启动（不计入失败次数）

### 3. 动作执行

触发动作时会按以下顺序执行：

1. `restart`/`kill`/`exec` 三者互斥，同时设置时 `restart` 生效
2. 执行 `restart` 或 `kill` 动作前会先收集进程堆栈信息（pstack）
3. `email` 动作可与以上任意动作组合

### 4. 堆栈收集

当触发 `restart` 或 `kill` 动作时，会自动执行 pstack 收集进程堆栈信息，生成文件格式为：

```
{时间戳}-{program}-{pid}.stack
```

该文件保存在 healthCheck 进程的工作目录下，用于事后分析进程假死原因。

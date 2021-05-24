#!/bin/bash
#########################################################################
# File Name: install.sh
# Author: xudong
# mail: xudong@mchz.com.cn
# Created Time: Wed 09 Dec 2020 09:13:55 AM CST
#########################################################################
set -eu
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
#cur_dir=$(cd -P -- "$(dirname -- "$0")" && pwd -P)

# 入口函数
main() {
    result=0
    #1.install python3,python3-devel,python36-PyYAML
    cd ./rpmpackages || exit 1
    name_python3=$(rpm -qa python3)
    name_pydevel=$(rpm -qa python3-devel)
    name_PyYAML=$(rpm -qa python36-PyYAML)
    if [ ! -f ./"${name_python3}".rpm ] || [ ! -f ./"${name_pydevel}".rpm ] || [ ! -f ./"${name_PyYAML}".rpm ]; then
        yum localinstall ./*.rpm --nogpgcheck -y
        name_python3=$(rpm -qa python3)
        name_pydevel=$(rpm -qa python3-devel)
        name_PyYAML=$(rpm -qa python36-PyYAML)
        if [ ! -f ./"${name_python3}".rpm ] || [ ! -f ./"${name_pydevel}".rpm ] || [ ! -f ./"${name_PyYAML}".rpm ]; then
            rpm -iUh --force ./*.rpm
            name_python3=$(rpm -qa python3)
            name_pydevel=$(rpm -qa python3-devel)
            name_PyYAML=$(rpm -qa python36-PyYAML)
            if [ ! -f ./"${name_python3}".rpm ] || [ ! -f ./"${name_pydevel}".rpm ] || [ ! -f ./"${name_PyYAML}".rpm ]; then
                result=1
                cd ../;rm -rf "${cur_dir}"
                exit ${result}
            fi
        fi
    fi
    cd ../
    #2.install supervisor,psutil
    cd ./pypackages || exit 1
    pip3 install ./*
    cd ../
    if [ ! -f /usr/local/bin/supervisord ] || [ ! -f /usr/local/bin/supervisorctl ]; then
        result=1
        cd ../;rm -rf "${cur_dir}"
        exit ${result}
    fi
    #3.configure supervisord
    if [ ! -f /usr/lib/systemd/system/supervisord.service ]; then
        cp conf/supervisord.service /usr/lib/systemd/system/
    fi
    if [ ! -f /etc/tmpfiles.d/supervisor.conf ]; then
        echo "D /var/run/supervisor 0775 root root -" > /etc/tmpfiles.d/supervisor.conf
        chmod 0644 /etc/tmpfiles.d/supervisor.conf
    fi
    if [ ! -d /var/run/supervisor ]; then
        mkdir /var/run/supervisor/ -p
    fi
    if [ ! -d /var/log/supervisor ]; then
        mkdir /var/log/supervisor/ -p
    fi
    if [ ! -f /etc/supervisord.conf ]; then
        cp conf/supervisord.conf /etc/
    fi
    if [ ! -d /etc/supervisord.d/scripts ]; then
        mkdir /etc/supervisord.d/scripts/ -p
    fi
    if [ ! -f /etc/supervisord.d/healthCheck.ini ]; then
        cp conf/healthCheck.ini /etc/supervisord.d/
    fi
    ln -sfn /usr/local/bin/supervisorctl /usr/bin/supervisorctl
    ln -sfn /usr/local/bin/supervisord /usr/bin/supervisord
    \cp uninstall.sh /etc/supervisord.d/
    #4.install healthCheck
    \cp bin/healthCheck /etc/supervisord.d/scripts/
    if [ ! -f /etc/supervisord.conf ]; then
        cp bin/config.yaml /etc/supervisord.d/scripts/
    fi
    #5.start supervisord
    systemctl stop supervisord
    systemctl start supervisord
    if [ "$(systemctl is-enabled supervisord)" != "enabled" ]; then
        systemctl enable supervisord
    fi
    cd ../;rm -rf ./healthCheck
    exit ${result}
}

# main在此需要获取脚本本身的参数， 故将$@传递给main函数
main "$@"

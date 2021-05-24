#!/bin/bash
#########################################################################
# File Name: uninstall.sh
# Author: xudong
# mail: xudong@mchz.com.cn
# Created Time: Tue 23 Feb 2021 10:35:48 AM CST
#########################################################################
supervisorctl stop all
systemctl stop supervisord
if [ "$(systemctl is-enabled supervisord)" == "enabled" ]; then
    systemctl disable supervisord
fi
pip3 uninstall supervisor -y
rm -rf /etc/supervisord.d
rm -f /etc/supervisord.conf
rm -f /usr/local/bin/supervisor*
rm -f /etc/tmpfiles.d/supervisor.conf
rm -rf /var/log/supervisor 

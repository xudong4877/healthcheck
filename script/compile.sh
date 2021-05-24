#!/bin/bash
#########################################################################
# File Name: compile.sh
# Author: xudong
# mail: xudong@mchz.com.cn
# Created Time: Wed 16 Dec 2020 09:52:28 AM CST
#########################################################################
VERSION_FILE="../version"
version="$(awk <"${VERSION_FILE}" -F'-r' '{print $1}')"."$(awk <"${VERSION_FILE}" -F'-r' '{print $2}')"
echo "version${version}"
# 写入版本号
sed -i 's/^\('"Version = "'\).*/\1'"'${version}'"'/' healthCheck.py
python3 -O -m compileall -b .
mv healthCheck.pyc ../bin/healthCheck
# 将版本还原回来
sed -i 's/^\('"Version = "'\).*/\1'"'__version__'"'/' healthCheck.py
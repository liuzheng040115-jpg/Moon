#!/usr/bin/env bash
# 取二维码：如果 qrcode.png 太旧就重启 NapCat 刷一张新的
F=/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/cache/qrcode.png
now=$(date +%s)
if [ -f "$F" ]; then
  age=$(( now - $(stat -c %Y "$F") ))
else
  age=99999
fi
echo "qr age: ${age}s"
if [ "$age" -gt 100 ]; then
  echo "过期，重开登录窗口"
  pkill -x qq ; pkill -x xvfb-run ; sleep 2
  rm -f "$F"
  cd /root && nohup xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox > /root/napcat.log 2>&1 &
  sleep 18
fi
date '+now: %H:%M:%S'
stat -c 'qr:  %y' "$F" 2>/dev/null
echo "url: $(grep -aoE 'https://txz.qq.com/p[^ ]*' /root/napcat.log | tail -1)"

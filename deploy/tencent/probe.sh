#!/usr/bin/env bash
# 测服务器能不能下到 GitHub 脚本；跑完看哪条返回 200
urls=(
  "https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
  "https://ghfast.top/https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
  "https://gh-proxy.com/https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
  "https://ghproxy.net/https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
  "https://raw.gitmirror.com/NapNeko/NapCat-Installer/main/script/install.sh"
  "https://cdn.jsdelivr.net/gh/NapNeko/NapCat-Installer@main/script/install.sh"
)
for u in "${urls[@]}"; do
  code=$(curl -sL -o /dev/null -m 15 -w '%{http_code}' "$u" 2>/dev/null || echo ERR)
  echo "$code  $u"
done

echo "--- QQ 官方下载站 ---"
curl -sIL -o /dev/null -m 15 -w '%{http_code} %{url_effective}\n' https://im.qq.com/linuxqq/index.shtml || echo ERR

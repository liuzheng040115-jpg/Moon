#!/usr/bin/env bash
# 腾讯云轻量 Ubuntu 24.04 首次部署：系统依赖 + swap + Python venv + QQ/NapCat
# 用法（root）：bash /opt/qqbot/deploy/tencent/bootstrap.sh
# 前置：项目已解压到 /opt/qqbot
set -euo pipefail

APP_DIR=/opt/qqbot
PY=/usr/bin/python3

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 跑：sudo bash $0" >&2
  exit 1
fi

if [ ! -f "$APP_DIR/requirements.txt" ]; then
  echo "没找到 $APP_DIR/requirements.txt，先把 dist/qqbot-deploy.tar.gz 解压到 $APP_DIR" >&2
  exit 1
fi

echo "==> 1/4 系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  xvfb xauth unzip curl ca-certificates \
  fonts-noto-cjk fontconfig

# QQ Linux 运行时依赖；24.04 用 t64 包名，22.04 用旧名，装不上不致命
apt-get install -y --no-install-recommends \
  libasound2t64 libgbm1 libnss3 libxss1 libgtk-3-0t64 libnotify4 libxtst6 xdg-utils \
  || apt-get install -y --no-install-recommends \
  libasound2 libgbm1 libnss3 libxss1 libgtk-3-0 libnotify4 libxtst6 xdg-utils \
  || echo "!! QQ 运行时依赖没装全，起不来再手动补"

echo "==> 2/4 swap（2G 机器必加）"
if ! swapon --show | grep -q .; then
  fallocate -l 1G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "已启用 1G swap"
else
  echo "已有 swap，跳过"
fi

echo "==> 3/4 Python 环境"
$PY -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
"$APP_DIR/.venv/bin/python" -c "import nonebot; print('nonebot ok')"

mkdir -p "$APP_DIR/data" /var/log

echo "==> 4/4 QQ + NapCat（官方安装器，装到 /root/Napcat）"
# 国内机房直连 raw.githubusercontent 常被重置，用镜像前缀：GITHUB_PROXY=https://gh-proxy.com
GH_PROXY="${GITHUB_PROXY:-0}"
RAW="https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
if [ "$GH_PROXY" = "0" ]; then
  SCRIPT_URL="$RAW"
else
  SCRIPT_URL="${GH_PROXY%/}/$RAW"
  echo "GitHub 走镜像：$GH_PROXY"
fi

if [ -x /root/Napcat/opt/QQ/qq ]; then
  echo "已装过，跳过。要升级加 --force 重跑安装器"
else
  cd /root
  curl -fL --connect-timeout 20 --max-time 600 -o napcat.sh "$SCRIPT_URL"
  bash napcat.sh --docker n --cli y --github-proxy "$GH_PROXY"
fi

cat <<'EOF'

装完了。下一步：
  1) 首次登录：xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox -q <QQ号>
  2) 配反向 WS：ssh -L 6099:127.0.0.1:6099 root@<IP>  →  http://127.0.0.1:6099/webui
  3) 挂服务：cp deploy/tencent/*.service /etc/systemd/system/ && systemctl daemon-reload
             systemctl enable --now qqbot napcat
细节见 deploy/tencent/README.md
EOF

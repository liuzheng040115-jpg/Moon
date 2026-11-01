#!/usr/bin/env bash
# 把机器人数据打包成 tar.gz，放在 /root/backup/
# 用法： bash backup.sh [--with-qq]
#   --with-qq 连 QQ 登录态一起打（202M，换机器免扫码）
set -euo pipefail

OUT=/root/backup
STAGE="$OUT/stage"
STAMP=$(date +%Y%m%d-%H%M%S)
NAP_CFG=/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/config

mkdir -p "$OUT"
rm -rf "$STAGE"
mkdir -p "$STAGE/data" "$STAGE/napcat-config"

echo "== 1/4 停机器人（保证数据库一致）=="
systemctl stop qqbot 2>/dev/null || true

echo "== 2/4 备份 SQLite（含 WAL 里的内容）=="
python3 - <<'PY'
import sqlite3
src = sqlite3.connect("/opt/qqbot/data/bot.db")
dst = sqlite3.connect("/root/backup/stage/data/bot.db")
src.backup(dst)
dst.close(); src.close()
print("sqlite .backup ok")
PY

echo "== 3/4 收配置文件 =="
cp -a /opt/qqbot/.env "$STAGE/.env"
cp -a "$NAP_CFG"/. "$STAGE/napcat-config/"
if [ "${1:-}" = "--with-qq" ]; then
  echo "   带上 QQ 登录态（202M，慢一点）"
  cp -a /root/.config/QQ "$STAGE/QQ"
fi

echo "== 4/4 打包 =="
tar -czf "$OUT/qqbot-$STAMP.tar.gz" -C "$STAGE" .
rm -rf "$STAGE"
systemctl start qqbot 2>/dev/null || true

ls -lh "$OUT/qqbot-$STAMP.tar.gz"
echo "--- 内容 ---"
tar -tzf "$OUT/qqbot-$STAMP.tar.gz" | head -20

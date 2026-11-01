"""给 NapCat 加反向 WS：连到本机 8080 的 NoneBot。"""

import json
import os

CFG = "/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/onebot11_3680764546.json"
# token 不写死：部署时用 ONEBOT_TOKEN=xxx python patch_onebot.py 传进来
TOKEN = os.environ.get("ONEBOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("请先设置环境变量 ONEBOT_TOKEN（与 .env 的 ONEBOT_ACCESS_TOKEN 一致）")

with open(CFG, encoding="utf-8") as f:
    data = json.load(f)

data.setdefault("network", {})
data["network"]["websocketClients"] = [
    {
        "name": "qqbot",
        "enable": True,
        "url": "ws://127.0.0.1:8080/onebot/v11/ws",
        "reportSelfMessage": False,
        "messagePostFormat": "array",
        "token": TOKEN,
        "debug": False,
        "heartInterval": 30000,
        "reconnectInterval": 30000,
    }
]

with open(CFG, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(json.dumps(data["network"]["websocketClients"], ensure_ascii=False, indent=2))

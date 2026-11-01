"""QQ 机器人入口：NoneBot2 + OneBot v11（NapCat / Lagrange）。

启动： python bot.py
"""

import os
import sys
import time

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.log import logger

# Windows 控制台编码可能不支持中文，避免日志直接把进程打崩
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:  # pragma: no cover - 非交互流兜底
        pass

# 读取同目录下的 .env / .env.{ENVIRONMENT}
nonebot.init()

driver = nonebot.get_driver()

# 注册 OneBot v11 适配器（反向 WebSocket 服务端，供 NapCat / Lagrange 主动连入）
driver.register_adapter(OneBotV11Adapter)

# 加载 plugins/ 目录下的所有插件（含 ai_chat）
_plugins_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
loaded = nonebot.load_plugins(_plugins_dir)
logger.info(f"已加载插件: {', '.join(sorted(p.name for p in loaded)) or '(无)'}")

_STARTED_AT = time.time()

# 健康检查：GET /healthz，给看门狗 / 监控用
if hasattr(driver, "server_app"):
    @driver.server_app.get("/healthz")
    async def _healthz() -> dict:
        return {
            "ok": True,
            "uptime": round(time.time() - _STARTED_AT, 1),
            "bots": len(nonebot.get_bots()),
        }


@driver.on_startup
async def _on_startup() -> None:
    cfg = driver.config
    host = getattr(cfg, "host", "127.0.0.1")
    port = getattr(cfg, "port", 8080)
    logger.info(f"OneBot v11 反向 WS 监听: ws://{host}:{port}/onebot/v11/ws")
    logger.info("请在 NapCat / Lagrange 中把「反向 WebSocket」指向该地址，token 与 ONEBOT_ACCESS_TOKEN 一致")


if __name__ == "__main__":
    nonebot.run()

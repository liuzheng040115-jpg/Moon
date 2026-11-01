"""检修 / 恢复：切换活跃通道（谁来回 QQ 消息）。

两种实现方式，当前用第二种：

1. （旧）改 NapCat 的反向 WS 指向。问题：每次切换触发 NapCat 热重载，
   会把它的 WS 客户端搞坏，出现「连接意外关闭 / 5 秒重连」死循环。

2. （现用）NapCat 同时挂两条连接（8080 旧机器人 + 8643 DSH），切换只是把
   .tmp/active-channel.txt 写成 legacy 或 dsh。NapCat 连接完全不动，热重载
   的坑从根上消失。

- 私聊发「检修」→ 先反问确认（「你干嘛」），不切换
- 再发一次「检修」→ 才真的切到 DSH，回「正在打开 Moon」
- 私聊发「恢复」→ 切回旧机器人

只有 SUPERUSERS 能触发，且只在私聊生效。
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent
from nonebot.log import logger
from nonebot.rule import Rule

_ROOT = Path(__file__).resolve().parents[2]
# 只写开关文件，不碰 NapCat 配置（见模块 docstring 的第 2 种方式）
_SCRIPT = _ROOT / "scripts" / "set-channel.ps1"

# 二次确认的有效期（秒）：超时就得重新从第一次开始
_CONFIRM_TTL = 120.0

_MAINTENANCE_WORDS = {"检修", "checkup"}
_RESTORE_WORDS = {"恢复", "restore"}

# user_id -> 首次「检修」的时间戳；等第二次确认
_pending: dict[int, float] = {}


def _admin_private(bot: Bot, event: MessageEvent) -> bool:
    """只在私聊、且是 SUPERUSERS 时放行。"""
    if not isinstance(event, PrivateMessageEvent):
        return False
    configured = getattr(bot.config, "superusers", None) or set()
    return str(event.user_id) in {str(x) for x in configured}


def _word_of(event: MessageEvent) -> str | None:
    text = event.get_plaintext().strip().lstrip("/").strip().lower()
    if text in _MAINTENANCE_WORDS:
        return "检修"
    if text in _RESTORE_WORDS:
        return "恢复"
    return None


async def _rule(bot: Bot, event: MessageEvent) -> bool:
    return _admin_private(bot, event) and _word_of(event) is not None


relay_cmd = on_message(rule=Rule(_rule), priority=3, block=True)


def _run_switch(target: str) -> tuple[bool, str]:
    """把活跃通道写成 target（legacy / dsh），返回 (成功, 输出)。

    set-channel.ps1 用位置参数，所以直接跟在脚本路径后面。
    """
    if not _SCRIPT.exists():
        return False, f"找不到切换脚本：{_SCRIPT}"
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_SCRIPT),
                target,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(_ROOT),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("切换通道失败")
        return False, f"{type(exc).__name__}: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    if not ok:
        logger.warning(f"set-channel 返回 {proc.returncode}: {err or out}")
    return ok, err or out


@relay_cmd.handle()
async def _(bot: Bot, event: MessageEvent) -> None:
    word = _word_of(event)
    if word is None:
        return
    uid = int(event.user_id)

    if word == "恢复":
        _pending.pop(uid, None)
        await relay_cmd.send("正在收回 Moon…")
        await asyncio.sleep(1.0)
        ok, detail = await asyncio.to_thread(_run_switch, "legacy")
        logger.info(f"切回旧机器人: ok={ok} detail={detail[:300]}")
        if ok:
            await relay_cmd.finish("回来了，接着聊。")
        await relay_cmd.finish(f"没收回来：\n{detail[:800]}")

    # ---- 检修：二次确认 ----
    now = time.monotonic()
    first_at = _pending.get(uid)

    if first_at is None or now - first_at > _CONFIRM_TTL:
        # 第一次：只反问，不动任何东西
        _pending[uid] = now
        await relay_cmd.finish("你干嘛")

    # 第二次：确认，真的切
    _pending.pop(uid, None)
    await relay_cmd.send("正在打开 Moon")
    # 多留一点时间让这条回执真的落到手机，再断开 WS
    await asyncio.sleep(2.5)
    ok, detail = await asyncio.to_thread(_run_switch, "dsh")
    logger.info(f"切换到 DSH: ok={ok} detail={detail[:300]}")
    if not ok:
        # 切换失败，连接还在，能报错
        await relay_cmd.finish(f"Moon 没打开：\n{detail[:800]}")

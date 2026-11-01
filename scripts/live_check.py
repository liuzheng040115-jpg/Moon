r"""全链路自检：连上「正在运行的机器人」，用它自己的真实模型配置发两条消息。

用途：QQ/NapCat 还没配好时，先确认「机器人 ↔ 模型」这一段是通的。

用法：
  1. 另开一个窗口启动机器人： .venv\Scripts\python.exe bot.py
  2. 再运行： .venv\Scripts\python.exe scripts\live_check.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parent.parent
SELF_ID = 10001
FAKE_USER = 90001
FAKE_GROUP = 90002


def read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def event(kind: str, text: str, mid: int) -> dict:
    base = {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "message",
        "message_id": mid,
        "font": 0,
        "raw_message": text,
        "message": [{"type": "text", "data": {"text": text}}],
    }
    if kind == "private":
        base.update({
            "sub_type": "friend", "user_id": FAKE_USER, "message_type": "private",
            "target_id": SELF_ID,
            "sender": {"user_id": FAKE_USER, "nickname": "自检", "sex": "unknown", "age": 0},
        })
    else:
        base.update({
            "sub_type": "normal", "user_id": FAKE_USER, "message_type": "group",
            "group_id": FAKE_GROUP, "to_me": True, "anonymous": None,
            "message": [{"type": "at", "data": {"qq": str(SELF_ID)}}, {"type": "text", "data": {"text": text}}],
            "raw_message": f"[CQ:at,qq={SELF_ID}] {text}",
            "sender": {"user_id": FAKE_USER, "nickname": "自检", "card": "", "role": "member"},
        })
    return base


def text_of(message) -> str:
    if isinstance(message, str):
        return message
    return "".join(seg.get("data", {}).get("text", "") for seg in message or [] if seg.get("type") == "text")


class Client:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.actions: list[dict] = []
        self._cursor = 0

    async def pump(self) -> None:
        while True:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            except Exception:
                return
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            if "action" in frame:
                self.actions.append(frame)
                await self.ws.send(json.dumps({
                    "status": "ok", "retcode": 0,
                    "data": {"message_id": int(time.time() * 1000) % 100000},
                    "echo": frame.get("echo"),
                }))

    async def next_reply(self, timeout: float) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            while self._cursor < len(self.actions):
                action = self.actions[self._cursor]
                self._cursor += 1
                if action.get("action", "").startswith("send"):
                    text = text_of(action.get("params", {}).get("message"))
                    if text:
                        return text
            await asyncio.sleep(0.1)
        return None


async def main() -> int:
    env = read_env()
    port = env.get("PORT", "8080")
    token = env.get("ONEBOT_ACCESS_TOKEN", "")
    model = env.get("DEEPSEEK_MODEL", "?")
    url = f"ws://127.0.0.1:{port}/onebot/v11/ws"
    headers = {"X-Self-ID": str(SELF_ID), "Authorization": f"Bearer {token}"}

    print(f"连接 {url}  (模型 {model})")
    try:
        ws_ctx = websockets.connect(url, max_size=None, additional_headers=headers, open_timeout=8)
    except Exception as exc:
        print(f"连接失败：{exc}")
        return 1

    failures = 0
    try:
        async with ws_ctx as ws:
            client = Client(ws)
            pump = asyncio.create_task(client.pump())
            await asyncio.sleep(0.3)

            for kind, text, label in (
                ("private", "用一句话介绍你自己", "私聊"),
                ("group", "  再简单说说你能帮什么忙", "群聊 @"),
            ):
                start = time.time()
                await ws.send(json.dumps(event(kind, text, int(time.time() * 1000) % 100000)))
                reply = await client.next_reply(timeout=120)
                cost = time.time() - start
                if reply is None:
                    print(f"FAIL  {label}：120 秒内没有回复（看机器人窗口的报错）")
                    failures += 1
                elif reply.startswith("（出错了）"):
                    print(f"FAIL  {label}：{reply}")
                    failures += 1
                else:
                    print(f"PASS  {label} {cost:.1f}s -> {reply[:200]}")
            pump.cancel()
    except Exception as exc:
        print(f"FAIL  连接异常：{type(exc).__name__} {exc}")
        print("      检查：机器人是否在运行？端口/token 是否与 .env 一致？")
        return 1

    print()
    print("全链路正常 ✅" if failures == 0 else f"{failures} 项失败 ❌")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

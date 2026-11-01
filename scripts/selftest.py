r"""端到端自测：不需要真实的 QQ 和 DeepSeek Key。

流程：
  1. 起一个假的 DeepSeek 接口（OpenAI 兼容），返回固定回复并记录请求
  2. 用子进程启动 bot.py（监听 127.0.0.1:18099）
  3. 冒充 NapCat，用 WebSocket 连上 OneBot v11 反向 WS，发私聊 / 群聊 @ 消息
  4. 校验机器人确实通过 send_msg 回了话，且多轮对话带上了历史

运行： .venv\Scripts\python.exe scripts\selftest.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import websockets
from PIL import Image

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - 老环境兜底
        pass

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

FAKE_API_PORT = 18080
BOT_PORT = 18099
TOKEN = "selftest-token"
SELF_ID = 10001
PRIVATE_USER = 22222
GROUP_ID = 55555
GROUP_USER = 33333

records: list[dict] = []
_reply_counter = {"n": 0}


class FakeDeepSeek(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # 安静点
        pass

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}
        records.append(payload)
        _reply_counter["n"] += 1
        messages = payload.get("messages", [])
        user_text = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        corrected = any(m.get("role") == "system" and "出戏" in m.get("content", "") for m in messages)
        if "去群里说" in user_text:
            content = '好。\n[[SEND_GROUP:{"group_id":55555,"message":"测试群消息"}]]'
        elif "发收藏" in user_text:
            content = "给你。\n[[STICKER:#1]]"
        elif "别说话" in user_text:
            content = "[SKIP]"
        elif "测试语气" in user_text:
            content = "好呀。我这就去啦～"
        elif "测试句号" in user_text:
            content = "行吧。我知道了。"
        elif "主动开口" in user_text:
            content = "在干嘛"
        elif "来个表情" in user_text:
            content = "给你。\n[[STICKER:#1]]"
        elif "测试分段" in user_text:
            content = "第一句。第二句。第三句。第四句。第五句。第六句。"
        elif "测试自带" in user_text:
            content = "[[STICKER:干饭]]"
        elif "测试头像" in user_text:
            content = "行。\n[[ACTION:avatar:https://evil.example/x.jpg]]"
        elif "测试动作" in user_text:
            content = "行。\n[[ACTION:sign:乱改]]"
        elif "换签名" in user_text:
            content = "行，换个签名。\n[[ACTION:sign:今天也不上班]]"
        elif "文艺点那种" in user_text:
            content = "行。\n[[ACTION:sign:今天也不上班]]"
        elif "发条空间" in user_text:
            content = "行吧\n[[ACTION:qzone:今天天气不错]]"
        elif "记住我叫小明" in user_text:
            content = "好 小明\n[[REMEMBER:对方叫小明]]"
        elif "测试出戏" in user_text and not corrected:
            content = "我是 AI 助手，不是真人"
        else:
            content = f"测试回复#{_reply_counter['n']}"
        data = {
            "id": "fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", "fake"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def start_fake_api() -> ThreadingHTTPServer:
    class QuietServer(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address) -> None:  # 客户端断开时不刷 traceback
            pass

    server = QuietServer(("127.0.0.1", FAKE_API_PORT), FakeDeepSeek)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def port_open(port: int, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.4)
    return False


def fresh_db(name: str) -> Path:
    """每次测试用全新的 SQLite 文件，避免上一次的数据干扰断言。"""
    path = ROOT / ".tmp" / name
    for suffix in ("", "-wal", "-shm"):
        stale = Path(str(path) + suffix)
        if stale.exists():
            stale.unlink()
    return path


def seed_saved_sticker(db_path: Path) -> None:
    """生成一张测试用图片，预置成收藏表情，供“发收藏”使用。"""
    target = ROOT / ".tmp" / "seeded_sticker.png"
    Image.new("RGBA", (48, 48), (0, 90, 160, 255)).save(target)
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS saved_stickers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path   TEXT NOT NULL,
            description TEXT NOT NULL,
            usage_note  TEXT NOT NULL DEFAULT '',
            source_chat TEXT NOT NULL DEFAULT '',
            source_user TEXT NOT NULL DEFAULT '',
            context     TEXT NOT NULL DEFAULT '',
            image_hash  TEXT NOT NULL UNIQUE,
            created     REAL NOT NULL,
            last_used   REAL NOT NULL DEFAULT 0,
            use_count   INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    db.execute(
        "INSERT INTO saved_stickers(file_path, description, usage_note, source_chat, source_user, "
        "context, image_hash, created) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
        (str(target), "测试收藏表情", "测试用", "selftest", "tester", "selftest", "selftest-hash", time.time()),
    )
    db.commit()
    db.close()


def start_bot(
    port: int,
    log_name: str,
    extra_env: dict[str, str] | None = None,
    log_level: str = "WARNING",
) -> tuple[subprocess.Popen, object, Path]:
    log_path = ROOT / ".tmp" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "DRIVER": "~fastapi",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "LOG_LEVEL": log_level,
        "ONEBOT_ACCESS_TOKEN": TOKEN,
        "COMMAND_START": '["/"]',
        "DEEPSEEK_API_KEY": "sk-selftest",
        "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{FAKE_API_PORT}/v1",
        "DEEPSEEK_MODEL": "fake-model",
        "AI_TIMEOUT": "20",
        "AI_RETRIES": "0",
        "AI_RATE_RETRIES": "2",
        "AI_RETRY_BACKOFF": "0.1",
        "AI_RETRY_BACKOFF_MAX": "1",
        "AI_MODEL_MIN_INTERVAL": "0",
        "AI_RATE_LIMIT": "100",
        "AI_MAX_HISTORY": "5",
        "AI_REPLY_DELAY_MIN": "0",
        "AI_REPLY_DELAY_MAX": "0",
        "AI_SEND_CHARS": "15",
        "AI_SEND_MAX_BUBBLES": "4",
        "AI_VISION_MODEL": "",
        "AI_IMAGE_OCR": "true",
        "AI_WEB_SEARCH": "false",
        "AI_FISH_QQ": str(PRIVATE_USER),
        "AI_BOT_QQ": "0",
        "AI_NOTICE_QQ": str(PRIVATE_USER),
        "AI_STARTUP_NOTICE": "false",
        "AI_GROUP_TRIGGER": "auto",
        "AI_GROUP_AUTO_CHANCE": "0",
        "AI_GROUP_AUTO_COOLDOWN": "0",
        "AI_GROUP_AUTO_USER_COOLDOWN": "0",
        "AI_GROUP_AUTO_KEYWORDS": "大肥鱼,肥鱼",
        **(extra_env or {}),
    }
    proc = subprocess.Popen(
        [str(PYTHON), "bot.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return proc, log_file, log_path


def stop_bot(proc: subprocess.Popen, log_file) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_file.close()


def message_event(
    kind: str,
    text: str,
    message_id: int,
    user_id: int | None = None,
    mention: bool = True,
    image_url: str | None = None,
    reply_id: str | None = None,
) -> dict:
    base = {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "message",
        "message_id": message_id,
        "raw_message": text,
        "font": 0,
        "message": [{"type": "text", "data": {"text": text}}],
    }
    if kind == "private":
        message = []
        if image_url:
            message.append({"type": "image", "data": {"url": image_url, "summary": "[图片]"}})
        if text:
            message.append({"type": "text", "data": {"text": text}})
        base.update(
            {
                "sub_type": "friend",
                "user_id": user_id or PRIVATE_USER,
                "message_type": "private",
                "target_id": SELF_ID,
                "message": message,
                "sender": {"user_id": user_id or PRIVATE_USER, "nickname": "tester", "sex": "unknown", "age": 0},
            }
        )
    else:
        message = []
        if mention:
            message.append({"type": "at", "data": {"qq": str(SELF_ID)}})
        if reply_id:
            message.append({"type": "reply", "data": {"id": str(reply_id)}})
        if image_url:
            message.append({"type": "image", "data": {"url": image_url, "summary": "[图片]"}})
        message.append({"type": "text", "data": {"text": text}})
        base.update(
            {
                "sub_type": "normal",
                "user_id": user_id or GROUP_USER,
                "message_type": "group",
                "group_id": GROUP_ID,
                "message": message,
                "raw_message": f"[CQ:at,qq={SELF_ID}] {text}" if mention else text,
                "anonymous": None,
                "to_me": mention,
                "sender": {"user_id": user_id or GROUP_USER, "nickname": "tester", "card": "", "role": "member"},
            }
        )
    return base


def extract_text(message) -> str:
    if isinstance(message, str):
        return message
    parts = []
    for seg in message or []:
        if isinstance(seg, dict) and seg.get("type") == "text":
            parts.append(seg.get("data", {}).get("text", ""))
    return "".join(parts)


def friend_request_event(user_id: int, comment: str, flag: str) -> dict:
    return {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "request",
        "request_type": "friend",
        "user_id": user_id,
        "flag": flag,
        "comment": comment,
    }


def group_invite_event(group_id: int, user_id: int, flag: str) -> dict:
    return {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "request",
        "request_type": "group",
        "sub_type": "invite",
        "group_id": group_id,
        "user_id": user_id,
        "flag": flag,
        "comment": "邀请你加入群聊",
    }


def notice_event(notice_type: str, **fields) -> dict:
    event = {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "notice",
        "notice_type": notice_type,
    }
    event.update(fields)
    return event


class Harness:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.actions: list[dict] = []
        self._cursor = 0
        self.last_sent_id = 0
        self._message_seq = 800000

    async def _ack_loop(self) -> None:
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
                action = frame.get("action")
                if action in {"send_msg", "send_private_msg", "send_group_msg"}:
                    self._message_seq += 1
                    self.last_sent_id = self._message_seq
                    data = {"message_id": self.last_sent_id}
                elif action == "ocr_image":
                    data = {"texts": [{"text": "图片里的测试文字", "coordinates": []}]}
                elif action == "get_group_member_info":
                    data = {"group_id": GROUP_ID, "user_id": SELF_ID, "nickname": "test", "card": "Moon"}
                elif action == "get_group_list":
                    data = [{"group_id": GROUP_ID, "group_name": "小团体"}]
                elif action == "get_friend_list":
                    data = [{"user_id": PRIVATE_USER, "nickname": "tester", "remark": ""}]
                elif action == "get_stranger_info":
                    data = {"user_id": frame.get("params", {}).get("user_id", 0), "nickname": "newbie", "sex": "unknown", "age": 0}
                elif action in {"set_friend_add_request", "set_group_add_request"}:
                    data = {}
                else:
                    data = {"message_id": int(time.time() * 1000) % 100000}
                await self.ws.send(
                    json.dumps({"status": "ok", "retcode": 0, "data": data, "echo": frame.get("echo")})
                )

    async def wait_reply(self, timeout: float = 25.0) -> str | None:
        """等待下一条「新的」机器人回复（游标只会前进，不会重复拿到旧回复）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            while self._cursor < len(self.actions):
                action = self.actions[self._cursor]
                self._cursor += 1
                if action.get("action") in {"send_msg", "send_private_msg", "send_group_msg"}:
                    params = action.get("params", {})
                    text = extract_text(params.get("message"))
                    if text:
                        return text
            await asyncio.sleep(0.1)
        return None

    async def wait_model_call(self, previous: int, timeout: float = 25.0) -> None:
        """等机器人真正请求了一次模型（用于断言请求内容）。"""
        deadline = time.time() + timeout
        while time.time() < deadline and len(records) <= previous:
            await asyncio.sleep(0.1)

    def drain(self) -> None:
        """丢弃游标之前的所有动作，避免上一条测试没消费完的回复串进来。"""
        self._cursor = len(self.actions)


async def scenario_no_key() -> tuple[bool, str]:
    """没填 API Key 时，机器人应该回一句友好提示而不是崩掉。"""
    port = 18100
    log_path = ROOT / ".tmp" / "selftest-nokey.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "DRIVER": "~fastapi",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "LOG_LEVEL": "WARNING",
        "ONEBOT_ACCESS_TOKEN": TOKEN,
        "DEEPSEEK_API_KEY": "",
        "AI_DB_PATH": str(fresh_db("selftest-nokey.db")),
        "AI_REPLY_DELAY_MIN": "0",
        "AI_REPLY_DELAY_MAX": "0",
        "AI_SEND_CHARS": "15",
        "AI_SEND_MAX_BUBBLES": "4",
        "AI_VISION_MODEL": "",
        "AI_IMAGE_OCR": "true",
        "AI_WEB_SEARCH": "false",
        "AI_FISH_QQ": str(PRIVATE_USER),
        "AI_BOT_QQ": "0",
        "AI_NOTICE_QQ": str(PRIVATE_USER),
        "AI_STARTUP_NOTICE": "false",
        "AI_GROUP_TRIGGER": "auto",
        "AI_GROUP_AUTO_CHANCE": "0",
        "AI_GROUP_AUTO_COOLDOWN": "0",
        "AI_GROUP_AUTO_USER_COOLDOWN": "0",
        "AI_GROUP_AUTO_KEYWORDS": "大肥鱼,肥鱼",
        "COMMAND_START": '["/"]',
        "SUPERUSERS": f'["{PRIVATE_USER}"]',
    }
    proc = subprocess.Popen([str(PYTHON), "bot.py"], cwd=str(ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT)
    try:
        if not port_open(port, timeout=30):
            return False, "机器人没起来"
        headers = {"X-Self-ID": str(SELF_ID), "Authorization": f"Bearer {TOKEN}"}
        async with websockets.connect(f"ws://127.0.0.1:{port}/onebot/v11/ws", max_size=None, additional_headers=headers) as ws:
            harness = Harness(ws)
            reader = asyncio.create_task(harness._ack_loop())
            await asyncio.sleep(0.5)
            await ws.send(json.dumps(message_event("private", "你好", 201)))
            reply = await harness.wait_reply(20)
            await ws.send(json.dumps(message_event("private", "在吗", 202, user_id=PRIVATE_USER + 1)))
            friend_reply = await harness.wait_reply(20)
            reader.cancel()
            ok = (
                bool(reply)
                and "API Key" in (reply or "")
                and bool(friend_reply)
                and "卡" in (friend_reply or "")
            )
            return ok, f"admin={reply!r} friend={friend_reply!r}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()


async def scenario_persistence() -> tuple[bool, str]:
    """重启机器人后，SQLite 里的记忆应该还在。"""
    port = 18101
    db = fresh_db("selftest-persist.db")

    async def one_turn(text: str, message_id: int) -> tuple[str | None, list[dict]]:
        proc, log_file, _ = start_bot(port, "selftest-persist.log", {"AI_DB_PATH": str(db), "SUPERUSERS": "[]"})
        try:
            if not port_open(port, timeout=40):
                return None, []
            headers = {"X-Self-ID": str(SELF_ID), "Authorization": f"Bearer {TOKEN}"}
            async with websockets.connect(
                f"ws://127.0.0.1:{port}/onebot/v11/ws", max_size=None, additional_headers=headers
            ) as ws:
                harness = Harness(ws)
                reader = asyncio.create_task(harness._ack_loop())
                await asyncio.sleep(0.6)
                before = len(records)
                await ws.send(json.dumps(message_event("private", text, message_id)))
                reply = await harness.wait_reply(20)
                await harness.wait_model_call(before)
                request = records[-1].get("messages", []) if len(records) > before else []
                reader.cancel()
                return reply, request
        finally:
            stop_bot(proc, log_file)

    first, _ = await one_turn("记住我叫小明", 301)
    second, second_request = await one_turn("我叫什么", 302)
    roles = [m.get("role") for m in second_request]
    system_text = " ".join(
        m.get("content", "") for m in second_request if m.get("role") == "system"
    )
    fact_ok = "对方叫小明" in system_text
    tag_ok = "REMEMBER" not in (first or "")
    ok = (
        bool(first)
        and bool(second)
        and roles == ["system", "user", "assistant", "user"]
        and fact_ok
        and tag_ok
    )
    return ok, f"first={first!r} second={second!r} roles={roles} fact={fact_ok} tag={tag_ok}"


async def scenario_whitelist() -> tuple[bool, str]:
    """群白名单之外的群不回复，私聊不受影响。"""
    port = 18102
    db = fresh_db("selftest-whitelist.db")
    proc, log_file, _ = start_bot(
        port,
        "selftest-whitelist.log",
        {"AI_DB_PATH": str(db), "AI_GROUP_WHITELIST": "99999"},
    )
    try:
        if not port_open(port, timeout=40):
            return False, "机器人没起来"
        headers = {"X-Self-ID": str(SELF_ID), "Authorization": f"Bearer {TOKEN}"}
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/onebot/v11/ws", max_size=None, additional_headers=headers
        ) as ws:
            harness = Harness(ws)
            reader = asyncio.create_task(harness._ack_loop())
            await asyncio.sleep(0.6)
            await ws.send(json.dumps(message_event("group", " 这个群不在白名单", 401)))
            await asyncio.sleep(3.0)
            leaked = [a for a in harness.actions if str(a.get("action", "")).startswith("send")]
            await ws.send(json.dumps(message_event("private", "私聊还能用吗", 402)))
            reply = await harness.wait_reply(20)
            reader.cancel()
            ok = not leaked and bool(reply)
            return ok, f"群消息被拦={not leaked} 私聊回复={reply!r}"
    finally:
        stop_bot(proc, log_file)


async def scenario_group_sleep() -> tuple[bool, str]:
    """被 @ 后高读一小段时间，之后休眠不再调模型。"""
    port = 18103
    db = fresh_db("selftest-sleep.db")
    proc, log_file, _ = start_bot(
        port,
        "selftest-sleep.log",
        {
            "AI_DB_PATH": str(db),
            "AI_GROUP_TRIGGER": "auto",
            "AI_GROUP_ACTIVE_SECONDS": "1",
            "AI_GROUP_WAKE_MINUTES": "10",
            "AI_GROUP_AUTO_CHANCE": "0",
            "AI_GROUP_AUTO_COOLDOWN": "0",
            "AI_GROUP_AUTO_USER_COOLDOWN": "0",
        },
    )
    try:
        if not port_open(port, timeout=40):
            return False, "机器人没起来"
        headers = {"X-Self-ID": str(SELF_ID), "Authorization": f"Bearer {TOKEN}"}
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/onebot/v11/ws", max_size=None, additional_headers=headers
        ) as ws:
            harness = Harness(ws)
            reader = asyncio.create_task(harness._ack_loop())
            await asyncio.sleep(0.6)
            await ws.send(json.dumps(message_event("group", "醒醒", 601)))
            wake_reply = await harness.wait_reply(20)
            before_active = len(records)
            await asyncio.sleep(0.2)
            await ws.send(json.dumps(message_event("group", "这事你怎么看", 602, mention=False)))
            await asyncio.sleep(2.2)
            active_calls = len(records) - before_active

            await asyncio.sleep(2.2)
            before_sleep = len(records)
            await ws.send(json.dumps(message_event("group", "随便说两句", 603, mention=False)))
            await asyncio.sleep(2.0)
            sleep_calls = len(records) - before_sleep
            reader.cancel()
            ok = bool(wake_reply) and active_calls >= 1 and sleep_calls == 0
            return (
                ok,
                f"wake={wake_reply!r} active_calls={active_calls} sleep_calls={sleep_calls}",
            )
    finally:
        stop_bot(proc, log_file)


async def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -> ' + detail) if detail and not ok else ''}")
        if not ok:
            failures.append(name)

    api = start_fake_api()
    log_path = ROOT / ".tmp" / "selftest-bot.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")

    main_db = fresh_db("selftest.db")
    seed_saved_sticker(main_db)

    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "DRIVER": "~fastapi",
        "HOST": "127.0.0.1",
        "PORT": str(BOT_PORT),
        "LOG_LEVEL": "INFO",
        "ONEBOT_ACCESS_TOKEN": TOKEN,
        "DEEPSEEK_API_KEY": "sk-selftest",
        "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{FAKE_API_PORT}/v1",
        "DEEPSEEK_MODEL": "fake-model",
        "AI_TIMEOUT": "20",
        "AI_RETRIES": "0",
        "AI_RATE_RETRIES": "2",
        "AI_RETRY_BACKOFF": "0.1",
        "AI_RETRY_BACKOFF_MAX": "1",
        "AI_MODEL_MIN_INTERVAL": "0",
        "AI_RATE_LIMIT": "100",
        "AI_MAX_HISTORY": "5",
        "AI_DB_PATH": str(main_db),
        "AI_REPLY_DELAY_MIN": "0",
        "AI_REPLY_DELAY_MAX": "0",
        "AI_SEND_CHARS": "15",
        "AI_SEND_MAX_BUBBLES": "4",
        "AI_VISION_MODEL": "",
        "AI_IMAGE_OCR": "true",
        "AI_WEB_SEARCH": "false",
        "AI_FISH_QQ": str(PRIVATE_USER),
        "AI_BOT_QQ": "0",
        "AI_NOTICE_QQ": str(PRIVATE_USER),
        "AI_STARTUP_NOTICE": "false",
        "AI_GROUP_TRIGGER": "auto",
        "AI_GROUP_AUTO_CHANCE": "0",
        "AI_GROUP_AUTO_COOLDOWN": "0",
        "AI_GROUP_AUTO_USER_COOLDOWN": "0",
        "AI_GROUP_AUTO_KEYWORDS": "大肥鱼,肥鱼",
        "COMMAND_START": '["/"]',
        "SUPERUSERS": f'["{PRIVATE_USER}"]',
    }
    proc = subprocess.Popen(
        [str(PYTHON), "bot.py"],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        if not port_open(BOT_PORT):
            print("FAIL  机器人没有在预期时间内监听端口")
            log_file.flush()
            print("--- bot log tail ---")
            print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))
            return 1
        check("机器人在 127.0.0.1:%d 监听" % BOT_PORT, True)

        try:
            health = httpx.get(f"http://127.0.0.1:{BOT_PORT}/healthz", timeout=10).json()
            check("GET /healthz 正常", health.get("ok") is True, f"body={health}")
        except Exception as exc:
            check("GET /healthz 正常", False, f"{type(exc).__name__}: {exc}")

        url = f"ws://127.0.0.1:{BOT_PORT}/onebot/v11/ws"
        headers = {
            "X-Self-ID": str(SELF_ID),
            "Authorization": f"Bearer {TOKEN}",
        }
        async with websockets.connect(url, max_size=None, additional_headers=headers) as ws:
            harness = Harness(ws)
            reader = asyncio.create_task(harness._ack_loop())
            await asyncio.sleep(0.5)

            # 1) 私聊
            await ws.send(json.dumps(message_event("private", "你好", 101)))
            reply = await harness.wait_reply()
            check("私聊消息得到回复", bool(reply), f"reply={reply!r}")
            check("私聊回复内容正确", (reply or "") == "测试回复#1", f"reply={reply!r}")

            first_sys = (
                [m.get("content", "") for m in records[-1].get("messages", []) if m.get("role") == "system"]
                if records
                else []
            )
            check("管理员使用大肥鱼人设", any("大肥鱼" in t for t in first_sys), f"system={first_sys}")
            check("管理员人设是鲸鱼娘", any("鲸鱼娘" in t for t in first_sys), f"system={first_sys}")

            # 1b) 普通账号私聊：普通人设，不是大肥鱼
            before_normal = len(records)
            await ws.send(json.dumps(message_event("private", "你好", 120, user_id=GROUP_USER)))
            normal_reply = await harness.wait_reply()
            await harness.wait_model_call(before_normal)
            normal_sys = (
                [m.get("content", "") for m in records[-1].get("messages", []) if m.get("role") == "system"]
                if len(records) > before_normal
                else []
            )
            check(
                "普通账号私聊不是大肥鱼",
                bool(normal_reply) and all("大肥鱼" not in t for t in normal_sys),
                f"reply={normal_reply!r} system={normal_sys}",
            )

            # 2) 第二轮：应带上历史
            before = len(records)
            await ws.send(json.dumps(message_event("private", "我叫什么", 102)))
            reply2 = await harness.wait_reply()
            await harness.wait_model_call(before)
            check("第二轮私聊得到回复", bool(reply2), f"reply={reply2!r}")
            second_req = records[-1].get("messages", []) if len(records) > before else []
            roles = [m.get("role") for m in second_req]
            check(
                "第二轮请求带上了历史(system+user+assistant+user)",
                roles == ["system", "user", "assistant", "user"],
                f"roles={roles}",
            )

            # 2b) 回复自我暴露成 AI 时，应自动重写
            before_leak = len(records)
            await ws.send(json.dumps(message_event("private", "测试出戏", 113)))
            leak_reply = await harness.wait_reply()
            await harness.wait_model_call(before_leak)
            check(
                "出戏回复会被重写成人话",
                bool(leak_reply) and "AI" not in (leak_reply or ""),
                f"reply={leak_reply!r}",
            )
            check(
                "出戏时确实触发了一次重写",
                len(records) >= before_leak + 2,
                f"calls={len(records) - before_leak}",
            )

            # 3) 群聊 @
            await ws.send(json.dumps(message_event("group", " 群里你好啊", 103)))
            reply3 = await harness.wait_reply()
            check("群聊 @ 得到回复", bool(reply3), f"reply={reply3!r}")
            group_action = next((a for a in harness.actions if a.get("action") == "send_msg" and a["params"].get("message_type") == "group"), None)
            check("群聊回复发往正确的群", bool(group_action) and group_action["params"].get("group_id") == GROUP_ID, f"action={group_action}")

            # 3a-1) 只 @ 不说话也要应一声
            await ws.send(json.dumps(message_event("group", "", 134)))
            bare_reply = await harness.wait_reply()
            check("群里只 @ 不说话也会回应", bool(bare_reply), f"reply={bare_reply!r}")

            # 3a-2) 回复机器人刚发的那条，算和自己有关，应该接话
            bot_mid = harness.last_sent_id
            before_thread = len(records)
            await ws.send(
                json.dumps(message_event("group", "你刚才说什么", 128, mention=False, reply_id=str(bot_mid)))
            )
            thread_reply = await harness.wait_reply()
            await harness.wait_model_call(before_thread)
            check("回复机器人消息会触发接话", bool(thread_reply), f"reply={thread_reply!r}")

            # 3b) 群聊上下文：没 @ 的消息也要记住，@ 的时候带进请求
            await ws.send(json.dumps(message_event("group", "小明今天又鸽了", 110, mention=False)))
            await asyncio.sleep(0.6)
            before_ctx = len(records)
            await ws.send(json.dumps(message_event("group", " 你怎么看", 111)))
            reply_ctx = await harness.wait_reply()
            await harness.wait_model_call(before_ctx)
            ctx_req = records[-1].get("messages", []) if len(records) > before_ctx else []
            sys_texts = [m.get("content", "") for m in ctx_req if m.get("role") == "system"]
            user_texts = [m.get("content", "") for m in ctx_req if m.get("role") == "user"]
            check("群聊上下文被带进请求", any("小明今天又鸽了" in t for t in sys_texts), f"system={sys_texts}")
            check(
                "群聊上下文包含机器人自己的回复",
                any("你：" in t and "测试回复" in t for t in sys_texts),
                f"system={sys_texts}",
            )
            check("当前发言人昵称带进请求", any("tester" in t for t in user_texts), f"user={user_texts}")
            check("普通账号群聊不是大肥鱼", all("大肥鱼" not in t for t in sys_texts), f"system={sys_texts}")
            check("群名片带进请求", any("Moon" in t for t in sys_texts), f"system={sys_texts}")

            # 3b-2) 管理员在群里也不能用大肥鱼人设（只有私聊才启用）
            before_admin_group = len(records)
            await ws.send(json.dumps(message_event("group", " 管理员在群里说话", 124, user_id=PRIVATE_USER)))
            admin_group_reply = await harness.wait_reply()
            await harness.wait_model_call(before_admin_group)
            admin_group_sys = (
                [m.get("content", "") for m in records[-1].get("messages", []) if m.get("role") == "system"]
                if len(records) > before_admin_group
                else []
            )
            check(
                "管理员在群里也是普通人设",
                bool(admin_group_reply) and all("大肥鱼" not in t for t in admin_group_sys),
                f"reply={admin_group_reply!r} system={admin_group_sys}",
            )
            check("群聊上下文得到回复", bool(reply_ctx), f"reply={reply_ctx!r}")

            # 3c) 模型答应后可以执行改资料；动作标签不能发给用户
            before_action = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "帮我换签名", 116)))
            action_reply = await harness.wait_reply()
            await asyncio.sleep(0.5)
            sign_actions = [
                a for a in harness.actions[before_action:] if a.get("action") == "set_self_longnick"
            ]
            check(
                "模型答应后能执行换签名",
                bool(sign_actions) and sign_actions[0].get("params", {}).get("longNick") == "今天也不上班",
                f"actions={sign_actions}",
            )
            check(
                "隐藏动作标签不会发给用户",
                "ACTION" not in (action_reply or "") and "今天也不上班" not in (action_reply or ""),
                f"reply={action_reply!r}",
            )

            # 3c-1a) 换签名后的追问没有“签名”二字，也要能执行
            before_follow = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "文艺点那种", 142)))
            await harness.wait_reply()
            await asyncio.sleep(0.5)
            follow_actions = [
                a for a in harness.actions[before_follow:] if a.get("action") == "set_self_longnick"
            ]
            check("改签名后的追问也能执行", bool(follow_actions), f"actions={follow_actions}")

            # 3c-1b) 模型答应后可以发 QQ 空间说说
            before_qzone = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "发条空间 今天天气不错", 141)))
            qzone_reply = await harness.wait_reply()
            await asyncio.sleep(0.5)
            qzone_actions = [
                a for a in harness.actions[before_qzone:] if a.get("action") == "send_qzone_msg"
            ]
            check(
                "模型答应后能发空间",
                bool(qzone_actions)
                and qzone_actions[0].get("params", {}).get("content") == "今天天气不错",
                f"actions={qzone_actions}",
            )
            check("隐藏空间标签不会发给用户", "ACTION" not in (qzone_reply or ""), f"reply={qzone_reply!r}")

            # 3c-2) 没有改资料意图 / 来源不明的头像 URL，都不执行
            before_action = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "测试动作", 118, user_id=GROUP_USER)))
            await harness.wait_reply()
            await asyncio.sleep(0.3)
            check(
                "没有改资料意图的动作被忽略",
                not [a for a in harness.actions[before_action:] if a.get("action") == "set_self_longnick"],
                "unexpected action",
            )

            before_action = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "测试头像", 119)))
            await harness.wait_reply()
            await asyncio.sleep(0.3)
            check(
                "来源不明的头像 URL 被忽略",
                not [a for a in harness.actions[before_action:] if a.get("action") == "set_qq_avatar"],
                "unexpected action",
            )

            # 3d) 群里不执行改资料，挡回私聊
            before_action = len(harness.actions)
            await asyncio.sleep(1.2)
            harness.drain()
            await ws.send(json.dumps(message_event("group", "帮我换签名", 117)))
            group_action_reply = await harness.wait_reply()
            await asyncio.sleep(0.5)
            group_actions = [
                a for a in harness.actions[before_action:] if a.get("action") == "set_self_longnick"
            ]
            check("群里不会执行改资料", not group_actions, f"actions={group_actions}")
            check("群里改资料请求被挡回私聊", "私聊" in (group_action_reply or ""), f"reply={group_action_reply!r}")

            # 3e) 没 @ 但提到名字，自主接话
            before_auto = len(records)
            await ws.send(json.dumps(message_event("group", "大肥鱼你在吗", 122, mention=False)))
            auto_reply = await harness.wait_reply()
            await harness.wait_model_call(before_auto)
            check("没 @ 提到名字会自主接话", bool(auto_reply), f"reply={auto_reply!r}")

            # 3f) 模型可以选择闭嘴
            before_skip = len(harness.actions)
            await ws.send(json.dumps(message_event("group", "大肥鱼别说话", 123, mention=False)))
            await asyncio.sleep(2.0)
            skipped_sends = [
                a for a in harness.actions[before_skip:] if a.get("action") == "send_msg"
            ]
            check("自主判断不想说时会闭嘴", not skipped_sends, f"sends={skipped_sends}")

            # 3g) 长回复分条发送，每条都不长
            before_split = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "测试分段", 121)))
            await asyncio.sleep(3.0)
            split_sends = [
                extract_text(a.get("params", {}).get("message"))
                for a in harness.actions[before_split:]
                if a.get("action") == "send_msg"
            ]
            split_sends = [text for text in split_sends if text]
            check("长回复会拆成多条发送", len(split_sends) >= 2, f"sends={split_sends}")
            check("每条消息都不长", bool(split_sends) and all(len(text) <= 15 for text in split_sends), f"sends={split_sends}")

            # 3h) 图片 OCR 结果进入模型请求
            before_image = len(records)
            await ws.send(json.dumps(message_event("private", "看看这个", 125, image_url="http://example.com/test.png")))
            image_reply = await harness.wait_reply()
            await harness.wait_model_call(before_image)
            image_user = " ".join(
                m.get("content", "")
                for m in (records[-1].get("messages", []) if len(records) > before_image else [])
                if m.get("role") == "user"
            )
            check("图片 OCR 结果带进请求", "图片里的测试文字" in image_user, f"user={image_user}")
            check("图片消息得到回复", bool(image_reply), f"reply={image_reply!r}")

            # 3i) 表情包发送
            before_sticker = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "来个表情", 126)))
            sticker_reply = await harness.wait_reply()
            await asyncio.sleep(1.5)
            sticker_actions = [a for a in harness.actions[before_sticker:] if a.get("action") == "send_msg"]

            def _has_image(action: dict) -> bool:
                message = action.get("params", {}).get("message")
                return any(isinstance(seg, dict) and seg.get("type") == "image" for seg in (message or []))

            check("隐藏表情标签不会发给用户", "STICKER" not in (sticker_reply or ""), f"reply={sticker_reply!r}")
            check("会单独发一张表情包", any(_has_image(a) for a in sticker_actions), f"actions={sticker_actions}")

            # 3i-2) 收藏的表情包可以按 #编号 发出来
            before_saved = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "发收藏", 131)))
            saved_reply = await harness.wait_reply()
            await asyncio.sleep(1.5)
            saved_actions = [
                a for a in harness.actions[before_saved:] if a.get("action") == "send_msg"
            ]
            check(
                "收藏表情可以发出来",
                bool(saved_reply) and any(_has_image(a) for a in saved_actions),
                f"reply={saved_reply!r} actions={saved_actions}",
            )

            # 3i-3) 收藏表情在群里和其他私聊也能发
            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("group", "发收藏", 137)))
            await asyncio.sleep(2.0)
            group_sends = [
                a
                for a in harness.actions[mark:]
                if a.get("action") == "send_msg"
                and a.get("params", {}).get("message_type") == "group"
            ]
            check("群里也能发收藏表情", any(_has_image(a) for a in group_sends), f"actions={group_sends}")

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "发收藏", 138, user_id=GROUP_USER)))
            await asyncio.sleep(2.0)
            other_private = [
                a
                for a in harness.actions[mark:]
                if a.get("action") == "send_msg"
                and a.get("params", {}).get("message_type") == "private"
                and a.get("params", {}).get("user_id") == GROUP_USER
            ]
            check(
                "其他私聊也能发收藏表情",
                any(_has_image(a) for a in other_private),
                f"actions={other_private}",
            )

            # 3i-4) 自带表情图不再发
            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "测试自带", 139)))
            await asyncio.sleep(1.5)
            builtin_sends = [
                a for a in harness.actions[mark:] if a.get("action") == "send_msg"
            ]
            check(
                "自带表情图不会被发出去",
                not any(_has_image(a) for a in builtin_sends),
                f"actions={builtin_sends}",
            )

            # 3j) 大肥鱼回复里的过量语气词会被压掉
            await ws.send(json.dumps(message_event("private", "测试语气", 127)))
            tone_reply = await harness.wait_reply()
            check(
                "堆叠语气词被压掉、必要的保留一个",
                bool(tone_reply)
                and "～" not in (tone_reply or "")
                and sum((tone_reply or "").count(ch) for ch in "呀啦哦呢呗咯哟") <= 1,
                f"reply={tone_reply!r}",
            )

            # 3j-2) 句末句号去掉、句中句号变逗号
            await asyncio.sleep(1.5)
            harness.drain()
            await ws.send(json.dumps(message_event("private", "测试句号", 136)))
            style_reply = await harness.wait_reply()
            check(
                "回复会去掉句末句号",
                style_reply == "行吧，我知道了",
                f"reply={style_reply!r}",
            )

            # 3k) 管理员可以手动触发一次主动私聊
            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "/proactive", 140)))
            await asyncio.sleep(2.0)
            proactive_sends = [
                a
                for a in harness.actions[mark:]
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
                and extract_text(a.get("params", {}).get("message")) == "在干嘛"
            ]
            check("可以手动触发主动私聊", bool(proactive_sends), f"actions={harness.actions[mark:]}")

            # 4) /help 指令
            before = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "/help", 104)))
            await asyncio.sleep(2.0)
            helps = [a for a in harness.actions[before:] if a.get("action") == "send_msg"]
            check("/help 指令有响应", bool(helps))

            # 5) /reset 清空记忆后，请求里不应再有历史
            await ws.send(json.dumps(message_event("private", "/reset", 105)))
            await asyncio.sleep(2.0)
            before_reset = len(records)
            await ws.send(json.dumps(message_event("private", "重新开始", 106)))
            await harness.wait_reply()
            await harness.wait_model_call(before_reset)
            after_reset = records[-1].get("messages", []) if len(records) > before_reset else []
            check(
                "/reset 后记忆被清空",
                [m.get("role") for m in after_reset] == ["system", "user"],
                f"roles={[m.get('role') for m in after_reset]}",
            )

            # 5b) 管理员查其他群聊记录；查完不进入日常上下文
            before_hist = len(records)
            await ws.send(json.dumps(message_event("private", "今天群里都说了些什么", 129)))
            hist_reply = await harness.wait_reply()
            await harness.wait_model_call(before_hist)
            hist_sys = " ".join(
                m.get("content", "")
                for m in (records[-1].get("messages", []) if len(records) > before_hist else [])
                if m.get("role") == "system"
            )
            check(
                "管理员能查群聊记录",
                bool(hist_reply) and "小团体" in hist_sys and "小明今天又鸽了" in hist_sys,
                f"reply={hist_reply!r} system={hist_sys[:500]}",
            )

            before_plain = len(records)
            await ws.send(json.dumps(message_event("private", "继续", 130)))
            await harness.wait_reply()
            await harness.wait_model_call(before_plain)
            plain_sys = " ".join(
                m.get("content", "")
                for m in (records[-1].get("messages", []) if len(records) > before_plain else [])
                if m.get("role") == "system"
            )
            check("历史记录不进日常上下文", "小团体" not in plain_sys, f"system={plain_sys[:300]}")

            # 5c) 管理员可以指挥去群里发消息
            before_delegate = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "去群里说 测试群消息", 133)))
            await asyncio.sleep(1.5)
            delegate_actions = harness.actions[before_delegate:]
            group_sends = [
                action
                for action in delegate_actions
                if action.get("action") in {"send_msg", "send_group_msg"}
                and action.get("params", {}).get("group_id") == GROUP_ID
            ]
            private_sends = [
                action
                for action in delegate_actions
                if action.get("action") == "send_msg"
                and action.get("params", {}).get("message_type") == "private"
            ]
            check(
                "管理员可以指挥去群里发消息",
                any(
                    extract_text(action.get("params", {}).get("message")) == "测试群消息"
                    for action in group_sends
                ),
                f"actions={delegate_actions}",
            )
            check(
                "指挥后会给管理员回执",
                any(extract_text(action.get("params", {}).get("message")) for action in private_sends),
                f"actions={delegate_actions}",
            )

            # 6) 超级用户权限：放行的能清空，非超管被拦
            def replies_since(start: int) -> list[str]:
                out = []
                for action in harness.actions[start:]:
                    if action.get("action", "").startswith("send"):
                        text = extract_text(action.get("params", {}).get("message"))
                        if text:
                            out.append(text)
                return out

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "/reset all", 107)))
            await asyncio.sleep(2.0)
            su = replies_since(mark)
            check("超级用户可以 /reset all", any("已清空" in r for r in su), f"replies={su}")

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "/status", 109)))
            await asyncio.sleep(1.5)
            status_replies = replies_since(mark)
            check("超级用户可以 /status", any("运行时长" in r for r in status_replies), f"replies={status_replies}")

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", " /reset all", 108, user_id=GROUP_USER)))
            await asyncio.sleep(2.0)
            normal = replies_since(mark)
            check("普通朋友不能使用管理指令", not normal, f"replies={normal}")

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("private", "/help", 112, user_id=GROUP_USER)))
            await asyncio.sleep(1.5)
            normal_help = replies_since(mark)
            check("普通朋友看不到帮助菜单", not normal_help, f"replies={normal_help}")

            mark = len(harness.actions)
            await ws.send(json.dumps(message_event("group", " /status", 115, user_id=PRIVATE_USER)))
            await asyncio.sleep(1.5)
            admin_group = replies_since(mark)
            check("管理员在群里也不响应管理指令", not admin_group, f"replies={admin_group}")

            # 7) 好友请求：正常请求自动通过并打招呼，广告号拒绝
            mark = len(harness.actions)
            await ws.send(json.dumps(friend_request_event(44444, "你好，交个朋友", "friend-ok")))
            await asyncio.sleep(1.5)
            req_actions = harness.actions[mark:]
            approves = [a for a in req_actions if a.get("action") == "set_friend_add_request"]
            greets = [
                a
                for a in req_actions
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == 44444
            ]
            admin_notes = [
                a
                for a in req_actions
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
            ]
            check(
                "正常的加好友请求会自动通过",
                bool(approves) and approves[0].get("params", {}).get("approve") is True,
                f"actions={req_actions}",
            )
            check(
                "通过好友请求后会打个招呼",
                any(extract_text(a.get("params", {}).get("message")) for a in greets),
                f"actions={req_actions}",
            )
            check(
                "好友请求会通知管理员",
                any(
                    ("好友请求" in text or "新好友" in text)
                    for text in (
                        extract_text(a.get("params", {}).get("message")) or ""
                        for a in admin_notes
                    )
                ),
                f"actions={admin_notes}",
            )

            mark = len(harness.actions)
            await ws.send(json.dumps(friend_request_event(44445, "刷单兼职日结，加我", "friend-spam")))
            await asyncio.sleep(1.5)
            spam_actions = [
                a for a in harness.actions[mark:] if a.get("action") == "set_friend_add_request"
            ]
            check(
                "广告号的好友请求会被拒绝",
                bool(spam_actions) and spam_actions[0].get("params", {}).get("approve") is False,
                f"actions={spam_actions}",
            )

            # 7b) 管理员拉进群自动同意；陌生人邀请不处理
            mark = len(harness.actions)
            await ws.send(json.dumps(group_invite_event(66666, PRIVATE_USER, "group-ok")))
            await asyncio.sleep(1.0)
            invite_actions = [
                a for a in harness.actions[mark:] if a.get("action") == "set_group_add_request"
            ]
            check(
                "管理员拉群会自动同意",
                bool(invite_actions) and invite_actions[0].get("params", {}).get("approve") is True,
                f"actions={invite_actions}",
            )

            mark = len(harness.actions)
            await ws.send(json.dumps(group_invite_event(66667, GROUP_USER, "group-stranger")))
            await asyncio.sleep(1.0)
            stranger_actions = [
                a for a in harness.actions[mark:] if a.get("action") == "set_group_add_request"
            ]
            check("陌生人拉群不会自动同意", not stranger_actions, f"actions={stranger_actions}")

            # 7c) 通过好友请求后，再收到 friend_add 不重复通知
            mark = len(harness.actions)
            await ws.send(json.dumps(notice_event("friend_add", user_id=44444)))
            await asyncio.sleep(1.0)
            dup_notes = [
                extract_text(a.get("params", {}).get("message")) or ""
                for a in harness.actions[mark:]
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
            ]
            check(
                "好友添加事件不会重复通知",
                not any("新好友" in text for text in dup_notes),
                f"notes={dup_notes}",
            )

            # 7d) 新好友事件
            mark = len(harness.actions)
            await ws.send(json.dumps(notice_event("friend_add", user_id=44446)))
            await asyncio.sleep(1.0)
            friend_notes = [
                extract_text(a.get("params", {}).get("message")) or ""
                for a in harness.actions[mark:]
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
            ]
            check(
                "新好友会通知管理员",
                any("新好友" in text and "44446" in text for text in friend_notes),
                f"notes={friend_notes}",
            )

            # 7e) 进群 / 被踢事件
            mark = len(harness.actions)
            await ws.send(
                json.dumps(
                    notice_event(
                        "group_increase",
                        sub_type="invite",
                        group_id=GROUP_ID,
                        user_id=SELF_ID,
                        operator_id=PRIVATE_USER,
                    )
                )
            )
            await asyncio.sleep(1.0)
            join_notes = [
                extract_text(a.get("params", {}).get("message")) or ""
                for a in harness.actions[mark:]
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
            ]
            check(
                "进群会通知管理员",
                any("进群了" in text and "小团体" in text for text in join_notes),
                f"notes={join_notes}",
            )

            mark = len(harness.actions)
            await ws.send(
                json.dumps(
                    notice_event(
                        "group_decrease",
                        sub_type="kick",
                        group_id=GROUP_ID,
                        user_id=SELF_ID,
                        operator_id=GROUP_USER,
                    )
                )
            )
            await asyncio.sleep(1.0)
            kick_notes = [
                extract_text(a.get("params", {}).get("message")) or ""
                for a in harness.actions[mark:]
                if a.get("action") == "send_private_msg"
                and a.get("params", {}).get("user_id") == PRIVATE_USER
            ]
            check(
                "被踢出群会通知管理员",
                any("被移出群" in text and "小团体" in text for text in kick_notes),
                f"notes={kick_notes}",
            )

            reader.cancel()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()

    # 重启后记忆不丢
    persist_ok, persist_detail = await scenario_persistence()
    check("机器人重启后记忆仍在", persist_ok, persist_detail)

    # 群白名单
    whitelist_ok, whitelist_detail = await scenario_whitelist()
    check("群白名单生效（私聊不受影响）", whitelist_ok, whitelist_detail)

    # 群聊高读窗口 / 休眠
    sleep_ok, sleep_detail = await scenario_group_sleep()
    check("高读窗口分析普通消息、休眠后不再调模型", sleep_ok, sleep_detail)

    api.shutdown()

    # 没配 Key 的首次体验
    no_key_ok, no_key_detail = await scenario_no_key()
    check("未配置 API Key 时给出友好提示", no_key_ok, no_key_detail)

    print()
    if failures:
        print(f"结果：{len(failures)} 项失败 -> {', '.join(failures)}")
        print(f"机器人日志：{log_path}")
        return 1
    print("结果：全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

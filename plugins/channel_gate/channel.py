"""活跃通道开关：决定 QQ 消息由谁来处理。

背景：NapCat 可以同时挂多个反向 WS 客户端（已验证），所以可以一直保持
8080（旧机器人）和 8643（DSH）两条连接同时在线。哪一边真正处理消息，
由 .tmp/active-channel.txt 的内容决定：

    legacy  → 只有 NoneBot（本进程）处理，DSH 侧沉默
    dsh     → 只有 DSH 处理，本进程沉默

这样切换通道只需要改这个文件，完全不用碰 NapCat 配置，也就不会触发
NapCat 热重载把连接搞坏的问题。

本模块只提供纯函数，不依赖 nonebot，方便复用和测试。
"""

from __future__ import annotations

from pathlib import Path

# 项目根目录（plugins/channel_gate/ 上两级）
ROOT = Path(__file__).resolve().parents[2]
SWITCH_FILE = ROOT / ".tmp" / "active-channel.txt"

LEGACY = "legacy"
DSH = "dsh"

# 文件缺失或内容无法识别时的默认值。
# 选 legacy 的原因：它是本地进程，行为确定；DSH 不在时消息也不会静默丢失。
DEFAULT = LEGACY


def read_active_channel() -> str:
    """读当前活跃通道；文件不存在或内容异常时返回默认值。

    用 utf-8-sig 解码：PowerShell 5.1 的 `Set-Content -Encoding utf8` 会写 BOM，
    而 Python 的 str.strip() 不把 U+FEFF 当空白，`"\\ufeffdsh"` 会匹配失败、
    静默回落到 DEFAULT（legacy）——表现就是切到 dsh 后旧机器人还在回话。
    JS 侧 trim() 恰好会吃掉 BOM，于是两边判定不一致，双回复。
    """
    try:
        raw = SWITCH_FILE.read_text(encoding="utf-8-sig").strip().lower()
    except (OSError, UnicodeError):
        return DEFAULT
    # 兜底：万一文件里有零宽字符残留
    raw = raw.lstrip("\ufeff").strip()
    if raw in (LEGACY, DSH):
        return raw
    return DEFAULT


def is_legacy_active() -> bool:
    """这个进程（NoneBot）是否该处理消息。"""
    return read_active_channel() == LEGACY

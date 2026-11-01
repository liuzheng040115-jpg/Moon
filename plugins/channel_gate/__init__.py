"""活跃通道闸门：不是自己该处理的消息，直接静默忽略。

工作方式：NapCat 同时连 8080 和 8643，两边都会收到每一条消息。本插件用
`run_preprocessor` 在**所有 matcher 之前**检查 .tmp/active-channel.txt：

    当前是 dsh   → 本进程 raise IgnoredException，全部 matcher 不执行
    当前是 legacy → 放行，正常处理

这样两个服务端同时在线也不会双回复。切换通道只改那个文件，不碰 NapCat。

注意：IgnoredException 只影响事件分发，不影响定时任务、主动发送、
本地 API 等能力，所以「检修」这类指令在 legacy 活跃时仍然正常工作。
"""

from __future__ import annotations

from nonebot.adapters import Event
from nonebot.exception import IgnoredException
from nonebot.log import logger
from nonebot.message import run_preprocessor

from .channel import DSH, read_active_channel

# 记一条日志就够了，别每条消息都刷屏
_warned = False


@run_preprocessor
async def _gate(event: Event) -> None:
    global _warned

    active = read_active_channel()
    if active != DSH:
        # 默认路径：让事件继续走。重置告警标记，下次再被切走时能再提示一次。
        _warned = False
        return

    if not _warned:
        logger.info(
            "当前活跃通道是 dsh，本进程（NoneBot）忽略所有 QQ 事件；"
            "要交回旧机器人请把 .tmp/active-channel.txt 写成 legacy"
        )
        _warned = True

    raise IgnoredException("active channel is dsh")

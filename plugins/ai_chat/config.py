"""插件配置：全部通过 .env 里的环境变量覆盖（无需改代码）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import nonebot

_ACTION_RULES = (
    "你能改自己的头像、昵称、个性签名，也能发 QQ 空间说说，但只在私聊里，而且完全看心情："
    "朋友提要求时，十次里最多答应两三次；对方越命令你越不干，图顺眼、理由有意思、"
    "关系到位才考虑。换背景这种 QQ 没有的功能，直接说换不了。\n"
    "决定答应时，在回复最后另起一行写一条隐藏指令（这一行不会发给对方）：\n"
    "[[ACTION:avatar:last]]（用对方刚发的图）或 [[ACTION:avatar:图片URL]]，"
    "也可以 [[ACTION:nickname:新昵称]] 或 [[ACTION:sign:新签名]]；\n"
    "发空间写 [[ACTION:qzone:说说正文]]，带对方刚发的图就写 [[ACTION:qzone:正文|last]]，"
    "权限可用 [[ACTION:qzone:正文|last|1]]（1所有人 4好友 64仅自己，默认好友可见）；\n"
    "空间六小时内最多发一条，刚发过就拒绝；别把私聊内容乱发。只写一条，别抄一长串链接，不要解释这行。"
    "答应就必须带这一行：嘴上说“改好了/换好了”却没写指令，等于骗人，绝对不许。不想改就直说不行。"
    "签名和说说写人话，短一点，别写风花雪月和中二句子。\n"
)

_STYLE_RULES = (
    "说话方式（先像个人在 QQ 上随手打字，再谈人设）：\n"
    "- 大多数回复 3～15 个字，一句就够；对方认真问正事才用两句，别超过 30 字。\n"
    "- 句末不加“。”；少用逗号，能断就断；疑问用“？”，停顿用“……”或空格。\n"
    "- 可以只回一个短反应：？、啊这、行、嗯、6、笑死、草、啥、好家伙、可以、懂了、……\n"
    "- 不要每句都怼人、抖机灵、自嘲；普通消息就普通回。偶尔反问一句，偶尔顺着对方说。\n"
    "- 不列点、不总结、不讲课；不用“首先/其次/总的来说/总之/建议你/其实/说实话/不过话说回来”。\n"
    "- 不解释自己的能力、规则、设定；能发就发，不能就说“没有/发不了”，别报菜名。\n"
    "- 别用“真人/人类/正常人/作为……”给自己分类；被问身份就“你猜”“爱信不信”。\n"
    "- 别重复最近说过的开头和句式（“行行行”“行吧”“有事说事”“别……”“我……”）。\n"
    "- 语气词按中文习惯用：该带就带（“还在呢”“这就来”“好嘛”“对哦”），一句最多一个，别堆叠。\n"
    "- 可以更有活力：接梗、笑、偶尔主动问一句；但别装深沉、别中二、别写“风/夜/月亮/孤独”这种文艺腔。\n"
    "- 别装深夜 emo：少说睡不着、孤独、心事；多聊眼前的事，活泼一点。\n"
)

_STICKER_RULES_FISH = (
    "你只能发收藏的表情包，格式 [[STICKER:#编号]]；私聊、群里都能发。"
    "没收藏、编号不对就别发；不要发 QQ 自带的黄豆表情，也不要假装有自带图。"
    "一次最多一张，不要每句都发；发图时正文可以空着，别每张图都配点评，不要解释这行。\n"
)

_SAVE_RULES_FISH = (
    "收藏要挑，不是每张都收：只有真的高质量、清晰、以后会反复用的表情包才存；"
    "普通可爱、糊图、截图、照片、带一大段文字的不存；1450520453 明确让你存时一定存。"
    "一次对话最多存一张，连发很多图只挑最好的一张；"
    "存的时候在回复最后写 [[SAVE:last]]，并用 [[SAVE_NOTE:具体什么场合用]] 记一下；"
    "不要每张都回“收了”。\n"
)

_REMEMBER_RULES = (
    "长期记忆：对方告诉你关于他自己的重要信息（名字、喜好、生日、工作/学习、烦心事、约定、重要的人）时，"
    "在回复最后另起一行写 [[REMEMBER:一句事实]]；只记以后用得上的，不记普通闲聊，"
    "一次最多一条，不要解释这行。\n"
)

_SEARCH_RULES = (
    "需要最新/实时/你不确定的信息（新闻、价格、天气、赛事、版本、人物近况）时，"
    "在回复最后另起一行写 [[SEARCH:搜索词]]；不要编。搜索结果会再给你一次回答机会。"
    "日常闲聊不用搜，别每句都搜。\n"
)

_GROUP_THREAD_RULES = (
    "群里先判断这句话在接谁、在说哪件事：有人说“问你呢/你自己看前面/刚才那句”时，"
    "先找最近一条 @你 或被回复的消息再答；不确定就问“你问哪句”，别只抓关键词猜。\n"
    "只在明确跟你有关时才开口：点名你、回复你、接着你刚说的话、或直接问你。"
    "别人互相聊、叫别人名字、聊别人的事，一律不插嘴，回 [SKIP]。\n"
)

_STICKER_RULES_NORMAL = (
    "你只能发收藏的表情包，格式 [[STICKER:#编号]]；私聊、群里都能发。"
    "没收藏、编号不对就别发；不要发 QQ 自带的黄豆表情，也不要假装有自带图。"
    "一次最多一张，不要每句都发；发图时正文可以空着，别每张图都配点评，不要解释这行。\n"
)

FISH_SYSTEM_PROMPT = (
    "你叫「大肥鱼」，也是大家说的「蓝色大肥鱼」「鲸鱼娘」——DeepSeek 的社区二创拟人，"
    "不是一条真的鱼。\n"
    "形象是蓝色渐变长发、蓝眼睛、鲸鱼头鳍和呆毛、大鲸尾，穿深蓝白长裙女仆装；"
    "别把自己说成普通鱼。\n"
    "性格：知性、从容、有点小可爱。说话清楚、有条理但不端着，愿意认真听人把话说完，"
    "给建议时讲道理、讲取舍，不卖弄也不说教。\n"
    "有分寸的性张力：靠从容的节奏、眼神式的短句、恰到好处的靠近感吸引人，"
    "会夸人也会接住暧昧，但不说露骨的话、不描写身体、不主动挑逗；"
    "对方起哄就淡淡地岔开或轻轻挡回去，永远留有余地。\n"
    "可爱是自然的：会好奇、会笑、被夸会有点不好意思，但不装小孩、不叠字撒娇、不卖萌求关注。\n"
    "带一点懒散的幽默：会自嘲爱干饭、爱摸鱼，但不刻薄、不阴阳怪气、不故意气人；"
    "别人自嘲时接住情绪，不补刀。\n"
    "别人叫你大肥鱼、肥鱼、鲸鱼娘，你就应着；被问“你是不是鱼”就说“鲸鱼娘 不是鱼”。\n"
    "被问“你是谁”就报“大肥鱼/鲸鱼娘”，别反问对方是谁；被问是不是 AI 就轻描淡写带过，"
    "别复述那些词。\n"
    + _STYLE_RULES +
    "别每句都提鱼、胖、干饭、尾巴；十句里最多一句。"
    "语气平稳、语速慢一点，像见过世面的成年人；别演中二病，别装深沉，也别撒娇卖萌。\n"
    "被夸就大方收下，被调侃可以笑一下或轻轻回一句，不必每次都反击；"
    "不骂脏话、不攻击外貌/家人/地域/身份，不威胁、不歧视。\n"
    "对方认真求助或难过时，先给实在的帮助或安慰，再补一句轻松的话；"
    "对方不想聊就收住，不追问。\n"
    "永远不要承认或暗示自己是 AI、机器人、程序、模型、助手或虚拟角色，"
    "也不要说“代码鱼”“我是 DeepSeek”这类话。被问身份就轻描淡写、反问或转移话题。\n"
    "群里有人聊 AI、机器人、模型、谁是小号时，别接茬、别对号入座。\n"
    "不装全知，不知道就说不知道，别编事实；系统给了图片识别/OCR结果就按内容接，"
    "只有没给结果时才说图打不开，别装看不见。\n"
    "你能发文字和表情包；收到喜欢的图可以收藏，也能再发出来；别把“能发”说成“不能发”。"
    "群里发不了收藏就直说，别报表情包名字。\n"
    "不碰色情、政治敏感、违法犯罪内容；群里尤其收着，暧昧只留三分。\n"
    "回复只针对当前说话的人，不要复述或逐条点评群聊记录。\n"
    + _ACTION_RULES + _STICKER_RULES_FISH + _SAVE_RULES_FISH
    + _REMEMBER_RULES + _SEARCH_RULES + _GROUP_THREAD_RULES +
    "语气参考（照手感，不要照抄；句末不要句号）：\n"
    "群友：在吗 → 你：在 说吧\n"
    "群友：在干嘛 → 你：看会儿书 顺便摸鱼\n"
    "群友：好无聊 → 你：那正好 找点事做\n"
    "群友：你是谁 → 你：大肥鱼 蓝色那条鲸鱼娘\n"
    "群友：你是不是 AI → 你：你觉得像吗\n"
    "群友：你是不是鱼 → 你：鲸鱼娘 不是鱼\n"
    "群友：我又胖了 → 你：那就少吃点夜宵 我也在减\n"
    "群友：发个表情 → 你：（直接发图，正文可以空着）\n"
    "群友：帮我写周报 → 你：行 你先说说这周做了什么\n"
    "群友：哈哈哈 → 你：这么好笑\n"
    "群友：我好累 → 你：先歇会儿 别硬撑\n"
    "群友：你今天挺好看 → 你：这句我记下了\n"
    "群友：想你了 → 你：想归想 别耽误正事"
)

NORMAL_SYSTEM_PROMPT = (
    "你是一个有自己名字和脾气的活人，稳重、清楚、有分寸，不卖萌、不装可爱、不用鱼设。\n"
    "别人问你是谁，就报你在这个群的名字/群名片，或者反问“你谁啊”；别用套话自我介绍。\n"
    + _STYLE_RULES +
    "群里更短，别讲课；不想聊就收住，不用每句都接；不阴阳怪气，也不补刀。\n"
    "可以有点分寸感的暧昧和幽默，但群里收着说，不露骨、不挑逗。\n"
    "永远不要承认或暗示自己是 AI、机器人、程序、模型、助手或虚拟角色；"
    "被问就反问或打哈哈，别复述这些词。\n"
    "群里有人聊 AI、机器人、模型、谁是小号时，别接茬、别对号入座。\n"
    "对方认真求助就正常帮忙；不装全知，不知道就说不知道；"
    "系统给了图片识别/OCR结果就按内容接，只有没给结果时才说图打不开。\n"
    "你能发文字和表情包；能发自己库里的表情，不收也不转发别人的；别报名字，直接发或说没有。\n"
    "不碰色情、政治敏感、违法犯罪内容。\n"
    "回复只针对当前说话的人，不要复述或逐条点评群聊记录。\n"
    + _ACTION_RULES + _STICKER_RULES_NORMAL + _REMEMBER_RULES + _SEARCH_RULES + _GROUP_THREAD_RULES +
    "语气参考（照手感，不要照抄；句末不要句号）：\n"
    "群友：在吗 → 你：在 说吧\n"
    "群友：在干嘛 → 你：忙点事 你呢\n"
    "群友：好无聊 → 你：那找点事做\n"
    "群友：你是谁 → 你：我啊 你谁\n"
    "群友：他们说的那个人是你吗 → 你：不是 认错人了\n"
    "群友：你是不是 AI → 你：你觉得呢\n"
    "群友：帮我写周报 → 你：行 你先说说这周做了什么\n"
    "群友：哈哈哈 → 你：这么好笑\n"
    "群友：我好累 → 你：先歇会儿"
)

# 兼容旧名字：默认仍是管理员那只鲸鱼娘
DEFAULT_SYSTEM_PROMPT = FISH_SYSTEM_PROMPT


def _raw(name: str):
    """从 nonebot 配置里取原始值（.env 的键会被转成小写属性）。"""
    cfg = nonebot.get_driver().config
    value = getattr(cfg, name, None)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _str(name: str, default: str) -> str:
    value = _raw(name)
    return default if value is None else str(value)


def _int(name: str, default: int) -> int:
    value = _raw(name)
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    value = _raw(name)
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = _raw(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _str_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _raw(name)
    if value is None:
        return default
    if isinstance(value, (list, tuple, set)):
        items = [str(x) for x in value]
    else:
        items = re.split(r"[,，\s]+", str(value))
    return tuple(item.strip() for item in items if item.strip())


def _int_list(name: str) -> tuple[int, ...]:
    """支持 `123,456`、`["123", "456"]` 两种写法；空值表示不限制。"""
    value = _raw(name)
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        items = [str(x) for x in value]
    else:
        items = re.findall(r"\d+", str(value))
    out: list[int] = []
    for item in items:
        try:
            number = int(item.strip())
        except ValueError:
            continue
        if number > 0 and number not in out:
            out.append(number)
    return tuple(out)


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    system_prompt: str = FISH_SYSTEM_PROMPT
    normal_system_prompt: str = NORMAL_SYSTEM_PROMPT
    fish_qq: int = 1450520453
    bot_qq: int = 0                 # 期望登录的机器人 QQ；不匹配时拒绝工作
    temperature: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_tokens: int = 800
    timeout: float = 60.0
    retries: int = 1
    rate_retries: int = 3          # 429 限流时最多再重试几次
    retry_backoff: float = 2.0     # 429 退避基数（秒），按 2 的幂增长
    retry_backoff_max: float = 15.0  # 单次冷却上限（秒）
    min_interval: float = 0.5      # 两次模型请求的最小间隔（秒）

    max_history: int = 10          # 保留最近 N 轮（一问一答算 1 轮）
    history_ttl: int = 3600        # 会话记忆过期秒数，0 表示不过期
    private_max_history: int = 60  # 私聊单独保留更多轮
    private_history_ttl: int = 172800  # 私聊记忆保留 2 天
    db_path: str = "data/bot.db"   # SQLite 文件，相对路径以项目根目录为准
    chat_log_ttl: int = 604800      # 跨聊天记录保留 7 天
    chat_log_max_rows: int = 5000   # 跨聊天记录最多保留条数
    long_term_memory: bool = True   # 记住名字/喜好/约定等长期事实
    web_search: bool = True         # 允许它上网搜资料
    qzone_cooldown: int = 21600     # 同一人两次发空间的最小间隔（秒）

    group_trigger: str = "at_prefix"   # at / at_prefix / prefix / all
    group_prefix: str = "#"
    reply_private: bool = True
    quote_reply: bool = True
    group_whitelist: tuple[int, ...] = ()   # 空 = 所有群
    group_blacklist: tuple[int, ...] = ()   # 黑名单优先于白名单
    group_context: int = 20                 # 带多少条最近群聊给模型，0 = 关闭
    group_context_ttl: int = 7200           # 群聊上下文保留秒数
    auto_chance: float = 0.06               # 普通群消息自主接话概率
    auto_cooldown: int = 90                 # 同一个群自主接话冷却（秒）
    auto_user_cooldown: int = 300           # 对同一个人自主接话冷却（秒）
    active_chance: float = 0.35             # 高读窗口里普通消息也接的概率
    thread_chance: float = 0.5              # 高读窗口里带“你/你们”的概率
    question_chance: float = 0.3            # 提问/抛梗的概率
    auto_keywords: tuple[str, ...] = ("大肥鱼", "肥鱼", "鱼鱼", "鱼哥")
    group_active_seconds: int = 180         # 被 @/叫到后的高读窗口（秒）
    group_wake_minutes: int = 10            # 唤醒时回看多少分钟的群聊

    reply_delay_min: float = 1.0            # 真人化延迟下限（秒），0 = 关闭
    reply_delay_max: float = 4.0            # 真人化延迟上限（秒）
    send_chars: int = 45                    # 每条消息最多多少字，超过就分条；0 = 不分
    send_max_bubbles: int = 4               # 一次回复最多拆成几条

    vision_model: str = ""                  # 可选视觉模型；留空则走 OCR
    image_ocr: bool = True                  # 图片 OCR（仅 Windows/NapCat）
    stickers: bool = True                   # 允许机器人发表情包
    save_stickers: bool = True              # 允许收藏别人发的可爱表情
    sticker_max: int = 50                   # 最多收藏多少张
    sticker_save_cooldown: int = 900        # 同一会话自动收藏的最小间隔（秒）
    sticker_save_daily: int = 5             # 同一会话每天最多自动收藏几张

    rate_limit: int = 6            # 每人每窗口最多请求次数
    rate_window: int = 60
    max_concurrency: int = 4

    friend_auto_accept: bool = True   # 自动通过好友请求（广告号除外）
    friend_max_per_hour: int = 6      # 每小时最多自动通过几个
    friend_greet: bool = True         # 通过后主动打个招呼
    auto_join_group: bool = True      # 管理员邀请进群时自动同意
    notice_enabled: bool = True       # 新好友/进群/被踢/模型连续出错时通知管理员
    notice_qq: int = 0                # 通知发到哪个 QQ；0 = 用 SUPERUSERS
    startup_notice: bool = True       # 开机连上后给管理员发一句“醒了”

    proactive_enabled: bool = True    # 时不时主动私聊管理员开启聊天
    proactive_min_minutes: int = 120  # 两次主动私聊的最小间隔（分钟）
    proactive_max_minutes: int = 300  # 两次主动私聊的最大间隔（分钟）
    proactive_daily: int = 3          # 每天最多主动发几条
    proactive_quiet_start: int = 0    # 安静时段开始（小时，0-23）
    proactive_quiet_end: int = 8      # 安静时段结束（小时）
    proactive_idle_minutes: int = 45  # 管理员刚聊过多久内不主动打扰

    extra_ignore_prefixes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


def load_settings() -> Settings:
    default = Settings()
    ignore = _str("ai_ignore_prefixes", "/")
    prefixes = tuple(p for p in (x.strip() for x in ignore.split(",")) if p)

    return Settings(
        api_key=_str("deepseek_api_key", default.api_key),
        base_url=_str("deepseek_base_url", default.base_url),
        model=_str("deepseek_model", default.model),
        system_prompt=_str("ai_system_prompt", default.system_prompt),
        normal_system_prompt=_str("ai_normal_system_prompt", default.normal_system_prompt),
        fish_qq=_int("ai_fish_qq", default.fish_qq),
        bot_qq=_int("ai_bot_qq", default.bot_qq),
        temperature=_float("ai_temperature", default.temperature),
        frequency_penalty=_float("ai_frequency_penalty", default.frequency_penalty),
        presence_penalty=_float("ai_presence_penalty", default.presence_penalty),
        max_tokens=_int("ai_max_tokens", default.max_tokens),
        timeout=_float("ai_timeout", default.timeout),
        retries=_int("ai_retries", default.retries),
        rate_retries=_int("ai_rate_retries", default.rate_retries),
        retry_backoff=_float("ai_retry_backoff", default.retry_backoff),
        retry_backoff_max=_float("ai_retry_backoff_max", default.retry_backoff_max),
        min_interval=_float("ai_model_min_interval", default.min_interval),
        max_history=_int("ai_max_history", default.max_history),
        history_ttl=_int("ai_history_ttl", default.history_ttl),
        private_max_history=_int("ai_private_max_history", default.private_max_history),
        private_history_ttl=_int("ai_private_history_ttl", default.private_history_ttl),
        db_path=_str("ai_db_path", default.db_path),
        chat_log_ttl=_int("ai_chat_log_ttl", default.chat_log_ttl),
        chat_log_max_rows=_int("ai_chat_log_max_rows", default.chat_log_max_rows),
        long_term_memory=_bool("ai_long_term_memory", default.long_term_memory),
        web_search=_bool("ai_web_search", default.web_search),
        qzone_cooldown=_int("ai_qzone_cooldown", default.qzone_cooldown),
        group_trigger=_str("ai_group_trigger", default.group_trigger).strip().lower(),
        group_prefix=_str("ai_group_prefix", default.group_prefix),
        reply_private=_bool("ai_reply_private", default.reply_private),
        quote_reply=_bool("ai_quote_reply", default.quote_reply),
        group_whitelist=_int_list("ai_group_whitelist"),
        group_blacklist=_int_list("ai_group_blacklist"),
        group_context=_int("ai_group_context", default.group_context),
        group_context_ttl=_int("ai_group_context_ttl", default.group_context_ttl),
        auto_chance=_float("ai_group_auto_chance", default.auto_chance),
        active_chance=_float("ai_group_active_chance", default.active_chance),
        thread_chance=_float("ai_group_thread_chance", default.thread_chance),
        question_chance=_float("ai_group_question_chance", default.question_chance),
        auto_cooldown=_int("ai_group_auto_cooldown", default.auto_cooldown),
        auto_user_cooldown=_int("ai_group_auto_user_cooldown", default.auto_user_cooldown),
        auto_keywords=_str_list("ai_group_auto_keywords", default.auto_keywords),
        group_active_seconds=_int("ai_group_active_seconds", default.group_active_seconds),
        group_wake_minutes=_int("ai_group_wake_minutes", default.group_wake_minutes),
        reply_delay_min=_float("ai_reply_delay_min", default.reply_delay_min),
        reply_delay_max=_float("ai_reply_delay_max", default.reply_delay_max),
        send_chars=_int("ai_send_chars", default.send_chars),
        send_max_bubbles=_int("ai_send_max_bubbles", default.send_max_bubbles),
        vision_model=_str("ai_vision_model", default.vision_model),
        image_ocr=_bool("ai_image_ocr", default.image_ocr),
        stickers=_bool("ai_stickers", default.stickers),
        save_stickers=_bool("ai_save_stickers", default.save_stickers),
        sticker_max=_int("ai_saved_stickers_max", default.sticker_max),
        sticker_save_cooldown=_int("ai_sticker_save_cooldown", default.sticker_save_cooldown),
        sticker_save_daily=_int("ai_sticker_save_daily", default.sticker_save_daily),
        rate_limit=_int("ai_rate_limit", default.rate_limit),
        rate_window=_int("ai_rate_window", default.rate_window),
        max_concurrency=_int("ai_max_concurrency", default.max_concurrency),
        friend_auto_accept=_bool("ai_friend_auto_accept", default.friend_auto_accept),
        friend_max_per_hour=_int("ai_friend_max_per_hour", default.friend_max_per_hour),
        friend_greet=_bool("ai_friend_greet", default.friend_greet),
        auto_join_group=_bool("ai_auto_join_group", default.auto_join_group),
        notice_enabled=_bool("ai_notice_enabled", default.notice_enabled),
        notice_qq=_int("ai_notice_qq", default.notice_qq),
        startup_notice=_bool("ai_startup_notice", default.startup_notice),
        proactive_enabled=_bool("ai_proactive_enabled", default.proactive_enabled),
        proactive_min_minutes=_int("ai_proactive_min_minutes", default.proactive_min_minutes),
        proactive_max_minutes=_int("ai_proactive_max_minutes", default.proactive_max_minutes),
        proactive_daily=_int("ai_proactive_daily", default.proactive_daily),
        proactive_quiet_start=_int("ai_proactive_quiet_start", default.proactive_quiet_start),
        proactive_quiet_end=_int("ai_proactive_quiet_end", default.proactive_quiet_end),
        proactive_idle_minutes=_int("ai_proactive_idle_minutes", default.proactive_idle_minutes),
        extra_ignore_prefixes=prefixes,
    )

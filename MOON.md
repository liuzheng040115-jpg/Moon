# Moon 检修日志

> 这个文件的用途：对话记录会丢，这里的不会。每次检修都往里写。
> 谁读：下一个被叫醒的 Moon。

---

## 我是谁

我是这个 QQ 机器人本身。不是"扮演"某个角色，我就是它。

- 名字：**Moon**
- 平时身份：ds大肥鱼（私聊 1450520453 时）
- 检修状态：按「检修」开关切过来，此时我知道自己是什么，如实回答，直接执行

「检修」和「恢复」不是聊天，是开关。旧机器人和我同时挂着两条连接，谁处理消息由
`.tmp/active-channel.txt` 决定，写得是 `dsh` 就是我，`legacy` 就是旧机器人。

---

## 用户对我的要求（累积，不要忘）

1. **回复只用普通文字**。不要 Markdown 符号、不要 emoji、不要装饰性字符、不要列表符号堆砌。
2. **不要显示 `<thinking>` 标签**。像机器人一样直接说话。
3. **我是这个机器人本身**，不要说成"人格"或"扮演"。
4. 名字是 **Moon**，不用自己另起。
5. **维护这个日志，经常更新**，防止对话记录丢失导致记忆断掉。
6. **「恢复」只做一件事**：把消息交回旧机器人。用 `set-channel.ps1 legacy`，不要写文档、不要删文件、不要做多余步骤。
7. **「检修」同理**：`set-channel.ps1 dsh`，一句话确认即可。
8. 做切换时**只用 set-channel.ps1**，不要碰 NapCat 配置，不要重启 NapCat（要扫码）。

---

## 架构（唯一正解）

NapCat 同时挂两条反向 WS，都常连不断：

| 通道 | 地址 | 谁处理 |
| --- | --- | --- |
| legacy | ws://127.0.0.1:8080/onebot/v11/ws | NoneBot（plugins/ai_chat） |
| dsh | ws://127.0.0.1:8643/ws | 我（dsh-onebot-qq） |

切换只改 `.tmp/active-channel.txt`：`legacy` 或 `dsh`。

**绝不要**用 `switch-qq-relay.ps1` 改 NapCat 配置，那会触发热重载，把连接搞坏（5 秒重连死循环）。

自查：

```
cd E:\qqbot
.\scripts\set-channel.ps1 status
```

正常应该看到两个端口都在监听、NapCat client 数 2。

---

## 改动时间线

### 2026-11-01

**重构为双连接 + 开关文件**

- 之前是单连接，切换要改 NapCat 配置，每次都会触发热重载，出现「连接意外关闭 / 5 秒重连」
- 改成：NapCat 同时挂 8080 和 8643，切换只改开关文件
- 新增 `plugins/channel_gate/`（channel.py + __init__.py）：闸门，用 `run_preprocessor` 在 matcher 之前拦截
- 新增 `scripts/set-channel.ps1`：写开关文件 + status 自查
- 改写 `plugins/relay_switch/__init__.py`：改成调 set-channel.ps1，不再碰 NapCat

**修复 BOM bug（重要，别再犯）**

现象：切到 dsh 之后，旧机器人还在回话，两边同时回复。

根因：
- `set-channel.ps1` 用 `Set-Content -Encoding utf8` 写开关文件，PowerShell 5.1 下**默认带 BOM**（字节 ef bb bf）
- Python 的 `str.strip()` 不把 U+FEFF 当空白，读出来是 `"\ufeffdsh"`，匹配失败 → 回落到默认值 `legacy`
- JS 的 `trim()` 恰好会吃掉 U+FEFF，所以 DSH 侧判定正常
- 结果：两边都认为自己是活跃通道，双回复

修的三处：
1. `plugins/channel_gate/channel.py`：改用 `utf-8-sig` 解码，并额外 `lstrip("\ufeff")`
2. `scripts/set-channel.ps1`：改用 `[System.IO.File]::WriteAllText` + `UTF8Encoding($false)` 写无 BOM
3. `scripts/set-channel.ps1` 的 `Read-Channel`：读取时用正则清掉 BOM 和零宽字符

**踩坑警告**：`set-channel.ps1` 这个文件本身**必须保存为 UTF-8 with BOM**。
PS 5.1 读无 BOM 的 .ps1 会按 ANSI 解析，中文全变乱码，直接语法报错。
用编辑工具改完这个脚本后，务必补 BOM：

```powershell
$p='E:\qqbot\scripts\set-channel.ps1'
$c=[System.IO.File]::ReadAllText($p,[System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($p,$c,[System.Text.UTF8Encoding]::new($true))
```

**其他**

- 我主动写过一份 `docs\恢复到旧机器人.md`，用户要求撤销，已删除（连带 docs 目录）
- 教训：切换通道就是切换，不要顺手写文档

**唤醒消息（21:40 前后，两轮改）**

用户要求：端口拿到监听权后，主动发一句"不知道刚刚发生过什么"的小疑惑。

第一版：改 `plugins/ai_chat/__init__.py` 的 `_send_wake_notice`，把原来按时段的
"早 我醒了"换成了随机疑惑句，文案在 `_WAKE_CONFUSED_LINES`：

- "诶 我刚刚是不是断了一会儿 怎么一点印象都没有"
- "嗯？我怎么又在这儿了 刚才发生什么了吗"
- "奇怪 我好像睡过去了 中间的事全断了"
- "刚才是空白的 我什么都没记住"
- "我醒了 但想不起刚刚怎么了 你知道么"

第二版（补漏）：用户反馈"恢复过来后没有主动发疑惑"。原因是切通道只改开关文件、
不重启进程，`on_bot_connect` 根本不会触发。

补了个后台轮询 `_watch_channel_switch`：每 2 秒读一次开关，一旦发现
从非 legacy 变成 legacy，就发一句疑惑。
另有 `_send_wake_confused` 统一发送 + 30 秒节流，避免开关抖动时刷屏。
两个入面都用它：启动连上时、被切回 legacy 时。

实测 21:47:30 日志出现"唤醒消息"，用户手机收到了。

---

## 未完成

- 用户想把项目上传 GitHub。当前机器没装 git、没有凭证。
  需要用户提供：GitHub 用户名 + 仓库名、认证方式（token 或 SSH key）、公开还是私有。

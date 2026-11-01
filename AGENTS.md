# qqbot 项目约定

## 架构：双连接 + 一个开关

NapCat **同时**挂着两条反向 WS 连接：

| 端 | 地址 | 谁在处理 |
| --- | --- | --- |
| 旧机器人 | `ws://127.0.0.1:8080/onebot/v11/ws` | NoneBot（`plugins/ai_chat`） |
| DSH | `ws://127.0.0.1:8643/ws` | DSH 插件（`dsh-onebot-qq`，也就是你） |

两条都常连不断。同一条消息两边都会收到，但**只有一个真正处理**，由开关文件决定：

```
E:\qqbot\.tmp\active-channel.txt
内容：legacy 或 dsh
```

- `legacy` → 旧机器人处理，**DSH 静默**
- `dsh` → DSH 处理，**旧机器人静默**

**切换只改这一个文件，绝不要碰 NapCat 配置。**
改 NapCat 配置会触发它热重载 OneBot11 适配器，新旧客户端实例打架，把连接搞坏——「连接意外关闭 / 5 秒重连」那个老毛病就是这么来的。

---

## 第一条：先确认自己在不在岗

```powershell
cd E:\qqbot
.\scripts\set-channel.ps1 status
```

看 `活跃通道`：

| 活跃通道 | 你该做什么 |
| --- | --- |
| `dsh` | 现在是你在处理消息，**收到指令就执行** |
| `legacy` | 消息本该由旧机器人处理。你能看到这条说明它是历史残留或误投，**回一句「当前在旧机器人通道，指令已忽略」，不要执行任何切换** |

补充：闸门（`bridge.js` 的 `dshChannelActive`）在活跃通道不是 `dsh` 时会直接丢弃入站消息（trace 里记为 `活跃通道不是 dsh，已忽略`），所以你**正常情况下只会在 `dsh` 时收到消息**。

---

## 检修 / 恢复：这是指令，收到就执行，不要探索

「检修」和「恢复」是**切换通道的指令**，不是聊天话题。

确认该你做之后，**立即执行对应脚本**，然后回一句确认即可。

**禁止**：
- 不要反问「你干嘛」「你确定吗」，除了下面写明的二次确认
- 不要自己摸索、反复试探、猜测该怎么做
- 不要为此写新文档、删文件、建目录
- 不要先分析半天再动手
- **切换只用 `set-channel.ps1`**。不要用 `switch-qq-relay.ps1`（它改 NapCat 配置，会破坏双连接），不要手工改 `onebot11_*.json`，不要重启 NapCat 进程（那要重新扫码）

---

## 收到「检修」= 把消息交给 DSH

```powershell
cd E:\qqbot
.\scripts\set-channel.ps1 dsh
```

看到 `活跃通道已切到: dsh` 就成功了。回一句「已切到检修模式」结束。

### 二次确认发生在旧机器人那边

旧机器人活跃时，「检修」由 `plugins/relay_switch` 处理：

- 第 1 次发「检修」→ 机器人回「你干嘛」（**这是二次确认，不是拒绝**）
- 120 秒内再发 1 次「检修」→ 才真的切换，回「正在打开 Moon」

如果你是 DSH 且真收到了「检修」，说明开关已经是 `dsh` 了，直接执行上面的脚本即可（幂等，重复执行无害）。

---

## 收到「恢复」= 把消息交回旧机器人

**先确认旧机器人在跑，再切。** 顺序反了会有一小段时间没人接消息。

### 第 1 步：确认 8080 活着

```powershell
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8080/healthz" -TimeoutSec 4 -UseBasicParsing).Content } catch { "DOWN" }
```

返回 `{"ok":true,...}` 就算活着（`bots` 应该是 1，因为双连接常连）。

### 第 2 步：没活着就拉起来

```powershell
cd E:\qqbot
Start-Process -FilePath "E:\qqbot\.venv\Scripts\python.exe" `
    -ArgumentList "-u", "bot.py" `
    -WorkingDirectory "E:\qqbot" `
    -WindowStyle Hidden
```

等 10~15 秒，再回到第 1 步确认。

### 第 3 步：切回旧机器人

```powershell
cd E:\qqbot
.\scripts\set-channel.ps1 legacy
```

看到 `活跃通道已切到: legacy` 就成功了。

### 第 4 步：回一句

「已恢复」就够了。

---

## 自查命令

```powershell
cd E:\qqbot
.\scripts\set-channel.ps1 status
```

输出会告诉你：当前活跃通道、两个端口是否在监听、NapCat 挂了几个 client。正常应该是 **2 个 client**（一个 legacy、一个 dsh）。

想单独看某一边：

```powershell
# 旧机器人是否健康
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8080/healthz" -TimeoutSec 4 -UseBasicParsing).Content } catch { "DOWN" }

# DSH 侧最近收到并被怎么处理了
Get-Content "$env:USERPROFILE\.dsh\media\onebot\qq-trace.jsonl" -Tail 5
```

两条通道的对话记录互相独立：旧机器人写 `data/bot.db`，DSH 写 `~/.dsh/sessions/`。

---

## 本机端口速查

| 端口 | 归谁 | 用途 |
| --- | --- | --- |
| 8080 | NoneBot（`bot.py`） | 旧机器人反向 WS + `/healthz` |
| 8643 | DSH 桌面应用 | DSH 插件反向 WS |
| 6099 | NapCat | WebUI 管理面板 |

---

## 常见故障

### 先分清「传输层」还是「会话层」

判断只看一条：**`qq-trace.jsonl` 里有没有这条消息的新记录。**

```powershell
Get-Content "$env:USERPROFILE\.dsh\media\onebot\qq-trace.jsonl" -Tail 5
```

- **有 `inbound` 记录** → 传输层通了。如果 `ok:false` 且原因是 `活跃通道不是 dsh`，那就是开关指向了 legacy，正常行为，不是故障
- **完全没有新记录** → 传输层断了。查下面「NapCat 5 秒重连」

这条判据比看端口、看 healthz 都准。端口显示 `Established` 也可能是假的（TCP 通了，WebSocket 握手后被踢）。

### NapCat 反复 5 秒重连

日志长这样，每 5 秒一次：

```
反向WebSocket (ws://xxx/ws) 连接意外关闭
在 5 秒后尝试重新连接
```

**这个循环意味着消息全丢，必须处理。** 首选修法（不重启进程、不扫码）：

```powershell
cd E:\qqbot
.\scripts\toggle-napcat-ws.ps1 -State off
Start-Sleep -Seconds 4
.\scripts\toggle-napcat-ws.ps1 -State on
```

2026-11-01 实测：51 秒零重连（原来每 5 秒一次）。

原理：关闭再打开是一次干净的客户端重建，不碰 QQ 登录态。

### 只有 toggle 无效时才重启进程（要重新扫码）

```powershell
Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8643 | Group-Object State   # 确认无 Established
cd E:\qqbot
.\scripts\start_napcat_scan.ps1                              # 要重新扫码
```

**代价大（必须重新扫码），所以放在 toggle 之后。**

### NapCat 只剩 1 个 client（双连接掉了）

用旧脚本 `switch-qq-relay.ps1` 或手工改过配置就会这样。恢复双连接：

```powershell
cd E:\qqbot
.\scripts\dual-ws-probe.ps1 -Mode dual
```

然后 `set-channel.ps1 status` 应该看到 2 个 client。

### 两条连接都在，但没人回话

查开关指向是不是和预期一致：

```powershell
cd E:\qqbot; .\scripts\set-channel.ps1 status
```

如果开关是 `dsh` 但 DSH 没在工作，或者 `legacy` 但 8080 没在跑，就会两边都静默。**这是双连接架构唯一的坑：开关指向的那一方必须真的活着。**

### 登录成主号（1450520453）而不是机器人号（235286703）

扫码前必须先切换手机 QQ 账号。NapCat 只做到「不读历史登录态」，控制不了你扫哪个号。

**后果很严重**：主号登录期间会以主号身份接收所有群消息。发现登错了要立刻停 NapCat（`Stop-Process -Name node -Force`）。

---

## 本项目的安全默认（勿改）

- NapCat 只走扫码登录，不用 `-q` 快速登录，不读本机历史登录态
- 启动前清空 `NAPCAT_QUICK_*` 环境变量与 WebUI 的 `autoLoginAccount`
- 只保留机器人号（235286703）的 `onebot11_*.json`，其他账号的配置改名为 `.disabled`
- 插件侧再兜一层：`AI_BOT_QQ` 不匹配时拒绝处理

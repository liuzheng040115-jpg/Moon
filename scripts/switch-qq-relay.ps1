# 在「旧机器人（8080）」和「DSH（8643）」之间切换 NapCat 的反向 WebSocket 指向。
#
# 用法：
#   .\switch-qq-relay.ps1 -Target dsh       # 切给 DSH（检修模式）
#   .\switch-qq-relay.ps1 -Target legacy    # 切回旧机器人（恢复）
#   .\switch-qq-relay.ps1 -Status           # 只看当前指向
#
# 原理：通过 NapCat WebUI 的 OB11Config 接口改写 websocketClients，
# 和 .\configure_napcat.ps1 用的是同一套 API。只改 URL/token，其余字段原样保留。

param(
    [ValidateSet("dsh", "legacy")]
    [string]$Target,
    [switch]$Status,
    [string]$NapCatRoot = (Join-Path $PSScriptRoot "..\tools\NapCat")
)

$ErrorActionPreference = "Stop"

# 两条通道的地址与 token。token 从 .env 读，不写死在仓库里：
#   ONEBOT_ACCESS_TOKEN  -> legacy（8080 旧机器人）
#   DSH_ONEBOT_TOKEN     -> dsh（8643 DSH 插件）
# 读不到就留空，NapCat 侧配置里已有的 token 会原样保留。
function Read-DotEnv([string]$key) {
    $envPath = Join-Path $PSScriptRoot "..\.env"
    if (-not (Test-Path $envPath)) { return "" }
    $m = [regex]::Match((Get-Content $envPath -Raw), "(?m)^\s*$key\s*=\s*(.+?)\s*$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ""
}

$CHANNELS = @{
    dsh    = @{ url = "ws://127.0.0.1:8643/ws"; token = (Read-DotEnv "DSH_ONEBOT_TOKEN"); label = "DSH (8643)" }
    legacy = @{ url = "ws://127.0.0.1:8080/onebot/v11/ws"; token = (Read-DotEnv "ONEBOT_ACCESS_TOKEN"); label = "旧机器人 (8080)" }
}

$stateFile = Join-Path $PSScriptRoot "..\.tmp\relay-target.txt"

function Get-NapCatApi {
    $cfgDir = Join-Path $NapCatRoot "napcat\config"
    $webuiPath = Join-Path $cfgDir "webui.json"
    if (-not (Test-Path $webuiPath)) {
        throw "找不到 $webuiPath —— NapCat 从未启动过？先跑一次 tools\NapCat\napcat.bat 完成扫码登录。"
    }
    $webui = Get-Content $webuiPath -Raw | ConvertFrom-Json
    $apiHost = if ($webui.host -in @("::", "0.0.0.0", "")) { "127.0.0.1" } else { $webui.host }
    $apiPort = if ($webui.port) { $webui.port } else { 6099 }
    $base = "http://${apiHost}:${apiPort}/api"

    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("$($webui.token).napcat")) |
        ForEach-Object { $_.ToString("x2") }) -join ""

    try {
        $login = Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType "application/json" `
            -Body (@{ hash = $hash } | ConvertTo-Json -Compress) -TimeoutSec 10
    } catch {
        throw "连不上 NapCat WebUI（$base）——NapCat 没在运行？请先启动 tools\NapCat\napcat.bat 并扫码登录。原始错误：$($_.Exception.Message)"
    }
    $cred = $login.data.Credential
    if (-not $cred) { throw "WebUI 登录失败：$($login.message)" }

    return @{
        Base    = $base
        Headers = @{ Authorization = "Bearer $cred" }
    }
}

$api = Get-NapCatApi

$r = Invoke-RestMethod -Uri "$($api.Base)/OB11Config/GetConfig" -Method Post -Headers $api.Headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 10
if ($r.code -ne 0) { throw "读取 OneBot 配置失败：$($r.message)（QQ 是否已经登录？）" }

$cfg = $r.data
$currentUrl = if ($cfg.network.websocketClients.Count -gt 0) { $cfg.network.websocketClients[0].url } else { "(无)" }

if ($Status) {
    $saved = if (Test-Path $stateFile) { (Get-Content $stateFile -Raw).Trim() } else { "未记录" }
    Write-Host "NapCat 当前指向 : $currentUrl"
    Write-Host "上次切换记录   : $saved"
    exit 0
}

if (-not $Target) { throw "请指定 -Target dsh 或 -Target legacy（或用 -Status 查看）" }

$ch = $CHANNELS[$Target]

# 保留 NapCat 里原有的其余字段，只替换 url 和 token
if ($cfg.network.websocketClients.Count -gt 0) {
    $entry = $cfg.network.websocketClients[0]
} else {
    $entry = [pscustomobject]@{}
}
$entry.enable            = $true
$entry.name              = "qqbot"
$entry.url               = $ch.url
$entry.token             = $ch.token
$entry.reportSelfMessage = $false
$entry.messagePostFormat = "array"
$entry.debug             = $false
$entry.heartInterval     = 30000
$entry.reconnectInterval = 5000
$cfg.network.websocketClients = @($entry)

$payload = @{ config = ($cfg | ConvertTo-Json -Depth 12 -Compress) } | ConvertTo-Json -Compress
$set = Invoke-RestMethod -Uri "$($api.Base)/OB11Config/SetConfig" -Method Post -Headers $api.Headers `
    -ContentType "application/json" -Body $payload -TimeoutSec 10
if ($set.code -ne 0) { throw "写入 OneBot 配置失败：$($set.message)" }

# 校验真的写进去了
$verify = Invoke-RestMethod -Uri "$($api.Base)/OB11Config/GetConfig" -Method Post -Headers $api.Headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 10
$nowUrl = $verify.data.network.websocketClients[0].url
if ($nowUrl -ne $ch.url) {
    throw "写入后校验失败：期望 $($ch.url)，实际 $nowUrl"
}

New-Item -ItemType Directory -Force -Path (Split-Path $stateFile) | Out-Null
Set-Content -LiteralPath $stateFile -Value "$Target $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))" -Encoding utf8

Write-Host "已切到 $($ch.label)" -ForegroundColor Green
Write-Host "  URL   : $($ch.url)"
Write-Host "  会话记录：两条通道各自独立（旧机器人 bot.db / DSH sessions），互不影响。"

# ---- 切到 legacy 后自愈：NoneBot 持有僵尸连接会导致新连接全被 403 ----
# 现象：healthz 仍返回 bots:1，但 NapCat 每次重连都被 "There's already a bot
# <qq>, ignored" + 403 拒绝，形成 5 秒重连死循环（QQ 消息全丢）。
# NoneBot 只在进程内维护 bots 字典，NapCat 断开时它不会及时清理，所以重启
# bot.py 是唯一可靠的清法。这里只探测"切到 legacy 之后"的循环，且限一次。
if ($Target -eq "legacy") {
    $healthUrl = "http://127.0.0.1:8080/healthz"
    $botAlive = $false
    try {
        $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 4
        $botAlive = ($h.ok -eq $true)
    } catch {
        $botAlive = $false
    }

    if (-not $botAlive) {
        Write-Host "旧机器人没在跑（healthz 不通）。先启动它，否则 NapCat 会一直重连。" -ForegroundColor Yellow
        Start-Process -FilePath (Join-Path (Split-Path $PSScriptRoot) ".venv\Scripts\python.exe") `
            -ArgumentList "-u", "bot.py" `
            -WorkingDirectory (Split-Path $PSScriptRoot) `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path (Split-Path $PSScriptRoot) ".tmp\bot-stdout.log") `
            -RedirectStandardError (Join-Path (Split-Path $PSScriptRoot) ".tmp\bot-stderr.log")
        Start-Sleep -Seconds 10
    }

    # 给 NapCat 一点时间完成首次握手
    Start-Sleep -Seconds 6

    # 判断是否陷入僵尸连接：连续两次 healthz 都 bots 有值，且 bot 日志出现 403
    $stdout = Join-Path (Split-Path $PSScriptRoot) ".tmp\bot-stdout.log"
    $zombie = $false
    for ($i = 0; $i -lt 2; $i++) {
        if (Test-Path $stdout) {
            $recent = Get-Content $stdout -Tail 40 -ErrorAction SilentlyContinue |
                Where-Object { $_ -match "403|already a bot" }
            if ($recent.Count -ge 2) { $zombie = $true; break }
        }
        Start-Sleep -Seconds 4
    }

    if ($zombie) {
        Write-Host "检测到僵尸连接（403 循环），正在重启旧机器人 ..." -ForegroundColor Yellow
        Get-Process -Name python -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "*qqbot*" -or $_.Path -like "*.venv*" } |
            ForEach-Object { try { Stop-Process -Id $_.Id -Force } catch { } }
        # 端口可能被子进程占着，等它真正释放
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            $busy = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
            if (-not $busy) { break }
        }
        Start-Process -FilePath (Join-Path (Split-Path $PSScriptRoot) ".venv\Scripts\python.exe") `
            -ArgumentList "-u", "bot.py" `
            -WorkingDirectory (Split-Path $PSScriptRoot) `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError (Join-Path (Split-Path $PSScriptRoot) ".tmp\bot-stderr.log")
        Start-Sleep -Seconds 12
        try {
            $h2 = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
            Write-Host "已重启旧机器人：bots=$($h2.bots)" -ForegroundColor Green
        } catch {
            Write-Host "重启后 healthz 仍不通，请手动检查 .tmp\bot-stderr.log" -ForegroundColor Yellow
        }
    } else {
        try {
            $h3 = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 4
            Write-Host "旧机器人连接正常：bots=$($h3.bots)" -ForegroundColor Green
        } catch { }
    }
}

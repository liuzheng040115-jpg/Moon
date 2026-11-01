# 把 NapCat 的反向 WebSocket 指向本机器人（登录成功后运行一次即可）
# 用法： .\scripts\configure_napcat.ps1
param(
    [string]$NapCatRoot = (Join-Path $PSScriptRoot "..\tools\NapCat")
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$cfgDir = Join-Path $NapCatRoot "napcat\config"
$webuiPath = Join-Path $cfgDir "webui.json"

if (-not (Test-Path $webuiPath)) {
    throw "找不到 $webuiPath，请先启动一次 NapCat 并完成登录"
}

# 读 .env 里的 token / 端口
$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path $envPath)) { throw "找不到 .env，请先从 .env.example 复制一份" }
$envText = Get-Content $envPath -Raw
$token = [regex]::Match($envText, '(?m)^\s*ONEBOT_ACCESS_TOKEN\s*=\s*(\S+)').Groups[1].Value
$botPort = [regex]::Match($envText, '(?m)^\s*PORT\s*=\s*(\d+)').Groups[1].Value
if (-not $botPort) { $botPort = "8080" }
if (-not $token) { throw ".env 里的 ONEBOT_ACCESS_TOKEN 为空" }

$webui = Get-Content $webuiPath -Raw | ConvertFrom-Json
$apiHost = if ($webui.host -in @("::", "0.0.0.0", "")) { "127.0.0.1" } else { $webui.host }
$apiPort = if ($webui.port) { $webui.port } else { 6099 }
$base = "http://${apiHost}:${apiPort}/api"

# WebUI 登录：hash = SHA256(token + ".napcat")
$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("$($webui.token).napcat")) |
    ForEach-Object { $_.ToString("x2") }) -join ""
$login = Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType "application/json" `
    -Body (@{ hash = $hash } | ConvertTo-Json -Compress) -TimeoutSec 10
$cred = $login.data.Credential
if (-not $cred) { throw "WebUI 登录失败：$($login.message)" }

$headers = @{ Authorization = "Bearer $cred" }
$r = Invoke-RestMethod -Uri "$base/OB11Config/GetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 10
if ($r.code -ne 0) { throw "读取 OneBot 配置失败：$($r.message)（QQ 是否已经登录？）" }

$cfg = $r.data
$cfg.network.websocketClients = @([ordered]@{
    enable            = $true
    name              = "qqbot"
    url               = "ws://127.0.0.1:${botPort}/onebot/v11/ws"
    reportSelfMessage = $false
    messagePostFormat = "array"
    token             = $token
    debug             = $false
    heartInterval     = 30000
    reconnectInterval = 5000
})

$payload = @{ config = ($cfg | ConvertTo-Json -Depth 12 -Compress) } | ConvertTo-Json -Compress
$set = Invoke-RestMethod -Uri "$base/OB11Config/SetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body $payload -TimeoutSec 10
if ($set.code -ne 0) { throw "写入 OneBot 配置失败：$($set.message)" }

Write-Host "已配置反向 WS: ws://127.0.0.1:${botPort}/onebot/v11/ws" -ForegroundColor Green
Write-Host "机器人日志出现 `Bot <QQ号> connected` 即接入成功。" -ForegroundColor Green

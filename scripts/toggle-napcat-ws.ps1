param(
    [Parameter(Mandatory = $true)][ValidateSet("on", "off")][string]$State,
    [string]$NapCatRoot = (Join-Path $PSScriptRoot "..\tools\NapCat")
)
# 临时开启/关闭 NapCat 的反向 WS 客户端（不重启 NapCat，不影响登录态）
# 用途：NapCat 每 5 秒重连会刷爆 DSH 的 churn guard（60s 内最多 5 次替换），
#       关掉一会儿让窗口滑过，再打开就能正常握手。
$ErrorActionPreference = "Stop"

$webuiPath = Join-Path $NapCatRoot "napcat\config\webui.json"
$webui = Get-Content $webuiPath -Raw | ConvertFrom-Json
$apiHost = if ($webui.host -in @("::", "0.0.0.0", "")) { "127.0.0.1" } else { $webui.host }
$apiPort = if ($webui.port) { $webui.port } else { 6099 }
$base = "http://${apiHost}:${apiPort}/api"

$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("$($webui.token).napcat")) |
    ForEach-Object { $_.ToString("x2") }) -join ""
$login = Invoke-RestMethod -Uri "$base/auth/login" -Method Post -ContentType "application/json" `
    -Body (@{ hash = $hash } | ConvertTo-Json -Compress) -TimeoutSec 10
$headers = @{ Authorization = "Bearer $($login.data.Credential)" }

$r = Invoke-RestMethod -Uri "$base/OB11Config/GetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 10
if ($r.code -ne 0) { throw "读取配置失败：$($r.message)" }

$cfg = $r.data
foreach ($entry in $cfg.network.websocketClients) {
    $entry.enable = ($State -eq "on")
}

$payload = @{ config = ($cfg | ConvertTo-Json -Depth 12 -Compress) } | ConvertTo-Json -Compress
$set = Invoke-RestMethod -Uri "$base/OB11Config/SetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body $payload -TimeoutSec 10
if ($set.code -ne 0) { throw "写入配置失败：$($set.message)" }

Write-Host "反向 WS 客户端已 $(if ($State -eq 'on') { '开启' } else { '关闭' })：$($cfg.network.websocketClients[0].url)" -ForegroundColor Green

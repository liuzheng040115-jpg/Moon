param(
    [ValidateSet("probe", "restore", "dual")][string]$Mode = "probe",
    [string]$NapCatRoot = (Join-Path $PSScriptRoot "..\tools\NapCat")
)
# 试验：NapCat 能否同时挂多个反向 WS 客户端
#  probe   = 加一个指向空端口(9999)的 client，验证多 client 是否被接受（不影响真实通道）
#  dual    = 真实双连：8080 + 8643 同时挂
#  restore = 恢复成单 client（8080）
$ErrorActionPreference = "Stop"

# token 从 .env 读，不写死在仓库里
function Read-DotEnv([string]$key) {
    $envPath = Join-Path $PSScriptRoot "..\.env"
    if (-not (Test-Path $envPath)) { return "" }
    $m = [regex]::Match((Get-Content $envPath -Raw), "(?m)^\s*$key\s*=\s*(.+?)\s*$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ""
}
$TOKEN_LEGACY = Read-DotEnv "ONEBOT_ACCESS_TOKEN"
$TOKEN_DSH    = Read-DotEnv "DSH_ONEBOT_TOKEN"

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

# 只保留第一个 client 的字段作模板
$template = $cfg.network.websocketClients[0]

function New-Client($name, $url, $token) {
    return [pscustomobject]@{
        enable            = $true
        name              = $name
        url               = $url
        reportSelfMessage = $false
        messagePostFormat = "array"
        token             = $token
        debug             = $false
        heartInterval     = 30000
        reconnectInterval = 5000
        verifyCertificate = $true
    }
}

switch ($Mode) {
    "probe" {
        $cfg.network.websocketClients = @(
            (New-Client "qqbot" "ws://127.0.0.1:8080/onebot/v11/ws" $TOKEN_LEGACY),
            (New-Client "probe" "ws://127.0.0.1:9999/ws" "probetoken")
        )
        Write-Host "已设置 2 个 client（8080 + 空端口 9999）" -ForegroundColor Cyan
    }
    "dual" {
        $cfg.network.websocketClients = @(
            (New-Client "legacy" "ws://127.0.0.1:8080/onebot/v11/ws" $TOKEN_LEGACY),
            (New-Client "dsh"    "ws://127.0.0.1:8643/ws"            $TOKEN_DSH)
        )
        Write-Host "已设置 2 个 client（8080 + 8643 双连）" -ForegroundColor Cyan
    }
    "restore" {
        $cfg.network.websocketClients = @(
            (New-Client "qqbot" "ws://127.0.0.1:8080/onebot/v11/ws" $TOKEN_LEGACY)
        )
        Write-Host "已恢复为单 client（8080）" -ForegroundColor Cyan
    }
}

$payload = @{ config = ($cfg | ConvertTo-Json -Depth 12 -Compress) } | ConvertTo-Json -Compress
$set = Invoke-RestMethod -Uri "$base/OB11Config/SetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body $payload -TimeoutSec 10
if ($set.code -ne 0) { throw "写入配置失败：$($set.message)" }

Start-Sleep -Seconds 2
$v = Invoke-RestMethod -Uri "$base/OB11Config/GetConfig" -Method Post -Headers $headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 10
Write-Host "回读确认：共 $($v.data.network.websocketClients.Count) 个 client"
$v.data.network.websocketClients | ForEach-Object { "  $($_.name): $($_.url)  enable=$($_.enable)" }

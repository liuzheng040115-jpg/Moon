param(
    [Parameter(Position = 0)][ValidateSet("legacy", "dsh", "status")][string]$Target = "status"
)
# 切换活跃通道：改一个文件，不动 NapCat 配置。
#
# 前提：NapCat 同时挂着 8080（旧机器人）和 8643（DSH）两条反向 WS 连接
# （用 scripts\dual-ws-probe.ps1 -Mode dual 配置）。
#
# 这样切换不会再触发 NapCat 热重载，也就不会出现「连接意外关闭 / 5 秒重连」。
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot
$gateFile = Join-Path $root ".tmp\active-channel.txt"

function Read-Channel {
    if (-not (Test-Path $gateFile)) { return "(未设置，默认 legacy)" }
    $v = (Get-Content $gateFile -Raw -ErrorAction SilentlyContinue)
    if ($null -eq $v) { return "(空，默认 legacy)" }
    # 去掉 BOM 和零宽字符，避免历史遗留的带 BOM 文件显示成怪字符
    $v = ($v -replace "[\uFEFF\u200B]", "").Trim()
    if ($v -eq "") { return "(空，默认 legacy)" }
    return $v
}

function Test-Port([int]$Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $Port)
        $c.Close()
        return $true
    } catch { return $false }
}

if ($Target -eq "status") {
    $cur = Read-Channel
    Write-Host "活跃通道: $cur"
    if (Test-Path $gateFile) { Write-Host "开关文件: $gateFile" }
    ""

    # 两条连接是否都在
    $legacyUp = Test-Port 8080
    $dshUp = Test-Port 8643
    Write-Host ("旧机器人 8080: " + $(if ($legacyUp) { "在监听" } else { "没在跑" }))
    Write-Host ("DSH 8643   : " + $(if ($dshUp) { "在监听" } else { "没在跑" }))
    ""

    # NapCat 现在挂了几个 client
    $cfgPath = Join-Path $root "tools\NapCat\napcat\config\onebot11_235286703.json"
    if (Test-Path $cfgPath) {
        try {
            $clients = (Get-Content $cfgPath -Raw | ConvertFrom-Json).network.websocketClients
            Write-Host "NapCat client 数: $($clients.Count)"
            $clients | ForEach-Object { "  $($_.name): $($_.url)" }
        } catch {
            Write-Host "读取 NapCat 配置失败: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    exit 0
}

# ---- 写开关 ----
New-Item -ItemType Directory -Force -Path (Split-Path $gateFile) | Out-Null
# 必须写无 BOM 的 UTF-8：Python 侧 str.strip() 不去 U+FEFF，
# 带 BOM 会让 channel_gate 匹配失败、回落到 legacy，导致两边同时回话。
[System.IO.File]::WriteAllText($gateFile, $Target, [System.Text.UTF8Encoding]::new($false))

Write-Host "活跃通道已切到: $Target" -ForegroundColor Green
if ($Target -eq "legacy") {
    Write-Host "  之后的消息由旧机器人（NoneBot / ai_chat）处理，DSH 静默。"
} else {
    Write-Host "  之后的消息由 DSH（dsh-onebot-qq）处理，旧机器人静默。"
}
Write-Host "  NapCat 连接未改动。"

# 提示：目标端口不在时会收不到消息
$port = if ($Target -eq "legacy") { 8080 } else { 8643 }
if (-not (Test-Port $port)) {
    Write-Host "警告：$port 现在没有在监听，切过去也收不到消息。" -ForegroundColor Yellow
}

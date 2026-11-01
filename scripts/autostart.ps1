$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $root ".tmp"
$log = Join-Path $logDir "autostart.log"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
function Write-Log([string]$message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message"
    $line | Out-File -FilePath $log -Append -Encoding utf8
}

# 开机后等桌面和网络就绪
Start-Sleep -Seconds 15

# 只启动机器人进程；NapCat 必须人工扫码，绝不自动登录
$port = Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue
if ($port) {
    Write-Log "bot already running on port 8080 (pid $($port.OwningProcess))"
} else {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $python) {
        $botLog = Join-Path $logDir "bot-autostart.log"
        $cmd = "`"$python`" bot.py *> `"$botLog`" 2>&1"
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory $root -WindowStyle Hidden
        Write-Log "bot started (waiting for manual QR login)"
    } else {
        Write-Log "python not found: $python"
    }
}

# 明确不启动 NapCat：避免免密/快速登录把管理员大号登上去
$napcatDir = Join-Path $root "tools\NapCat"
$napcat = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq "node.exe" -and $_.CommandLine -like "*$napcatDir*" }
if ($napcat) {
    Write-Log "napcat already running (pid $($napcat[0].ProcessId)); left untouched"
} else {
    Write-Log "napcat not started on purpose; run scripts\start_napcat_scan.ps1 and scan the QR code"
}

# 一键启动：机器人 + NapCat 各开一个窗口（已在运行则跳过）
# 用法： .\start_all.bat  或  .\scripts\start_all.ps1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Test-Port([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

# 机器人端口
$botPort = 8080
$envPath = Join-Path $root ".env"
if (Test-Path $envPath) {
    $m = [regex]::Match((Get-Content $envPath -Raw), '(?m)^\s*PORT\s*=\s*(\d+)')
    if ($m.Success) { $botPort = [int]$m.Groups[1].Value }
}

if (Test-Port $botPort) {
    Write-Host "机器人已在运行（端口 $botPort），跳过。" -ForegroundColor Yellow
} else {
    Write-Host "启动机器人 ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-File", "$root\run.ps1") `
        -WorkingDirectory $root
}

# NapCat
$napcat = Join-Path $root "tools\NapCat\napcat.bat"
if (-not (Test-Path $napcat)) {
    Write-Host "未找到 NapCat，先运行 .\scripts\setup_napcat.ps1" -ForegroundColor Yellow
} elseif (Test-Port 6099) {
    Write-Host "NapCat 已在运行（WebUI 6099），跳过。" -ForegroundColor Yellow
} else {
    Write-Host "启动 NapCat（仅扫码登录，不做免密/快速登录）..." -ForegroundColor Cyan
    # 清掉快速登录入口，避免免密登到别的号
    foreach ($name in @("NAPCAT_QUICK_ACCOUNT", "NAPCAT_QUICK_PASSWORD", "NAPCAT_QUICK_PASSWORD_MD5")) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }
    $webuiPath = Join-Path $root "tools\NapCat\napcat\config\webui.json"
    if (Test-Path $webuiPath) {
        try {
            $webui = Get-Content $webuiPath -Raw | ConvertFrom-Json
            if ($webui.autoLoginAccount) {
                $webui.autoLoginAccount = ""
                [System.IO.File]::WriteAllText(
                    $webuiPath,
                    ($webui | ConvertTo-Json -Depth 12),
                    [System.Text.UTF8Encoding]::new($false)
                )
                Write-Host "已清空 WebUI 自动登录账号。" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "检查 webui.json 失败：$($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList @("/k", "`"$napcat`"") `
        -WorkingDirectory (Join-Path $root "tools\NapCat")
    Write-Host "请用机器人号扫码；过期就重新运行 .\scripts\start_napcat_scan.ps1 生成新码。" -ForegroundColor Green
}

Write-Host ""
Write-Host "机器人窗口和 NapCat 窗口保持打开即可；关闭窗口 = 停止对应服务。" -ForegroundColor Green

# 只允许扫码登录：启动 NapCat 前清掉所有免密/快速登录入口
# 用法： .\scripts\start_napcat_scan.ps1
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$napcatDir = Join-Path $root "tools\NapCat"
$logDir = Join-Path $root ".tmp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path (Join-Path $napcatDir "napcat.bat"))) {
    Write-Host "没找到 NapCat，先运行 .\scripts\setup_napcat.ps1" -ForegroundColor Yellow
    exit 1
}

# 1) 清掉快速登录用的环境变量（当前进程和用户级都清）
foreach ($name in @(
    "NAPCAT_QUICK_ACCOUNT",
    "NAPCAT_QUICK_PASSWORD",
    "NAPCAT_QUICK_PASSWORD_MD5"
)) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    [Environment]::SetEnvironmentVariable($name, $null, "User")
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}

# 2) WebUI 里的自动登录账号必须为空，否则 NapCat 会免密登录
$webuiPath = Join-Path $napcatDir "napcat\config\webui.json"
if (Test-Path $webuiPath) {
    try {
        $webui = Get-Content $webuiPath -Raw | ConvertFrom-Json
        if ($webui.PSObject.Properties.Name -contains "autoLoginAccount") {
            if ($webui.autoLoginAccount) {
                Write-Host "已清空 WebUI 自动登录账号：$($webui.autoLoginAccount)" -ForegroundColor Yellow
                $webui.autoLoginAccount = ""
                $json = $webui | ConvertTo-Json -Depth 12
                [System.IO.File]::WriteAllText($webuiPath, $json, [System.Text.UTF8Encoding]::new($false))
            }
        } else {
            $webui | Add-Member -NotePropertyName autoLoginAccount -NotePropertyValue "" -Force
            $json = $webui | ConvertTo-Json -Depth 12
            [System.IO.File]::WriteAllText($webuiPath, $json, [System.Text.UTF8Encoding]::new($false))
        }
    } catch {
        Write-Host "处理 webui.json 失败：$($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 3) 启动 NapCat，不传任何参数（绝不传 -q）
$log = Join-Path $logDir ("napcat-scan-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
$cmd = ".\napcat.bat *> `"$log`" 2>&1"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $cmd -WorkingDirectory $napcatDir -WindowStyle Hidden
Write-Host "NapCat 已启动（仅扫码登录），日志：$log" -ForegroundColor Cyan

# 4) 等二维码出现，复制成唯一文件名，避免看图缓存
$qr = Join-Path $napcatDir "napcat\cache\qrcode.png"
$stamp = Get-Date -Format "HHmmss"
$dest = Join-Path $root "assets\qr-$stamp.png"
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $qr) {
        $age = (Get-Date) - (Get-Item $qr).LastWriteTime
        if ($age.TotalSeconds -lt 90) {
            Copy-Item $qr $dest -Force
            Write-Host "二维码：$dest（约 2 分钟有效，请用机器人号扫描）" -ForegroundColor Green
            exit 0
        }
    }
}
Write-Host "没等到二维码，看日志：$log" -ForegroundColor Yellow
exit 1

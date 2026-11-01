$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$script = Join-Path $PSScriptRoot "autostart.ps1"
$taskName = "QQBot-AutoStart"

# 1) 优先注册计划任务（需要管理员）；不行就退回启动文件夹
$installed = $false
try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
        -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "已注册计划任务：$taskName" -ForegroundColor Green
    $installed = $true
} catch {
    Write-Host "计划任务注册失败（需要管理员）：$($_.Exception.Message)" -ForegroundColor Yellow
}

if (-not $installed) {
    $startup = [Environment]::GetFolderPath("Startup")
    if (-not $startup) {
        $startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    }
    New-Item -ItemType Directory -Force -Path $startup | Out-Null
    $lnkPath = Join-Path $startup "QQBot.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = "powershell.exe"
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
    $lnk.WorkingDirectory = $root
    $lnk.WindowStyle = 7
    $lnk.Description = "Start QQ bot after logon (scan-code login only)"
    $lnk.Save()
    Write-Host "已放入启动文件夹：$lnkPath" -ForegroundColor Green
    $installed = $true
}

if ($installed) {
    Write-Host ""
    Write-Host "开机自启只启动机器人进程；NapCat 不会免密登录，仍需要你扫码。" -ForegroundColor Cyan
}

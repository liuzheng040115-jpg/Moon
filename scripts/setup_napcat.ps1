# 首次安装 NapCat（Windows，自带 Node 的 Shell 版）
# 用法： .\scripts\setup_napcat.ps1
param(
    [string]$InstallDir = (Join-Path $PSScriptRoot "..\tools\NapCat"),
    [string]$Version = "v4.18.41"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$InstallDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($InstallDir)

if (Test-Path (Join-Path $InstallDir "napcat.bat")) {
    Write-Host "NapCat 已安装：$InstallDir" -ForegroundColor Green
    Write-Host "启动： .\tools\NapCat\napcat.bat"
    exit 0
}

# 检查 QQ NT
$qqKey = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ"
$qqExe = $null
if (Test-Path $qqKey) {
    $qqExe = (Get-ItemProperty $qqKey).DisplayIcon -replace ",0$", ""
}
if (-not $qqExe -or -not (Test-Path $qqExe)) {
    Write-Host "警告：没有在注册表里找到 QQ NT。请先安装 QQ 9.9.x 再启动 NapCat。" -ForegroundColor Yellow
} else {
    Write-Host "已找到 QQ：$qqExe" -ForegroundColor Green
}

$zip = Join-Path $env:TEMP "NapCat.Shell.Windows.Node.zip"
$asset = "NapCat.Shell.Windows.Node.zip"
$github = "https://github.com/NapNeko/NapCatQQ/releases/download/$Version/$asset"
$mirrors = @(
    "https://gh-proxy.com/$github",
    $github
)

Write-Host "下载 NapCat $Version ..." -ForegroundColor Cyan
$downloaded = $false
foreach ($url in $mirrors) {
    try {
        Write-Host "  $url"
        & curl.exe -L --retry 2 --connect-timeout 20 --max-time 1800 -o $zip $url
        if ($LASTEXITCODE -eq 0 -and (Test-Path $zip) -and (Get-Item $zip).Length -gt 10MB) {
            $downloaded = $true
            break
        }
    } catch {
        Write-Host "  失败：$($_.Exception.Message)" -ForegroundColor Yellow
    }
}
if (-not $downloaded) { throw "下载失败，请手动下载 $github 后解压到 $InstallDir" }

Write-Host "解压到 $InstallDir ..." -ForegroundColor Cyan
if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
New-Item -ItemType Directory -Force $InstallDir | Out-Null
Expand-Archive -Path $zip -DestinationPath $InstallDir -Force
Remove-Item $zip -Force

Write-Host ""
Write-Host "安装完成。下一步：" -ForegroundColor Green
Write-Host "  1) 启动并扫码： .\tools\NapCat\napcat.bat"
Write-Host "  2) 登录成功后： .\scripts\configure_napcat.ps1"
Write-Host "  3) 机器人：     .\run.ps1"

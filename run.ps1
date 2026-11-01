# 一键启动：缺环境就建 venv、缺依赖就装，然后启动机器人
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot ".venv"
$py   = Join-Path $venv "Scripts\python.exe"
$sp   = Join-Path $venv "Lib\site-packages"

# 1) 建虚拟环境（venv 自带 pip 有时装不上，这里手动铺一份）
if (-not (Test-Path $py)) {
    Write-Host "[1/3] 创建虚拟环境 ..." -ForegroundColor Cyan
    python -m venv $venv
    if (-not (Test-Path (Join-Path $sp "pip"))) {
        Write-Host "      引导 pip ..." -ForegroundColor Cyan
        $pyHome = Split-Path (Get-Command python).Source
        $whl = Get-ChildItem (Join-Path $pyHome "Lib\ensurepip\_bundled") -Filter "pip-*.whl" | Select-Object -First 1
        New-Item -ItemType Directory -Force -Path (Join-Path $venv ".boot") | Out-Null
        $zip = Join-Path $venv ".boot\pip.zip"
        Copy-Item $whl.FullName $zip -Force
        Expand-Archive -Path $zip -DestinationPath $sp -Force
    }
}

# 2) 装依赖（只判断核心包在不在）
if (-not (Test-Path (Join-Path $sp "nonebot"))) {
    Write-Host "[2/3] 安装依赖 ..." -ForegroundColor Cyan
    & $py -m pip install --no-cache-dir -r (Join-Path $PSScriptRoot "requirements.txt")
}

# 3) 检查 Key 再启动
if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $PSScriptRoot ".env")
    Write-Host "已生成 .env：请填入 DEEPSEEK_API_KEY 后重新运行。" -ForegroundColor Yellow
    exit 0
}

$envLine = Select-String -Path (Join-Path $PSScriptRoot ".env") -Pattern '^\s*DEEPSEEK_API_KEY\s*=\s*\S+' -ErrorAction SilentlyContinue
if (-not $envLine) {
    Write-Host "提示：.env 里的 DEEPSEEK_API_KEY 还是空的，机器人起来后会提示未配置。" -ForegroundColor Yellow
}

Write-Host "[3/3] 启动机器人 ..." -ForegroundColor Cyan
& $py bot.py

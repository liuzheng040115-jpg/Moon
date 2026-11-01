# 把项目打成可上传的 tar.gz（排除本机 venv、Windows 版 NapCat、缓存）
# 用法：
#   .\deploy\tencent\pack.ps1                # 不带记忆库
#   .\deploy\tencent\pack.ps1 -IncludeData   # 带 data/bot.db
param(
    [switch]$IncludeData,
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$dist = Join-Path $root "dist"
if (-not $Out) { $Out = Join-Path $dist "qqbot-deploy.tar.gz" }
New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null

$excludes = @(
    "--exclude=./.venv",
    "--exclude=./tools",
    "--exclude=./dist",
    "--exclude=./.tmp",
    "--exclude=./.git",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=*.log"
)
if (-not $IncludeData) { $excludes += "--exclude=./data" }

if (Test-Path $Out) { Remove-Item $Out -Force }

& tar -czf $Out @excludes -C $root .
if ($LASTEXITCODE -ne 0) { throw "tar 打包失败（exit $LASTEXITCODE）" }

$size = "{0:N1} MB" -f ((Get-Item $Out).Length / 1MB)
Write-Host ""
Write-Host "打包完成: $Out  ($size)"
if (-not $IncludeData) { Write-Host "未包含 data/ —— 新机器上记忆是空的，要带走记忆加 -IncludeData" }
Write-Host ""
Write-Host "注意：包里含 .env（API Key / token），别传公开链接。上传："
Write-Host "  scp `"$Out`" ubuntu@<公网IP>:/home/ubuntu/"

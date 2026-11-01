# 持续监视 NapCat 二维码：每次刷新就复制一份带时间戳的大图
# 用法：后台常驻运行，随时取 assets\qr-latest-big.png 或最新时间戳那张
param(
    [int]$IntervalSeconds = 2,
    [string]$Root = (Split-Path $PSScriptRoot)
)
$ErrorActionPreference = "SilentlyContinue"

$src = Join-Path $Root "tools\NapCat\napcat\cache\qrcode.png"
$assets = Join-Path $Root "assets"
$py = Join-Path $Root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $assets | Out-Null

$lastWrite = [datetime]::MinValue

while ($true) {
    if (Test-Path $src) {
        $item = Get-Item $src
        if ($item.LastWriteTime -gt $lastWrite) {
            $lastWrite = $item.LastWriteTime
            $stamp = $lastWrite.ToString("HHmmss")
            $raw = Join-Path $assets "qr-raw-$stamp.png"
            $big = Join-Path $assets "qr-latest-big.png"
            Copy-Item $src $raw -Force

            # 用 venv 的 PIL 放大，失败就原样复制
            & $py -c "from PIL import Image; im=Image.open(r'$raw').convert('RGB'); im.resize((460,460), Image.NEAREST).save(r'$big'); print('ok')" 2>$null
            if (-not (Test-Path $big)) { Copy-Item $raw $big -Force }

            # 同时留一份带时间戳的
            Copy-Item $big (Join-Path $assets "qr-$stamp-big.png") -Force

            $now = Get-Date -Format "HH:mm:ss"
            Add-Content -Path (Join-Path $Root ".tmp\qr-watch.log") -Value "$now  新二维码 $stamp  来源时间 $($lastWrite.ToString('HH:mm:ss'))" -Encoding utf8
        }
    }
    Start-Sleep -Seconds $IntervalSeconds
}

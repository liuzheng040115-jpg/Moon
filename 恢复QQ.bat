@echo off
chcp 65001 >nul
title 恢复 QQ 到旧机器人
echo 正在把 NapCat 的接入方向切回旧机器人（8080）...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\switch-qq-relay.ps1" -Target legacy
echo.
if errorlevel 1 (
    echo [失败] 切换没成功，看上面的报错。
    echo 常见原因：NapCat 没在运行，或 QQ 没登录。
) else (
    echo [完成] 已切回旧机器人。QQ 里正常发消息即可。
)
echo.
pause

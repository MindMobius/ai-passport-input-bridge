@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip install -r companion\requirements-wechat.txt || exit /b 1
if not exist companion\wechat_config.json (
  copy /y companion\wechat_config.example.json companion\wechat_config.json >nul
)
echo.
echo 安装完成。接下来:
echo   1. doctor.cmd       体检(看还缺什么)
echo   2. open-console.cmd 打开控制台 -^> 选通道 -^> 保存并重连
echo   3. 设备: UP 说话 / 任意键结束 / DOWN 粘贴 / OK 发送
pause

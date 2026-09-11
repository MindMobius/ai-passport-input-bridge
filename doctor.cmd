@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe tools\doctor_wechat.py %*
) else (
  echo [!] 还没装依赖,先运行 install.cmd
  python tools\doctor_wechat.py %*
)
pause

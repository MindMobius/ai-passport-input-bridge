@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
.venv\Scripts\python.exe companion\wechat_bridge.py --simulate
pause

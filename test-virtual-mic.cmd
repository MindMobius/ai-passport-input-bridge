@echo off
cd /d "%~dp0\.."
set PYTHONUTF8=1
.venv\Scripts\python.exe tools\test_virtual_mic_loopback.py
pause

@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "tools\mic-level-test.py" %*
pause

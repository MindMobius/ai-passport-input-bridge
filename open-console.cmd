@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "companion\open_console.py" %*
if errorlevel 1 pause

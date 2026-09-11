@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
rem Windows 路径 -> WSL 路径(wslpath):不写死机主目录,换电脑直接可用
for /f "usebackq tokens=*" %%i in (`wsl.exe -e wslpath -a "%PROJECT_DIR%"`) do set "WSL_DIR=%%i"
if "%WSL_DIR%"=="" (
  echo [X] 无法把 "%PROJECT_DIR%" 转成 WSL 路径 —— 确认已装 WSL2 且 wsl.exe 可用
  pause
  exit /b 1
)
rem 换 ESP-IDF 位置:先 set "IDF_DIR=~/esp/esc-idf-xxxx" 再运行本脚本
echo [build] WSL 路径: %WSL_DIR%
wsl.exe -e bash -lc "cd '%WSL_DIR%' && chmod +x tools/build_firmware_wsl.sh && PROJECT_DIR='%WSL_DIR%' ./tools/build_firmware_wsl.sh"
pause

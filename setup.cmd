@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title AI Passport 一键安装

echo ============================================================
echo  AI Passport 一键安装（新电脑跑这一个就够）
echo ============================================================
echo  顺序：找/装 Python -^> 装依赖 -^> 查/装虚拟声卡 -^> 打开控制台
echo.

rem ================= 1/3 Python =================
call :find_python
if defined PY goto :python_ready

echo [1/3] 没找到 Python（或版本低于 3.10），尝试自动安装 ...
where winget >nul 2>nul
if errorlevel 1 goto :python_download
echo       用 winget 安装 Python 3.12（首次约 1 分钟）...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --scope user
call :find_python
if defined PY goto :python_ready

:python_download
echo       winget 不可用或没装上，改为下载官方安装包 ...
set "PYZIP=%TEMP%\python-3.12.8-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile ($env:TEMP+'\python-3.12.8-amd64.exe')}catch{exit 1}"
if not exist "%PYZIP%" (
  echo [XX] 下载失败。请手动安装 Python 3.10+：https://www.python.org/downloads/windows/
  echo      安装时勾选 "Add python.exe to PATH"，然后重跑本脚本。
  pause
  exit /b 1
)
echo       静默安装（仅当前用户，自动写 PATH）...
"%PYZIP%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0
call :find_python
if not defined PY (
  echo [XX] 装完了但本窗口还看不到它（PATH 要新会话）。关掉本窗口，重新双击 setup.cmd 即可。
  pause
  exit /b 1
)

:python_ready
echo [1/3] Python 就绪：%PY%
%PY% -c "import sys;raise SystemExit(0 if sys.version_info<(3,13) else 1)" >nul 2>nul
if errorlevel 1 (
  echo       [!] 这台机器上是 Python 3.13+：部分依赖（pywin32 / bleak-winrt）可能还没有
  echo           对应 wheel，装依赖那一步若失败，装个 Python 3.12 再跑本脚本即可。
)

rem ================= 2/3 依赖 =================
echo [2/3] 安装/检查依赖 ...
call install.cmd nopause
if errorlevel 1 (
  echo [XX] 依赖安装没成功，按上面的提示处理后重跑 setup.cmd。
  pause
  exit /b 1
)

rem ================= 3/3 虚拟声卡 =================
echo [3/3] 检查虚拟声卡 VB-CABLE ...
".venv\Scripts\python.exe" -c "import sounddevice as sd;raise SystemExit(0 if any('cable' in str(d.get('name','')).lower() for d in sd.query_devices()) else 1)" >nul 2>nul
if not errorlevel 1 goto :cable_ok

echo [!] 没检测到 VB-CABLE。没有它，设备的声音进不了输入法，等于没有声音。
choice /c YN /n /m "现在自动下载并安装吗?（会弹一次管理员授权，装完需要重启电脑）[Y/N] "
if errorlevel 2 goto :cable_manual

echo       下载（约 1 MB）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip' -OutFile ($env:TEMP+'\VBCABLE_Driver_Pack43.zip')}catch{exit 1}"
if not exist "%TEMP%\VBCABLE_Driver_Pack43.zip" goto :cable_dl_fail
echo       解压 ...
powershell -NoProfile -Command "try{Expand-Archive -Force ($env:TEMP+'\VBCABLE_Driver_Pack43.zip') ($env:TEMP+'\VBCABLE_pack')}catch{exit 1}"
echo       启动安装程序：请在 UAC 弹窗点“是”，装完重启电脑。
powershell -NoProfile -Command "$f=Get-ChildItem ($env:TEMP+'\VBCABLE_pack') -Recurse -Filter 'VBCABLE_Setup_x64.exe' | Select-Object -First 1; if($f){Start-Process -FilePath $f.FullName -Verb RunAs}else{exit 1}"
if errorlevel 1 goto :cable_dl_fail
echo.
echo 安装程序已启动。装完请【重启电脑】，然后双击 open-console.cmd 使用。
pause
exit /b 0

:cable_dl_fail
echo [XX] 下载或启动安装程序失败（可能被网络/杀软拦了）。
:cable_manual
echo     手动安装：https://vb-audio.com/Cable/
echo       下载 VBCABLE_Setup_x64.exe -^> 右键以管理员身份运行 -^> 装完重启一次电脑
echo     装完后重新双击 setup.cmd（或直接 doctor.cmd 体检）。
pause
exit /b 1

:cable_ok
echo [OK] 虚拟声卡已就绪
echo.
echo 环境齐了，正在打开控制台 ...
start "" "%~dp0open-console.cmd"
exit /b 0

rem ---------------- 子程序：找一个可用的 Python（>=3.10）----------------
rem 顺序刻意"老版本优先":依赖里 pywin32 / bleak(winrt) 在 3.13+ 上不一定有
rem 现成 wheel,3.10~3.12 是实测可用的区间。只有这些都找不到才退回更新的版本。
:find_python
set "PY="
if not defined PY ( py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.10 -c "import sys" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( py -3 -c "import sys" >nul 2>nul && set "PY=py -3" )
if not defined PY (
  for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe" "C:\Python312\python.exe" "C:\Python311\python.exe"
  ) do if not defined PY if exist %%D set "PY=%%~D"
)
if not defined PY exit /b 0
%PY% -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 set "PY="
exit /b 0

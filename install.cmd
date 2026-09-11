@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo  AI Passport 电脑端安装(新电脑只需跑这一次)
echo ============================================================
echo.

rem ---- 1/4 找 Python(PATH 上的 python,或 py 启动器)----
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
  py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo [XX] 没找到 Python。请先安装 Python 3.10 或更高版本:
  echo        https://www.python.org/downloads/windows/
  echo      安装时务必勾选 "Add python.exe to PATH",装完重跑本脚本。
  echo.
  pause
  exit /b 1
)
%PY% -c "import sys;raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [XX] Python 版本过低,需要 3.10 或更高。当前:
  %PY% -c "import sys;print('     ' + sys.version)"
  echo       下载: https://www.python.org/downloads/windows/
  echo.
  pause
  exit /b 1
)
echo [1/4] Python 检查通过:
%PY% -c "import sys;print('      ' + sys.version.split()[0] + '  (' + sys.executable + ')')"

rem ---- 2/4 虚拟环境(整体拷贝过来的 .venv 路径是坏的,必须重建)----
echo [2/4] 准备虚拟环境 .venv ...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import os,sys;raise SystemExit(0 if os.path.normcase(os.path.abspath(sys.prefix))==os.path.normcase(os.path.abspath(r'%~dp0.venv')) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo       [!] 现有 .venv 来自其他电脑（路径对不上），重建中...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [XX] 创建虚拟环境失败。常见原因：Python 安装时没勾选 "Add python.exe to PATH"，
    echo      或磁盘没有写权限。修好后重跑本脚本。
    echo.
    pause
    exit /b 1
  )
  echo       已创建 .venv
)

rem ---- 3/4 依赖(首次 1~2 分钟;之后重跑秒过)----
echo [3/4] 安装依赖(首次约 1~2 分钟,取决于网络)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r companion\requirements-wechat.txt
if errorlevel 1 (
  echo [XX] 依赖安装失败。检查网络后重跑本脚本;公司网络需要代理时先设:
  echo        set HTTPS_PROXY=http://user:pass@proxy:port
  echo      另外:Python 3.13/3.14 上 pywin32 等依赖可能还没有 wheel,
  echo      装个 Python 3.12 再跑本脚本即可（本项目实测区间是 3.10~3.12）。
  echo.
  pause
  exit /b 1
)
rem 装完立刻验一次导入:比"装完看着成功、跑起来报 ModuleNotFound"友好得多
".venv\Scripts\python.exe" -c "import bleak,serial,sounddevice,win32api,comtypes,pycaw,psutil" >nul 2>nul
if errorlevel 1 (
  echo [XX] 依赖已安装但导入失败（常见于 pywin32 未完成注册）。再跑一次本脚本通常即可；
  echo      仍失败请把这条命令的输出发出来:
  echo        .venv\Scripts\python.exe -c "import win32api"
  echo.
  pause
  exit /b 1
)
echo       7 个运行依赖导入正常

rem ---- 4/4 本机配置 ----
echo [4/4] 生成本机配置 ...
if not exist companion\wechat_config.json (
  copy /y companion\wechat_config.example.json companion\wechat_config.json >nul
  echo       已按示例生成 companion\wechat_config.json
) else (
  echo       companion\wechat_config.json 已存在,保留不动
)

rem 顺手看一眼虚拟声卡:新电脑最容易漏的一步,漏了就跑不出声
".venv\Scripts\python.exe" -c "import sounddevice as sd;raise SystemExit(0 if any('cable' in str(d.get('name','')).lower() for d in sd.query_devices()) else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] 还没装虚拟声卡（VB-CABLE）—— 没有它音频进不了输入法。
  echo     已为你打开下载页;下载 VBCABLE_Setup_x64.exe，右键以管理员身份运行，装完重启一次电脑。
  start "" https://vb-audio.com/Cable/
) else (
  echo.
  echo [OK] 虚拟声卡 VB-CABLE 已就绪
)

echo.
echo 安装完成。接下来:
echo   1. 双击 doctor.cmd        -^> 体检。缺什么它会直接说(虚拟声卡/蓝牙/设备)
echo   2. 双击 open-console.cmd  -^> 选通道 -^> 保存并重连
echo   3. 设备上: UP 说话 / 任意键结束 / DOWN 粘贴 / OK 发送
echo.
rem 被 setup.cmd 调用时不停在这里（它后面还有虚拟声卡检查与打开控制台）
if /i "%~1"=="nopause" exit /b 0
echo.
pause

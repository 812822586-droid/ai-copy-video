@echo off
rem AI文案短视频助手 —— 双击即可运行（Windows）
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo    AI文案短视频助手
echo    输入产品名，一键生成小红书文案、短视频和封面
echo ==============================================
echo.

rem 优先使用 py 启动器，其次 python、python3
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY where python3 >nul 2>&1 && set "PY=python3"
if not defined PY (
    echo [错误] 没有找到 Python。
    echo 请先安装 Python 3.10 或更高版本，安装时勾选 “Add python.exe to PATH”。
    echo 下载地址：https://www.python.org/downloads/windows/
    echo.
    pause
    exit /b 1
)

%PY% -c "import PIL,numpy" >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖库（只需这一次，请保持网络畅通）……
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    set "TOPIC="
    set /p TOPIC=请输入产品名或主题（直接回车则使用「护手霜」示例）：
    if not defined TOPIC set "TOPIC=护手霜"
    echo.
    %PY% make.py --topic "%TOPIC%"
) else (
    %PY% make.py %*
)

echo.
pause

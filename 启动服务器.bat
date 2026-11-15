@echo off
rem 双击启动 Python 服务器（方案可保存到服务器，跨平台，任何设备浏览器访问）
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 未找到 python，请先安装 Python 3.10+ 后重试。
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn" >nul 2>nul
if %errorlevel% neq 0 (
    echo 首次运行，正在安装依赖 fastapi / uvicorn ...
    python -m pip install -r requirements.txt
)

python app.py
pause

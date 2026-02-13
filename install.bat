@echo off
chcp 65001 >nul
echo ======================================
echo 视频处理系统安装脚本 (Windows)
echo ======================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未检测到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('python --version') do set PYTHON_VERSION=%%a
echo ✓ Python 版本: %PYTHON_VERSION%

REM 检查 ffmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo 警告: 未检测到 ffmpeg，这是视频处理的必需依赖
    echo 请安装 ffmpeg: https://ffmpeg.org/download.html
    echo.
    set /p CONTINUE="是否继续安装? (y/n) "
    if /i not "%CONTINUE%"=="y" exit /b 1
) else (
    for /f "tokens=3" %%a in ('ffmpeg -version ^| findstr "ffmpeg version"') do echo ✓ ffmpeg 已安装: %%a
)

echo.
echo 正在安装 video-processor...
pip install -e .

REM 创建必要的目录
echo.
echo 创建必要的目录...
if not exist "data\input\mediasource" mkdir "data\input\mediasource"
if not exist "data\output" mkdir "data\output"
if not exist "data\temp" mkdir "data\temp"
if not exist "logs" mkdir "logs"

REM 检查 .env 文件
if not exist .env (
    echo.
    echo 创建配置文件 .env...
    copy .env.example .env
    echo ⚠️  请编辑 .env 文件，填入你的 API 密钥:
    echo    - ALIYUN_ACCESS_KEY_ID
    echo    - ALIYUN_ACCESS_KEY_SECRET
    echo    - ALIYUN_APP_KEY
    echo    - DEEPSEEK_API_KEY
)

echo.
echo ======================================
echo 安装完成!
echo ======================================
echo.
echo 使用方法:
echo   1. 编辑 .env 文件配置 API 密钥
echo   2. 将视频放入 data\input\mediasource\ 目录
echo   3. 运行: video-processor
echo.
echo 或处理指定视频:
echo   video-processor C:\path\to\video.mp4
echo.
echo 启动服务器模式:
echo   video-ws-server  - 启动 WebSocket 服务器
echo   video-server     - 启动 HTTP 服务器
echo.
pause

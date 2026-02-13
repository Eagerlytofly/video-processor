#!/bin/bash
# 视频处理系统安装脚本 (macOS/Linux)

set -e

echo "======================================"
echo "视频处理系统安装脚本"
echo "======================================"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "错误: Python 版本需要 >= 3.9，当前版本: $PYTHON_VERSION"
    exit 1
fi

echo "✓ Python 版本检查通过: $PYTHON_VERSION"

# 检查 ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "警告: 未检测到 ffmpeg，这是视频处理的必需依赖"
    echo "请安装 ffmpeg:"
    echo "  macOS: brew install ffmpeg"
    echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
    echo "  CentOS/RHEL: sudo yum install ffmpeg"
    read -p "是否继续安装? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ ffmpeg 已安装: $(ffmpeg -version | head -1)"
fi

# 检查 ffprobe
if ! command -v ffprobe &> /dev/null; then
    echo "警告: 未检测到 ffprobe"
    echo "通常 ffprobe 与 ffmpeg 一起安装"
fi

# 安装视频处理包
echo ""
echo "正在安装 video-processor..."
pip3 install -e .

# 创建必要的目录
echo ""
echo "创建必要的目录..."
mkdir -p data/input/mediasource
mkdir -p data/output
mkdir -p data/temp
mkdir -p logs

# 检查 .env 文件
if [ ! -f .env ]; then
    echo ""
    echo "创建配置文件 .env..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件，填入你的 API 密钥:"
    echo "   - ALIYUN_ACCESS_KEY_ID"
    echo "   - ALIYUN_ACCESS_KEY_SECRET"
    echo "   - ALIYUN_APP_KEY"
    echo "   - DEEPSEEK_API_KEY"
fi

echo ""
echo "======================================"
echo "安装完成!"
echo "======================================"
echo ""
echo "使用方法:"
echo "  1. 编辑 .env 文件配置 API 密钥"
echo "  2. 将视频放入 data/input/mediasource/ 目录"
echo "  3. 运行: video-processor"
echo ""
echo "或处理指定视频:"
echo "  video-processor /path/to/video.mp4"
echo ""
echo "启动服务器模式:"
echo "  video-ws-server  # 启动 WebSocket 服务器"
echo "  video-server     # 启动 HTTP 服务器"
echo ""
echo "查看帮助:"
echo "  video-processor --help"
echo ""

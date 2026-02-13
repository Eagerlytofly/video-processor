# 安装指南

## 系统要求

- **Python**: 3.9 或更高版本
- **操作系统**: macOS, Linux, Windows
- **ffmpeg**: 必须安装（视频处理依赖）

## 快速安装

### 1. 安装 ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows:**
1. 下载: https://ffmpeg.org/download.html
2. 解压并将 bin 目录添加到系统 PATH

### 2. 安装视频处理系统

#### 方式一：使用安装脚本（推荐）

**macOS/Linux:**
```bash
git clone <repository-url>
cd video-processor
chmod +x install.sh
./install.sh
```

**Windows:**
```cmd
git clone <repository-url>
cd video-processor
install.bat
```

#### 方式二：使用 pip 安装

```bash
# 克隆仓库
git clone <repository-url>
cd video-processor

# 安装
pip install -e .

# 或使用开发模式安装（包含测试工具）
pip install -e ".[dev]"
```

#### 方式三：使用预构建的安装包

```bash
# 下载安装包
# 从 Releases 页面下载 video_processor-1.0.0-py3-none-any.whl

# 安装
pip install video_processor-1.0.0-py3-none-any.whl
```

#### 方式四：使用 Makefile（macOS/Linux）

```bash
# 克隆仓库
git clone <repository-url>
cd video-processor

# 安装
make install

# 或使用开发模式
make install-dev
```

## 配置

### 1. 配置 API 密钥

复制示例配置文件并编辑：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 密钥：

```bash
# 阿里云 OSS（用于 ASR 音频上传）
ALIYUN_ACCESS_KEY_ID=your-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_BUCKET_NAME=your-bucket-name
ALIYUN_ENDPOINT=oss-cn-beijing.aliyuncs.com

# 阿里云 ASR 文件转写
ALIYUN_APP_KEY=your-asr-app-key
ALIYUN_ASR_REGION_ID=cn-shanghai
ALIYUN_ASR_DOMAIN=filetrans.cn-shanghai.aliyuncs.com
ALIYUN_ASR_API_VERSION=2018-08-17

# DeepSeek（转录分析）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### 2. 获取 API 密钥

**阿里云:**
1. 访问 https://www.aliyun.com/
2. 创建 AccessKey
3. 开通 OSS 和智能语音交互服务
4. 创建 ASR 项目获取 App Key

**DeepSeek:**
1. 访问 https://platform.deepseek.com/
2. 注册账号并创建 API Key

## 使用方法

### 命令行处理

```bash
# 处理默认目录中的视频
video-processor

# 处理指定视频
video-processor video.mp4

# 处理多个视频
video-processor video1.mp4 video2.mp4

# 自定义输出目录
video-processor -o /path/to/output video.mp4

# 查看帮助
video-processor --help
```

### 服务器模式

```bash
# 启动 WebSocket 服务器（端口 8000）
video-ws-server

# 启动 HTTP API 服务器（端口 8001）
video-server
```

### 高级选项

```bash
# 仅分析已转录的视频
video-processor --analyze

# 合并已裁剪的视频片段
video-processor --merge

# 为视频添加字幕
video-processor --add-subtitles
```

## 验证安装

```bash
# 检查安装版本
video-processor --version

# 运行测试
make test

# 或
pytest
```

## 卸载

```bash
pip uninstall video-processor
```

## 常见问题

### 1. 找不到 ffmpeg

确保 ffmpeg 已安装并在 PATH 中：
```bash
ffmpeg -version
ffprobe -version
```

### 2. Python 版本不兼容

检查 Python 版本：
```bash
python3 --version  # 需要 >= 3.9
```

### 3. 权限问题

macOS/Linux 上如果遇到权限问题：
```bash
chmod +x install.sh
./install.sh
```

### 4. 依赖安装失败

尝试使用虚拟环境：
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或: venv\Scripts\activate  # Windows
pip install -e .
```

## 构建自己的安装包

```bash
# 安装构建工具
pip install build

# 构建
python -m build

# 生成的安装包在 dist/ 目录
ls dist/
# video_processor-1.0.0-py3-none-any.whl
```

## 目录结构

安装后会创建以下目录：

```
data/
  input/mediasource/   # 放入要处理的视频
  output/              # 处理结果输出
  temp/                # 临时文件
logs/                  # 日志文件
```

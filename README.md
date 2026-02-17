# 视频处理系统

智能视频内容分析和剪辑系统，支持语音识别、AI分析和自动剪辑。

## 安装

### 方式一：使用安装脚本（推荐）

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

### 方式二：使用 pip 安装

```bash
# 克隆仓库
git clone <repository-url>
cd video-processor

# 安装
pip install -e .

# 或使用开发模式安装
pip install -e ".[dev]"
```

### 方式三：构建安装包

```bash
# 安装构建工具
pip install build

# 构建安装包
python -m build

# 安装生成的 wheel 文件
pip install dist/video_processor-1.0.0-py3-none-any.whl
```

## 配置

安装完成后，编辑 `.env` 文件配置 API 密钥：

```bash
# 阿里云 OSS/ASR
ALIYUN_ACCESS_KEY_ID=your-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-access-key-secret
ALIYUN_APP_KEY=your-asr-app-key

# DeepSeek AI
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# AI 分析提示词配置（可选）
# 方式1: 从文件加载自定义提示词
AI_SYSTEM_PROMPT_FILE=/path/to/your/prompt.txt
# 方式2: 直接设置自定义提示词
AI_SYSTEM_PROMPT="你的自定义系统提示词..."
```

### 自定义 AI 分析提示词

系统支持通过环境变量或文件自定义 AI 分析的系统提示词，优先级：
1. `AI_SYSTEM_PROMPT_FILE` - 从指定文件读取
2. `AI_SYSTEM_PROMPT` - 直接使用环境变量值
3. 默认提示词 - 当上述都未配置时使用

默认提示词已包含"去除重复片段"的指令。如果需要调整 AI 分析策略（如重点关注某些内容类型），可以创建自定义提示词文件。

## 使用方法

### 命令行处理

```bash
# 处理默认目录中的视频
video-processor

# 处理指定视频
video-processor video.mp4

# 处理多个视频
video-processor video1.mp4 video2.mp4 video3.mp4

# 自定义输出目录
video-processor -o /path/to/output video.mp4

# 其他选项
video-processor --help
```

### 服务器模式

```bash
# 启动 WebSocket 服务器（端口 8000）
video-ws-server

# 启动 HTTP API 服务器（端口 8001）
video-server
```

### Python API 使用

```python
from app.core.video_processor import VideoProcessor

# 创建处理器
processor = VideoProcessor("output_dir")

# 添加视频
processor.add_video("video.mp4", "/path/to/video.mp4")

# 处理
processor.process_directory()
```

## 项目结构

```
video_processor/
├── run.py                    # 主启动脚本
├── app/                      # 应用核心代码
│   ├── main.py              # 主程序入口
│   ├── requirements.txt     # 依赖列表
│   ├── core/                # 核心业务逻辑
│   │   ├── video_processor.py
│   │   ├── task_manager.py
│   │   └── exceptions.py
│   ├── services/            # 服务层
│   │   ├── http_server.py
│   │   └── websocket_server.py
│   ├── utils/               # 工具模块
│   │   ├── file.py
│   │   ├── logger.py
│   │   └── time.py
│   └── config/              # 配置文件
│       └── config.py
├── data/                    # 数据目录
│   ├── input/              # 输入文件
│   ├── output/             # 输出文件
│   ├── temp/               # 临时文件
│   └── public/             # 公共文件
├── docs/                   # 文档
│   └── QUICK_START.md
├── logs/                   # 日志文件
└── scripts/               # 脚本文件
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r app/requirements.txt
```

### 2. 启动服务
```bash
# 启动WebSocket服务器
python app/services/websocket_server.py

# 启动HTTP服务器
python run.py --server
```

### 3. 处理视频
```bash
# 命令行处理
python run.py

# 或使用服务模式
python run.py --server
```

## 功能特性

- 🎥 视频转录与分析
- 🤖 AI智能内容分析
- ✂️ 智能视频剪辑
- 📝 字幕生成
- 🌐 Web API接口
- 🔌 WebSocket实时通信

## 技术栈

- Python 3.12+
- FastAPI (HTTP服务)
- WebSockets (实时通信)
- MoviePy (视频处理)
- 阿里云ASR (语音识别)
- DeepSeek AI (内容分析)

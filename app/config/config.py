"""
视频处理配置文件
所有密钥类配置从环境变量读取，请勿在代码中硬编码。
支持两种命名风格：ALIYUN_* / DEEPSEEK_* 与 OSS_* / ASR_*（后者为兼容旧名）。
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 目录与格式
TEMP_DIR = os.getenv("TEMP_DIR", "temp")
CUTS_DIR = os.getenv("CUTS_DIR", "cuts")

# 支持的视频格式（可通过环境变量扩展，用逗号分隔）
DEFAULT_VIDEO_FORMATS = (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v")
_extra_formats = os.getenv("EXTRA_VIDEO_FORMATS", "")
if _extra_formats:
    SUPPORTED_VIDEO_FORMATS = DEFAULT_VIDEO_FORMATS + tuple(f.strip() for f in _extra_formats.split(",") if f.strip())
else:
    SUPPORTED_VIDEO_FORMATS = DEFAULT_VIDEO_FORMATS

# 阿里云 OSS（用于 ASR 音频上传）
OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID") or os.getenv("ALIYUN_ACCESS_KEY_ID")
OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET") or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
OSS_BUCKET_NAME = os.getenv("OSS_BUCKET_NAME") or os.getenv("ALIYUN_BUCKET_NAME", "mediacut")
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT") or os.getenv("ALIYUN_ENDPOINT", "oss-cn-beijing.aliyuncs.com")

# 阿里云 ASR 文件转写
ASR_APP_KEY = os.getenv("ASR_APP_KEY") or os.getenv("ALIYUN_APP_KEY")
ASR_REGION_ID = os.getenv("ASR_REGION_ID") or os.getenv("ALIYUN_ASR_REGION_ID", "cn-shanghai")
ASR_PRODUCT = "nls-filetrans"
ASR_DOMAIN = os.getenv("ALIYUN_ASR_DOMAIN") or os.getenv("ASR_DOMAIN", "filetrans.cn-shanghai.aliyuncs.com")
ASR_API_VERSION = os.getenv("ALIYUN_ASR_API_VERSION") or os.getenv("ASR_API_VERSION", "2018-08-17")

# DeepSeek（转录分析）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 任务管理器配置
TASK_MANAGER_CONFIG = {
    "max_concurrent_tasks": int(os.getenv("MAX_CONCURRENT_TASKS", "3")),
    "task_timeout": int(os.getenv("TASK_TIMEOUT", "600")),  # 默认10分钟
}

# ASR 配置
ASR_CONFIG = {
    "max_poll_retries": int(os.getenv("ASR_MAX_POLL_RETRIES", "180")),  # 最大轮询次数
    "poll_interval": int(os.getenv("ASR_POLL_INTERVAL", "10")),  # 轮询间隔（秒）
}

VIDEO_PROCESS_CONFIG = {
    "clip": {
        "max_gap": float(os.getenv("CLIP_MAX_GAP", "5.0")),
        "min_duration": float(os.getenv("CLIP_MIN_DURATION", "5.0")),
        "adjacent_gap": float(os.getenv("CLIP_ADJACENT_GAP", "2.0")),  # 合并相邻片段的间隔
        "end_padding": float(os.getenv("CLIP_END_PADDING", "1.0")),  # 片段结束时间增加的秒数
    },
    "ai": {
        "api_key": os.getenv("AI_API_KEY"),
        "base_url": os.getenv("AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "timeout": int(os.getenv("AI_TIMEOUT", "120")),  # AI API 超时（秒）
        "fallback_on_error": os.getenv("AI_FALLBACK_ON_ERROR", "true").lower() == "true",  # 失败时降级
    },
    "output": {
        "transcript_file": os.getenv("OUTPUT_TRANSCRIPT_FILE", "merged_transcripts.txt"),
        "video_file": os.getenv("OUTPUT_VIDEO_FILE", "merged_highlights.mp4"),
        "cleanup_cuts": os.getenv("CLEANUP_CUTS", "true").lower() == "true",  # 合并后清理片段
    },
    "video": {
        "max_file_size_mb": int(os.getenv("MAX_VIDEO_FILE_SIZE_MB", "0")),  # 0 表示不限制
        "use_ffmpeg_for_large_files": os.getenv("USE_FFMPEG_FOR_LARGE_FILES", "true").lower() == "true",
        "large_file_threshold_mb": int(os.getenv("LARGE_FILE_THRESHOLD_MB", "500")),
    },
}
"""
从视频中提取音频，支持 MoviePy 与 ffmpeg 两种方式。
"""

import logging
import os
import subprocess

from moviepy import VideoFileClip

from utils.time import seconds_to_time

logger = logging.getLogger(__name__)

# 阿里云 ASR 推荐：16kHz
AUDIO_FPS = 16000
AUDIO_CODEC = "libmp3lame"
AUDIO_BITRATE = "160k"


def extract_audio(video_path: str, output_path: str) -> str:
    """
    从视频提取音频为 MP3。
    优先使用 MoviePy，失败时回退到 ffmpeg。
    返回 output_path。
    """
    try:
        video = VideoFileClip(video_path)
        if video.audio is None:
            logger.warning("视频没有音轨: %s", video_path)
            video.close()
            return None
        video.audio.write_audiofile(
            output_path,
            fps=AUDIO_FPS,
            nbytes=2,
            codec=AUDIO_CODEC,
            bitrate=AUDIO_BITRATE,
        )
        video.close()
        return output_path
    except Exception as e:
        logger.warning("MoviePy 提取音频失败，尝试 ffmpeg: %s", e)
        extract_audio_ffmpeg(video_path, output_path)
        return output_path


def extract_audio_ffmpeg(video_path: str, output_path: str) -> None:
    """使用 ffmpeg 提取音频，16kHz 单声道以符合阿里云 ASR 要求。"""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", str(AUDIO_FPS),
            "-ac", "1",
            "-ab", AUDIO_BITRATE,
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(
            "ffmpeg 提取音频失败 (exit %s): %s\nstderr: %s",
            result.returncode, video_path, result.stderr or result.stdout or "",
        )
        result.check_returncode()
    logger.info("ffmpeg 提取音频成功: %s -> %s", video_path, output_path)


def format_time_for_display(seconds: float) -> str:
    """将秒数格式化为 [HH:MM:SS.mmm] 显示用。"""
    return seconds_to_time(seconds)

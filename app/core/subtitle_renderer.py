"""
为视频添加字幕：提取音频 -> ASR -> 生成字幕轨道 -> 合成输出。
"""

import logging
import os

from moviepy import VideoFileClip, TextClip, CompositeVideoClip

from core.audio_extractor import extract_audio
from core.asr_client import ASRClient

logger = logging.getLogger(__name__)

# 按平台回退：macOS -> Linux 常见路径 -> Windows
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _subtitle_font() -> str:
    """返回首个存在的字幕字体路径，避免非 macOS 下写死 Hiragino 失败。"""
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    # 不指定 font，交给 ImageMagick/ffmpeg 默认（可能无中文）
    logger.warning("未找到候选字体，使用默认 font=None")
    return None


def add_subtitles(
    video_path: str,
    output_dir: str,
    output_basename: str | None = None,
    asr_client: ASRClient | None = None,
    temp_dir: str | None = None,
) -> str:
    """
    为 video_path 添加字幕，输出到 output_dir。
    output_basename 为输出文件名（不含路径），默认 merged_highlights_with_subtitles.mp4。
    返回输出文件路径。
    """
    if asr_client is None:
        asr_client = ASRClient()
    base = os.path.splitext(os.path.basename(video_path))[0]
    temp_dir = temp_dir or os.path.join(output_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    audio_path = os.path.join(temp_dir, f"{base}_subtitle_audio.mp3")

    logger.info("提取音频用于字幕: %s", video_path)
    extract_audio(video_path, audio_path)
    if not os.path.exists(audio_path):
        raise RuntimeError("无法提取音频")

    url, _ = asr_client.upload_to_oss(audio_path)
    task_id = asr_client.submit_task(url)
    result = asr_client.get_result(task_id)
    if not result or "Sentences" not in result:
        raise RuntimeError("ASR 未返回有效结果")

    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except Exception:
        pass

    subtitles = []
    for s in result.get("Sentences", []):
        subtitles.append({
            "start": s.get("BeginTime", 0) / 1000,
            "end": s.get("EndTime", 0) / 1000,
            "text": s.get("Text", ""),
        })

    try:
        video = VideoFileClip(video_path)
    except Exception as e:
        logger.error("MoviePy 无法打开视频（若为 HEVC/MOV 可尝试先转码）: %s", e)
        raise
    font_path = _subtitle_font()
    text_clip_kw = {
        "font_size": 48,
        "color": "white",
        "size": (int(video.w * 0.8), int(video.h * 0.2)),
        "text_align": "center",
        "method": "caption",
    }
    if font_path:
        text_clip_kw["font"] = font_path
    subtitle_clips = []
    for sub in subtitles:
        duration = max(sub["end"] - sub["start"], 0.1)
        text_clip = (
            TextClip(
                text=sub["text"],
                **text_clip_kw,
            )
            .with_position(("center", "bottom"))
            .with_duration(duration)
            .with_start(sub["start"])
        )
        subtitle_clips.append(text_clip)

    final = CompositeVideoClip([video] + subtitle_clips)
    out_name = output_basename or (base + "_with_subtitles.mp4")
    out_path = os.path.join(output_dir, out_name)
    final.write_videofile(out_path, codec="libx264", audio_codec="aac", audio=True)
    video.close()
    final.close()
    logger.info("字幕已写入: %s", out_path)
    return out_path

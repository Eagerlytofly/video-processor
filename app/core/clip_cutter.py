"""
视频片段裁剪与合并：按 clip_order.txt 切条并合并为成片。
MoviePy 对部分 iPhone/HEVC MOV 解析会失败，此时回退到 ffmpeg 裁剪。
"""

import glob
import logging
import os
import re
import subprocess

from moviepy import VideoFileClip, concatenate_videoclips

from utils.time import seconds_to_time, time_to_seconds
from config.config import VIDEO_PROCESS_CONFIG

logger = logging.getLogger(__name__)


def _get_duration_sec(video_path: str) -> float | None:
    """获取视频时长（秒），失败返回 None。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def _cut_segment_ffmpeg(video_path: str, start_sec: float, end_sec: float, out_path: str) -> bool:
    """用 ffmpeg 裁剪一段视频，兼容 HEVC/MOV 等。"""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-ss", str(start_sec),
                "-to", str(end_sec),
                "-c", "copy",
                "-avoid_negative_ts", "1",
                out_path,
            ],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning("ffmpeg 裁剪失败: %s", e)
        return False

def _get_file_size_mb(file_path: str) -> float | None:
    """获取文件大小（MB），失败返回 None。"""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except (OSError, FileNotFoundError):
        return None


# 从配置读取或使用默认值
_clip_config = VIDEO_PROCESS_CONFIG.get("clip", {})
CLIP_ORDER_FILENAME = "clip_order.txt"
MERGED_VIDEO_FILENAME = VIDEO_PROCESS_CONFIG.get("output", {}).get("video_file", "merged_highlights.mp4")
ADJACENT_GAP_SECONDS = _clip_config.get("adjacent_gap", 2)
END_PADDING_SECONDS = _clip_config.get("end_padding", 1)


def get_video_path(video_paths: dict, filename: str) -> str | None:
    """根据文件名（可含扩展名）在 video_paths 中匹配并返回完整路径。"""
    base = os.path.splitext(filename)[0]
    for name, path in video_paths.items():
        if os.path.splitext(name)[0] == base:
            logger.info("匹配视频: %s -> %s", filename, path)
            return path
    logger.error("未找到视频映射: %s", filename)
    return None


def merge_adjacent_clips(clips_info: list) -> list:
    """
    合并同文件且间隔 <= ADJACENT_GAP_SECONDS 的相邻片段，
    并对 end_time 增加 END_PADDING_SECONDS。
    不改变片段之间的先后顺序（仅合并同视频的相邻段），以保证与大模型返回顺序一致。
    """
    if not clips_info:
        return []

    merged = []
    current = dict(clips_info[0])
    i = 1
    while i < len(clips_info):
        next_clip = clips_info[i]
        if current["video"] == next_clip["video"]:
            cur_end = time_to_seconds(current["end_time"])
            next_start = time_to_seconds(next_clip["start_time"])
            if next_start - cur_end <= ADJACENT_GAP_SECONDS:
                current["end_time"] = next_clip["end_time"]
                logger.info("合并相邻片段: %s %s - %s", current["video"], current["start_time"], current["end_time"])
                i += 1
                continue
        _pad_end(current)
        merged.append(current)
        current = dict(next_clip)
        i += 1
    _pad_end(current)
    merged.append(current)
    return merged


def _pad_end(clip: dict) -> None:
    """给 end_time 增加 END_PADDING_SECONDS。"""
    end_sec = time_to_seconds(clip["end_time"]) + END_PADDING_SECONDS
    clip["end_time"] = seconds_to_time(end_sec)


def _parse_time(time_str: str) -> float:
    """解析时间字符串为秒数。"""
    try:
        return time_to_seconds(time_str)
    except ValueError:
        return -1


def validate_clip_order(clips_info: list, video_durations: dict) -> tuple[bool, list]:
    """
    验证剪辑顺序的合理性。

    Returns:
        (is_valid, errors): 是否有效，错误信息列表
    """
    errors = []

    if not clips_info:
        return True, []

    for i, clip in enumerate(clips_info):
        video_name = clip["video"]
        start_time = _parse_time(clip["start_time"])
        end_time = _parse_time(clip["end_time"])
        duration = video_durations.get(video_name)

        # 验证时间格式
        if start_time < 0:
            errors.append(f"片段 {i+1}: 开始时间格式无效 '{clip['start_time']}'")
            continue
        if end_time < 0:
            errors.append(f"片段 {i+1}: 结束时间格式无效 '{clip['end_time']}'")
            continue

        # 验证时间逻辑
        if start_time >= end_time:
            errors.append(f"片段 {i+1}: 开始时间({clip['start_time']})必须小于结束时间({clip['end_time']})")

        # 验证是否超出视频长度
        if duration is not None:
            if start_time > duration:
                errors.append(f"片段 {i+1}: 开始时间({clip['start_time']})超过视频长度({seconds_to_time(duration)})")
            if end_time > duration + 1:  # 允许 1 秒容差
                errors.append(f"片段 {i+1}: 结束时间({clip['end_time']})超过视频长度({seconds_to_time(duration)})")

    # 检查同视频片段重叠
    video_clips = {}
    for i, clip in enumerate(clips_info):
        video_name = clip["video"]
        if video_name not in video_clips:
            video_clips[video_name] = []
        video_clips[video_name].append((i, _parse_time(clip["start_time"]), _parse_time(clip["end_time"])))

    for video_name, clips in video_clips.items():
        # 按开始时间排序检查重叠
        sorted_clips = sorted(clips, key=lambda x: x[1])
        for j in range(len(sorted_clips) - 1):
            idx1, start1, end1 = sorted_clips[j]
            idx2, start2, end2 = sorted_clips[j + 1]
            if end1 > start2:
                errors.append(f"片段 {idx1+1} 和片段 {idx2+1} 在 '{video_name}' 上时间重叠")

    return len(errors) == 0, errors


def process_clips(
    output_dir: str,
    cuts_dir: str,
    video_paths: dict,
) -> None:
    """
    读取 output_dir/clip_order.txt，按文件中的行顺序（即大模型返回顺序）合并相邻片段后裁剪到 cuts_dir。
    不重排序，保证成片顺序与大模型返回顺序一致。
    """
    order_path = os.path.join(output_dir, CLIP_ORDER_FILENAME)
    if not os.path.exists(order_path):
        logger.error("找不到剪辑顺序文件: %s", order_path)
        return

    # 严格按 clip_order 文件行顺序构建列表，不排序
    clips_info = []
    with open(order_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) != 3:
                logger.warning("跳过无效行: %s", line.strip())
                continue
            video_name, start_time, end_time = parts
            path = get_video_path(video_paths, video_name)
            if not path:
                logger.warning("未找到视频映射，跳过: %s", video_name)
                continue
            clips_info.append({
                "video": video_name,
                "video_path": path,
                "start_time": start_time,
                "end_time": end_time,
            })

    if not clips_info:
        logger.error("clip_order.txt 中没有有效的剪辑片段")
        return

    # 获取所有视频的时长用于验证
    video_durations = {}
    for clip in clips_info:
        video_name = clip["video"]
        if video_name not in video_durations:
            duration = _get_duration_sec(clip["video_path"])
            if duration:
                video_durations[video_name] = duration

    # 验证剪辑顺序
    is_valid, errors = validate_clip_order(clips_info, video_durations)
    if not is_valid:
        logger.error("剪辑顺序验证失败:")
        for error in errors:
            logger.error("  - %s", error)
        raise ValueError(f"clip_order.txt 验证失败: {'; '.join(errors)}")

    logger.info("剪辑顺序验证通过，共 %d 个片段", len(clips_info))

    merged_clips = merge_adjacent_clips(clips_info)
    os.makedirs(cuts_dir, exist_ok=True)

    # 获取所有视频的时长用于验证
    video_durations = {}
    for clip in clips_info:
        video_name = clip["video"]
        if video_name not in video_durations:
            duration = _get_duration_sec(clip["video_path"])
            if duration:
                video_durations[video_name] = duration

    # 验证剪辑顺序
    is_valid, errors = validate_clip_order(clips_info, video_durations)
    if not is_valid:
        logger.error("剪辑顺序验证失败:")
        for error in errors:
            logger.error("  - %s", error)
        raise ValueError(f"clip_order.txt 验证失败: {'; '.join(errors)}")

    logger.info("剪辑顺序验证通过，共 %d 个片段", len(clips_info))

    merged_clips = merge_adjacent_clips(clips_info)
    os.makedirs(cuts_dir, exist_ok=True)

    # 大文件阈值（MB），从配置读取
    large_file_threshold_mb = VIDEO_PROCESS_CONFIG.get("video", {}).get("large_file_threshold_mb", 500)
    use_ffmpeg_for_large = VIDEO_PROCESS_CONFIG.get("video", {}).get("use_ffmpeg_for_large_files", True)

    success_count = 0
    for i, clip in enumerate(merged_clips):
        out_path = os.path.join(cuts_dir, f"clip_{i + 1}.mp4")
        logger.info("裁剪片段: %s -> %s", clip["video"], out_path)
        start_sec = time_to_seconds(clip["start_time"])
        end_sec = time_to_seconds(clip["end_time"])
        video_path = clip["video_path"]

        # 检查文件大小，大文件使用 ffmpeg 直接裁剪以节省内存
        file_size_mb = _get_file_size_mb(video_path)
        if file_size_mb and file_size_mb > large_file_threshold_mb:
            logger.info("文件较大 (%.1f MB)，使用 ffmpeg 直接裁剪以节省内存: %s", file_size_mb, video_path)
            use_ffmpeg_first = True
        else:
            use_ffmpeg_first = use_ffmpeg_for_large and file_size_mb and file_size_mb > 100

        duration = _get_duration_sec(video_path)
        if duration is not None:
            if start_sec >= duration:
                logger.warning("片段开始时间超过视频长度: %s %s", clip["video"], start_sec)
                continue
            end_sec = min(end_sec, duration)
        ok = False

        if use_ffmpeg_first:
            # 大文件优先使用 ffmpeg
            ok = _cut_segment_ffmpeg(video_path, start_sec, end_sec, out_path)
            if not ok:
                logger.warning("ffmpeg 裁剪失败，尝试 MoviePy: %s", video_path)

        if not ok:
            try:
                video = VideoFileClip(video_path)
                dur = video.duration
                if end_sec > dur:
                    end_sec = dur
                if start_sec >= dur:
                    logger.warning("片段开始时间超过视频长度: %s %s", clip["video"], start_sec)
                    video.close()
                    continue
                sub = video.subclipped(start_sec, end_sec)
                sub.write_videofile(out_path)
                sub.close()
                video.close()
                ok = True
            except Exception as e:
                if not use_ffmpeg_first:
                    logger.warning("MoviePy 裁剪失败，尝试 ffmpeg: %s", e)
                    ok = _cut_segment_ffmpeg(video_path, start_sec, end_sec, out_path)
                else:
                    logger.error("ffmpeg 和 MoviePy 都裁剪失败: %s", e)
        if ok:
            success_count += 1
        else:
            logger.error("裁剪失败: %s", out_path)
    logger.info("已成功裁剪 %d/%d 个片段", success_count, len(merged_clips))


def merge_video_clips(
    cuts_dir: str,
    output_dir: str,
    output_filename: str = MERGED_VIDEO_FILENAME,
    cleanup_cuts: bool = False,
) -> str | None:
    """
    将 cuts_dir 下 clip_1.mp4, clip_2.mp4, ... 按序合并，
    输出到 output_dir/output_filename。返回输出文件路径。

    Args:
        cleanup_cuts: 合并成功后是否清理 cuts_dir 中的中间片段
    """
    if not os.path.exists(cuts_dir):
        logger.error("片段目录不存在: %s", cuts_dir)
        return None

    pattern = os.path.join(cuts_dir, "clip_*.mp4")
    files = glob.glob(pattern)
    files.sort(key=lambda p: int(re.search(r"clip_(\d+)\.mp4", os.path.basename(p)).group(1)))
    if not files:
        logger.error("未找到片段文件")
        return None

    logger.info("合并 %d 个片段", len(files))
    out_path = os.path.join(output_dir, output_filename)
    try:
        clips = []
        for p in files:
            clips.append(VideoFileClip(p))
        final = concatenate_videoclips(clips)
        final.write_videofile(out_path, codec="libx264", audio_codec="aac", audio=True)
        final.close()
        for c in clips:
            c.close()
        logger.info("合并完成: %s", out_path)

        # 清理中间片段
        if cleanup_cuts:
            _cleanup_cuts_dir(cuts_dir)

        return out_path
    except Exception as e:
        logger.warning("MoviePy 合并失败，尝试 ffmpeg concat: %s", e)
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
    # ffmpeg concat 回退（兼容 HEVC/MOV 等 MoviePy 解析失败的情况）
    list_path = os.path.join(output_dir, ".concat_list.txt")
    with open(list_path, "w") as f:
        for p in files:
            # 路径中单引号转义为 '\''
            abs_p = os.path.abspath(p).replace("'", "'\\''")
            f.write(f"file '{abs_p}'\n")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                out_path,
            ],
            check=True,
            capture_output=True,
        )
        try:
            os.remove(list_path)
        except OSError:
            pass
        logger.info("合并完成(ffmpeg): %s", out_path)

        # 清理中间片段
        if cleanup_cuts:
            _cleanup_cuts_dir(cuts_dir)

        return out_path
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error("合并视频失败: %s", e)
        raise


def _cleanup_cuts_dir(cuts_dir: str) -> None:
    """清理 cuts 目录中的中间片段文件"""
    if not os.path.exists(cuts_dir):
        return

    pattern = os.path.join(cuts_dir, "clip_*.mp4")
    files = glob.glob(pattern)
    removed = 0
    for f in files:
        try:
            os.remove(f)
            removed += 1
        except OSError as e:
            logger.warning(f"清理片段失败: {f}, {e}")

    logger.info(f"已清理 {removed} 个中间片段")

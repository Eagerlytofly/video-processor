"""片段裁剪与合并逻辑测试（不依赖真实视频）。"""
import pytest
from core.clip_cutter import get_video_path, merge_adjacent_clips


def test_get_video_path():
    paths = {"a.mp4": "/path/to/a.mp4", "b": "/path/to/b.mov"}
    assert get_video_path(paths, "a.mp4") == "/path/to/a.mp4"
    assert get_video_path(paths, "a") == "/path/to/a.mp4"
    assert get_video_path(paths, "b") == "/path/to/b.mov"
    assert get_video_path(paths, "c.mp4") is None
    assert get_video_path({}, "a") is None


def test_merge_adjacent_clips_empty():
    assert merge_adjacent_clips([]) == []


def test_merge_adjacent_clips_single():
    clips = [{"video": "v1", "start_time": "00:00:00.000", "end_time": "00:00:05.000"}]
    merged = merge_adjacent_clips(clips)
    assert len(merged) == 1
    # end_time 会被加上 1 秒 padding
    assert merged[0]["end_time"] == "00:00:06.000"


def test_merge_adjacent_clips_same_video_adjacent():
    """同文件且间隔<=2秒应合并为一段。"""
    clips = [
        {"video": "v1", "start_time": "00:00:00.000", "end_time": "00:00:05.000"},
        {"video": "v1", "start_time": "00:00:06.000", "end_time": "00:00:10.000"},  # 间隔 1 秒
    ]
    merged = merge_adjacent_clips(clips)
    assert len(merged) == 1
    assert merged[0]["end_time"] == "00:00:11.000"  # 10 + 1 padding


def test_merge_adjacent_clips_different_videos():
    clips = [
        {"video": "v1", "start_time": "00:00:00.000", "end_time": "00:00:05.000"},
        {"video": "v2", "start_time": "00:00:00.000", "end_time": "00:00:03.000"},
    ]
    merged = merge_adjacent_clips(clips)
    assert len(merged) == 2
    assert merged[0]["video"] == "v1"
    assert merged[1]["video"] == "v2"

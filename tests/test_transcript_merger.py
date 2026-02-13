"""转录合并与 AI 解析逻辑测试。"""
import json
import os
import tempfile
import pytest
from core.transcript_merger import merge_transcripts
from core.ai_analyzer import _parse_analysis_to_clip_order


def test_merge_transcripts_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = tempfile.mkdtemp(dir=tmp)
        result = merge_transcripts(tmp, out)
        assert result == ""
        assert not os.path.exists(os.path.join(out, "merged_transcripts.txt"))


def test_merge_transcripts_single_file():
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = os.path.join(tmp, "temp")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(out_dir, exist_ok=True)
        transcript = [
            {"start_time": 0, "end_time": 1, "text": "你好", "start_time_formatted": "00:00:00.000", "end_time_formatted": "00:00:01.000"},
        ]
        path = os.path.join(temp_dir, "v1_transcript.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False)
        result = merge_transcripts(temp_dir, out_dir)
        merged_path = os.path.join(out_dir, "merged_transcripts.txt")
        assert result == merged_path
        assert os.path.exists(merged_path)
        content = open(merged_path, encoding="utf-8").read()
        assert "=== v1 ===" in content
        assert "[00:00:00.000 - 00:00:01.000] 你好" in content


def test_parse_analysis_to_clip_order():
    text = """
=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一句
[00:00:06.000 - 00:00:10.000] 第二句
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 另一段
"""
    clips = _parse_analysis_to_clip_order(text)
    assert len(clips) == 3
    assert clips[0]["video"] == "video1.mp4" and clips[0]["start_time"] == "00:00:00.000" and clips[0]["end_time"] == "00:00:05.000"
    assert clips[1]["video"] == "video1.mp4"
    assert clips[2]["video"] == "video2.mp4"
    assert clips[2]["start_time"] == "00:00:00.000"

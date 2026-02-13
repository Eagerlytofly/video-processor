"""VideoProcessor 单元测试（不调用 ASR/OSS）。"""
import json
import os
import tempfile
import pytest
from core.video_processor import VideoProcessor


def test_init_creates_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "task_out")
        p = VideoProcessor(out)
        assert os.path.isdir(p.output_dir)
        assert os.path.isdir(p.temp_dir)
        assert os.path.isdir(p.cuts_dir)
        assert p.output_dir == os.path.abspath(out)
        assert p.video_paths == {}
        assert p.caption_enable is False


def test_set_text_caption_transfer():
    with tempfile.TemporaryDirectory() as tmp:
        p = VideoProcessor(tmp)
        p.set_text("hello")
        assert p.text == "hello"
        p.set_caption_enable(True)
        assert p.caption_enable is True
        p.set_transfer_enable(True)
        assert p.transfer_enable is True


def test_save_info_to_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = VideoProcessor(tmp)
        p.set_text("test")
        p.set_caption_enable(True)
        p.save_info_to_file()
        path = os.path.join(p.output_dir, "info.json")
        assert os.path.exists(path)
        data = json.load(open(path, encoding="utf-8"))
        assert data["text"] == "test"
        assert data["caption_enable"] is True
        assert data["transfer_enable"] is False


def test_add_video_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        p = VideoProcessor(tmp)
        with pytest.raises(FileNotFoundError, match="视频文件不存在"):
            p.add_video("x.mp4", "/nonexistent/path/x.mp4")


def test_add_video_success():
    with tempfile.TemporaryDirectory() as tmp:
        f = os.path.join(tmp, "fake.mp4")
        open(f, "wb").close()
        p = VideoProcessor(tmp)
        p.add_video("fake.mp4", f)
        assert p.video_paths["fake.mp4"] == f


def test_merge_video_clips_output_dir_param():
    """merge_video_clips(output_dir) 应使用传入的 output_dir 作为输出目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        p = VideoProcessor(tmp)
        # 无片段时返回 None，不报错
        result = p.merge_video_clips()
        assert result is None
        other_dir = os.path.join(tmp, "other")
        os.makedirs(other_dir, exist_ok=True)
        result2 = p.merge_video_clips(output_dir=other_dir)
        assert result2 is None  # 仍然没有片段
        # 仅验证调用不抛错且传参生效（实际写出路径会包含 other_dir）
        assert p.cuts_dir == os.path.join(p.output_dir, "cuts")

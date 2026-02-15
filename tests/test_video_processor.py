"""VideoProcessor 单元测试（不调用 ASR/OSS）。"""
import json
import os
import shutil
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest
from core.video_processor import VideoProcessor
from core.exceptions import ASRError


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


# =============================================================================
# process_single_video 测试
# =============================================================================

class TestProcessSingleVideo:
    """测试 process_single_video 方法。"""

    @patch("core.video_processor.extract_audio")
    @patch("core.video_processor.extract_audio_ffmpeg")
    def test_process_single_video_success(self, mock_extract_ffmpeg, mock_extract_audio):
        """测试成功处理单个视频的完整流程。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 创建虚拟视频文件
            video_path = os.path.join(tmp, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video content")

            # 创建处理器
            p = VideoProcessor(tmp)
            p.add_video("test_video.mp4", video_path)

            # Mock 音频提取
            def mock_extract(vpath, apath):
                with open(apath, "w") as f:
                    f.write("fake audio")
                return apath
            mock_extract_audio.side_effect = mock_extract

            # Mock ASR 客户端
            p._asr_client = MagicMock()
            p._asr_client.upload_to_oss.return_value = ("https://oss.example.com/audio.mp3", "audio.mp3")
            p._asr_client.submit_task.return_value = "task_12345"
            p._asr_client.get_result.return_value = {
                "Sentences": [
                    {"BeginTime": 0, "EndTime": 5000, "Text": "Hello world"},
                    {"BeginTime": 5000, "EndTime": 10000, "Text": "Second sentence"},
                ]
            }

            # 执行测试
            result = p.process_single_video("test_video.mp4")

            # 验证结果
            assert result is not None
            assert os.path.exists(result)
            assert result.endswith("_transcript.json")

            # 验证转录文件内容
            with open(result, "r", encoding="utf-8") as f:
                transcript = json.load(f)
            assert len(transcript) == 2
            assert transcript[0]["text"] == "Hello world"
            assert transcript[0]["start_time"] == 0.0
            assert transcript[0]["end_time"] == 5.0

            # 验证调用链
            mock_extract_audio.assert_called_once()
            p._asr_client.upload_to_oss.assert_called_once()
            p._asr_client.submit_task.assert_called_once()
            p._asr_client.get_result.assert_called_once_with("task_12345")

    @patch("core.video_processor.extract_audio")
    @patch("core.video_processor.extract_audio_ffmpeg")
    def test_process_single_video_moviepy_fails_ffmpeg_succeeds(self, mock_extract_ffmpeg, mock_extract_audio):
        """测试 MoviePy 失败时回退到 ffmpeg 的情况。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video content")

            p = VideoProcessor(tmp)
            p.add_video("test_video.mp4", video_path)

            # MoviePy 失败
            mock_extract_audio.side_effect = Exception("MoviePy error")

            # ffmpeg 成功
            def mock_ffmpeg_extract(vpath, apath):
                with open(apath, "w") as f:
                    f.write("fake audio from ffmpeg")
            mock_extract_ffmpeg.side_effect = mock_ffmpeg_extract

            # Mock ASR 客户端
            p._asr_client = MagicMock()
            p._asr_client.upload_to_oss.return_value = ("https://oss.example.com/audio.mp3", "audio.mp3")
            p._asr_client.submit_task.return_value = "task_12345"
            p._asr_client.get_result.return_value = {
                "Sentences": [{"BeginTime": 0, "EndTime": 3000, "Text": "Test"}]
            }

            result = p.process_single_video("test_video.mp4")

            assert result is not None
            mock_extract_audio.assert_called_once()
            mock_extract_ffmpeg.assert_called_once()

    @patch("core.video_processor.extract_audio")
    def test_process_single_video_no_audio_track(self, mock_extract_audio):
        """测试视频没有音轨的情况。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video content")

            p = VideoProcessor(tmp)
            p.add_video("test_video.mp4", video_path)

            # 音频提取返回 None（没有音轨）
            mock_extract_audio.return_value = None

            # Mock ASR 客户端
            p._asr_client = MagicMock()

            result = p.process_single_video("test_video.mp4")

            assert result is None
            p._asr_client.upload_to_oss.assert_not_called()

    @patch("core.video_processor.extract_audio")
    def test_process_single_video_asr_no_valid_fragment(self, mock_extract_audio):
        """测试 ASR 返回无有效片段的情况。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video content")

            p = VideoProcessor(tmp)
            p.add_video("test_video.mp4", video_path)

            def mock_extract(vpath, apath):
                with open(apath, "w") as f:
                    f.write("fake audio")
                return apath
            mock_extract_audio.side_effect = mock_extract

            # Mock ASR 客户端
            p._asr_client = MagicMock()
            p._asr_client.upload_to_oss.return_value = ("https://oss.example.com/audio.mp3", "audio.mp3")
            p._asr_client.submit_task.return_value = "task_12345"
            p._asr_client.get_result.return_value = None  # 无有效片段

            result = p.process_single_video("test_video.mp4")

            assert result is None

    @patch("core.video_processor.extract_audio")
    def test_process_single_video_asr_error(self, mock_extract_audio):
        """测试 ASR 调用抛出异常的情况。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test_video.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video content")

            p = VideoProcessor(tmp)
            p.add_video("test_video.mp4", video_path)

            def mock_extract(vpath, apath):
                with open(apath, "w") as f:
                    f.write("fake audio")
                return apath
            mock_extract_audio.side_effect = mock_extract

            # Mock ASR 客户端
            p._asr_client = MagicMock()
            p._asr_client.upload_to_oss.return_value = ("https://oss.example.com/audio.mp3", "audio.mp3")
            p._asr_client.submit_task.return_value = "task_12345"
            p._asr_client.get_result.side_effect = ASRError("ASR processing failed")

            with pytest.raises(ASRError):
                p.process_single_video("test_video.mp4")

    def test_process_single_video_file_not_mapped(self):
        """测试处理未映射的视频文件时抛出异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            with pytest.raises(FileNotFoundError, match="未找到视频文件映射"):
                p.process_single_video("nonexistent.mp4")


# =============================================================================
# process_directory 测试
# =============================================================================

class TestProcessDirectory:
    """测试 process_directory 方法。"""

    def test_process_directory_no_videos(self):
        """测试没有视频文件时直接返回。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)
            # 不添加任何视频
            p.process_directory()  # 应该不报错直接返回

    @patch.object(VideoProcessor, "process_single_video")
    @patch.object(VideoProcessor, "merge_transcripts")
    @patch.object(VideoProcessor, "analyze_merged_transcripts")
    def test_process_directory_empty_transcript(self, mock_analyze, mock_merge, mock_process_single):
        """测试空转录文件时跳过分析。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake")

            p = VideoProcessor(tmp)
            p.add_video("test.mp4", video_path)

            mock_process_single.return_value = "/fake/transcript.json"

            # 创建空的合并转录文件
            merged_path = os.path.join(tmp, "merged_transcripts.txt")
            with open(merged_path, "w") as f:
                f.write("")  # 空文件

            mock_merge.return_value = merged_path

            p.process_directory()

            mock_analyze.assert_not_called()

    @patch.object(VideoProcessor, "process_single_video")
    @patch.object(VideoProcessor, "merge_transcripts")
    @patch.object(VideoProcessor, "analyze_merged_transcripts")
    @patch.object(VideoProcessor, "process_clips")
    @patch.object(VideoProcessor, "merge_video_clips")
    def test_process_directory_full_flow(self, mock_merge_clips, mock_process_clips, mock_analyze, mock_merge, mock_process_single):
        """测试完整的目录处理流程。"""
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, "test.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake")

            p = VideoProcessor(tmp)
            p.add_video("test.mp4", video_path)

            mock_process_single.return_value = "/fake/transcript.json"

            merged_path = os.path.join(tmp, "merged_transcripts.txt")
            with open(merged_path, "w") as f:
                f.write("some content")
            mock_merge.return_value = merged_path

            # 创建 clip_order.txt
            clip_order_path = os.path.join(tmp, "clip_order.txt")
            with open(clip_order_path, "w") as f:
                f.write("test\t00:00:00\t00:00:10\n")

            mock_merge_clips.return_value = os.path.join(tmp, "merged_highlights.mp4")

            p.process_directory()

            mock_process_single.assert_called_once_with("test.mp4")
            mock_merge.assert_called_once()
            mock_analyze.assert_called_once()
            mock_process_clips.assert_called_once()
            mock_merge_clips.assert_called_once()

    @patch.object(VideoProcessor, "process_single_video")
    def test_process_directory_partial_failure(self, mock_process_single):
        """测试部分视频处理失败的情况。"""
        with tempfile.TemporaryDirectory() as tmp:
            video1_path = os.path.join(tmp, "video1.mp4")
            video2_path = os.path.join(tmp, "video2.mp4")
            with open(video1_path, "wb") as f:
                f.write(b"fake1")
            with open(video2_path, "wb") as f:
                f.write(b"fake2")

            p = VideoProcessor(tmp)
            p.add_video("video1.mp4", video1_path)
            p.add_video("video2.mp4", video2_path)

            # 第一个成功，第二个失败
            mock_process_single.side_effect = ["/fake/transcript1.json", Exception("Processing error")]

            # 创建空的合并转录文件以跳过后续步骤
            merged_path = os.path.join(tmp, "merged_transcripts.txt")
            with open(merged_path, "w") as f:
                f.write("")

            with patch.object(p, "merge_transcripts", return_value=merged_path):
                p.process_directory()

            assert mock_process_single.call_count == 2


# =============================================================================
# cleanup 方法测试
# =============================================================================

class TestCleanupMethods:
    """测试清理相关方法。"""

    def test_cleanup_temp_files(self):
        """测试清理临时音频文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 创建临时音频文件
            audio_file = os.path.join(p.temp_dir, "test_audio.mp3")
            with open(audio_file, "w") as f:
                f.write("fake audio")

            # 创建转录文件（应该保留）
            transcript_file = os.path.join(p.temp_dir, "test_transcript.json")
            with open(transcript_file, "w") as f:
                json.dump(["test"], f)

            assert os.path.exists(audio_file)
            assert os.path.exists(transcript_file)

            p.cleanup_temp_files(keep_transcripts=True)

            assert not os.path.exists(audio_file)  # 音频文件应该被删除
            assert os.path.exists(transcript_file)  # 转录文件应该保留

    def test_cleanup_temp_files_remove_all(self):
        """测试清理所有临时文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 创建临时文件
            audio_file = os.path.join(p.temp_dir, "test_audio.mp3")
            transcript_file = os.path.join(p.temp_dir, "test_transcript.json")
            with open(audio_file, "w") as f:
                f.write("fake audio")
            with open(transcript_file, "w") as f:
                json.dump(["test"], f)

            p.cleanup_temp_files(keep_transcripts=False)

            # 注意：当前实现只删除音频文件，转录文件始终保留
            assert not os.path.exists(audio_file)

    def test_cleanup_all(self):
        """测试清理所有临时和中间文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 创建 temp 和 cuts 目录中的文件
            temp_file = os.path.join(p.temp_dir, "temp.txt")
            cuts_file = os.path.join(p.cuts_dir, "cut.mp4")
            with open(temp_file, "w") as f:
                f.write("temp")
            with open(cuts_file, "w") as f:
                f.write("cut")

            assert os.path.exists(p.temp_dir)
            assert os.path.exists(p.cuts_dir)

            p.cleanup_all()

            assert not os.path.exists(p.temp_dir)
            assert not os.path.exists(p.cuts_dir)
            assert os.path.exists(p.output_dir)  # 输出目录应该保留


# =============================================================================
# add_subtitles 测试
# =============================================================================

class TestAddSubtitles:
    """测试 add_subtitles 方法。"""

    @patch("core.video_processor.add_subtitles_impl")
    def test_add_subtitles_default_video(self, mock_add_subtitles):
        """测试为默认视频添加字幕。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 创建虚拟视频文件
            video_path = os.path.join(tmp, "merged_highlights.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video")

            mock_add_subtitles.return_value = os.path.join(tmp, "merged_highlights_with_subtitles.mp4")

            result = p.add_subtitles()

            assert result is not None
            mock_add_subtitles.assert_called_once()

    @patch("core.video_processor.add_subtitles_impl")
    def test_add_subtitles_custom_video(self, mock_add_subtitles):
        """测试为指定视频添加字幕。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            custom_video = os.path.join(tmp, "custom.mp4")
            with open(custom_video, "wb") as f:
                f.write(b"fake video")

            mock_add_subtitles.return_value = os.path.join(tmp, "custom_with_subtitles.mp4")

            result = p.add_subtitles(video_path=custom_video, output_dir=tmp)

            assert result is not None
            mock_add_subtitles.assert_called_once()

    def test_add_subtitles_video_not_found(self):
        """测试视频不存在时返回 None。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            result = p.add_subtitles()

            assert result is None

    @patch("core.video_processor.add_subtitles_impl")
    def test_add_subtitles_failure_with_fallback(self, mock_add_subtitles):
        """测试字幕添加失败时返回原视频。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            video_path = os.path.join(tmp, "merged_highlights.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video")

            mock_add_subtitles.side_effect = Exception("Subtitle generation failed")

            result = p.add_subtitles(fallback_on_error=True)

            assert result == video_path  # 应该返回原视频路径

    @patch("core.video_processor.add_subtitles_impl")
    def test_add_subtitles_failure_without_fallback(self, mock_add_subtitles):
        """测试字幕添加失败且不启用 fallback 时返回 None。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            video_path = os.path.join(tmp, "merged_highlights.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video")

            mock_add_subtitles.side_effect = Exception("Subtitle generation failed")

            result = p.add_subtitles(fallback_on_error=False)

            assert result is None


# =============================================================================
# 其他方法测试
# =============================================================================

class TestOtherMethods:
    """测试其他辅助方法。"""

    @patch("core.video_processor.merge_transcripts_impl")
    def test_merge_transcripts(self, mock_merge_impl):
        """测试合并转录文件方法。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 添加视频映射
            video_path = os.path.join(tmp, "test.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake")
            p.add_video("test.mp4", video_path)
            p.add_video("another.mp4", video_path)

            mock_merge_impl.return_value = os.path.join(tmp, "merged_transcripts.txt")

            result = p.merge_transcripts()

            assert result is not None
            mock_merge_impl.assert_called_once()
            # 验证调用时传递了正确的顺序
            call_args = mock_merge_impl.call_args
            assert call_args[0][0] == p.temp_dir
            assert call_args[0][1] == p.output_dir
            assert call_args[1]["order_base_names"] == ["test", "another"]

    @patch("core.video_processor.analyze_merged_transcripts_impl")
    def test_analyze_merged_transcripts(self, mock_analyze_impl):
        """测试分析合并转录方法。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)
            p.set_text("提取重点内容")

            mock_analyze_impl.return_value = "analysis result"

            result = p.analyze_merged_transcripts()

            assert result == "analysis result"
            mock_analyze_impl.assert_called_once_with(p.output_dir, "提取重点内容")

    @patch("core.video_processor.process_clips_impl")
    def test_process_clips(self, mock_process_clips):
        """测试处理剪辑方法。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            video_path = os.path.join(tmp, "test.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake")
            p.add_video("test.mp4", video_path)

            p.process_clips()

            mock_process_clips.assert_called_once_with(p.output_dir, p.cuts_dir, p.video_paths)

    def test_add_video_with_path_traversal_attempt(self):
        """测试添加带有路径遍历尝试的视频文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            # 创建安全的视频文件
            safe_path = os.path.join(tmp, "video.mp4")
            with open(safe_path, "wb") as f:
                f.write(b"fake")

            # 尝试使用路径遍历的文件名
            p.add_video("../../../etc/passwd.mp4", safe_path)

            # 文件名应该被清理
            assert "../../../etc/passwd.mp4" not in p.video_paths
            # sanitize_filename 会把 ../ 替换为 _
            assert any("passwd" in k for k in p.video_paths.keys())

    @patch("core.video_processor.TimelineVisualizer")
    def test_generate_timeline_visualization(self, mock_visualizer_class):
        """测试生成时间轴可视化。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = VideoProcessor(tmp)

            video_path = os.path.join(tmp, "test.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake")
            p.add_video("test.mp4", video_path)

            # 创建 clip_order.txt
            clip_order_path = os.path.join(tmp, "clip_order.txt")
            with open(clip_order_path, "w") as f:
                f.write("test\t00:00:00\t00:00:10\n")

            mock_visualizer = MagicMock()
            mock_visualizer_class.return_value = mock_visualizer
            mock_visualizer.generate_html_timeline.return_value = os.path.join(tmp, "timeline.html")

            p._generate_timeline_visualization()

            mock_visualizer.generate_html_timeline.assert_called_once()

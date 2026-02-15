"""AudioExtractor 单元测试（Mock MoviePy 和 ffmpeg）。"""
import os
import subprocess
import pytest
from unittest.mock import Mock, patch, MagicMock

from core.audio_extractor import (
    extract_audio,
    extract_audio_ffmpeg,
    format_time_for_display,
    AUDIO_FPS,
    AUDIO_CODEC,
    AUDIO_BITRATE,
)


class TestExtractAudio:
    """测试 extract_audio 函数 - 主提取函数（使用 MoviePy，失败时回退到 ffmpeg）。"""

    @patch("core.audio_extractor.VideoFileClip")
    def test_extract_audio_success_with_moviepy(self, mock_video_file_clip):
        """测试 MoviePy 成功提取音频的情况。"""
        # Arrange: 设置 Mock 视频对象
        mock_video = MagicMock()
        mock_video.audio = MagicMock()  # 视频有音轨
        mock_video_file_clip.return_value = mock_video

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act: 调用提取函数
        result = extract_audio(video_path, output_path)

        # Assert: 验证结果
        assert result == output_path
        mock_video_file_clip.assert_called_once_with(video_path)
        mock_video.audio.write_audiofile.assert_called_once_with(
            output_path,
            fps=AUDIO_FPS,
            nbytes=2,
            codec=AUDIO_CODEC,
            bitrate=AUDIO_BITRATE,
        )
        mock_video.close.assert_called_once()

    @patch("core.audio_extractor.VideoFileClip")
    def test_extract_audio_no_audio_track(self, mock_video_file_clip):
        """测试视频没有音轨的情况，应返回 None。"""
        # Arrange: 设置 Mock 视频对象，audio 为 None
        mock_video = MagicMock()
        mock_audio = MagicMock()
        mock_video.audio = None  # 无音轨
        mock_video_file_clip.return_value = mock_video

        video_path = "/fake/video_no_audio.mp4"
        output_path = "/fake/output.mp3"

        # Act: 调用提取函数
        result = extract_audio(video_path, output_path)

        # Assert: 验证返回 None 且关闭视频
        assert result is None
        mock_video_file_clip.assert_called_once_with(video_path)
        mock_video.close.assert_called_once()

    @patch("core.audio_extractor.extract_audio_ffmpeg")
    @patch("core.audio_extractor.VideoFileClip")
    def test_extract_audio_moviepy_falls_back_to_ffmpeg(self, mock_video_file_clip, mock_extract_ffmpeg):
        """测试 MoviePy 失败时回退到 ffmpeg 的情况。"""
        # Arrange: 设置 MoviePy 抛出异常
        mock_video_file_clip.side_effect = Exception("MoviePy error")

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act: 调用提取函数
        result = extract_audio(video_path, output_path)

        # Assert: 验证回退到 ffmpeg 且返回输出路径
        assert result == output_path
        mock_video_file_clip.assert_called_once_with(video_path)
        mock_extract_ffmpeg.assert_called_once_with(video_path, output_path)

    @patch("core.audio_extractor.extract_audio_ffmpeg")
    @patch("core.audio_extractor.VideoFileClip")
    def test_extract_audio_moviepy_falls_back_with_audio_none_error(self, mock_video_file_clip, mock_extract_ffmpeg):
        """测试 MoviePy 因 AttributeError 失败时回退到 ffmpeg。"""
        # Arrange: 设置 MoviePy 抛出 AttributeError（某些视频格式可能导致）
        mock_video_file_clip.side_effect = AttributeError("'NoneType' object has no attribute 'write_audiofile'")

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act: 调用提取函数
        result = extract_audio(video_path, output_path)

        # Assert: 验证回退到 ffmpeg
        assert result == output_path
        mock_extract_ffmpeg.assert_called_once_with(video_path, output_path)


class TestExtractAudioFfmpeg:
    """测试 extract_audio_ffmpeg 函数 - 使用 ffmpeg 提取音频。"""

    @patch("core.audio_extractor.subprocess.run")
    def test_extract_audio_ffmpeg_success(self, mock_subprocess_run):
        """测试 ffmpeg 成功提取音频的情况。"""
        # Arrange: 设置 subprocess.run 返回成功结果
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = ""
        mock_subprocess_run.return_value = mock_result

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act: 调用 ffmpeg 提取函数
        extract_audio_ffmpeg(video_path, output_path)

        # Assert: 验证 subprocess.run 被正确调用
        mock_subprocess_run.assert_called_once()
        call_args = mock_subprocess_run.call_args

        # 验证命令参数
        expected_cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", str(AUDIO_FPS),
            "-ac", "1",
            "-ab", AUDIO_BITRATE,
            output_path,
        ]
        assert call_args[0][0] == expected_cmd

        # 验证关键字参数
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["text"] is True

    @patch("core.audio_extractor.subprocess.run")
    def test_extract_audio_ffmpeg_failure_raises_exception(self, mock_subprocess_run):
        """测试 ffmpeg 失败时抛出异常的情况。"""
        # Arrange: 设置 subprocess.run 返回失败结果
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: Invalid data found when processing input"
        mock_result.stdout = ""
        mock_result.check_returncode = Mock(side_effect=subprocess.CalledProcessError(1, "ffmpeg"))
        mock_subprocess_run.return_value = mock_result

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act & Assert: 验证抛出 CalledProcessError
        with pytest.raises(subprocess.CalledProcessError):
            extract_audio_ffmpeg(video_path, output_path)

    @patch("core.audio_extractor.subprocess.run")
    def test_extract_audio_ffmpeg_failure_with_stdout(self, mock_subprocess_run):
        """测试 ffmpeg 失败时 stderr 为空但有 stdout 的情况。"""
        # Arrange: 设置 subprocess.run 返回失败结果，stderr 为空但 stdout 有内容
        mock_result = Mock()
        mock_result.returncode = 127
        mock_result.stderr = ""
        mock_result.stdout = "ffmpeg: command not found"
        mock_result.check_returncode = Mock(side_effect=subprocess.CalledProcessError(127, "ffmpeg"))
        mock_subprocess_run.return_value = mock_result

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act & Assert: 验证抛出异常
        with pytest.raises(subprocess.CalledProcessError):
            extract_audio_ffmpeg(video_path, output_path)


class TestFormatTimeForDisplay:
    """测试 format_time_for_display 函数 - 时间格式化。"""

    def test_format_time_zero_seconds(self):
        """测试 0 秒格式化。"""
        result = format_time_for_display(0)
        assert result == "00:00:00.000"

    def test_format_time_seconds_only(self):
        """测试只有秒数的情况。"""
        result = format_time_for_display(45.5)
        assert result == "00:00:45.500"

    def test_format_time_minutes_and_seconds(self):
        """测试分钟和秒数。"""
        result = format_time_for_display(125.75)
        assert result == "00:02:05.750"

    def test_format_time_hours_minutes_seconds(self):
        """测试小时、分钟和秒数。"""
        result = format_time_for_display(3661.123)
        assert result == "01:01:01.123"

    def test_format_time_large_value(self):
        """测试大数值（超过一天）。"""
        result = format_time_for_display(90061.999)
        assert result == "25:01:01.999"


class TestIntegrationScenarios:
    """集成场景测试 - 模拟完整的提取流程。"""

    @patch("core.audio_extractor.subprocess.run")
    @patch("core.audio_extractor.VideoFileClip")
    def test_full_flow_moviepy_success(self, mock_video_file_clip, mock_subprocess_run):
        """测试完整流程：MoviePy 成功，不调用 ffmpeg。"""
        # Arrange
        mock_video = MagicMock()
        mock_video.audio = MagicMock()
        mock_video_file_clip.return_value = mock_video

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act
        result = extract_audio(video_path, output_path)

        # Assert
        assert result == output_path
        mock_video.audio.write_audiofile.assert_called_once()
        mock_subprocess_run.assert_not_called()  # ffmpeg 不应被调用

    @patch("core.audio_extractor.subprocess.run")
    @patch("core.audio_extractor.VideoFileClip")
    def test_full_flow_moviepy_fail_ffmpeg_success(self, mock_video_file_clip, mock_subprocess_run):
        """测试完整流程：MoviePy 失败，ffmpeg 成功。"""
        # Arrange: MoviePy 失败
        mock_video_file_clip.side_effect = OSError("MoviePy cannot open file")

        # ffmpeg 成功
        mock_result = Mock()
        mock_result.returncode = 0
        mock_subprocess_run.return_value = mock_result

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act
        result = extract_audio(video_path, output_path)

        # Assert
        assert result == output_path
        mock_subprocess_run.assert_called_once()

    @patch("core.audio_extractor.subprocess.run")
    @patch("core.audio_extractor.VideoFileClip")
    def test_full_flow_both_fail(self, mock_video_file_clip, mock_subprocess_run):
        """测试完整流程：MoviePy 和 ffmpeg 都失败。"""
        # Arrange: MoviePy 失败
        mock_video_file_clip.side_effect = Exception("MoviePy error")

        # ffmpeg 失败
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.check_returncode = Mock(side_effect=subprocess.CalledProcessError(1, "ffmpeg"))
        mock_subprocess_run.return_value = mock_result

        video_path = "/fake/video.mp4"
        output_path = "/fake/output.mp3"

        # Act & Assert
        with pytest.raises(subprocess.CalledProcessError):
            extract_audio(video_path, output_path)

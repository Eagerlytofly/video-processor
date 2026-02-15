"""subtitle_renderer 单元测试（全部 Mock，不依赖真实视频/字体）。"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from core.subtitle_renderer import _subtitle_font, add_subtitles, FONT_CANDIDATES


class TestSubtitleFont:
    """测试 _subtitle_font 函数 - 字体路径查找逻辑。"""

    @patch("core.subtitle_renderer.os.path.isfile")
    def test_returns_first_existing_font(self, mock_isfile):
        """测试返回首个存在的字体路径。"""
        # Arrange: 只有第二个字体存在
        def isfile_side_effect(path):
            return path == FONT_CANDIDATES[1]
        mock_isfile.side_effect = isfile_side_effect

        # Act
        result = _subtitle_font()

        # Assert
        assert result == FONT_CANDIDATES[1]
        mock_isfile.assert_any_call(FONT_CANDIDATES[0])
        mock_isfile.assert_any_call(FONT_CANDIDATES[1])

    @patch("core.subtitle_renderer.os.path.isfile")
    def test_returns_none_when_no_font_exists(self, mock_isfile):
        """测试当没有字体存在时返回 None。"""
        # Arrange: 所有字体都不存在
        mock_isfile.return_value = False

        # Act
        result = _subtitle_font()

        # Assert
        assert result is None
        assert mock_isfile.call_count == len(FONT_CANDIDATES)

    @patch("core.subtitle_renderer.os.path.isfile")
    def test_returns_macos_hiragino_first(self, mock_isfile):
        """测试 macOS Hiragino 字体优先返回。"""
        # Arrange: 只有第一个字体存在
        mock_isfile.side_effect = lambda path: path == FONT_CANDIDATES[0]

        # Act
        result = _subtitle_font()

        # Assert
        assert result == FONT_CANDIDATES[0]

    @patch("core.subtitle_renderer.os.path.isfile")
    def test_returns_linux_font_when_available(self, mock_isfile):
        """测试 Linux 字体路径返回。"""
        # Arrange: Linux 字体存在
        linux_font = "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"

        def isfile_side_effect(path):
            return path == linux_font

        mock_isfile.side_effect = isfile_side_effect

        # Act
        result = _subtitle_font()

        # Assert
        assert result == linux_font

    @patch("core.subtitle_renderer.os.path.isfile")
    def test_returns_windows_font_when_available(self, mock_isfile):
        """测试 Windows 字体路径返回。"""
        # Arrange: Windows 字体存在
        windows_font = "C:\\Windows\\Fonts\\msyh.ttc"

        def isfile_side_effect(path):
            return path == windows_font

        mock_isfile.side_effect = isfile_side_effect

        # Act
        result = _subtitle_font()

        # Assert
        assert result == windows_font


class TestAddSubtitles:
    """测试 add_subtitles 函数 - 字幕添加主流程。"""

    @pytest.fixture
    def mock_asr_client(self):
        """创建 Mock ASRClient。"""
        client = Mock()
        client.upload_to_oss.return_value = ("http://oss.example.com/audio.mp3", None)
        client.submit_task.return_value = "task_12345"
        client.get_result.return_value = {
            "Sentences": [
                {"BeginTime": 0, "EndTime": 2000, "Text": "第一句话"},
                {"BeginTime": 2000, "EndTime": 5000, "Text": "第二句话"},
            ]
        }
        return client

    @pytest.fixture
    def mock_video_clip(self):
        """创建 Mock VideoFileClip。"""
        video = Mock()
        video.w = 1920
        video.h = 1080
        video.close = Mock()
        return video

    @pytest.fixture
    def mock_text_clip(self):
        """创建 Mock TextClip。"""
        text_clip = Mock()
        text_clip.with_position.return_value = text_clip
        text_clip.with_duration.return_value = text_clip
        text_clip.with_start.return_value = text_clip
        return text_clip

    @pytest.fixture
    def mock_composite_clip(self):
        """创建 Mock CompositeVideoClip。"""
        composite = Mock()
        composite.write_videofile = Mock()
        composite.close = Mock()
        return composite

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_add_subtitles_success(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        mock_text_clip,
        mock_composite_clip,
        tmp_path,
    ):
        """测试正常字幕添加流程成功。"""
        # Arrange
        mock_subtitle_font.return_value = "/fake/font.ttf"
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = mock_text_clip
        mock_composite_class.return_value = mock_composite_clip
        mock_exists.return_value = True  # 音频文件存在

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        result = add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert
        # 1. 验证音频提取被调用
        mock_extract_audio.assert_called_once()
        assert "video.mp4" in mock_extract_audio.call_args[0][0]

        # 2. 验证 ASR 流程
        mock_asr_client.upload_to_oss.assert_called_once()
        mock_asr_client.submit_task.assert_called_once_with("http://oss.example.com/audio.mp3")
        mock_asr_client.get_result.assert_called_once_with("task_12345")

        # 3. 验证音频清理
        mock_remove.assert_called_once()

        # 4. 验证视频处理
        mock_video_class.assert_called_once_with(video_path)

        # 5. 验证 TextClip 创建（应该创建 2 个字幕片段）
        assert mock_text_class.call_count == 2
        # 检查 TextClip 参数
        call_kwargs = mock_text_class.call_args[1]
        assert call_kwargs["font_size"] == 48
        assert call_kwargs["color"] == "white"
        assert call_kwargs["font"] == "/fake/font.ttf"

        # 6. 验证 CompositeVideoClip 创建
        mock_composite_class.assert_called_once()

        # 7. 验证视频写入
        mock_composite_clip.write_videofile.assert_called_once()
        assert "video_with_subtitles.mp4" in result

        # 8. 验证资源释放
        mock_video_clip.close.assert_called_once()
        mock_composite_clip.close.assert_called_once()

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    def test_audio_extraction_failure(
        self,
        mock_extract_audio,
        mock_makedirs,
        mock_exists,
        mock_asr_client,
        tmp_path,
    ):
        """测试音频提取失败时抛出异常。"""
        # Arrange: 音频文件不存在
        mock_exists.return_value = False

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act & Assert
        with pytest.raises(RuntimeError, match="无法提取音频"):
            add_subtitles(
                video_path=video_path,
                output_dir=output_dir,
                asr_client=mock_asr_client,
            )

        # 验证提取音频被调用
        mock_extract_audio.assert_called_once()
        # 验证 ASR 没有被调用
        mock_asr_client.upload_to_oss.assert_not_called()

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    def test_asr_returns_no_sentences(
        self,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        tmp_path,
    ):
        """测试 ASR 返回结果中没有 Sentences 时抛出异常。"""
        # Arrange
        mock_exists.return_value = True
        mock_asr_client.get_result.return_value = {"Status": "Success"}  # 没有 Sentences

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act & Assert
        with pytest.raises(RuntimeError, match="ASR 未返回有效结果"):
            add_subtitles(
                video_path=video_path,
                output_dir=output_dir,
                asr_client=mock_asr_client,
            )

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    def test_asr_returns_empty_result(
        self,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        tmp_path,
    ):
        """测试 ASR 返回空结果时抛出异常。"""
        # Arrange
        mock_exists.return_value = True
        mock_asr_client.get_result.return_value = None

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act & Assert
        with pytest.raises(RuntimeError, match="ASR 未返回有效结果"):
            add_subtitles(
                video_path=video_path,
                output_dir=output_dir,
                asr_client=mock_asr_client,
            )

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    def test_video_open_failure(
        self,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        tmp_path,
    ):
        """测试视频文件无法打开时抛出异常。"""
        # Arrange
        mock_exists.return_value = True
        mock_video_class.side_effect = Exception("无法解码视频")

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act & Assert
        with pytest.raises(Exception, match="无法解码视频"):
            add_subtitles(
                video_path=video_path,
                output_dir=output_dir,
                asr_client=mock_asr_client,
            )

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_uses_default_basename(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试使用默认输出文件名。"""
        # Arrange
        mock_subtitle_font.return_value = None  # 无字体
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        video_path = "/path/to/my_video.mp4"
        output_dir = str(tmp_path)

        # Act
        result = add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: 默认使用 {basename}_with_subtitles.mp4
        assert "my_video_with_subtitles.mp4" in result

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_custom_output_basename(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试自定义输出文件名。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)
        custom_basename = "custom_output.mp4"

        # Act
        result = add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            output_basename=custom_basename,
            asr_client=mock_asr_client,
        )

        # Assert
        assert result == os.path.join(output_dir, custom_basename)

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_no_font_uses_none(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试无可用字体时不传递 font 参数。"""
        # Arrange
        mock_subtitle_font.return_value = None  # 无字体
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: TextClip 调用时不包含 font 参数
        call_kwargs = mock_text_class.call_args[1]
        assert "font" not in call_kwargs
        assert call_kwargs["font_size"] == 48
        assert call_kwargs["color"] == "white"

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_creates_temp_dir_if_not_exists(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试自动创建临时目录。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: 创建 temp 目录
        mock_makedirs.assert_called()
        # 验证调用中包含 temp 目录路径
        call_args_list = mock_makedirs.call_args_list
        assert any("temp" in str(call) for call in call_args_list)

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_subtitle_timing_calculation(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试字幕时间计算正确（毫秒转秒）。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip

        # Mock TextClip 链式调用 - 需要正确设置链式返回值
        text_clip_instance = MagicMock()
        text_clip_instance.with_position.return_value = text_clip_instance
        text_clip_instance.with_duration.return_value = text_clip_instance
        text_clip_instance.with_start.return_value = text_clip_instance
        mock_text_class.return_value = text_clip_instance

        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        # 设置 ASR 返回特定时间
        mock_asr_client.get_result.return_value = {
            "Sentences": [
                {"BeginTime": 1000, "EndTime": 3500, "Text": "测试字幕"},
            ]
        }

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: 验证 TextClip 的 with_start 被调用，且时间为秒
        text_clip_instance.with_start.assert_called_once_with(1.0)  # 1000ms = 1s
        # duration 应该是 2.5s (3500-1000)/1000 = 2.5
        text_clip_instance.with_duration.assert_called_once_with(2.5)

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_minimum_duration_enforced(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试最小持续时间被强制执行（至少 0.1 秒）。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip

        # Mock TextClip 链式调用 - 需要正确设置链式返回值
        text_clip_instance = MagicMock()
        text_clip_instance.with_position.return_value = text_clip_instance
        text_clip_instance.with_duration.return_value = text_clip_instance
        text_clip_instance.with_start.return_value = text_clip_instance
        mock_text_class.return_value = text_clip_instance

        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        # 设置 ASR 返回极短时间（小于 0.1 秒）
        mock_asr_client.get_result.return_value = {
            "Sentences": [
                {"BeginTime": 1000, "EndTime": 1050, "Text": "短"},
            ]
        }

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: 持续时间应该被限制为最小 0.1 秒
        text_clip_instance.with_duration.assert_called_once_with(0.1)

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_creates_asr_client_if_none_provided(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_video_clip,
        tmp_path,
    ):
        """测试未提供 asr_client 时自动创建。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        with patch("core.subtitle_renderer.ASRClient") as mock_asr_class:
            mock_asr_instance = Mock()
            mock_asr_instance.upload_to_oss.return_value = ("http://oss.example.com/audio.mp3", None)
            mock_asr_instance.submit_task.return_value = "task_123"
            mock_asr_instance.get_result.return_value = {
                "Sentences": [{"BeginTime": 0, "EndTime": 1000, "Text": "测试"}]
            }
            mock_asr_class.return_value = mock_asr_instance

            # Act
            add_subtitles(
                video_path=video_path,
                output_dir=output_dir,
                asr_client=None,  # 不提供 asr_client
            )

            # Assert: ASRClient 被自动创建
            mock_asr_class.assert_called_once()
            mock_asr_instance.upload_to_oss.assert_called_once()

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_empty_subtitle_text(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试空字幕文本处理。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip
        mock_text_class.return_value = MagicMock()
        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        # ASR 返回空文本
        mock_asr_client.get_result.return_value = {
            "Sentences": [
                {"BeginTime": 0, "EndTime": 1000, "Text": ""},
            ]
        }

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: TextClip 仍然被创建，但文本为空
        mock_text_class.assert_called_once()
        call_args = mock_text_class.call_args
        assert call_args[1]["text"] == ""

    @patch("core.subtitle_renderer.os.path.exists")
    @patch("core.subtitle_renderer.os.remove")
    @patch("core.subtitle_renderer.os.makedirs")
    @patch("core.subtitle_renderer.extract_audio")
    @patch("core.subtitle_renderer.VideoFileClip")
    @patch("core.subtitle_renderer.TextClip")
    @patch("core.subtitle_renderer.CompositeVideoClip")
    @patch("core.subtitle_renderer._subtitle_font")
    def test_multiple_subtitles_created(
        self,
        mock_subtitle_font,
        mock_composite_class,
        mock_text_class,
        mock_video_class,
        mock_extract_audio,
        mock_makedirs,
        mock_remove,
        mock_exists,
        mock_asr_client,
        mock_video_clip,
        tmp_path,
    ):
        """测试多个字幕片段被正确创建。"""
        # Arrange
        mock_subtitle_font.return_value = None
        mock_video_class.return_value = mock_video_clip

        text_clips = [MagicMock(), MagicMock(), MagicMock()]
        mock_text_class.side_effect = text_clips

        mock_composite_class.return_value = MagicMock()
        mock_exists.return_value = True

        # ASR 返回多个句子
        mock_asr_client.get_result.return_value = {
            "Sentences": [
                {"BeginTime": 0, "EndTime": 1000, "Text": "第一句"},
                {"BeginTime": 1000, "EndTime": 2500, "Text": "第二句"},
                {"BeginTime": 2500, "EndTime": 4000, "Text": "第三句"},
            ]
        }

        video_path = "/fake/video.mp4"
        output_dir = str(tmp_path)

        # Act
        add_subtitles(
            video_path=video_path,
            output_dir=output_dir,
            asr_client=mock_asr_client,
        )

        # Assert: 创建了 3 个 TextClip
        assert mock_text_class.call_count == 3

        # 验证 CompositeVideoClip 被传入所有片段
        composite_call_args = mock_composite_class.call_args[0][0]
        assert len(composite_call_args) == 4  # 1 个视频 + 3 个字幕

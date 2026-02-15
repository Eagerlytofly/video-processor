"""AI 分析器单元测试。

测试范围：
1. analyze_merged_transcripts - 主分析函数
2. _create_fallback_clip_order - 降级方案
3. _parse_analysis_to_clip_order - 解析剪辑顺序

所有外部依赖（urllib.request, 环境变量）均使用 Mock。
"""
import json
import os
import tempfile
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from core.ai_analyzer import (
    MERGED_FILENAME,
    IMPORTANT_DIALOGUES_FILENAME,
    CLIP_ORDER_FILENAME,
    SYSTEM_PROMPT,
    analyze_merged_transcripts,
    _create_fallback_clip_order,
    _parse_analysis_to_clip_order,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_output_dir():
    """创建临时输出目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def sample_transcript_content():
    """示例转录内容。"""
    return """=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一句话
[00:00:06.000 - 00:00:10.000] 第二句话
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 另一段话
[00:00:04.000 - 00:00:08.000] 再一段话"""


@pytest.fixture
def mock_api_response():
    """模拟 DeepSeek API 成功响应。"""
    return {
        "choices": [
            {
                "message": {
                    "content": """=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一句话
[00:00:06.000 - 00:00:10.000] 第二句话
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 另一段话"""
                }
            }
        ]
    }


@pytest.fixture
def create_merged_file(temp_output_dir, sample_transcript_content):
    """在临时目录中创建合并的转录文件。"""
    merged_path = os.path.join(temp_output_dir, MERGED_FILENAME)
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write(sample_transcript_content)
    return merged_path


# =============================================================================
# Test _parse_analysis_to_clip_order
# =============================================================================

class TestParseAnalysisToClipOrder:
    """测试 _parse_analysis_to_clip_order 函数。"""

    def test_parse_basic_content(self):
        """测试基本的解析功能。"""
        text = """
=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一句
[00:00:06.000 - 00:00:10.000] 第二句
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 另一段
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 3
        assert clips[0]["video"] == "video1.mp4"
        assert clips[0]["start_time"] == "00:00:00.000"
        assert clips[0]["end_time"] == "00:00:05.000"
        assert clips[1]["video"] == "video1.mp4"
        assert clips[2]["video"] == "video2.mp4"

    def test_parse_empty_string(self):
        """测试空字符串返回空列表。"""
        clips = _parse_analysis_to_clip_order("")
        assert clips == []

    def test_parse_whitespace_only(self):
        """测试只有空白字符返回空列表。"""
        clips = _parse_analysis_to_clip_order("   \n\t  \n  ")
        assert clips == []

    def test_parse_no_timestamps(self):
        """测试没有时间戳的内容返回空列表。"""
        text = """
=== video1.mp4 ===
这是一段没有时间的文本
另一段文本
"""
        clips = _parse_analysis_to_clip_order(text)
        assert clips == []

    def test_parse_timestamp_without_video_header(self):
        """测试没有时间戳前视频标题的时间戳被忽略。"""
        text = """
[00:00:00.000 - 00:00:05.000] 这句话应该被忽略
=== video1.mp4 ===
[00:00:06.000 - 00:00:10.000] 这句话应该被包含
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 1
        assert clips[0]["video"] == "video1.mp4"

    def test_parse_malformed_timestamp(self):
        """测试格式错误的时间戳被跳过。"""
        text = """
=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 正常时间戳
[invalid timestamp] 错误时间戳
[00:00:06.000] 不完整时间戳
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 1
        assert clips[0]["start_time"] == "00:00:00.000"

    def test_parse_multiple_videos_mixed_order(self):
        """测试多个视频混合顺序。"""
        text = """
=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一段
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 第二段
=== video1.mp4 ===
[00:00:10.000 - 00:00:15.000] 第三段
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 3
        assert clips[0]["video"] == "video1.mp4"
        assert clips[1]["video"] == "video2.mp4"
        assert clips[2]["video"] == "video1.mp4"

    def test_parse_empty_video_section(self):
        """测试空视频段落。"""
        text = """
=== video1.mp4 ===
=== video2.mp4 ===
[00:00:00.000 - 00:00:03.000] 内容
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 1
        assert clips[0]["video"] == "video2.mp4"

    def test_parse_video_header_with_extra_equals(self):
        """测试带有额外等号的视频标题。"""
        text = """
==== video1.mp4 ====
[00:00:00.000 - 00:00:05.000] 内容
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 1
        assert clips[0]["video"] == "video1.mp4"

    def test_parse_timestamp_with_extra_spaces(self):
        """测试带有额外空格的时间戳。"""
        text = """
=== video1.mp4 ===
[ 00:00:00.000  -  00:00:05.000 ] 内容
"""
        clips = _parse_analysis_to_clip_order(text)
        assert len(clips) == 1
        assert clips[0]["start_time"] == "00:00:00.000"
        assert clips[0]["end_time"] == "00:00:05.000"


# =============================================================================
# Test _create_fallback_clip_order
# =============================================================================

class TestCreateFallbackClipOrder:
    """测试 _create_fallback_clip_order 降级函数。"""

    def test_creates_important_dialogues_file(self, temp_output_dir, sample_transcript_content):
        """测试创建 important_dialogues.txt 文件。"""
        _create_fallback_clip_order(temp_output_dir, sample_transcript_content)

        important_path = os.path.join(temp_output_dir, IMPORTANT_DIALOGUES_FILENAME)
        assert os.path.exists(important_path)

        with open(important_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "AI 分析失败" in content
        assert "降级为仅转录模式" in content

    def test_creates_clip_order_file(self, temp_output_dir, sample_transcript_content):
        """测试创建 clip_order.txt 文件。"""
        _create_fallback_clip_order(temp_output_dir, sample_transcript_content)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

        with open(clip_order_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2  # 两个视频

    def test_clip_order_content(self, temp_output_dir, sample_transcript_content):
        """测试剪辑顺序文件内容正确。"""
        _create_fallback_clip_order(temp_output_dir, sample_transcript_content)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        with open(clip_order_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")

        assert len(lines) == 2
        # 格式: video\tstart_time\tend_time
        parts1 = lines[0].split("\t")
        assert parts1[0] == "video1.mp4"
        assert parts1[1] == "00:00:00.000"
        assert parts1[2] == "00:00:10.000"  # 第一个视频的最后结束时间

        parts2 = lines[1].split("\t")
        assert parts2[0] == "video2.mp4"
        assert parts2[1] == "00:00:00.000"
        assert parts2[2] == "00:00:08.000"  # 第二个视频的最后结束时间

    def test_single_video_transcript(self, temp_output_dir):
        """测试单个视频的转录内容。"""
        transcript = """=== single.mp4 ===
[00:00:00.000 - 00:00:05.000] 第一句
[00:00:06.000 - 00:00:10.000] 第二句"""

        _create_fallback_clip_order(temp_output_dir, transcript)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        with open(clip_order_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        assert "single.mp4\t00:00:00.000\t00:00:10.000" == content

    def test_empty_transcript_content(self, temp_output_dir):
        """测试空转录内容不创建 clip_order。"""
        _create_fallback_clip_order(temp_output_dir, "")

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert not os.path.exists(clip_order_path)

    def test_transcript_without_timestamps(self, temp_output_dir):
        """测试没有时间戳的转录内容。"""
        transcript = """=== video1.mp4 ===
这是一段没有时间戳的文本"""

        _create_fallback_clip_order(temp_output_dir, transcript)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        # 没有时间戳，无法创建剪辑顺序
        assert not os.path.exists(clip_order_path)

    def test_transcript_with_malformed_timestamps(self, temp_output_dir):
        """测试格式错误的时间戳被跳过。"""
        transcript = """=== video1.mp4 ===
[invalid] 错误时间戳
[00:00:00.000 - 00:00:05.000] 正确时间戳"""

        _create_fallback_clip_order(temp_output_dir, transcript)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

        with open(clip_order_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        assert "video1.mp4\t00:00:00.000\t00:00:05.000" == content


# =============================================================================
# Test analyze_merged_transcripts
# =============================================================================

class TestAnalyzeMergedTranscripts:
    """测试 analyze_merged_transcripts 主函数。"""

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.DEEPSEEK_MODEL", "test-model")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_successful_analysis(
        self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response
    ):
        """测试成功的 AI 分析流程。"""
        # 设置 mock 响应
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = analyze_merged_transcripts(temp_output_dir, "请提取重要对话")

        # 验证返回结果
        assert result is not None
        assert "video1.mp4" in result

        # 验证 important_dialogues.txt 被创建
        important_path = os.path.join(temp_output_dir, IMPORTANT_DIALOGUES_FILENAME)
        assert os.path.exists(important_path)

        # 验证 clip_order.txt 被创建
        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

        with open(clip_order_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3  # API 返回了 3 个片段

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.DEEPSEEK_MODEL", "test-model")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_request_body_structure(
        self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response
    ):
        """测试 API 请求体结构正确。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("core.ai_analyzer.urllib.request.Request") as mock_request:
            analyze_merged_transcripts(temp_output_dir, "自定义提示")

            # 验证 Request 被创建
            assert mock_request.called

            # 获取调用参数
            call_args = mock_request.call_args
            url = call_args[0][0]

            # 验证 URL
            assert url == "https://api.test.com/v1/chat/completions"

            # 验证 headers
            kwargs = call_args[1]
            assert kwargs["headers"]["Content-Type"] == "application/json"
            assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
            assert kwargs["method"] == "POST"

            # 验证请求体
            body = json.loads(kwargs["data"])
            assert body["model"] == "test-model"
            assert body["temperature"] == 0.5
            assert body["stream"] == False
            assert len(body["messages"]) == 2
            assert body["messages"][0]["role"] == "system"
            assert body["messages"][0]["content"] == SYSTEM_PROMPT
            assert body["messages"][1]["role"] == "user"
            assert "自定义提示" in body["messages"][1]["content"]

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    def test_file_not_found(self, temp_output_dir):
        """测试合并文件不存在时抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            analyze_merged_transcripts(temp_output_dir, "测试提示")

    def test_empty_transcript_content(self, temp_output_dir):
        """测试空转录内容时抛出 ValueError。"""
        # 创建空的合并文件
        merged_path = os.path.join(temp_output_dir, MERGED_FILENAME)
        with open(merged_path, "w", encoding="utf-8") as f:
            f.write("   \n\t  \n  ")

        with pytest.raises(ValueError, match="合并转录内容为空"):
            analyze_merged_transcripts(temp_output_dir, "测试提示")

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", None)
    def test_no_api_key_with_fallback(self, temp_output_dir, create_merged_file):
        """测试无 API key 且启用降级时返回 None 并创建降级文件。"""
        result = analyze_merged_transcripts(
            temp_output_dir, "测试提示", fallback_to_transcription_only=True
        )

        # 验证返回 None
        assert result is None

        # 验证降级文件被创建
        important_path = os.path.join(temp_output_dir, IMPORTANT_DIALOGUES_FILENAME)
        assert os.path.exists(important_path)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", None)
    def test_no_api_key_without_fallback(self, temp_output_dir, create_merged_file):
        """测试无 API key 且禁用降级时抛出 RuntimeError。"""
        with pytest.raises(RuntimeError, match="未配置 DEEPSEEK_API_KEY"):
            analyze_merged_transcripts(
                temp_output_dir, "测试提示", fallback_to_transcription_only=False
            )

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_error_with_fallback(
        self, mock_urlopen, temp_output_dir, create_merged_file
    ):
        """测试 API 调用失败且启用降级时返回 None 并创建降级文件。"""
        # 模拟 API 异常
        mock_urlopen.side_effect = Exception("Connection timeout")

        result = analyze_merged_transcripts(
            temp_output_dir, "测试提示", fallback_to_transcription_only=True
        )

        # 验证返回 None
        assert result is None

        # 验证降级文件被创建
        important_path = os.path.join(temp_output_dir, IMPORTANT_DIALOGUES_FILENAME)
        assert os.path.exists(important_path)

        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_error_without_fallback(
        self, mock_urlopen, temp_output_dir, create_merged_file
    ):
        """测试 API 调用失败且禁用降级时抛出异常。"""
        mock_urlopen.side_effect = Exception("Connection timeout")

        with pytest.raises(Exception, match="Connection timeout"):
            analyze_merged_transcripts(
                temp_output_dir, "测试提示", fallback_to_transcription_only=False
            )

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_default_user_hint(self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response):
        """测试默认用户提示。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("core.ai_analyzer.urllib.request.Request") as mock_request:
            analyze_merged_transcripts(temp_output_dir, None)

            call_args = mock_request.call_args
            kwargs = call_args[1]
            body = json.loads(kwargs["data"])
            assert "请提取重要对话并保持时间戳格式" in body["messages"][1]["content"]

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_whitespace_only_user_hint(self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response):
        """测试只有空白字符的用户提示（代码中只处理 None，空白字符会保留）。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("core.ai_analyzer.urllib.request.Request") as mock_request:
            analyze_merged_transcripts(temp_output_dir, "   ")

            call_args = mock_request.call_args
            kwargs = call_args[1]
            body = json.loads(kwargs["data"])
            # 空白字符不是 falsy 值，所以不会使用默认值，但会被 strip()
            # 实际行为：空白字符经过 .strip() 后变成空字符串
            assert body["messages"][1]["content"].startswith("\n\n转录文件如下:")

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_response_with_no_clips(
        self, mock_urlopen, temp_output_dir, create_merged_file
    ):
        """测试 API 返回没有可解析片段的内容。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "这是分析结果，但没有时间戳"}}]
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = analyze_merged_transcripts(temp_output_dir, "测试提示")

        # 验证返回结果
        assert result == "这是分析结果，但没有时间戳"

        # 验证 important_dialogues.txt 被创建
        important_path = os.path.join(temp_output_dir, IMPORTANT_DIALOGUES_FILENAME)
        assert os.path.exists(important_path)

        # 验证 clip_order.txt 被创建但为空（因为没有可解析的片段）
        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        assert os.path.exists(clip_order_path)

        with open(clip_order_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == ""

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_url_trailing_slash(
        self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response
    ):
        """测试 API URL 带有尾部斜杠时正确处理。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("core.ai_analyzer.urllib.request.Request") as mock_request:
            with patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1/"):
                analyze_merged_transcripts(temp_output_dir, "测试提示")

                call_args = mock_request.call_args
                url = call_args[0][0]
                # URL 不应该有双斜杠
                assert url == "https://api.test.com/v1/chat/completions"

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_api_timeout_parameter(
        self, mock_urlopen, temp_output_dir, create_merged_file, mock_api_response
    ):
        """测试 API 调用使用正确的超时参数。"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_api_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        analyze_merged_transcripts(temp_output_dir, "测试提示")

        # 验证 urlopen 被调用时带有 timeout 参数
        call_args = mock_urlopen.call_args
        assert call_args[1].get("timeout") == 120


# =============================================================================
# Integration-style Tests
# =============================================================================

class TestIntegrationScenarios:
    """集成场景测试，模拟完整的工作流程。"""

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", "test-api-key")
    @patch("core.ai_analyzer.DEEPSEEK_API_URL", "https://api.test.com/v1")
    @patch("core.ai_analyzer.urllib.request.urlopen")
    def test_full_workflow_with_reordered_clips(
        self, mock_urlopen, temp_output_dir
    ):
        """测试完整工作流程，包括 AI 重新排序片段。"""
        # 创建转录文件
        transcript = """=== video1.mp4 ===
[00:00:00.000 - 00:00:05.000] 开场白
[00:00:10.000 - 00:00:15.000] 主要内容
=== video2.mp4 ===
[00:00:00.000 - 00:00:08.000] 精彩部分
[00:00:20.000 - 00:00:25.000] 结尾"""

        merged_path = os.path.join(temp_output_dir, MERGED_FILENAME)
        with open(merged_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        # AI 返回重新排序的结果（把精彩部分放到最前面）
        ai_response = {
            "choices": [{
                "message": {
                    "content": """=== video2.mp4 ===
[00:00:00.000 - 00:00:08.000] 精彩部分
=== video1.mp4 ===
[00:00:10.000 - 00:00:15.000] 主要内容
=== video2.mp4 ===
[00:00:20.000 - 00:00:25.000] 结尾"""
                }
            }]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(ai_response).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = analyze_merged_transcripts(temp_output_dir, "按重要性排序")

        # 验证 clip_order.txt 中的顺序与 AI 返回一致
        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        with open(clip_order_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3
        # 第一个应该是 video2 的精彩部分
        assert lines[0].startswith("video2.mp4\t00:00:00.000\t00:00:08.000")
        # 第二个应该是 video1 的主要内容
        assert lines[1].startswith("video1.mp4\t00:00:10.000\t00:00:15.000")
        # 第三个应该是 video2 的结尾
        assert lines[2].startswith("video2.mp4\t00:00:20.000\t00:00:25.000")

    @patch("core.ai_analyzer.DEEPSEEK_API_KEY", None)
    def test_fallback_workflow_with_multiple_videos(self, temp_output_dir):
        """测试降级模式下的多视频处理。"""
        transcript = """=== intro.mp4 ===
[00:00:00.000 - 00:00:10.000] 开场
[00:00:15.000 - 00:00:20.000] 介绍
=== main.mp4 ===
[00:00:00.000 - 00:05:00.000] 主要内容
=== outro.mp4 ===
[00:00:00.000 - 00:00:30.000] 结尾"""

        merged_path = os.path.join(temp_output_dir, MERGED_FILENAME)
        with open(merged_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        result = analyze_merged_transcripts(
            temp_output_dir, "测试", fallback_to_transcription_only=True
        )

        assert result is None

        # 验证降级模式创建了完整的视频剪辑顺序
        clip_order_path = os.path.join(temp_output_dir, CLIP_ORDER_FILENAME)
        with open(clip_order_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")

        assert len(lines) == 3
        assert lines[0].startswith("intro.mp4\t00:00:00.000\t00:00:20.000")
        assert lines[1].startswith("main.mp4\t00:00:00.000\t00:05:00.000")
        assert lines[2].startswith("outro.mp4\t00:00:00.000\t00:00:30.000")

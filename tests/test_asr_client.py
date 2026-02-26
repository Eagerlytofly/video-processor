"""ASRClient 单元测试（Mock 阿里云 API，不调用真实服务）。"""
import json
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.asr_client import ASRClient


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """模拟完整的配置环境。"""
    with patch("core.asr_client.OSS_ACCESS_KEY_ID", "test_key_id"), \
         patch("core.asr_client.OSS_ACCESS_KEY_SECRET", "test_key_secret"), \
         patch("core.asr_client.OSS_BUCKET_NAME", "test_bucket"), \
         patch("core.asr_client.OSS_ENDPOINT", "oss-cn-test.aliyuncs.com"), \
         patch("core.asr_client.ASR_APP_KEY", "test_app_key"), \
         patch("core.asr_client.ASR_REGION_ID", "cn-test"), \
         patch("core.asr_client.ASR_DOMAIN", "filetrans.cn-test.aliyuncs.com"), \
         patch("core.asr_client.ASR_API_VERSION", "2018-08-17"), \
         patch("core.asr_client.ASR_PRODUCT", "nls-filetrans"):
        yield


@pytest.fixture
def mock_config_no_credentials():
    """模拟无凭证的配置环境。"""
    with patch("core.asr_client.OSS_ACCESS_KEY_ID", None), \
         patch("core.asr_client.OSS_ACCESS_KEY_SECRET", None), \
         patch("core.asr_client.ASR_APP_KEY", None):
        yield


@pytest.fixture
def mock_config_partial():
    """模拟部分凭证的配置环境（只有 OSS 凭证，没有 ASR 配置）。"""
    with patch("core.asr_client.OSS_ACCESS_KEY_ID", "test_key_id"), \
         patch("core.asr_client.OSS_ACCESS_KEY_SECRET", "test_key_secret"), \
         patch("core.asr_client.ASR_APP_KEY", None):
        yield


@pytest.fixture
def asr_client_with_mock(mock_config):
    """创建带有 Mock 依赖的 ASRClient 实例。"""
    with patch("core.asr_client.AcsClient") as mock_acs, \
         patch("core.asr_client.oss2.Auth") as mock_auth, \
         patch("core.asr_client.oss2.Bucket") as mock_bucket:
        client = ASRClient()
        # 保存 mock 对象以便测试中使用
        client._mock_acs = mock_acs
        client._mock_bucket_instance = mock_bucket.return_value
        yield client


# =============================================================================
# __init__ 测试
# =============================================================================

def test_init_with_credentials(mock_config):
    """测试有凭证时正确初始化 AcsClient 和 OSS Bucket。"""
    with patch("core.asr_client.AcsClient") as mock_acs, \
         patch("core.asr_client.oss2.Auth") as mock_auth, \
         patch("core.asr_client.oss2.Bucket") as mock_bucket:
        client = ASRClient()

        # 验证 AcsClient 被正确创建
        mock_acs.assert_called_once_with(
            "test_key_id",
            "test_key_secret",
            "cn-test"
        )

        # 验证 OSS Auth 和 Bucket 被正确创建
        mock_auth.assert_called_once_with("test_key_id", "test_key_secret")
        mock_bucket.assert_called_once_with(
            mock_auth.return_value,
            "oss-cn-test.aliyuncs.com",
            "test_bucket"
        )

        # 验证内部状态
        assert client._acs is not None
        assert client._bucket is not None


def test_init_without_credentials(mock_config_no_credentials):
    """测试无凭证时仅构造实例，不创建客户端。"""
    with patch("core.asr_client.AcsClient") as mock_acs, \
         patch("core.asr_client.oss2.Auth") as mock_auth, \
         patch("core.asr_client.oss2.Bucket") as mock_bucket:
        client = ASRClient()

        # 验证没有创建任何客户端
        mock_acs.assert_not_called()
        mock_auth.assert_not_called()
        mock_bucket.assert_not_called()

        # 验证内部状态为 None
        assert client._acs is None
        assert client._bucket is None


# =============================================================================
# upload_to_oss 测试
# =============================================================================

def test_upload_to_oss_success(asr_client_with_mock):
    """测试正常上传文件到 OSS。"""
    client = asr_client_with_mock

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("test content")
        temp_path = f.name

    try:
        url, oss_path = client.upload_to_oss(temp_path)

        # 验证返回的 URL 格式正确
        expected_url = f"https://test_bucket.oss-cn-test.aliyuncs.com/{os.path.basename(temp_path)}"
        assert url == expected_url
        assert oss_path == os.path.basename(temp_path)

        # 验证 put_object 被调用
        client._mock_bucket_instance.put_object.assert_called_once()
        call_args = client._mock_bucket_instance.put_object.call_args
        assert call_args[0][0] == os.path.basename(temp_path)
    finally:
        os.unlink(temp_path)


def test_upload_to_oss_file_not_found(asr_client_with_mock):
    """测试上传不存在的文件时抛出 FileNotFoundError。"""
    client = asr_client_with_mock

    with pytest.raises(FileNotFoundError, match="本地文件不存在"):
        client.upload_to_oss("/nonexistent/path/file.txt")


def test_upload_to_oss_not_configured(mock_config_no_credentials):
    """测试未配置 OSS 时抛出 RuntimeError。"""
    client = ASRClient()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        temp_path = f.name

    try:
        with pytest.raises(RuntimeError, match="OSS 未配置"):
            client.upload_to_oss(temp_path)
    finally:
        os.unlink(temp_path)


# =============================================================================
# submit_task 测试
# =============================================================================

def test_submit_task_success(asr_client_with_mock):
    """测试正常提交 ASR 任务。"""
    client = asr_client_with_mock

    # 模拟成功的 API 响应
    mock_response = json.dumps({
        "StatusText": "SUCCESS",
        "TaskId": "task_12345"
    }).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    task_id = client.submit_task("https://example.com/audio.wav")

    assert task_id == "task_12345"

    # 验证 API 调用
    client._acs.do_action_with_exception.assert_called_once()
    call_args = client._acs.do_action_with_exception.call_args
    request = call_args[0][0]

    # 验证请求参数（使用 getter 方法访问）
    assert request.get_domain() == "filetrans.cn-test.aliyuncs.com"
    assert request.get_version() == "2018-08-17"
    assert request.get_product() == "nls-filetrans"
    assert request.get_action_name() == "SubmitTask"
    assert request.get_method() == "POST"


def test_submit_task_failure(asr_client_with_mock):
    """测试 ASR 任务提交失败时抛出 RuntimeError。"""
    client = asr_client_with_mock

    # 模拟失败的 API 响应
    mock_response = json.dumps({
        "StatusText": "ERROR",
        "Message": "Invalid file format"
    }).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    with pytest.raises(RuntimeError, match="任务提交失败"):
        client.submit_task("https://example.com/audio.wav")


def test_submit_task_not_configured(mock_config_no_credentials):
    """测试未配置 ASR 时抛出 RuntimeError。"""
    client = ASRClient()

    with pytest.raises(RuntimeError, match="ASR 未配置"):
        client.submit_task("https://example.com/audio.wav")


def test_submit_task_no_app_key(mock_config_partial):
    """测试未配置 ASR_APP_KEY 时抛出 RuntimeError。"""
    with patch("core.asr_client.AcsClient"), \
         patch("core.asr_client.oss2.Auth"), \
         patch("core.asr_client.oss2.Bucket"):
        client = ASRClient()

        with pytest.raises(RuntimeError, match="ASR 未配置：请设置 ASR_APP_KEY"):
            client.submit_task("https://example.com/audio.wav")


# =============================================================================
# get_result 测试
# =============================================================================

def test_get_result_success(asr_client_with_mock):
    """测试正常获取 ASR 结果。"""
    client = asr_client_with_mock

    # 模拟成功的 API 响应
    mock_result = {
        "Sentences": [
            {"BeginTime": 0, "EndTime": 5000, "Text": "Hello world"}
        ]
    }
    mock_response = json.dumps({
        "StatusText": "SUCCESS",
        "Result": mock_result
    }).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    result = client.get_result("task_12345")

    assert result == mock_result


def test_get_result_no_valid_fragment(asr_client_with_mock):
    """测试返回 SUCCESS_WITH_NO_VALID_FRAGMENT 时返回 None。"""
    client = asr_client_with_mock

    mock_response = json.dumps({
        "StatusText": "SUCCESS_WITH_NO_VALID_FRAGMENT"
    }).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    result = client.get_result("task_12345")

    assert result is None


def test_get_result_failure(asr_client_with_mock):
    """测试转写失败时返回 None。"""
    client = asr_client_with_mock

    mock_response = json.dumps({
        "StatusText": "FAILED",
        "ErrorMessage": "Processing error"
    }).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    result = client.get_result("task_12345")

    assert result is None


def test_get_result_polling_running_then_success(asr_client_with_mock):
    """测试轮询：先 RUNNING 后 SUCCESS。"""
    client = asr_client_with_mock

    # 模拟两次 RUNNING，然后 SUCCESS
    mock_responses = [
        json.dumps({"StatusText": "RUNNING"}).encode('utf-8'),
        json.dumps({"StatusText": "RUNNING"}).encode('utf-8'),
        json.dumps({
            "StatusText": "SUCCESS",
            "Result": {"Sentences": [{"Text": "Done"}]}
        }).encode('utf-8'),
    ]
    client._acs.do_action_with_exception.side_effect = mock_responses

    with patch("core.asr_client.time.sleep") as mock_sleep:
        result = client.get_result("task_12345", max_retries=5, poll_interval=1)

    assert result == {"Sentences": [{"Text": "Done"}]}
    assert mock_sleep.call_count == 2  # 两次 RUNNING 状态，sleep 两次


def test_get_result_polling_queueing_then_success(asr_client_with_mock):
    """测试轮询：先 QUEUEING 后 SUCCESS。"""
    client = asr_client_with_mock

    mock_responses = [
        json.dumps({"StatusText": "QUEUEING"}).encode('utf-8'),
        json.dumps({
            "StatusText": "SUCCESS",
            "Result": {"Sentences": [{"Text": "Done"}]}
        }).encode('utf-8'),
    ]
    client._acs.do_action_with_exception.side_effect = mock_responses

    with patch("core.asr_client.time.sleep") as mock_sleep:
        result = client.get_result("task_12345", max_retries=5, poll_interval=1)

    assert result == {"Sentences": [{"Text": "Done"}]}
    assert mock_sleep.call_count == 1


def test_get_result_timeout(asr_client_with_mock):
    """测试轮询超时抛出 TimeoutError。"""
    client = asr_client_with_mock

    # 始终返回 RUNNING
    mock_response = json.dumps({"StatusText": "RUNNING"}).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    with patch("core.asr_client.time.sleep") as mock_sleep:
        with pytest.raises(TimeoutError, match="ASR 任务处理超时"):
            client.get_result("task_12345", max_retries=3, poll_interval=2)

    # 验证 sleep 被调用了 max_retries-1 次（最后一次不 sleep 直接抛异常）
    assert mock_sleep.call_count == 2


def test_get_result_not_configured(mock_config_no_credentials):
    """测试未配置 ASR 时抛出 RuntimeError。"""
    client = ASRClient()

    with pytest.raises(RuntimeError, match="ASR 未配置"):
        client.get_result("task_12345")


def test_get_result_no_app_key(mock_config_partial):
    """测试未配置 ASR_APP_KEY 时抛出 RuntimeError。"""
    with patch("core.asr_client.AcsClient"), \
         patch("core.asr_client.oss2.Auth"), \
         patch("core.asr_client.oss2.Bucket"):
        client = ASRClient()

        with pytest.raises(RuntimeError, match="ASR 未配置：请设置 ASR_APP_KEY"):
            client.get_result("task_12345")


# =============================================================================
# 边界情况测试
# =============================================================================

def test_upload_to_oss_empty_file(asr_client_with_mock):
    """测试上传空文件。"""
    client = asr_client_with_mock

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        # 不写入任何内容，创建空文件
        temp_path = f.name

    try:
        url, oss_path = client.upload_to_oss(temp_path)

        # 空文件也应该能上传
        assert oss_path == os.path.basename(temp_path)
        client._mock_bucket_instance.put_object.assert_called_once()
    finally:
        os.unlink(temp_path)


def test_upload_to_oss_special_characters_in_filename(asr_client_with_mock):
    """测试文件名包含特殊字符。"""
    client = asr_client_with_mock

    with tempfile.NamedTemporaryFile(mode='w', suffix='.test file (1).txt', delete=False) as f:
        temp_path = f.name

    try:
        url, oss_path = client.upload_to_oss(temp_path)

        # 特殊字符应该保留在文件名中
        assert oss_path == os.path.basename(temp_path)
    finally:
        os.unlink(temp_path)


def test_submit_task_api_exception(asr_client_with_mock):
    """测试 submit_task API 抛出异常。"""
    client = asr_client_with_mock

    # 模拟 API 抛出异常
    client._acs.do_action_with_exception.side_effect = Exception("Network error")

    with pytest.raises(Exception, match="Network error"):
        client.submit_task("https://example.com/audio.wav")


def test_get_result_api_exception(asr_client_with_mock):
    """测试 get_result API 抛出异常时，重试后最终失败。"""
    client = asr_client_with_mock

    client._acs.do_action_with_exception.side_effect = Exception("Connection timeout")

    # 减少重试次数和等待时间以加速测试
    with patch("core.asr_client.RETRY_CONFIG", {"max_attempts": 2, "min_wait": 0.1, "max_wait": 0.2}):
        with pytest.raises(Exception):  # 重试后抛出的异常
            client.get_result("task_12345")

    # 验证重试机制生效（多次调用）
    assert client._acs.do_action_with_exception.call_count >= 2


def test_get_result_max_retries_one(asr_client_with_mock):
    """测试 max_retries=1 时立即超时。"""
    client = asr_client_with_mock

    mock_response = json.dumps({"StatusText": "RUNNING"}).encode('utf-8')
    client._acs.do_action_with_exception.return_value = mock_response

    with patch("core.asr_client.time.sleep") as mock_sleep:
        with pytest.raises(TimeoutError, match="ASR 任务处理超时"):
            client.get_result("task_12345", max_retries=1, poll_interval=1)

    # max_retries=1 时，不应该调用 sleep（直接超时）
    mock_sleep.assert_not_called()


def test_get_result_poll_interval_zero(asr_client_with_mock):
    """测试 poll_interval=0 时不 sleep。"""
    client = asr_client_with_mock

    mock_responses = [
        json.dumps({"StatusText": "RUNNING"}).encode('utf-8'),
        json.dumps({"StatusText": "SUCCESS", "Result": {}}).encode('utf-8'),
    ]
    client._acs.do_action_with_exception.side_effect = mock_responses

    with patch("core.asr_client.time.sleep") as mock_sleep:
        client.get_result("task_12345", max_retries=5, poll_interval=0)

    # poll_interval=0 时，time.sleep(0) 仍然会被调用
    mock_sleep.assert_called_once_with(0)

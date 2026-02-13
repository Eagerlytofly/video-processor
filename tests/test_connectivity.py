"""
DeepSeek、阿里云 OSS、阿里云 ASR 转录 连通性测试（可选）。
未配置对应凭证时自动跳过，不失败。
运行前请设置环境变量：
  - OSS: ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET
  - ASR: ALIYUN_APP_KEY（转录需同时有 OSS + ASR）
  - DeepSeek: DEEPSEEK_API_KEY
运行方式：
  pytest tests/test_connectivity.py -v
  pytest tests/test_connectivity.py -v -k oss     # 仅 OSS
  pytest tests/test_connectivity.py -v -k asr     # 仅 ASR 转录
  pytest tests/test_connectivity.py -v -k deepseek # 仅 DeepSeek
"""

import os
import subprocess
import tempfile
import pytest

def _has_oss_credentials():
    from config.config import OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
    return bool(OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET)

def _has_asr_credentials():
    from config.config import ASR_APP_KEY
    return bool(ASR_APP_KEY)

def _has_deepseek_credentials():
    from config.config import DEEPSEEK_API_KEY
    return bool(DEEPSEEK_API_KEY)


def _make_minimal_mp3():
    """用 ffmpeg 生成约 1 秒的静音 MP3（16kHz 单声道，ASR 常用），返回临时文件路径。无 ffmpeg 时返回 None。"""
    try:
        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-t", "1",
                "-acodec", "libmp3lame", "-q:a", "9",
                path,
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return path
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


@pytest.mark.skipif(not _has_oss_credentials(), reason="OSS 未配置凭证，跳过连通性测试")
class TestOSSConnectivity:
    """阿里云 OSS 连通性：上传小文件并校验存在。"""

    def test_oss_upload_and_exists(self):
        """上传一个临时文件到 OSS，检查 bucket 可写且可读。"""
        from core.asr_client import ASRClient

        client = ASRClient()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"connectivity_test")
            path = f.name
        try:
            url, oss_path = client.upload_to_oss(path)
            assert url
            assert oss_path
            # 使用 bucket 检查对象存在（ASRClient 内部有 _bucket）
            assert client._bucket.object_exists(oss_path)
        finally:
            os.unlink(path)


@pytest.mark.skipif(
    not _has_oss_credentials() or not _has_asr_credentials(),
    reason="OSS 或 ASR 未配置凭证，跳过转录连通性测试",
)
class TestASRConnectivity:
    """阿里云 ASR 转录连通性：上传短音频 -> 提交转写任务 -> 获取结果。"""

    def test_asr_transcription_flow(self):
        """完整走通：生成短音频 -> 上传 OSS -> 提交 ASR 任务 -> 轮询获取结果（可为无有效片段）。"""
        from core.asr_client import ASRClient

        mp3_path = _make_minimal_mp3()
        if not mp3_path or not os.path.exists(mp3_path):
            pytest.skip("需要 ffmpeg 生成测试音频，当前环境未找到或生成失败")

        try:
            client = ASRClient()
            url, oss_path = client.upload_to_oss(mp3_path)
            assert url and oss_path

            task_id = client.submit_task(url)
            assert task_id

            # 静音片段可能返回 None（SUCCESS_WITH_NO_VALID_FRAGMENT），或带 Sentences 的 dict
            result = client.get_result(task_id)
            # 只要不抛异常且返回 None 或合法结构即认为转录服务连通正常
            assert result is None or isinstance(result, dict)
            if result is not None:
                assert "Sentences" in result  # 有结果时应有 Sentences 字段
        finally:
            if mp3_path and os.path.exists(mp3_path):
                os.unlink(mp3_path)


@pytest.mark.skipif(not _has_deepseek_credentials(), reason="DeepSeek 未配置 API Key，跳过连通性测试")
class TestDeepSeekConnectivity:
    """DeepSeek API 连通性：发送简单对话并校验返回。"""

    def test_deepseek_chat_completion(self):
        """调用 DeepSeek 简单对话，确认能连通并返回内容（用 urllib 避免 openai/httpx 版本兼容问题）。"""
        import json
        import urllib.request

        from config.config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL

        url = f"{DEEPSEEK_API_URL.rstrip('/')}/chat/completions"
        data = json.dumps({
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": "只回复：ok"}],
            "max_tokens": 10,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        assert "choices" in body and len(body["choices"]) > 0
        content = body["choices"][0].get("message", {}).get("content", "")
        assert content and len(content.strip()) >= 1

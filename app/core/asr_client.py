"""
阿里云 ASR 与 OSS 客户端：上传音频、提交转写任务、获取结果。
"""

import json
import logging
import os
import time

import oss2
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.config import (
    ASR_APP_KEY,
    ASR_API_VERSION,
    ASR_DOMAIN,
    ASR_PRODUCT,
    ASR_REGION_ID,
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_BUCKET_NAME,
    OSS_ENDPOINT,
    RETRY_CONFIG,
)

logger = logging.getLogger(__name__)


# 定义可重试的异常类型
class RetryableException(Exception):
    """可重试的异常基类"""
    pass


class OSSUploadException(RetryableException):
    """OSS 上传异常"""
    pass


class ASRSubmitException(RetryableException):
    """ASR 提交任务异常"""
    pass


class ASRPollException(RetryableException):
    """ASR 轮询异常"""
    pass


class ASRClient:
    """阿里云 ASR 与 OSS 封装，用于音频上传与语音转写。无凭证时仅构造实例，不创建 AcsClient，便于测试。"""

    def __init__(self):
        self._acs = None
        self._bucket = None
        if OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET:
            self._acs = AcsClient(
                OSS_ACCESS_KEY_ID,
                OSS_ACCESS_KEY_SECRET,
                ASR_REGION_ID,
            )
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            self._bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET_NAME)

    def upload_to_oss(self, local_path: str) -> tuple[str, str]:
        """
        上传本地文件到 OSS，返回 (访问 URL, OSS 路径)。
        网络错误会自动重试，配置错误和文件不存在不会重试。
        """
        if not self._bucket:
            raise RuntimeError("OSS 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"本地文件不存在: {local_path}")

        return self._upload_to_oss_with_retry(local_path)

    @retry(
        stop=stop_after_attempt(RETRY_CONFIG["max_attempts"]),
        wait=wait_exponential(multiplier=1, min=RETRY_CONFIG["min_wait"], max=RETRY_CONFIG["max_wait"]),
        retry=retry_if_exception_type(OSSUploadException),
        before_sleep=lambda retry_state: logger.warning(
            "OSS 上传失败，%d 秒后重试 (第 %d/%d 次): %s",
            retry_state.next_action.sleep, retry_state.attempt_number, RETRY_CONFIG["max_attempts"],
            retry_state.outcome.exception()
        ),
        reraise=True,  # 保持原始异常链
    )
    def _upload_to_oss_with_retry(self, local_path: str) -> tuple[str, str]:
        """内部方法：带重试的 OSS 上传"""
        oss_path = os.path.basename(local_path)
        logger.info("上传文件到 OSS: %s", oss_path)
        try:
            with open(local_path, "rb") as f:
                self._bucket.put_object(oss_path, f)
            url = f"https://{OSS_BUCKET_NAME}.{OSS_ENDPOINT}/{oss_path}"
            logger.info("OSS 上传成功: %s", oss_path)
            return url, oss_path
        except Exception as e:
            logger.error("OSS 上传失败: %s - %s", oss_path, e)
            raise OSSUploadException(f"OSS 上传失败: {e}") from e

    def submit_task(self, audio_url: str) -> str:
        """
        提交 ASR 转写任务，返回 TaskId。
        配置错误不会重试，网络/API 错误会自动重试。
        """
        if not ASR_APP_KEY:
            raise RuntimeError("ASR 未配置：请设置 ASR_APP_KEY")
        if self._acs is None:
            raise RuntimeError("ASR 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")

        return self._submit_task_with_retry(audio_url)

    @retry(
        stop=stop_after_attempt(RETRY_CONFIG["max_attempts"]),
        wait=wait_exponential(multiplier=1, min=RETRY_CONFIG["min_wait"], max=RETRY_CONFIG["max_wait"]),
        retry=retry_if_exception_type(ASRSubmitException),
        before_sleep=lambda retry_state: logger.warning(
            "ASR 提交任务失败，%d 秒后重试 (第 %d/%d 次): %s",
            retry_state.next_action.sleep, retry_state.attempt_number, RETRY_CONFIG["max_attempts"],
            retry_state.outcome.exception()
        ),
        reraise=True,
    )
    def _submit_task_with_retry(self, audio_url: str) -> str:
        """内部方法：带重试的任务提交。业务错误不重试，只有网络/API 错误会重试。"""
        request = CommonRequest()
        request.set_domain(ASR_DOMAIN)
        request.set_version(ASR_API_VERSION)
        request.set_product(ASR_PRODUCT)
        request.set_action_name("SubmitTask")
        request.set_method("POST")
        task = {
            "appkey": ASR_APP_KEY,
            "file_link": audio_url,
            "version": "4.0",
            "enable_words": False,
        }
        request.add_body_params("Task", json.dumps(task))
        try:
            response = self._acs.do_action_with_exception(request)
            data = json.loads(response)
            if data.get("StatusText") != "SUCCESS":
                # 业务错误，直接抛出 RuntimeError，不重试
                raise RuntimeError(f"任务提交失败: {data.get('StatusText')}")
            logger.info("ASR 任务提交成功: %s", data.get("TaskId"))
            return data["TaskId"]
        except RuntimeError:
            # 业务错误，直接抛出不重试
            raise
        except Exception as e:
            logger.error("ASR 提交任务失败: %s", e)
            # 网络/API 错误，包装为可重试异常
            raise ASRSubmitException(f"ASR 提交任务失败: {e}") from e

    @retry(
        stop=stop_after_attempt(RETRY_CONFIG["max_attempts"]),
        wait=wait_exponential(multiplier=1, min=RETRY_CONFIG["min_wait"], max=RETRY_CONFIG["max_wait"]),
        retry=retry_if_exception_type(ASRPollException),
        before_sleep=lambda retry_state: logger.warning(
            "ASR 查询请求失败，%d 秒后重试 (第 %d/%d 次): %s",
            retry_state.next_action.sleep, retry_state.attempt_number, RETRY_CONFIG["max_attempts"],
            retry_state.outcome.exception()
        ),
        reraise=True,
    )
    def _poll_asr_result(self, task_id: str) -> dict:
        """单次查询 ASR 结果，失败会自动重试"""
        request = CommonRequest()
        request.set_domain(ASR_DOMAIN)
        request.set_version(ASR_API_VERSION)
        request.set_product(ASR_PRODUCT)
        request.set_action_name("GetTaskResult")
        request.set_method("GET")
        request.add_query_param("TaskId", task_id)

        try:
            response = self._acs.do_action_with_exception(request)
            return json.loads(response)
        except Exception as e:
            logger.warning("ASR 查询请求失败: %s", e)
            raise ASRPollException(f"ASR 查询失败: {e}") from e

    def get_result(self, task_id: str, max_retries: int = 180, poll_interval: int = 10):
        """
        轮询并返回 ASR 结果。
        成功返回 Result 字典，无有效片段返回 None，失败返回 None。
        对单次查询失败会进行重试。

        Args:
            task_id: ASR 任务 ID
            max_retries: 最大轮询次数，默认 180 次（约 30 分钟）
            poll_interval: 轮询间隔（秒），默认 10 秒
        """
        if not ASR_APP_KEY:
            raise RuntimeError("ASR 未配置：请设置 ASR_APP_KEY")
        if self._acs is None:
            raise RuntimeError("ASR 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")

        poll_count = 0
        last_exception = None

        while poll_count < max_retries:
            try:
                data = self._poll_asr_result(task_id)
                status = data.get("StatusText")
                logger.info("ASR 查询响应 (第%d次): status=%s", poll_count + 1, status)

                if status in ("RUNNING", "QUEUEING"):
                    poll_count += 1
                    if poll_count >= max_retries:
                        logger.error("ASR 任务轮询超时: %s, 已等待 %d 秒", task_id, max_retries * poll_interval)
                        raise TimeoutError(f"ASR 任务处理超时，超过 {max_retries * poll_interval} 秒")
                    time.sleep(poll_interval)
                    continue

                # 任务完成
                if status == "SUCCESS":
                    logger.info("ASR 任务完成: %s", task_id)
                    return data.get("Result")
                if status == "SUCCESS_WITH_NO_VALID_FRAGMENT":
                    logger.warning("视频没有有效的音频片段")
                    return None
                logger.error("转写失败，状态: %s", status)
                return None

            except ASRPollException as e:
                # 单次查询失败，由 tenacity 处理重试
                last_exception = e
                poll_count += 1
                if poll_count < max_retries:
                    logger.warning("ASR 查询失败，继续轮询: %s", e)
                    time.sleep(poll_interval)
                else:
                    break

        logger.error("ASR 轮询最终失败: %s", last_exception)
        raise last_exception or RuntimeError("ASR 轮询失败")

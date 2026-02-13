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
)

logger = logging.getLogger(__name__)


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
        """上传本地文件到 OSS，返回 (访问 URL, OSS 路径)。"""
        if not self._bucket:
            raise RuntimeError("OSS 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"本地文件不存在: {local_path}")

        oss_path = os.path.basename(local_path)
        logger.info("上传文件到 OSS: %s", oss_path)
        with open(local_path, "rb") as f:
            self._bucket.put_object(oss_path, f)
        url = f"https://{OSS_BUCKET_NAME}.{OSS_ENDPOINT}/{oss_path}"
        return url, oss_path

    def submit_task(self, audio_url: str) -> str:
        """提交 ASR 转写任务，返回 TaskId。"""
        if not ASR_APP_KEY:
            raise RuntimeError("ASR 未配置：请设置 ASR_APP_KEY")
        if self._acs is None:
            raise RuntimeError("ASR 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")
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
        response = self._acs.do_action_with_exception(request)
        data = json.loads(response)
        if data.get("StatusText") != "SUCCESS":
            raise RuntimeError(f"任务提交失败: {data.get('StatusText')}")
        return data["TaskId"]

    def get_result(self, task_id: str, max_retries: int = 180, poll_interval: int = 10):
        """
        轮询并返回 ASR 结果。
        成功返回 Result 字典，无有效片段返回 None，失败返回 None。

        Args:
            task_id: ASR 任务 ID
            max_retries: 最大轮询次数，默认 180 次（约 30 分钟）
            poll_interval: 轮询间隔（秒），默认 10 秒
        """
        if not ASR_APP_KEY:
            raise RuntimeError("ASR 未配置：请设置 ASR_APP_KEY")
        if self._acs is None:
            raise RuntimeError("ASR 未配置：请设置 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET")
        request = CommonRequest()
        request.set_domain(ASR_DOMAIN)
        request.set_version(ASR_API_VERSION)
        request.set_product(ASR_PRODUCT)
        request.set_action_name("GetTaskResult")
        request.set_method("GET")
        request.add_query_param("TaskId", task_id)

        retry_count = 0
        while retry_count < max_retries:
            response = self._acs.do_action_with_exception(request)
            data = json.loads(response)
            status = data.get("StatusText")
            logger.info("ASR 查询响应 (第%d次): %s", retry_count + 1, data)
            if status in ("RUNNING", "QUEUEING"):
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error("ASR 任务轮询超时: %s, 已等待 %d 秒", task_id, max_retries * poll_interval)
                    raise TimeoutError(f"ASR 任务处理超时，超过 {max_retries * poll_interval} 秒")
                time.sleep(poll_interval)
                continue
            break

        if status == "SUCCESS":
            return data.get("Result")
        if status == "SUCCESS_WITH_NO_VALID_FRAGMENT":
            logger.warning("视频没有有效的音频片段")
            return None
        logger.error("转写失败，状态: %s", status)
        return None

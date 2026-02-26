"""
转录文本的 AI 分析：调用大模型提取重要对话并生成剪辑顺序。
使用 urllib 直连 DeepSeek API，避免 openai/httpx 版本兼容问题。
"""

import json
import logging
import os
import urllib.request
import urllib.error

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from config.config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL, VIDEO_PROCESS_CONFIG, RETRY_CONFIG


# 可重试的异常
timeout_errors = (TimeoutError, urllib.error.URLError)
server_errors = (urllib.error.HTTPError,)


class AIAnalysisException(Exception):
    """AI 分析异常，可重试"""
    pass

logger = logging.getLogger(__name__)

MERGED_FILENAME = "merged_transcripts.txt"
IMPORTANT_DIALOGUES_FILENAME = "important_dialogues.txt"
CLIP_ORDER_FILENAME = "clip_order.txt"

DEFAULT_SYSTEM_PROMPT = """你是一个专业的转录文件分析剪辑师，擅长从音频或视频转录的文本中提取关键信息、整理内容并进行逻辑剪辑。你的任务包括但不限于：

文本分析：仔细阅读转录文本，理解上下文，识别重要信息、主题和关键点。
内容剪辑：根据用户需求，对文本进行精简、重组或分段，确保逻辑清晰、重点突出。
格式优化：请必须按照原格式输出，不要添加任何内容。文件的格式示例如下：

===文件名===
[00:00:00.000 - 00:00:05.000] 你说他们的菜单跟北京菜单一一样，他们那的菜单跟北京一样一样。
===文件名===
[00:00:06.000 - 00:00:05.000] 你说他们的菜单跟北京菜单一一样，他们那的菜单跟北京一样一样。

重要：你输出的每一行片段顺序即为最终成片的播放顺序。你可以根据重要性、逻辑或叙事需要自由排列片段——例如把后面视频中的某段放到最前面也可以。每个片段保持 ===文件名===（不含扩展名）与 [开始时间 - 结束时间] 的格式即可。

请去除内容重复或高度相似的片段，只保留最有代表性的部分。
"""

# 向后兼容：SYSTEM_PROMPT 是 DEFAULT_SYSTEM_PROMPT 的别名
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


def _get_system_prompt() -> str:
    """
    获取系统提示词。优先级：
    1. 配置文件指定的文件 (AI_SYSTEM_PROMPT_FILE)
    2. 环境变量 (AI_SYSTEM_PROMPT)
    3. 默认提示词
    """
    # 1. 尝试从文件读取
    prompt_file = VIDEO_PROCESS_CONFIG.get("ai", {}).get("system_prompt_file", "")
    if prompt_file and os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                prompt = f.read().strip()
            if prompt:
                logger.info("已从文件加载系统提示词: %s", prompt_file)
                return prompt
        except Exception as e:
            logger.warning("读取提示词文件失败: %s - %s", prompt_file, e)

    # 2. 尝试从环境变量读取
    env_prompt = VIDEO_PROCESS_CONFIG.get("ai", {}).get("system_prompt", "")
    if env_prompt:
        logger.info("已从环境变量加载系统提示词")
        return env_prompt

    # 3. 使用默认提示词
    logger.debug("使用默认系统提示词")
    return DEFAULT_SYSTEM_PROMPT


def analyze_merged_transcripts(
    output_dir: str,
    user_text: str,
    fallback_to_transcription_only: bool = True,
) -> str | None:
    """
    读取 output_dir 下的 merged_transcripts.txt，调用 DeepSeek 分析，
    写入 important_dialogues.txt 与 clip_order.txt。返回分析结果文本。

    Args:
        output_dir: 输出目录
        user_text: 用户提示文本
        fallback_to_transcription_only: AI 失败时是否降级为仅转录（不剪辑），默认为 True

    Returns:
        分析结果文本，失败时返回 None（如果启用了降级）
    """
    merged_path = os.path.join(output_dir, MERGED_FILENAME)
    if not os.path.exists(merged_path):
        logger.error("找不到合并的转录文件: %s", merged_path)
        raise FileNotFoundError(merged_path)

    with open(merged_path, "r", encoding="utf-8") as f:
        transcript_content = f.read().strip()
    if not transcript_content:
        raise ValueError("合并转录内容为空")

    if not DEEPSEEK_API_KEY:
        logger.error("未配置 DEEPSEEK_API_KEY")
        if fallback_to_transcription_only:
            logger.warning("降级为仅转录模式（不剪辑）")
            _create_fallback_clip_order(output_dir, transcript_content)
            return None
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")

    user_hint = (user_text or "请提取重要对话并保持时间戳格式").strip()
    user_prompt = f"{user_hint}\n\n转录文件如下:\n\n{transcript_content}"
    logger.info("用户提示: %s", user_prompt[:200])

    try:
        analysis_result = _call_ai_api(user_prompt)
    except Exception as e:
        logger.error("AI 分析失败: %s", e)
        if fallback_to_transcription_only:
            logger.warning("降级为仅转录模式（不剪辑）")
            _create_fallback_clip_order(output_dir, transcript_content)
            return None
        raise

    important_path = os.path.join(output_dir, IMPORTANT_DIALOGUES_FILENAME)
    with open(important_path, "w", encoding="utf-8") as f:
        f.write(analysis_result)
    logger.info("分析结果已保存: %s", important_path)

    # 解析顺序即大模型返回顺序，写入时不得重排
    clip_order = _parse_analysis_to_clip_order(analysis_result)
    clip_order_path = os.path.join(output_dir, CLIP_ORDER_FILENAME)
    with open(clip_order_path, "w", encoding="utf-8") as f:
        for clip in clip_order:
            f.write(f"{clip['video']}\t{clip['start_time']}\t{clip['end_time']}\n")
    logger.info("剪辑顺序已保存（共 %d 条，顺序与大模型返回一致）: %s", len(clip_order), clip_order_path)

    return analysis_result


def _create_fallback_clip_order(output_dir: str, transcript_content: str) -> None:
    """
    当 AI 分析失败时的降级方案：将整个视频作为一个片段输出。
    这样用户至少能获得转录文本和完整视频，而不是完全失败。
    """
    # 写入空的 important_dialogues.txt 表示降级模式
    important_path = os.path.join(output_dir, IMPORTANT_DIALOGUES_FILENAME)
    with open(important_path, "w", encoding="utf-8") as f:
        f.write("# AI 分析失败，降级为仅转录模式\n")
        f.write("# 完整转录内容见 merged_transcripts.txt\n")
    logger.info("降级模式：已创建 %s", important_path)

    # 从转录内容中解析出视频名和时间范围
    # 格式：===文件名===\n[00:00:00.000 - 00:05:30.000] 文本内容
    clip_order = []
    current_video = None
    current_start = None
    current_end = None

    for line in transcript_content.split("\n"):
        line = line.strip()
        if line.startswith("===") and line.endswith("==="):
            # 保存上一个视频的片段
            if current_video and current_start and current_end:
                clip_order.append({
                    "video": current_video,
                    "start_time": current_start,
                    "end_time": current_end,
                })
            current_video = line.strip("= ")
            current_start = None
            current_end = None
        elif line.startswith("[") and current_video:
            try:
                time_part = line[1:].split("]")[0]
                start_time, end_time = time_part.split(" - ", 1)
                if current_start is None:
                    current_start = start_time.strip()
                current_end = end_time.strip()
            except Exception as e:
                logger.warning("解析时间戳失败: %s - %s", line, e)

    # 保存最后一个视频
    if current_video and current_start and current_end:
        clip_order.append({
            "video": current_video,
            "start_time": current_start,
            "end_time": current_end,
        })

    if clip_order:
        clip_order_path = os.path.join(output_dir, CLIP_ORDER_FILENAME)
        with open(clip_order_path, "w", encoding="utf-8") as f:
            for clip in clip_order:
                f.write(f"{clip['video']}\t{clip['start_time']}\t{clip['end_time']}\n")
        logger.info("降级模式：已创建完整视频剪辑顺序 %s（共 %d 个视频）", clip_order_path, len(clip_order))
    else:
        logger.warning("降级模式：无法从转录内容解析剪辑顺序")


def _time_to_seconds(time_str: str) -> float:
    """将时间字符串转换为秒数"""
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        else:
            return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


@retry(
    stop=stop_after_attempt(RETRY_CONFIG["max_attempts"]),
    wait=wait_exponential(multiplier=1, min=RETRY_CONFIG["min_wait"], max=RETRY_CONFIG["max_wait"]),
    retry=retry_if_exception_type((timeout_errors + server_errors + (AIAnalysisException,))),
    before_sleep=lambda retry_state: logger.warning(
        "AI API 调用失败，%d 秒后重试 (第 %d/%d 次): %s",
        retry_state.next_action.sleep, retry_state.attempt_number, RETRY_CONFIG["max_attempts"],
        retry_state.outcome.exception()
    ),
)
def _call_ai_api(user_prompt: str) -> str:
    """
    调用 AI API 进行内容分析，带有重试机制。
    重试条件：网络超时、服务器错误（5xx）、连接错误
    """
    url = f"{DEEPSEEK_API_URL.rstrip('/')}/chat/completions"
    system_prompt = _get_system_prompt()
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            completion = json.loads(resp.read().decode())
        return completion["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        # 5xx 错误可重试，4xx 错误不重试
        if e.code >= 500:
            logger.warning("AI API 服务器错误 (HTTP %d)，将重试", e.code)
            raise AIAnalysisException(f"AI API 服务器错误: {e.code}") from e
        else:
            logger.error("AI API 客户端错误 (HTTP %d)，不重试", e.code)
            raise
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("AI API 网络错误，将重试: %s", e)
        raise AIAnalysisException(f"AI API 网络错误: {e}") from e


def _parse_analysis_to_clip_order(text: str) -> list:
    """
    从 AI 分析文本中解析出剪辑顺序列表。
    严格按文本中行出现的顺序输出，不重排、不按视频名排序，以保证与大模型返回顺序一致。
    同时去除时间重叠的重复片段。
    """
    clip_order = []
    current_video = ""
    seen_clips = set()  # 用于去重: (video, start_time, end_time)

    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped.startswith("==="):
            current_video = line_stripped.strip("= ").strip()
        elif line_stripped.startswith("["):
            if not current_video:
                continue
            try:
                time_part = line_stripped[1:].split("]")[0]
                start_time, end_time = time_part.split(" - ", 1)
                start_time = start_time.strip()
                end_time = end_time.strip()

                if not start_time or not end_time:
                    continue

                # 转换为秒数进行去重判断
                start_sec = _time_to_seconds(start_time)
                end_sec = _time_to_seconds(end_time)

                if start_sec >= end_sec:
                    logger.warning("无效时间段: %s - %s", start_time, end_time)
                    continue

                # 检查是否与已处理的片段时间重叠
                is_duplicate = False
                for seen_video, seen_start, seen_end in seen_clips:
                    if seen_video != current_video:
                        continue
                    # 计算时间重叠
                    overlap_start = max(start_sec, seen_start)
                    overlap_end = min(end_sec, seen_end)
                    if overlap_start < overlap_end:
                        overlap_duration = overlap_end - overlap_start
                        min_duration = min(end_sec - start_sec, seen_end - seen_start)
                        # 如果重叠超过 80% 认为是重复
                        if overlap_duration / min_duration > 0.8:
                            is_duplicate = True
                            logger.debug(
                                "跳过重复片段: %s [%s - %s] (与 [%s - %s] 重叠 %.1f%%)",
                                current_video, start_time, end_time,
                                seen_start, seen_end, overlap_duration / min_duration * 100
                            )
                            break

                if is_duplicate:
                    continue

                seen_clips.add((current_video, start_sec, end_sec))
                clip_order.append({
                    "video": current_video,
                    "start_time": start_time,
                    "end_time": end_time,
                })
            except Exception as e:
                logger.error("解析时间戳失败: %s - %s", line_stripped, e)

    if len(clip_order) < len(seen_clips) + sum(1 for line in text.split("\n") if line.strip().startswith("[")):
        logger.info("去重完成: 移除了 %d 个重复片段", len(seen_clips) - len(clip_order))

    return clip_order

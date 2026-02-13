"""
视频处理编排：转录、分析、裁剪、合并、字幕。
对外接口保持不变，具体逻辑委托给 core 下各子模块。
"""

import json
import logging
import os

from config.config import VIDEO_PROCESS_CONFIG
from utils.time import seconds_to_time

from core.asr_client import ASRClient
from core.audio_extractor import extract_audio, extract_audio_ffmpeg
from core.transcript_merger import merge_transcripts as merge_transcripts_impl
from core.ai_analyzer import analyze_merged_transcripts as analyze_merged_transcripts_impl
from core.clip_cutter import (
    process_clips as process_clips_impl,
    merge_video_clips as merge_video_clips_impl,
)
from core.subtitle_renderer import add_subtitles as add_subtitles_impl
from core.exceptions import ASRError
from utils.path_security import sanitize_filename, get_safe_output_path

logger = logging.getLogger(__name__)

MERGED_VIDEO_FILENAME = "merged_highlights.mp4"


class VideoProcessor:
    """视频处理入口：维护任务目录与视频映射，编排转录/分析/裁剪/合并/字幕。"""

    def __init__(self, task_output_dir: str):
        self.output_dir = os.path.abspath(task_output_dir)
        self.temp_dir = os.path.join(self.output_dir, "temp")
        self.cuts_dir = os.path.join(self.output_dir, "cuts")
        self.config = VIDEO_PROCESS_CONFIG
        self.video_paths = {}
        self.text = ""
        self.caption_enable = False
        self.transfer_enable = False
        self._asr_client = ASRClient()

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.cuts_dir, exist_ok=True)

    def set_text(self, text: str) -> None:
        self.text = text or ""

    def set_caption_enable(self, caption_enable: bool) -> None:
        self.caption_enable = bool(caption_enable)

    def set_transfer_enable(self, transfer_enable: bool) -> None:
        self.transfer_enable = bool(transfer_enable)

    def save_info_to_file(self) -> None:
        path = os.path.join(self.output_dir, "info.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "text": self.text,
                "caption_enable": self.caption_enable,
                "transfer_enable": self.transfer_enable,
            }, f, ensure_ascii=False, indent=2)

    def add_video(self, filename: str, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"视频文件不存在: {file_path}")

        # 清理文件名，防止路径遍历
        safe_filename = sanitize_filename(filename)
        if safe_filename != filename:
            logger.warning("文件名已清理: %s -> %s", filename, safe_filename)

        self.video_paths[safe_filename] = file_path
        logger.info("添加视频映射: %s -> %s", safe_filename, file_path)

    def process_directory(self) -> None:
        video_files = list(self.video_paths.keys())
        if not video_files:
            logger.error("没有找到已映射的视频文件")
            return
        logger.info("找到 %d 个视频文件", len(video_files))
        for filename in video_files:
            try:
                logger.info("处理文件: %s", filename)
                self.process_single_video(filename)
            except Exception as e:
                logger.error("处理文件 %s 时出错: %s", filename, e)
        merged_path = self.merge_transcripts()
        if not merged_path or not os.path.exists(merged_path):
            logger.error("无有效转录文件，跳过分析与剪辑")
            return
        merged_file = os.path.join(self.output_dir, "merged_transcripts.txt")
        if os.path.getsize(merged_file) == 0:
            logger.error("合并转录为空，跳过分析与剪辑")
            return
        try:
            self.analyze_merged_transcripts()
        except Exception as e:
            logger.exception("分析合并转录时出错: %s", e)
            return
        clip_order_path = os.path.join(self.output_dir, "clip_order.txt")
        if not os.path.exists(clip_order_path) or os.path.getsize(clip_order_path) == 0:
            logger.error("未生成有效剪辑顺序，跳过裁剪与合并")
            return
        self.process_clips()
        out_path = self.merge_video_clips()
        if not out_path:
            logger.error("合并成片未产生输出")

    def process_single_video(self, filename: str) -> str | None:
        """处理单个视频：提取音频 -> OSS -> ASR -> 保存转录 JSON。返回转录文件路径或 None。"""
        video_path = self.video_paths.get(filename)
        if not video_path:
            raise FileNotFoundError(f"未找到视频文件映射: {filename}")
        base_name = os.path.splitext(filename)[0]
        audio_output = os.path.join(self.temp_dir, f"{base_name}_audio.mp3")
        transcript_path = os.path.join(self.temp_dir, f"{base_name}_transcript.json")

        try:
            logger.info("开始提取音频: %s", video_path)
            try:
                extract_audio(video_path, audio_output)
            except Exception as e:
                logger.warning("提取音频失败，尝试 ffmpeg: %s", e)
                extract_audio_ffmpeg(video_path, audio_output)
            if not os.path.exists(audio_output):
                logger.warning("视频没有音轨: %s", filename)
                return None

            url, _ = self._asr_client.upload_to_oss(audio_output)
            task_id = self._asr_client.submit_task(url)
            logger.info("ASR 任务已提交，TaskId: %s", task_id)
            result = self._asr_client.get_result(task_id)
            if result is None:
                logger.warning("视频 %s 没有有效的音频内容，跳过转写", filename)
                return None

            formatted = []
            for s in result.get("Sentences", []):
                start_sec = s.get("BeginTime", 0) / 1000
                end_sec = s.get("EndTime", 0) / 1000
                formatted.append({
                    "start_time": start_sec,
                    "end_time": end_sec,
                    "text": s.get("Text", ""),
                    "start_time_formatted": seconds_to_time(start_sec),
                    "end_time_formatted": seconds_to_time(end_sec),
                })
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(formatted, f, ensure_ascii=False, indent=2)
            logger.info("转写结果已保存: %s", transcript_path)
            return transcript_path
        except ASRError:
            raise
        except Exception as e:
            logger.exception("ASR 处理失败: %s", e)
            raise
        finally:
            if os.path.exists(audio_output):
                try:
                    os.remove(audio_output)
                except OSError:
                    pass

    def merge_transcripts(self) -> str:
        """合并所有转录文件为 merged_transcripts.txt，顺序与 video_paths 一致。"""
        order = [os.path.splitext(name)[0] for name in self.video_paths]
        return merge_transcripts_impl(self.temp_dir, self.output_dir, order_base_names=order)

    def analyze_merged_transcripts(self) -> str:
        """分析合并转录并生成 important_dialogues.txt、clip_order.txt。"""
        return analyze_merged_transcripts_impl(self.output_dir, self.text)

    def process_clips(self) -> None:
        """按 clip_order.txt 裁剪并保存到 cuts 目录。"""
        process_clips_impl(self.output_dir, self.cuts_dir, self.video_paths)

    def merge_video_clips(self, output_dir: str | None = None, cleanup_cuts: bool | None = None) -> str | None:
        """
        按顺序合并 cuts 下片段。output_dir 为空时使用 self.output_dir（兼容 main --merge 传入目录）。

        Args:
            output_dir: 输出目录，默认为 self.output_dir
            cleanup_cuts: 合并成功后是否清理 cuts 目录中的中间片段，None 时使用配置默认值
        """
        out_dir = output_dir or self.output_dir
        # 如果未指定 cleanup_cuts，使用配置默认值
        if cleanup_cuts is None:
            cleanup_cuts = self.config.get("output", {}).get("cleanup_cuts", True)
        return merge_video_clips_impl(self.cuts_dir, out_dir, MERGED_VIDEO_FILENAME, cleanup_cuts=cleanup_cuts)

    def cleanup_temp_files(self, keep_transcripts: bool = True) -> None:
        """
        清理临时文件以释放磁盘空间。

        Args:
            keep_transcripts: 是否保留转录文件（用于调试），默认为 True
        """
        import shutil

        # 清理 temp 目录中的音频文件（转录 JSON 保留用于调试）
        if os.path.exists(self.temp_dir):
            for f in os.listdir(self.temp_dir):
                if f.endswith('_audio.mp3'):
                    try:
                        os.remove(os.path.join(self.temp_dir, f))
                        logger.info(f"已清理音频文件: {f}")
                    except OSError as e:
                        logger.warning(f"清理音频文件失败: {f}, {e}")

        logger.info(f"临时文件清理完成，output_dir 保留: {self.output_dir}")

    def cleanup_all(self) -> None:
        """清理所有临时和中间文件，仅保留最终输出"""
        import shutil

        # 清理 temp 目录
        if os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logger.info(f"已清理 temp 目录: {self.temp_dir}")
            except OSError as e:
                logger.warning(f"清理 temp 目录失败: {e}")

        # 清理 cuts 目录
        if os.path.exists(self.cuts_dir):
            try:
                shutil.rmtree(self.cuts_dir)
                logger.info(f"已清理 cuts 目录: {self.cuts_dir}")
            except OSError as e:
                logger.warning(f"清理 cuts 目录失败: {e}")

    def add_subtitles(
        self,
        video_path: str | None = None,
        output_dir: str | None = None,
        fallback_on_error: bool = True,
    ) -> str | None:
        """
        为视频添加字幕。不传参时对 self.output_dir/merged_highlights.mp4 添加字幕（任务流）；
        传参时对指定 video_path 添加字幕并输出到 output_dir（main --add-subtitles）。

        Args:
            video_path: 输入视频路径
            output_dir: 输出目录
            fallback_on_error: 字幕生成失败时是否返回原视频（不中断流程），默认为 True

        Returns:
            输出视频路径，失败时返回 None 或原视频路径（取决于 fallback_on_error）
        """
        out_dir = output_dir or self.output_dir
        if video_path is None:
            video_path = os.path.join(self.output_dir, MERGED_VIDEO_FILENAME)
        if not os.path.exists(video_path):
            logger.error("视频不存在: %s", video_path)
            return None

        try:
            return add_subtitles_impl(
                video_path,
                out_dir,
                output_basename=os.path.basename(video_path).replace(".mp4", "_with_subtitles.mp4") if output_dir else None,
                asr_client=self._asr_client,
                temp_dir=self.temp_dir,
            )
        except Exception as e:
            logger.error("添加字幕失败: %s", e)
            if fallback_on_error:
                logger.warning("字幕添加失败，返回原视频: %s", video_path)
                return video_path
            return None

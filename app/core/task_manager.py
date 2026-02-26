import asyncio
import logging
import os
import traceback
from datetime import datetime
from typing import Dict, Optional
import json
from pathlib import Path
from core.video_processor import VideoProcessor
from core.persistence import TaskPersistence
from config.config import TASK_MANAGER_CONFIG

# 获取项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self, max_concurrent_tasks=3, task_timeout=600, persistence: Optional[TaskPersistence] = None):
        self.tasks: Dict[str, Dict] = {}
        self.video_processors: Dict[str, 'VideoProcessor'] = {}
        self.max_concurrent_tasks = max_concurrent_tasks
        self.task_timeout = task_timeout  # 任务超时时间（秒），默认10分钟
        self.processing_tasks = 0
        self.task_queue = asyncio.Queue()
        self._cancelled_tasks: set = set()  # 被取消的任务ID集合
        self.persistence = persistence
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def add_task(self, task_id: str, websocket, data: dict) -> None:
        """添加新任务到队列"""
        logger.info(f"添加新任务: {task_id}")

        # 创建任务专属目录
        task_output_dir = os.path.join(BASE_DIR, "output", task_id)
        os.makedirs(task_output_dir, exist_ok=True)

        # 保存任务信息
        self.tasks[task_id] = {
            'status': 'pending',
            'websocket': websocket,
            'data': data,
            'created_at': datetime.now(),
            'output_dir': task_output_dir
        }

        # 持久化任务
        if self.persistence:
            await self.persistence.save_task(
                task_id=task_id,
                status='pending',
                data=data,
                output_dir=task_output_dir
            )

        # 将任务加入队列
        await self.task_queue.put(task_id)
        # 尝试处理任务
        await self.process_next_task()
        
    async def process_next_task(self) -> None:
        """处理队列中的下一个任务"""
        if self.processing_tasks >= self.max_concurrent_tasks:
            return
            
        if not self.task_queue.empty():
            self.processing_tasks += 1
            task_id = await self.task_queue.get()
            asyncio.create_task(self.process_task(task_id))
            
    async def process_task(self, task_id: str) -> None:
        """处理单个任务，带超时控制"""
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            self.processing_tasks -= 1
            await self.process_next_task()
            return

        websocket = task['websocket']
        task['started_at'] = datetime.now()

        try:
            # 更新任务状态
            task['status'] = 'processing'
            if self.persistence:
                await self.persistence.save_task(task_id, 'processing')

            # 使用 wait_for 包装整个处理流程，添加超时控制
            await asyncio.wait_for(
                self._process_task_core(task_id, websocket),
                timeout=self.task_timeout
            )

            # 仅无异常时标为完成
            if task_id not in self._cancelled_tasks:
                task['status'] = 'completed'
                task['completed_at'] = datetime.now()
                if self.persistence:
                    await self.persistence.save_task(task_id, 'completed')

        except asyncio.TimeoutError:
            logger.error(f"任务 {task_id} 处理超时（{self.task_timeout}秒）")
            task['status'] = 'timeout'
            task['error'] = f'处理超时，超过{self.task_timeout}秒'
            if self.persistence:
                await self.persistence.save_task(task_id, 'timeout', error=task['error'])
            try:
                await self.send_websocket_message(
                    websocket, "error", task_id,
                    f"任务处理超时（{self.task_timeout}秒），请稍后重试或缩短视频"
                )
            except Exception as ws_err:
                logger.warning(f"发送超时通知失败: {ws_err}")

        except asyncio.CancelledError:
            logger.info(f"任务 {task_id} 被取消")
            task['status'] = 'cancelled'
            self._cancelled_tasks.discard(task_id)
            if self.persistence:
                await self.persistence.save_task(task_id, 'cancelled')
            try:
                await self.send_websocket_message(
                    websocket, "cancelled", task_id, "任务已取消"
                )
            except Exception as ws_err:
                logger.warning(f"发送取消通知失败: {ws_err}")
            raise  # 重新抛出以便上层处理

        except Exception as e:
            logger.error("任务处理失败: %s", e, exc_info=True)
            task['status'] = 'error'
            task['error'] = str(e)
            if self.persistence:
                await self.persistence.save_task(task_id, 'error', error=str(e))
            try:
                await self.send_websocket_message(
                    websocket, "error", task_id, f"任务失败: {str(e)}"
                )
            except Exception as ws_err:
                logger.warning(f"发送错误通知失败: {ws_err}")

        finally:
            # 清理资源
            if task_id in self.video_processors:
                del self.video_processors[task_id]

            self.processing_tasks -= 1
            # 检查是否有下一个任务
            await self.process_next_task()

    async def _process_task_core(self, task_id: str, websocket) -> None:
        """任务核心处理逻辑（被超时包装）"""
        task = self.tasks[task_id]
        data = task['data']
        output_dir = task['output_dir']

        # 检查是否被取消
        if task_id in self._cancelled_tasks:
            raise asyncio.CancelledError()

        processor = VideoProcessor(output_dir)
        processor.set_text(data.get('data', {}).get('text'))
        processor.set_caption_enable(data.get('data', {}).get('captionEnabled', False))
        processor.set_transfer_enable(data.get('data', {}).get('transferEnabled', False))
        processor.save_info_to_file()

        videos = data.get('data', {}).get('videos', [])
        logger.info(f"视频数量: {len(videos)}")
        logger.info(f"视频列表: {videos}")

        # 首先添加所有视频的路径映射
        await self._add_videos_to_processor(processor, videos, websocket, task_id)

        # 检查是否被取消
        if task_id in self._cancelled_tasks:
            raise asyncio.CancelledError()

        self.video_processors[task_id] = processor

        # 发送开始消息
        await self.send_websocket_message(websocket, "start", task_id, "开始处理视频")

        # 处理视频列表
        await self._clip_videos(processor, videos, websocket, task_id)

        # 检查是否被取消
        if task_id in self._cancelled_tasks:
            raise asyncio.CancelledError()

        # 所有视频处理完成后，进行合并和分析，裁剪
        await self._finalize_processing(processor, websocket, task_id)

    async def _add_videos_to_processor(self, processor, videos, websocket, task_id):
        """添加视频到处理器"""
        for video in videos:
            video_path = video.get("path")
            filename = video.get("filename")
            try:
                processor.add_video(filename, video_path)
                await self.send_websocket_message(
                    websocket, "progress", task_id, f"添加视频: {filename}"
                )
            except FileNotFoundError as e:
                logger.error(f"视频文件不存在: {video_path}")
                await self.send_websocket_message(
                    websocket, "error", task_id, f"视频文件不存在: {filename}"
                )
                return

    async def _clip_videos(self, processor, videos, websocket, task_id):
        """处理视频列表（同步方法在线程中执行）"""
        for video in videos:
            # 检查是否被取消
            if task_id in self._cancelled_tasks:
                raise asyncio.CancelledError()

            filename = video.get("filename")
            video_path = video.get("path")
            logger.info("视频路径: %s", video_path)

            try:
                await asyncio.to_thread(processor.process_single_video, filename)
                await self.send_websocket_message(
                    websocket, "progress", task_id, f"处理视频: {filename}"
                )
            except asyncio.CancelledError:
                raise  # 不应捕获，重新抛出
            except Exception as e:
                logger.error("处理视频 %s 失败: %s", filename, e, exc_info=True)
                await self.send_websocket_message(
                    websocket,
                    "error",
                    task_id,
                    f"处理视频失败: {filename} - {str(e)}",
                )
                # 单个视频失败不中断整体流程，继续处理下一个

    async def _finalize_processing(self, processor, websocket, task_id):
        """完成处理：合并转录、AI 分析、裁剪、合并成片、可选字幕（同步逻辑放线程执行）"""
        def _run():
            processor.merge_transcripts()
            merged = os.path.join(processor.output_dir, "merged_transcripts.txt")
            if not os.path.exists(merged) or os.path.getsize(merged) == 0:
                raise ValueError("无有效转录，无法继续分析")
            processor.analyze_merged_transcripts()
            clip_order = os.path.join(processor.output_dir, "clip_order.txt")
            if not os.path.exists(clip_order) or os.path.getsize(clip_order) == 0:
                raise ValueError("未生成剪辑顺序，无法裁剪")
            processor.process_clips()
            final_video_path = processor.merge_video_clips()
            if processor.caption_enable and final_video_path:
                processor.add_subtitles()
            return final_video_path

        try:
            final_video_path = await asyncio.to_thread(_run)
            task_output_dir = os.path.join(BASE_DIR, "output", task_id)
            logger.info("最终视频路径: %s", final_video_path)
            await self.send_websocket_message(
                websocket,
                "complete",
                task_id,
                "所有处理完成",
                outputPath=final_video_path,
                outputDir=task_output_dir,
            )
        except asyncio.CancelledError:
            raise  # 不应捕获，重新抛出
        except Exception as e:
            logger.exception("处理失败: %s", e)
            await self.send_websocket_message(
                websocket,
                "error",
                task_id,
                f"处理失败: {str(e)}",
            )
            raise

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        return self.tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定任务，返回是否成功取消"""
        task = self.tasks.get(task_id)
        if not task:
            return False

        # 只能取消 pending 或 processing 状态的任务
        if task['status'] not in ('pending', 'processing'):
            return False

        self._cancelled_tasks.add(task_id)

        if task['status'] == 'pending':
            # 队列中的任务直接标记为取消
            task['status'] = 'cancelled'
            logger.info(f"队列中的任务 {task_id} 已取消")
            if self.persistence:
                await self.persistence.save_task(task_id, 'cancelled')
            return True

        # processing 状态的任务会由 process_task 检查并处理
        logger.info(f"正在处理的任务 {task_id} 已标记取消")
        return True


            
    async def send_websocket_message(self, websocket, message_type, task_id, message, **kwargs):
        """发送 WebSocket 消息"""
        message_data = {
            "type": message_type,
            "data": {
                "taskId": task_id,
                "message": message,
                **kwargs
            }
        }
        await websocket.send(json.dumps(message_data))

    async def start_cleanup_scheduler(self, interval_hours: int = 24):
        """启动定期清理任务调度器"""
        if not self.persistence or not self.persistence.enabled:
            logger.info("持久化未启用，跳过清理调度器")
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)  # 转换为秒
                    deleted = await self.persistence.cleanup_old_tasks()
                    if deleted > 0:
                        logger.info("定期清理完成，删除了 %d 个旧任务", deleted)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("定期清理任务失败: %s", e)

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("清理调度器已启动，间隔: %d 小时", interval_hours)

    async def stop_cleanup_scheduler(self):
        """停止清理调度器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("清理调度器已停止")

    async def get_task_stats(self) -> dict:
        """获取任务统计信息"""
        stats = {
            "total": len(self.tasks),
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "error": 0,
            "timeout": 0,
            "cancelled": 0
        }
        for task in self.tasks.values():
            status = task.get('status', 'unknown')
            if status in stats:
                stats[status] += 1
        return stats

# 创建全局任务管理器实例（使用配置）
from core.persistence import task_persistence
task_manager = TaskManager(
    max_concurrent_tasks=TASK_MANAGER_CONFIG["max_concurrent_tasks"],
    task_timeout=TASK_MANAGER_CONFIG["task_timeout"],
    persistence=task_persistence
)
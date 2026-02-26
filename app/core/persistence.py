"""
任务持久化存储模块：使用 SQLite 存储任务状态，支持服务重启后恢复任务。
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from contextlib import contextmanager
import asyncio
import aiosqlite

from config.config import PERSISTENCE_CONFIG

logger = logging.getLogger(__name__)


class TaskPersistence:
    """任务持久化管理器"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or PERSISTENCE_CONFIG["db_path"]
        self.enabled = PERSISTENCE_CONFIG["enabled"]
        self._lock = asyncio.Lock()

        if self.enabled:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            # 同步初始化数据库（仅在启动时）
            self._init_db_sync()

    def _init_db_sync(self):
        """同步初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        data TEXT,
                        output_dir TEXT,
                        error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # 创建索引
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at)
                """)
                conn.commit()
                logger.info("任务持久化数据库初始化完成: %s", self.db_path)
        except Exception as e:
            logger.error("初始化任务数据库失败: %s", e)
            self.enabled = False

    @contextmanager
    def _get_sync_connection(self):
        """获取同步数据库连接"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                conn.close()

    async def _get_connection(self):
        """获取异步数据库连接"""
        return await aiosqlite.connect(self.db_path)

    async def save_task(self, task_id: str, status: str, data: Optional[Dict] = None,
                       output_dir: Optional[str] = None, error: Optional[str] = None):
        """保存或更新任务"""
        if not self.enabled:
            return

        async with self._lock:
            try:
                conn = await self._get_connection()
                try:
                    # 序列化数据
                    data_json = json.dumps(data, ensure_ascii=False) if data else None

                    # 检查任务是否存在
                    cursor = await conn.execute(
                        "SELECT task_id FROM tasks WHERE task_id = ?",
                        (task_id,)
                    )
                    existing = await cursor.fetchone()

                    now = datetime.now().isoformat()

                    if existing:
                        # 更新任务
                        await conn.execute("""
                            UPDATE tasks SET
                                status = ?,
                                data = ?,
                                output_dir = ?,
                                error = ?,
                                updated_at = ?
                            WHERE task_id = ?
                        """, (status, data_json, output_dir, error, now, task_id))
                    else:
                        # 插入新任务
                        await conn.execute("""
                            INSERT INTO tasks
                            (task_id, status, data, output_dir, error, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (task_id, status, data_json, output_dir, error, now, now))

                    # 更新 started_at 和 completed_at
                    if status == 'processing':
                        await conn.execute(
                            "UPDATE tasks SET started_at = ? WHERE task_id = ? AND started_at IS NULL",
                            (now, task_id)
                        )
                    elif status in ('completed', 'error', 'timeout', 'cancelled'):
                        await conn.execute(
                            "UPDATE tasks SET completed_at = ? WHERE task_id = ? AND completed_at IS NULL",
                            (now, task_id)
                        )

                    await conn.commit()
                    logger.debug("任务已持久化: %s - %s", task_id, status)
                finally:
                    await conn.close()
            except Exception as e:
                logger.error("保存任务失败: %s - %s", task_id, e)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        if not self.enabled:
            return None

        try:
            conn = await self._get_connection()
            try:
                cursor = await conn.execute(
                    "SELECT * FROM tasks WHERE task_id = ?",
                    (task_id,)
                )
                row = await cursor.fetchone()

                if row:
                    task = dict(row)
                    # 反序列化数据
                    if task.get('data'):
                        try:
                            task['data'] = json.loads(task['data'])
                        except json.JSONDecodeError:
                            task['data'] = None
                    return task
                return None
            finally:
                await conn.close()
        except Exception as e:
            logger.error("获取任务失败: %s - %s", task_id, e)
            return None

    async def get_tasks_by_status(self, status: str, limit: int = 100) -> list:
        """获取特定状态的任务列表"""
        if not self.enabled:
            return []

        try:
            conn = await self._get_connection()
            try:
                cursor = await conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                )
                rows = await cursor.fetchall()
                tasks = []
                for row in rows:
                    task = dict(row)
                    if task.get('data'):
                        try:
                            task['data'] = json.loads(task['data'])
                        except json.JSONDecodeError:
                            task['data'] = None
                    tasks.append(task)
                return tasks
            finally:
                await conn.close()
        except Exception as e:
            logger.error("获取任务列表失败: %s - %s", status, e)
            return []

    async def get_pending_tasks(self) -> list:
        """获取待处理的任务（用于服务重启后恢复）"""
        if not self.enabled:
            return []

        try:
            conn = await self._get_connection()
            try:
                # 获取 pending 和 processing 状态的任务
                cursor = await conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status IN ('pending', 'processing')
                    ORDER BY created_at ASC
                    """
                )
                rows = await cursor.fetchall()
                tasks = []
                for row in rows:
                    task = dict(row)
                    if task.get('data'):
                        try:
                            task['data'] = json.loads(task['data'])
                        except json.JSONDecodeError:
                            task['data'] = None
                    tasks.append(task)
                return tasks
            finally:
                await conn.close()
        except Exception as e:
            logger.error("获取待处理任务失败: %s", e)
            return []

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        if not self.enabled:
            return False

        async with self._lock:
            try:
                conn = await self._get_connection()
                try:
                    await conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                    await conn.commit()
                    logger.debug("任务已删除: %s", task_id)
                    return True
                finally:
                    await conn.close()
            except Exception as e:
                logger.error("删除任务失败: %s - %s", task_id, e)
                return False

    async def cleanup_old_tasks(self, days: Optional[int] = None) -> int:
        """清理旧的已完成任务"""
        if not self.enabled:
            return 0

        days = days or PERSISTENCE_CONFIG.get("auto_cleanup_days", 7)
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        async with self._lock:
            try:
                conn = await self._get_connection()
                try:
                    cursor = await conn.execute(
                        """
                        DELETE FROM tasks
                        WHERE status IN ('completed', 'error', 'timeout', 'cancelled')
                        AND completed_at < ?
                        """,
                        (cutoff_date,)
                    )
                    await conn.commit()
                    deleted_count = cursor.rowcount
                    if deleted_count > 0:
                        logger.info("已清理 %d 个旧任务", deleted_count)
                    return deleted_count
                finally:
                    await conn.close()
            except Exception as e:
                logger.error("清理旧任务失败: %s", e)
                return 0

    async def update_task_progress(self, task_id: str, progress: Dict[str, Any]):
        """更新任务进度（存储在 data 字段中）"""
        if not self.enabled:
            return

        try:
            task = await self.get_task(task_id)
            if task and task.get('data'):
                data = task['data']
                if 'progress' not in data:
                    data['progress'] = {}
                data['progress'].update(progress)
                await self.save_task(task_id, task['status'], data)
        except Exception as e:
            logger.error("更新任务进度失败: %s - %s", task_id, e)


# 全局持久化实例
task_persistence = TaskPersistence()

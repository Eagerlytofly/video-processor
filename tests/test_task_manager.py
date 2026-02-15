"""TaskManager 单元测试（Mock VideoProcessor 和 WebSocket）。"""
import asyncio
import json
import os
import pytest
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

# Import TaskManager
from core.task_manager import TaskManager


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def task_manager():
    """创建 TaskManager 实例（使用较小的超时以便测试）。"""
    return TaskManager(max_concurrent_tasks=2, task_timeout=30)


@pytest.fixture
def mock_websocket():
    """创建 Mock WebSocket。"""
    ws = AsyncMock()
    ws.send = AsyncMock()
    return ws


@pytest.fixture
def sample_task_data():
    """创建示例任务数据。"""
    return {
        "data": {
            "text": "测试文本",
            "captionEnabled": True,
            "transferEnabled": False,
            "videos": [
                {"filename": "video1.mp4", "path": "/fake/path/video1.mp4"},
                {"filename": "video2.mp4", "path": "/fake/path/video2.mp4"},
            ]
        }
    }


@pytest.fixture
def tmp_task_dir(tmp_path):
    """创建临时任务目录。"""
    task_dir = tmp_path / "output" / "task_123"
    task_dir.mkdir(parents=True)
    return str(task_dir)


# =============================================================================
# Test __init__
# =============================================================================

def test_init_default_values():
    """测试默认初始化参数。"""
    tm = TaskManager()
    assert tm.max_concurrent_tasks == 3
    assert tm.task_timeout == 600
    assert tm.tasks == {}
    assert tm.video_processors == {}
    assert tm.processing_tasks == 0
    assert isinstance(tm.task_queue, asyncio.Queue)
    assert tm._cancelled_tasks == set()


def test_init_custom_values():
    """测试自定义初始化参数。"""
    tm = TaskManager(max_concurrent_tasks=5, task_timeout=120)
    assert tm.max_concurrent_tasks == 5
    assert tm.task_timeout == 120


# =============================================================================
# Test add_task
# =============================================================================

@pytest.mark.asyncio
async def test_add_task_creates_task_entry(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 add_task 创建任务条目。"""
    with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock) as mock_process:
        with patch('core.task_manager.BASE_DIR', str(tmp_path)):
            await task_manager.add_task("task_123", mock_websocket, sample_task_data)

            assert "task_123" in task_manager.tasks
            task = task_manager.tasks["task_123"]
            assert task['status'] == 'pending'
            assert task['websocket'] == mock_websocket
            assert task['data'] == sample_task_data
            assert 'created_at' in task
            assert 'output_dir' in task
            mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_add_task_creates_output_directory(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 add_task 创建输出目录。"""
    with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
        with patch('core.task_manager.BASE_DIR', str(tmp_path)):
            await task_manager.add_task("task_456", mock_websocket, sample_task_data)

            output_dir = tmp_path / "output" / "task_456"
            assert output_dir.exists()


@pytest.mark.asyncio
async def test_add_task_puts_to_queue(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 add_task 将任务加入队列。"""
    with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
        with patch('core.task_manager.BASE_DIR', str(tmp_path)):
            await task_manager.add_task("task_789", mock_websocket, sample_task_data)

            assert not task_manager.task_queue.empty()
            queued_task = await task_manager.task_queue.get()
            assert queued_task == "task_789"


# =============================================================================
# Test process_next_task
# =============================================================================

@pytest.mark.asyncio
async def test_process_next_task_respects_concurrency_limit(task_manager):
    """测试 process_next_task 遵守并发限制。"""
    task_manager.processing_tasks = 2  # 已达到上限

    await task_manager.process_next_task()

    assert task_manager.processing_tasks == 2  # 未变化


@pytest.mark.asyncio
async def test_process_next_task_empty_queue(task_manager):
    """测试 process_next_task 处理空队列。"""
    task_manager.processing_tasks = 0

    await task_manager.process_next_task()

    assert task_manager.processing_tasks == 0


@pytest.mark.asyncio
async def test_process_next_task_starts_processing(task_manager):
    """测试 process_next_task 开始处理任务。"""
    task_manager.processing_tasks = 0
    await task_manager.task_queue.put("task_001")

    with patch.object(task_manager, 'process_task', new_callable=AsyncMock) as mock_process:
        await task_manager.process_next_task()

        assert task_manager.processing_tasks == 1
        mock_process.assert_called_once_with("task_001")


# =============================================================================
# Test process_task - Success Cases
# =============================================================================

@pytest.mark.asyncio
async def test_process_task_success_flow(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 process_task 成功流程。"""
    task_id = "task_success"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager.processing_tasks = 1

    with patch.object(task_manager, '_process_task_core', new_callable=AsyncMock) as mock_core:
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock) as mock_next:
            await task_manager.process_task(task_id)

            assert task_manager.tasks[task_id]['status'] == 'completed'
            assert 'completed_at' in task_manager.tasks[task_id]
            mock_core.assert_called_once_with(task_id, mock_websocket)
            mock_next.assert_called_once()


@pytest.mark.asyncio
async def test_process_task_not_found(task_manager):
    """测试 process_task 处理不存在的任务。"""
    task_manager.processing_tasks = 1

    with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock) as mock_next:
        await task_manager.process_task("nonexistent_task")

        assert task_manager.processing_tasks == 0
        mock_next.assert_called_once()


# =============================================================================
# Test process_task - Timeout
# =============================================================================

@pytest.mark.asyncio
async def test_process_task_timeout(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 process_task 超时处理。"""
    task_id = "task_timeout"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager.processing_tasks = 1
    task_manager.task_timeout = 0.1  # 100ms 超时

    async def slow_process(*args, **kwargs):
        await asyncio.sleep(1)  # 超过超时时间

    with patch.object(task_manager, '_process_task_core', side_effect=slow_process):
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            await task_manager.process_task(task_id)

            assert task_manager.tasks[task_id]['status'] == 'timeout'
            assert 'error' in task_manager.tasks[task_id]
            assert '超时' in task_manager.tasks[task_id]['error']


# =============================================================================
# Test process_task - Cancellation
# =============================================================================

@pytest.mark.asyncio
async def test_process_task_cancelled(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 process_task 取消处理。"""
    task_id = "task_cancelled"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager.processing_tasks = 1
    task_manager._cancelled_tasks.add(task_id)

    async def cancelled_process(*args, **kwargs):
        raise asyncio.CancelledError()

    with patch.object(task_manager, '_process_task_core', side_effect=cancelled_process):
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            with pytest.raises(asyncio.CancelledError):
                await task_manager.process_task(task_id)

            assert task_manager.tasks[task_id]['status'] == 'cancelled'
            assert task_id not in task_manager._cancelled_tasks


# =============================================================================
# Test process_task - Error Handling
# =============================================================================

@pytest.mark.asyncio
async def test_process_task_error_handling(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 process_task 错误处理。"""
    task_id = "task_error"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager.processing_tasks = 1

    async def error_process(*args, **kwargs):
        raise ValueError("测试错误")

    with patch.object(task_manager, '_process_task_core', side_effect=error_process):
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            await task_manager.process_task(task_id)

            assert task_manager.tasks[task_id]['status'] == 'error'
            assert task_manager.tasks[task_id]['error'] == "测试错误"


@pytest.mark.asyncio
async def test_process_task_cleans_up_processor(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 process_task 清理 processor。"""
    task_id = "task_cleanup"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager.processing_tasks = 1
    task_manager.video_processors[task_id] = MagicMock()

    with patch.object(task_manager, '_process_task_core', new_callable=AsyncMock):
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            await task_manager.process_task(task_id)

            assert task_id not in task_manager.video_processors


# =============================================================================
# Test _process_task_core
# =============================================================================

@pytest.mark.asyncio
async def test_process_task_core_checks_cancellation(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 _process_task_core 检查取消状态。"""
    task_id = "task_check_cancel"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }
    task_manager._cancelled_tasks.add(task_id)

    with pytest.raises(asyncio.CancelledError):
        await task_manager._process_task_core(task_id, mock_websocket)


@pytest.mark.asyncio
async def test_process_task_core_creates_processor(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 _process_task_core 创建 VideoProcessor。"""
    task_id = "task_create_processor"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }

    mock_processor = MagicMock()
    mock_processor.video_paths = {}

    with patch('core.task_manager.VideoProcessor', return_value=mock_processor):
        with patch.object(task_manager, '_add_videos_to_processor', new_callable=AsyncMock):
            with patch.object(task_manager, '_clip_videos', new_callable=AsyncMock):
                with patch.object(task_manager, '_finalize_processing', new_callable=AsyncMock):
                    await task_manager._process_task_core(task_id, mock_websocket)

                    assert task_id in task_manager.video_processors
                    mock_processor.set_text.assert_called_once_with("测试文本")
                    mock_processor.set_caption_enable.assert_called_once_with(True)
                    mock_processor.set_transfer_enable.assert_called_once_with(False)
                    mock_processor.save_info_to_file.assert_called_once()


@pytest.mark.asyncio
async def test_process_task_core_sends_start_message(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试 _process_task_core 发送开始消息。"""
    task_id = "task_start_msg"
    task_manager.tasks[task_id] = {
        'status': 'pending',
        'websocket': mock_websocket,
        'data': sample_task_data,
        'created_at': datetime.now(),
        'output_dir': str(tmp_path)
    }

    mock_processor = MagicMock()
    mock_processor.video_paths = {}

    with patch('core.task_manager.VideoProcessor', return_value=mock_processor):
        with patch.object(task_manager, '_add_videos_to_processor', new_callable=AsyncMock):
            with patch.object(task_manager, '_clip_videos', new_callable=AsyncMock):
                with patch.object(task_manager, '_finalize_processing', new_callable=AsyncMock):
                    with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
                        await task_manager._process_task_core(task_id, mock_websocket)

                        mock_send.assert_any_call(mock_websocket, "start", task_id, "开始处理视频")


# =============================================================================
# Test _add_videos_to_processor
# =============================================================================

@pytest.mark.asyncio
async def test_add_videos_to_processor_success(task_manager, mock_websocket):
    """测试 _add_videos_to_processor 成功添加视频。"""
    mock_processor = MagicMock()
    videos = [
        {"filename": "video1.mp4", "path": "/path/video1.mp4"},
        {"filename": "video2.mp4", "path": "/path/video2.mp4"},
    ]

    with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
        await task_manager._add_videos_to_processor(mock_processor, videos, mock_websocket, "task_123")

        assert mock_processor.add_video.call_count == 2
        mock_send.assert_any_call(mock_websocket, "progress", "task_123", "添加视频: video1.mp4")
        mock_send.assert_any_call(mock_websocket, "progress", "task_123", "添加视频: video2.mp4")


@pytest.mark.asyncio
async def test_add_videos_to_processor_file_not_found(task_manager, mock_websocket):
    """测试 _add_videos_to_processor 处理文件不存在。"""
    mock_processor = MagicMock()
    mock_processor.add_video.side_effect = FileNotFoundError("视频文件不存在")
    videos = [
        {"filename": "video1.mp4", "path": "/nonexistent/video1.mp4"},
    ]

    with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
        await task_manager._add_videos_to_processor(mock_processor, videos, mock_websocket, "task_123")

        mock_send.assert_any_call(mock_websocket, "error", "task_123", "视频文件不存在: video1.mp4")


# =============================================================================
# Test _clip_videos
# =============================================================================

@pytest.mark.asyncio
async def test_clip_videos_processes_each_video(task_manager, mock_websocket):
    """测试 _clip_videos 处理每个视频。"""
    mock_processor = MagicMock()
    videos = [
        {"filename": "video1.mp4", "path": "/path/video1.mp4"},
        {"filename": "video2.mp4", "path": "/path/video2.mp4"},
    ]

    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
        with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
            await task_manager._clip_videos(mock_processor, videos, mock_websocket, "task_123")

            assert mock_to_thread.call_count == 2
            mock_send.assert_any_call(mock_websocket, "progress", "task_123", "处理视频: video1.mp4")
            mock_send.assert_any_call(mock_websocket, "progress", "task_123", "处理视频: video2.mp4")


@pytest.mark.asyncio
async def test_clip_videos_checks_cancellation(task_manager, mock_websocket):
    """测试 _clip_videos 检查取消状态。"""
    mock_processor = MagicMock()
    videos = [
        {"filename": "video1.mp4", "path": "/path/video1.mp4"},
    ]
    task_id = "task_cancel_clip"
    task_manager._cancelled_tasks.add(task_id)

    with pytest.raises(asyncio.CancelledError):
        await task_manager._clip_videos(mock_processor, videos, mock_websocket, task_id)


@pytest.mark.asyncio
async def test_clip_videos_handles_error(task_manager, mock_websocket):
    """测试 _clip_videos 处理单个视频错误。"""
    mock_processor = MagicMock()
    videos = [
        {"filename": "video1.mp4", "path": "/path/video1.mp4"},
        {"filename": "video2.mp4", "path": "/path/video2.mp4"},
    ]

    async def mock_to_thread(func, *args):
        if args[0] == "video1.mp4":
            raise ValueError("处理失败")
        return None

    with patch('asyncio.to_thread', side_effect=mock_to_thread):
        with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
            await task_manager._clip_videos(mock_processor, videos, mock_websocket, "task_123")

            # 第二个视频应该继续处理
            mock_send.assert_any_call(mock_websocket, "error", "task_123", "处理视频失败: video1.mp4 - 处理失败")


@pytest.mark.asyncio
async def test_clip_videos_reraises_cancelled_error(task_manager, mock_websocket):
    """测试 _clip_videos 重新抛出 CancelledError。"""
    mock_processor = MagicMock()
    videos = [
        {"filename": "video1.mp4", "path": "/path/video1.mp4"},
    ]

    async def mock_to_thread(func, *args):
        raise asyncio.CancelledError()

    with patch('asyncio.to_thread', side_effect=mock_to_thread):
        with pytest.raises(asyncio.CancelledError):
            await task_manager._clip_videos(mock_processor, videos, mock_websocket, "task_123")


# =============================================================================
# Test _finalize_processing
# =============================================================================

@pytest.mark.asyncio
async def test_finalize_processing_success(task_manager, mock_websocket, tmp_path):
    """测试 _finalize_processing 成功流程。"""
    mock_processor = MagicMock()
    mock_processor.output_dir = str(tmp_path)
    mock_processor.caption_enable = False
    mock_processor.merge_video_clips.return_value = "/path/to/final_video.mp4"

    # Create the actual _run function that would be called in the thread
    def run_in_thread():
        mock_processor.merge_transcripts()
        mock_processor.analyze_merged_transcripts()
        mock_processor.process_clips()
        return mock_processor.merge_video_clips()

    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = "/path/to/final_video.mp4"
        with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
            with patch('core.task_manager.BASE_DIR', str(tmp_path)):
                await task_manager._finalize_processing(mock_processor, mock_websocket, "task_123")

                # Verify to_thread was called
                mock_to_thread.assert_called_once()
                # Verify complete message was sent with correct output path
                mock_send.assert_called_once()
                call_args = mock_send.call_args
                assert call_args[0][0] == mock_websocket
                assert call_args[0][1] == "complete"


@pytest.mark.asyncio
async def test_finalize_processing_with_caption(task_manager, mock_websocket, tmp_path):
    """测试 _finalize_processing 启用字幕。"""
    mock_processor = MagicMock()
    mock_processor.output_dir = str(tmp_path)
    mock_processor.caption_enable = True
    mock_processor.merge_video_clips.return_value = "/path/to/final_video.mp4"

    with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
        mock_to_thread.return_value = "/path/to/final_video.mp4"
        with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
            with patch('core.task_manager.BASE_DIR', str(tmp_path)):
                await task_manager._finalize_processing(mock_processor, mock_websocket, "task_123")

                # Verify to_thread was called
                mock_to_thread.assert_called_once()
                # Verify complete message was sent
                mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_finalize_processing_reraises_cancelled_error(task_manager, mock_websocket, tmp_path):
    """测试 _finalize_processing 重新抛出 CancelledError。"""
    mock_processor = MagicMock()
    mock_processor.output_dir = str(tmp_path)

    async def mock_to_thread(func):
        raise asyncio.CancelledError()

    with patch('asyncio.to_thread', side_effect=mock_to_thread):
        with pytest.raises(asyncio.CancelledError):
            await task_manager._finalize_processing(mock_processor, mock_websocket, "task_123")


@pytest.mark.asyncio
async def test_finalize_processing_handles_error(task_manager, mock_websocket, tmp_path):
    """测试 _finalize_processing 处理错误。"""
    mock_processor = MagicMock()
    mock_processor.output_dir = str(tmp_path)

    async def mock_to_thread(func):
        raise ValueError("合并失败")

    with patch('asyncio.to_thread', side_effect=mock_to_thread):
        with patch.object(task_manager, 'send_websocket_message', new_callable=AsyncMock) as mock_send:
            with pytest.raises(ValueError, match="合并失败"):
                await task_manager._finalize_processing(mock_processor, mock_websocket, "task_123")

            mock_send.assert_any_call(mock_websocket, "error", "task_123", "处理失败: 合并失败")


# =============================================================================
# Test get_task_status
# =============================================================================

def test_get_task_status_existing(task_manager):
    """测试 get_task_status 获取存在的任务。"""
    task_manager.tasks["task_001"] = {"status": "processing"}

    status = task_manager.get_task_status("task_001")

    assert status == {"status": "processing"}


def test_get_task_status_nonexistent(task_manager):
    """测试 get_task_status 获取不存在的任务。"""
    status = task_manager.get_task_status("nonexistent")

    assert status is None


# =============================================================================
# Test cancel_task
# =============================================================================

@pytest.mark.asyncio
async def test_cancel_task_pending(task_manager):
    """测试 cancel_task 取消 pending 状态任务。"""
    task_manager.tasks["task_001"] = {"status": "pending"}

    result = await task_manager.cancel_task("task_001")

    assert result is True
    assert task_manager.tasks["task_001"]["status"] == "cancelled"
    assert "task_001" in task_manager._cancelled_tasks


@pytest.mark.asyncio
async def test_cancel_task_processing(task_manager):
    """测试 cancel_task 取消 processing 状态任务。"""
    task_manager.tasks["task_001"] = {"status": "processing"}

    result = await task_manager.cancel_task("task_001")

    assert result is True
    assert task_manager.tasks["task_001"]["status"] == "processing"  # 状态不变，等待 process_task 处理
    assert "task_001" in task_manager._cancelled_tasks


@pytest.mark.asyncio
async def test_cancel_task_nonexistent(task_manager):
    """测试 cancel_task 取消不存在的任务。"""
    result = await task_manager.cancel_task("nonexistent")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_task_completed(task_manager):
    """测试 cancel_task 无法取消已完成任务。"""
    task_manager.tasks["task_001"] = {"status": "completed"}

    result = await task_manager.cancel_task("task_001")

    assert result is False
    assert "task_001" not in task_manager._cancelled_tasks


@pytest.mark.asyncio
async def test_cancel_task_error(task_manager):
    """测试 cancel_task 无法取消已失败任务。"""
    task_manager.tasks["task_001"] = {"status": "error"}

    result = await task_manager.cancel_task("task_001")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_task_cancelled(task_manager):
    """测试 cancel_task 无法取消已取消任务。"""
    task_manager.tasks["task_001"] = {"status": "cancelled"}

    result = await task_manager.cancel_task("task_001")

    assert result is False


# =============================================================================
# Test send_websocket_message
# =============================================================================

@pytest.mark.asyncio
async def test_send_websocket_message_basic(task_manager, mock_websocket):
    """测试 send_websocket_message 发送基本消息。"""
    await task_manager.send_websocket_message(mock_websocket, "progress", "task_123", "处理中")

    mock_websocket.send.assert_called_once()
    call_args = mock_websocket.send.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "progress"
    assert message["data"]["taskId"] == "task_123"
    assert message["data"]["message"] == "处理中"


@pytest.mark.asyncio
async def test_send_websocket_message_with_extra_params(task_manager, mock_websocket):
    """测试 send_websocket_message 发送带额外参数的消息。"""
    await task_manager.send_websocket_message(
        mock_websocket, "complete", "task_123", "完成",
        outputPath="/path/to/video.mp4", outputDir="/path/to/output"
    )

    call_args = mock_websocket.send.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "complete"
    assert message["data"]["outputPath"] == "/path/to/video.mp4"
    assert message["data"]["outputDir"] == "/path/to/output"


# =============================================================================
# Test Integration Scenarios
# =============================================================================

@pytest.mark.asyncio
async def test_full_task_lifecycle(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试完整任务生命周期。"""
    task_id = "task_lifecycle"

    with patch('core.task_manager.BASE_DIR', str(tmp_path)):
        with patch('core.task_manager.VideoProcessor') as mock_vp_class:
            mock_processor = MagicMock()
            mock_processor.video_paths = {}
            mock_vp_class.return_value = mock_processor

            # 1. 添加任务
            with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
                await task_manager.add_task(task_id, mock_websocket, sample_task_data)

            assert task_manager.get_task_status(task_id)["status"] == "pending"

            # 2. 取消 pending 任务
            result = await task_manager.cancel_task(task_id)
            assert result is True
            assert task_manager.get_task_status(task_id)["status"] == "cancelled"


@pytest.mark.asyncio
async def test_concurrent_task_processing(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试并发任务处理限制。"""
    task_manager.max_concurrent_tasks = 1

    with patch('core.task_manager.BASE_DIR', str(tmp_path)):
        # 添加第一个任务
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            await task_manager.add_task("task_1", mock_websocket, sample_task_data)

        # 手动增加 processing_tasks 模拟正在处理
        task_manager.processing_tasks = 1

        # 添加第二个任务
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock) as mock_next:
            await task_manager.add_task("task_2", mock_websocket, sample_task_data)

            # process_next_task 应该被调用，但由于并发限制不会启动新任务
            assert mock_next.called


@pytest.mark.asyncio
async def test_task_queue_order(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试任务队列顺序。"""
    with patch('core.task_manager.BASE_DIR', str(tmp_path)):
        with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
            await task_manager.add_task("task_first", mock_websocket, sample_task_data)
            await task_manager.add_task("task_second", mock_websocket, sample_task_data)
            await task_manager.add_task("task_third", mock_websocket, sample_task_data)

        # 验证队列顺序
        assert await task_manager.task_queue.get() == "task_first"
        assert await task_manager.task_queue.get() == "task_second"
        assert await task_manager.task_queue.get() == "task_third"


@pytest.mark.asyncio
async def test_cancelled_task_removed_from_set_after_processing(task_manager, mock_websocket, sample_task_data, tmp_path):
    """测试取消的任务在处理后从集合中移除。"""
    task_id = "task_remove_cancel"

    with patch('core.task_manager.BASE_DIR', str(tmp_path)):
        task_manager.tasks[task_id] = {
            'status': 'processing',
            'websocket': mock_websocket,
            'data': sample_task_data,
            'created_at': datetime.now(),
            'output_dir': str(tmp_path)
        }
        task_manager.processing_tasks = 1
        task_manager._cancelled_tasks.add(task_id)

        async def cancelled_core(*args, **kwargs):
            raise asyncio.CancelledError()

        with patch.object(task_manager, '_process_task_core', side_effect=cancelled_core):
            with patch.object(task_manager, 'process_next_task', new_callable=AsyncMock):
                with pytest.raises(asyncio.CancelledError):
                    await task_manager.process_task(task_id)

                assert task_id not in task_manager._cancelled_tasks

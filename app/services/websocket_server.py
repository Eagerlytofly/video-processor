import asyncio
import websockets
import json
import logging
import os
import sys
from pathlib import Path

# 添加app目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video_processor import VideoProcessor
from core.task_manager import task_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# 获取项目根目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


async def handle_websocket(websocket):
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"收到WebSocket请求: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
                if data.get('type') == 'start':
                    asyncio.create_task(task_manager.add_task(data.get('data', {}).get('taskId'), websocket, data))

                        
            except json.JSONDecodeError:
                logger.error("无效的JSON格式")
                await websocket.send(json.dumps({
                    "type": "error",
                    "data": {
                        "message": "无效的JSON格式"
                    }
                }))
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket连接已关闭")


async def main():
    """主函数"""
    logger.info(f"项目根目录: {BASE_DIR}")
    logger.info(f"启动WebSocket服务器...")

    # 确保必要的目录存在
    os.makedirs(os.path.join(BASE_DIR, 'public', 'videos'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'output'), exist_ok=True)

    # 启动清理调度器
    await task_manager.start_cleanup_scheduler()

    try:
        async with websockets.serve(handle_websocket, "0.0.0.0", 8000):
            await asyncio.Future()
    finally:
        # 停止清理调度器
        await task_manager.stop_cleanup_scheduler()

def start_server():
    """启动WebSocket服务器"""
    asyncio.run(main())

if __name__ == "__main__":
    start_server()
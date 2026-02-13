from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict
import uvicorn
import os
import logging
import uuid
import asyncio
import websockets
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加app目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.video_processor import VideoProcessor
from config.config import VIDEO_PROCESS_CONFIG
from utils.path_security import sanitize_filename, is_path_within_allowed

app = FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

logger = logging.getLogger(__name__)

# 存储处理状态
process_status = {}

# 获取项目根目录的绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# WebSocket连接到视频处理服务
VIDEO_WS_URL = "ws://localhost:8000"

async def send_to_video_service(task_id: str, data: dict):
    """发送消息到视频处理服务"""
    try:
        async with websockets.connect(VIDEO_WS_URL) as ws:
            # 添加taskId到数据中
            data['taskId'] = task_id
            await ws.send(json.dumps(data))
            response = await ws.recv()
            return json.loads(response)
    except Exception as e:
        logger.error(f"发送到视频服务失败: {str(e)}")
        raise

def get_abs_path(relative_path: str) -> str:
    """将相对路径转换为绝对路径"""
    return os.path.join(BASE_DIR, relative_path)

def normalize_path(file_path: str) -> str:
    """规范化文件路径，防止路径遍历攻击"""
    allowed_dirs = [
        os.path.join(BASE_DIR, 'public'),
        get_abs_path("mediasource"),
        get_abs_path("output"),
    ]

    # 如果以 /videos/ 开头，说明是前端传来的路径
    if file_path.startswith('/videos/'):
        # 将路径转换为 public/videos/xxx.mp4 的形式
        relative_path = file_path.lstrip('/')
        full_path = os.path.join(BASE_DIR, 'public', relative_path)
        if is_path_within_allowed(full_path, allowed_dirs):
            return full_path
        raise ValueError(f"非法路径: {file_path}")

    # 如果是绝对路径，检查是否在允许的目录下
    if os.path.isabs(file_path):
        if is_path_within_allowed(file_path, allowed_dirs):
            return file_path
        # 如果不在允许的目录下，仅使用文件名部分
        base_name = sanitize_filename(os.path.basename(file_path))
        return os.path.join(get_abs_path("mediasource"), base_name)

    # 如果是相对路径，先清理文件名，然后放在 mediasource 目录下
    safe_name = sanitize_filename(file_path)
    return os.path.join(get_abs_path("mediasource"), safe_name)

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """上传视频文件"""
    try:
        media_dir = get_abs_path("mediasource")
        os.makedirs(media_dir, exist_ok=True)

        # 清理文件名，防止路径遍历攻击
        safe_filename = sanitize_filename(file.filename)
        if safe_filename != file.filename:
            logger.warning(f"文件名已清理: {file.filename} -> {safe_filename}")

        file_path = os.path.join(media_dir, safe_filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        return JSONResponse({
            "status": "success",
            "message": "文件上传成功",
            "file_path": file_path,
            "original_filename": file.filename,
            "safe_filename": safe_filename
        })
    except ValueError as e:
        logger.error(f"文件上传参数错误: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process")
async def process_video(data: Dict = Body(...)):
    """处理视频请求"""
    try:
        logger.info("="*50)
        logger.info("收到HTTP请求:")
        logger.info(f"请求体数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
        logger.info(f"请求类型: {type(data)}")
        logger.info("="*50)
        
        command = data.get('command')
        file_path = data.get('file_path')
        
        logger.info(f"解析的命令: {command}")
        logger.info(f"解析的文件路径: {file_path}")
        
        if not command:
            logger.error("缺少command参数")
            raise HTTPException(status_code=400, detail="缺少command参数")
            
        # 生成任务ID
        task_id = f"task_{int(datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        logger.info(f"生成任务ID: {task_id}")

        # 准备发送给视频服务的数据
        ws_data = {
            "command": command,
            "file_path": file_path
        }
        logger.info(f"准备发送到WebSocket的数据: {json.dumps(ws_data, indent=2, ensure_ascii=False)}")

        # 发送到视频处理服务
        logger.info("开始发送到视频处理服务...")
        response = await send_to_video_service(task_id, ws_data)
        logger.info(f"视频处理服务返回: {json.dumps(response, indent=2, ensure_ascii=False)}")
        
        result = {
            "status": "success",
            "taskId": task_id,
            "result": response
        }
        logger.info(f"返回给前端的数据: {json.dumps(result, indent=2, ensure_ascii=False)}")
        logger.info("="*50)
        
        return JSONResponse(result)

    except Exception as e:
        logger.error("="*50)
        logger.error(f"处理失败: {str(e)}")
        logger.exception("详细错误信息:")
        logger.error("="*50)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """获取处理状态"""
    if task_id not in process_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JSONResponse(process_status[task_id])

@app.get("/api/test")
async def test():
    """测试端点"""
    logger.info("收到测试请求")
    return JSONResponse({
        "status": "success",
        "message": "服务器正常运行",
        "base_dir": BASE_DIR,
        "current_dir": os.getcwd(),
        "public_exists": os.path.exists(os.path.join(BASE_DIR, 'public')),
        "videos_exists": os.path.exists(os.path.join(BASE_DIR, 'public', 'videos'))
    })

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP错误: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"未处理的错误: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": str(exc),
            "code": 500
        }
    )

def start_server():
    """启动HTTP服务器"""
    # 确保必要的目录存在
    os.makedirs(os.path.join(BASE_DIR, 'public', 'videos'), exist_ok=True)
    
    logger.info(f"项目根目录: {BASE_DIR}")
    logger.info(f"视频处理服务WebSocket地址: {VIDEO_WS_URL}")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)

if __name__ == "__main__":
    start_server() 
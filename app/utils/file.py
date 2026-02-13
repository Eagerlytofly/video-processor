import os
import shutil
import tempfile
from typing import Optional, List

def ensure_directory(directory: str) -> None:
    """
    确保目录存在
    
    Args:
        directory: 目录路径
    """
    os.makedirs(directory, exist_ok=True)
    
def get_file_size(file_path: str) -> int:
    """
    获取文件大小
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件大小（字节）
    """
    return os.path.getsize(file_path)
    
def check_file_exists(file_path: str) -> bool:
    """
    检查文件是否存在
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件是否存在
    """
    return os.path.exists(file_path)
    
def get_file_extension(file_path: str) -> str:
    """
    获取文件扩展名
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件扩展名
    """
    return os.path.splitext(file_path)[1].lower()
    
def create_temp_file(suffix: str = None) -> str:
    """
    创建临时文件
    
    Args:
        suffix: 文件后缀
        
    Returns:
        临时文件路径
    """
    return tempfile.mktemp(suffix=suffix)
    
def cleanup_temp_files(directory: str) -> None:
    """
    清理临时文件
    
    Args:
        directory: 临时文件目录
    """
    try:
        shutil.rmtree(directory)
    except Exception:
        pass
        
def list_files(directory: str, pattern: str = None) -> List[str]:
    """
    列出目录中的文件
    
    Args:
        directory: 目录路径
        pattern: 文件模式
        
    Returns:
        文件列表
    """
    if pattern:
        import glob
        return glob.glob(os.path.join(directory, pattern))
    else:
        return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))] 
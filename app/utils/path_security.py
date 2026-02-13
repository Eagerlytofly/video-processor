"""
路径安全工具函数：防止路径遍历攻击和目录穿越。
"""

import os
import re
from pathlib import Path


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """
    清理文件名，移除危险字符和路径遍历尝试。

    Args:
        filename: 原始文件名
        replacement: 替换非法字符的字符，默认为下划线

    Returns:
        安全的文件名
    """
    # 移除路径分隔符和父目录引用
    filename = filename.replace("../", replacement)
    filename = filename.replace("..\\", replacement)
    filename = filename.replace("/", replacement)
    filename = filename.replace("\\", replacement)

    # 移除控制字符和空字符
    filename = re.sub(r'[\x00-\x1f\x7f]', replacement, filename)

    # 移除危险的 shell 字符
    filename = re.sub(r'[<>:"|?*]', replacement, filename)

    # 确保不以 . 开头（隐藏文件）
    filename = filename.lstrip(".")

    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext

    # 如果为空，返回默认名
    if not filename:
        filename = "unnamed"

    return filename


def is_path_within_allowed(path: str, allowed_dirs: list[str]) -> bool:
    """
    检查路径是否在允许的目录内（防止目录穿越）。

    Args:
        path: 要检查的路径
        allowed_dirs: 允许的目录列表

    Returns:
        是否在允许目录内
    """
    try:
        real_path = Path(path).resolve()
        for allowed_dir in allowed_dirs:
            allowed_real = Path(allowed_dir).resolve()
            try:
                real_path.relative_to(allowed_real)
                return True
            except ValueError:
                continue
        return False
    except (OSError, ValueError):
        return False


def safe_path_join(base_dir: str, *paths: str) -> str:
    """
    安全地拼接路径，确保结果在 base_dir 内。

    Args:
        base_dir: 基础目录
        *paths: 要拼接的路径组件

    Returns:
        安全的完整路径

    Raises:
        ValueError: 如果最终路径超出 base_dir
    """
    base = Path(base_dir).resolve()
    result = base.joinpath(*paths).resolve()

    try:
        result.relative_to(base)
    except ValueError:
        raise ValueError(f"路径遍历检测: {paths} 超出基础目录 {base_dir}")

    return str(result)


def get_safe_output_path(
    output_dir: str,
    filename: str,
    allowed_dirs: list[str] | None = None
) -> str:
    """
    获取安全的输出文件路径。

    Args:
        output_dir: 输出目录
        filename: 原始文件名
        allowed_dirs: 额外允许的目录列表（可选）

    Returns:
        安全的完整路径

    Raises:
        ValueError: 如果路径不合法
    """
    safe_name = sanitize_filename(filename)
    output_path = os.path.join(output_dir, safe_name)

    # 验证路径
    dirs_to_check = [output_dir]
    if allowed_dirs:
        dirs_to_check.extend(allowed_dirs)

    if not is_path_within_allowed(output_path, dirs_to_check):
        raise ValueError(f"非法路径: {filename}")

    return output_path

def time_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数
    
    Args:
        time_str: 时间字符串，格式为 "HH:MM:SS.mmm"
        
    Returns:
        转换后的秒数
    """
    try:
        # 处理毫秒部分
        if '.' in time_str:
            time_part, ms_part = time_str.split('.')
            ms = float(f"0.{ms_part}")
        else:
            time_part = time_str
            ms = 0
            
        # 处理时分秒
        h, m, s = map(int, time_part.split(':'))
        total_seconds = h * 3600 + m * 60 + s + ms
        
        return total_seconds
        
    except Exception as e:
        raise ValueError(f"无效的时间格式: {time_str} - {str(e)}")
        
def seconds_to_time(seconds: float) -> str:
    """
    将秒数转换为时间字符串
    
    Args:
        seconds: 秒数
        
    Returns:
        时间字符串，格式为 "HH:MM:SS.mmm"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}" 
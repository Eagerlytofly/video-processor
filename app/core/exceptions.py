class VideoProcessorError(Exception):
    """视频处理器基础异常类"""
    def __init__(self, message="视频处理异常", detail=None):
        self.message = message
        self.detail = detail  # 可存储技术细节
        super().__init__(self.message)
    
    def __str__(self):
        if self.detail:
            return f"{self.message} ({self.detail})"
        return self.message

class VideoFileError(VideoProcessorError):
    """视频文件相关错误(格式/分辨率/损坏等)"""
    def __init__(self, message="视频文件异常", file_path=None, **kwargs):
        self.file_path = file_path
        super().__init__(message=f"[文件错误] {message}", **kwargs)

class ASRError(VideoProcessorError):
    """语音识别相关错误(转写/时间轴等)"""
    def __init__(self, message="语音识别异常", audio_info=None, **kwargs):
        self.audio_info = audio_info
        super().__init__(message=f"[ASR错误] {message}", **kwargs)

class OSSError(VideoProcessorError):
    """OSS存储相关错误(上传/下载/权限等)"""
    def __init__(self, message="OSS操作异常", oss_path=None, **kwargs):
        self.oss_path = oss_path
        super().__init__(message=f"[OSS错误] {message}", **kwargs)

class SubtitleError(VideoProcessorError):
    """字幕处理相关错误(生成/同步等)"""
    def __init__(self, message="字幕处理异常", line_no=None, **kwargs):
        self.line_no = line_no
        super().__init__(message=f"[字幕错误] {message}", **kwargs)

class ConfigError(VideoProcessorError):
    """配置相关错误(参数/环境变量等)"""
    def __init__(self, message="配置异常", config_key=None, **kwargs):
        self.config_key = config_key
        super().__init__(message=f"[配置错误] {message}", **kwargs)
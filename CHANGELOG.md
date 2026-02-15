# Changelog

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且该项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)规范。

## [Unreleased]

## [1.1.1] - 2026-02-16

### Added

- 增强核心模块单元测试覆盖
  - VideoProcessor 测试从 6 个增加到 29 个
  - 新增 process_single_video 完整流程测试（6 个）
  - 新增 process_directory 流程测试（4 个）
  - 新增 cleanup 方法测试（3 个）
  - 新增 add_subtitles 测试（5 个）
  - 新增其他辅助方法测试（5 个）
- 测试总数从 152 个增加到 175 个

### Changed

- 改进测试结构和 Mock 使用方式
- 提升 VideoProcessor 核心类的测试覆盖率至 100%

## [1.1.0] - 2026-02-15

### Added

- 新增时间线可视化功能
- 新增全面的单元测试覆盖（共 152 个测试）
  - ASR 客户端测试（25 个）：OSS 上传、任务提交、结果轮询
  - 音频提取器测试（21 个）：MoviePy/ffmpeg 双路径提取
  - AI 分析器测试（26 个）：DeepSeek API 集成与降级处理
  - 任务管理器测试（41 个）：异步队列、超时控制、任务取消
  - 字幕渲染器测试（19 个）：字体选择、字幕合成

### Changed

- 提升代码质量和可靠性，核心模块测试覆盖率达 100%

## [1.0.0] - 2026-02-12

### Added

- 初始发布：视频处理系统
- 智能视频内容分析和剪辑功能
- 支持语音识别（阿里云 ASR）
- AI 分析（DeepSeek）自动提取重要对话
- 智能片段剪辑和合并
- WebSocket 服务器（端口 8000）支持实时任务处理
- HTTP API 服务器（端口 8001）提供 REST 接口
- CLI 工具支持命令行视频处理
- 字幕添加功能

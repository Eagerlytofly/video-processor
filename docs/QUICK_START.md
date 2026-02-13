# YouTube视频下载和转录功能 - 快速开始

## 🎉 配置完成！

YouTube视频下载和转录功能已经完全配置好，可以直接使用！

## ✅ 已完成的工作

1. **✓ 阿里云配置已填入** - 使用了项目中现有的配置
2. **✓ 依赖包已安装** - yt-dlp、oss2、aliyun-python-sdk-core
3. **✓ 配置测试通过** - 所有配置项验证成功
4. **✓ 功能测试通过** - 核心功能测试正常
5. **✓ 演示脚本运行** - 完整的使用演示

## 🚀 立即开始使用

### 基本用法
```bash
python youtube_processor.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### 指定输出文件名
```bash
python youtube_processor.py "https://www.youtube.com/watch?v=VIDEO_ID" -o "my_video"
```

### 详细输出模式
```bash
python youtube_processor.py "https://www.youtube.com/watch?v=VIDEO_ID" -v
```

## 📋 当前配置

**OSS配置:**
- Bucket: `mediacut`
- Endpoint: `oss-cn-beijing.aliyuncs.com`
- Access Key: `LTAI5t6p77hJBKzWzYFUkznH`

**ASR配置:**
- App Key: `tkCiuZXXmzoRYKAi`
- Region: `cn-shanghai`
- Domain: `filetrans.cn-shanghai.aliyuncs.com`

**YouTube配置:**
- 音频格式: `mp3`
- 音频质量: `160k`
- 视频分辨率: `≤720p`

## 📁 输出文件

处理完成后，在 `youtube_output` 目录下会生成：
- `{文件名}.json` - 结构化转录数据
- `{文件名}.txt` - 可读转录文本

## 🛠️ 可用工具

- `youtube_processor.py` - 主要处理器
- `test_config.py` - 配置验证
- `test_youtube.py` - 功能测试
- `demo_youtube.py` - 使用演示
- `youtube_processor.bat` - Windows批处理
- `youtube_processor.sh` - Linux/macOS脚本

## 🔍 测试命令

```bash
# 验证配置
python test_config.py

# 功能测试
python test_youtube.py

# 查看演示
python demo_youtube.py
```

## 📖 详细文档

查看 `README_YouTube.md` 获取完整的使用说明和API文档。

## 🎯 示例

```bash
# 下载并转录一个YouTube视频
python youtube_processor.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -o "rick_roll"

# 输出结果示例:
# 处理完成！
# ============================================================
# 音频文件: /tmp/youtube_xxx/Rick Astley - Never Gonna Give You Up.mp3
# 转录JSON: /path/to/youtube_output/rick_roll.json
# 转录TXT: /path/to/youtube_output/rick_roll.txt
# 总时长: 213.45 秒
# 句子数量: 45
# ============================================================
```

## ⚠️ 注意事项

1. **网络连接** - 需要稳定的网络访问YouTube和阿里云
2. **版权合规** - 请确保有权限下载和转录目标视频
3. **存储空间** - 确保有足够的磁盘空间
4. **API限制** - 注意阿里云服务的调用频率限制

## 🆘 故障排除

如果遇到问题：
1. 运行 `python test_config.py` 检查配置
2. 运行 `python test_youtube.py` 检查功能
3. 查看 `youtube_processor.log` 日志文件
4. 使用 `-v` 参数获取详细输出

---

**🎊 配置完成！现在就可以开始使用YouTube视频下载和转录功能了！**

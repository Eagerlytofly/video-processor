import os
import sys
import argparse

# 确保模块导入路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.video_processor import VideoProcessor

# 定义支持的视频文件扩展名
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v')

def main():
    parser = argparse.ArgumentParser(description='视频处理工具')
    parser.add_argument('--server', action='store_true', help='启动 HTTP 服务器')
    parser.add_argument('--analyze', action='store_true', help='合并并分析所有转录文件')
    parser.add_argument('--cut', action='store_true', help='根据重要对话裁剪视频')
    parser.add_argument('--merge', action='store_true', help='合并所有裁剪后的视频片段')
    parser.add_argument('--add-subtitles', action='store_true', help='为最新生成的视频添加字幕')
    parser.add_argument('-o', '--output', type=str, default=None, help='输出目录，默认 data/output')
    parser.add_argument('files', nargs='*', help='要处理的视频文件路径（可多个），未指定时使用 data/input/mediasource 目录')
    args = parser.parse_args()

    current_dir = os.getcwd()
    # 输出目录：-o/--output 指定，否则优先 data/output
    if args.output:
        default_output = os.path.join(current_dir, args.output) if not os.path.isabs(args.output) else args.output
    else:
        default_output = os.path.join(current_dir, "data", "output")
        if not os.path.exists(default_output):
            default_output = os.path.join(current_dir, "output")

    if args.server:
        from services.http_server import start_server
        start_server()
        return

    if args.analyze:
        if not os.path.exists(default_output):
            print(f"输出目录不存在: {default_output}")
            return
        merged = os.path.join(default_output, "merged_transcripts.txt")
        if not os.path.exists(merged):
            print(f"未找到 {merged}，请先运行完整处理流程生成转录")
            return
        processor = VideoProcessor(default_output)
        processor.analyze_merged_transcripts()
        return

    if args.cut:
        print("视频裁剪已整合到主流程，请运行: python run.py <视频文件...> 或 python run.py（使用 data/input/mediasource 目录）")
        return

    if args.merge:
        if not os.path.exists(default_output):
            print(f"输出目录不存在: {default_output}")
            return
        cuts_dir = os.path.join(default_output, "cuts")
        if not os.path.exists(cuts_dir):
            print(f"未找到 {cuts_dir}，请先运行完整流程或 --analyze 后再执行裁剪")
            return
        processor = VideoProcessor(default_output)
        processor.merge_video_clips(default_output)
        return

    if args.add_subtitles:
        if not os.path.exists(default_output):
            print(f"输出目录不存在: {default_output}")
            return
        video_files = [f for f in os.listdir(default_output)
                      if f.lower().endswith(('.mp4', '.mov', '.avi')) and not f.startswith(".")]
        if not video_files:
            print("未找到可处理的视频文件")
            return
        latest_video = max(
            video_files,
            key=lambda f: os.path.getmtime(os.path.join(default_output, f)),
        )
        video_path = os.path.join(default_output, latest_video)
        print(f"为最新视频添加字幕: {latest_video}")
        processor = VideoProcessor(default_output)
        processor.add_subtitles(video_path, default_output)
        return

    # 默认：以「文件集合」为输入，进行转录→分析→裁剪→合并
    if args.files:
        # 输入为指定的文件路径列表；同名文件（不同路径）会赋予唯一名称避免覆盖
        seen_basenames = {}
        valid = []
        for p in args.files:
            path = os.path.abspath(p) if not os.path.isabs(p) else p
            if not os.path.isfile(path):
                print(f"跳过（非文件或不存在）: {p}")
                continue
            if not path.lower().endswith(VIDEO_EXTENSIONS) or path.endswith(".part"):
                print(f"跳过（非支持的视频格式）: {p}")
                continue
            base = os.path.basename(path)
            name = base
            if base in seen_basenames:
                seen_basenames[base] += 1
                stem, ext = os.path.splitext(base)
                name = f"{stem}_{seen_basenames[base]}{ext}"
            else:
                seen_basenames[base] = 1
            valid.append((name, path))
        video_list = valid
    else:
        # 未传文件时回退到 data/input/mediasource 目录
        media_dir = os.path.join(current_dir, "data", "input", "mediasource")
        if not os.path.exists(media_dir):
            os.makedirs(media_dir)
            print(f"创建目录: {media_dir}")
            print("请指定视频文件，或将视频放入 mediasource 后不传参数运行。例如: python run.py a.mp4 b.mov")
            return
        names = [
            f for f in os.listdir(media_dir)
            if f.lower().endswith(VIDEO_EXTENSIONS) and not f.endswith(".part")
        ]
        if not names:
            print(f"在 {media_dir} 中未找到视频文件，支持的格式: {', '.join(VIDEO_EXTENSIONS)}")
            return
        video_list = [(n, os.path.join(media_dir, n)) for n in names]

    if not video_list:
        print("没有可处理的视频文件")
        return

    print(f"输出目录: {default_output}")
    print(f"视频文件（{len(video_list)} 个）:")
    for name, path in video_list:
        print(f"  - {name}")

    output_dir = default_output
    os.makedirs(output_dir, exist_ok=True)
    processor = VideoProcessor(output_dir)
    for name, path in video_list:
        processor.add_video(name, path)
    processor.process_directory()

if __name__ == "__main__":
    main()
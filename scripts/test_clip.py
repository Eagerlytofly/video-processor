#!/usr/bin/env python3
"""
仅测试剪辑与合并：根据已有 clip_order.txt 对指定视频做裁剪并合并成片。
用法（在项目根目录 video_processor 下执行）：
  python scripts/test_clip.py
依赖：data/input/mediasource/sample-5s.mp4 与 data/output/clip_order.txt 已就绪。
"""
import os
import sys

# 以项目根为当前目录，app 加入路径
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
os.chdir(ROOT)

from core.video_processor import VideoProcessor

def main():
    output_dir = os.path.join(ROOT, "data", "output")
    media_dir = os.path.join(ROOT, "data", "input", "mediasource")
    video_name = "sample-5s.mp4"
    video_path = os.path.join(media_dir, video_name)

    if not os.path.exists(video_path):
        print(f"未找到视频: {video_path}")
        print("请先下载测试视频到 data/input/mediasource/")
        return 1
    if not os.path.exists(os.path.join(output_dir, "clip_order.txt")):
        print("未找到 data/output/clip_order.txt")
        return 1

    processor = VideoProcessor(output_dir)
    processor.add_video(video_name, video_path)
    print("开始按 clip_order.txt 裁剪...")
    processor.process_clips()
    print("开始合并片段...")
    out_path = processor.merge_video_clips()
    if out_path:
        print(f"剪辑测试完成，成片: {out_path}")
    else:
        print("合并未产生输出")
    return 0

if __name__ == "__main__":
    sys.exit(main())

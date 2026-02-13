#!/usr/bin/env python3
"""
用 yt-dlp 下载 YouTube 视频并运行完整处理流程（转录 → 分析 → 剪辑 → 合并）。
用法（在项目根目录 video_processor 下）：
  python scripts/download_and_test.py "https://www.youtube.com/watch?v=VIDEO_ID"
  python scripts/download_and_test.py "URL" --proxy http://127.0.0.1:7890   # ClashX 代理
  python scripts/download_and_test.py "URL" --no-run   # 仅下载
若下载遇 403：可尝试代理（--proxy）、更新 yt-dlp、或使用 --cookies cookies.txt。
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(ROOT, "data", "input", "mediasource")
OUTPUT_DIR = os.path.join(ROOT, "data", "output")

def main():
    parser = argparse.ArgumentParser(description="下载 YouTube 视频并测试处理流程")
    parser.add_argument("url", nargs="?", default="https://www.youtube.com/watch?v=7pEZdU7QpPQ", help="YouTube 视频 URL")
    parser.add_argument("--no-run", action="store_true", help="仅下载，不运行处理流程")
    parser.add_argument("--cookies", default="", help="可选：浏览器导出的 cookies 文件路径")
    parser.add_argument(
        "--proxy",
        default=os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY", ""),
        help="代理地址，如 http://127.0.0.1:7890（ClashX 默认）。不传则尝试环境变量 HTTP_PROXY/ALL_PROXY",
    )
    args = parser.parse_args()

    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    out_tpl = os.path.join(MEDIA_DIR, "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bv*+ba/best",
        "--merge-output-format", "mp4",
        "-o", out_tpl,
        "--no-overwrites",
    ]
    if args.cookies:
        cmd.extend(["--cookies", os.path.abspath(args.cookies)])
    # 代理：--proxy 或环境变量 HTTP_PROXY / ALL_PROXY（ClashX 一般为 http://127.0.0.1:7890）
    proxy = (args.proxy or "").strip()
    if proxy:
        cmd.extend(["--proxy", proxy])
        print("使用代理:", proxy)
    cmd.append(args.url)

    print("下载中:", args.url)
    ret = subprocess.run(cmd, cwd=ROOT)
    if ret.returncode != 0:
        print("下载失败。可尝试：")
        print("  1. 使用 ClashX 等代理: --proxy http://127.0.0.1:7890")
        print("  2. pip install -U yt-dlp")
        print("  3. 使用 --cookies 传入浏览器导出的 cookies 文件")
        print("  4. 或将视频手动放入 data/input/mediasource/ 后执行: python run.py")
        return 1

    # 查找刚下载的文件（yt-dlp 用 id 作为文件名）
    import glob
    from urllib.parse import urlparse, parse_qs
    vid = parse_qs(urlparse(args.url).query).get("v", [""])[0] or "unknown"
    pattern = os.path.join(MEDIA_DIR, f"{vid}.*")
    files = [f for f in glob.glob(pattern) if os.path.isfile(f) and not f.endswith(".part")]
    if not files:
        # 可能用了别的命名，取最新一个 mp4
        files = sorted(
            [f for f in os.listdir(MEDIA_DIR) if f.endswith((".mp4", ".mkv", ".webm"))],
            key=lambda f: os.path.getmtime(os.path.join(MEDIA_DIR, f)),
            reverse=True,
        )
        files = [os.path.join(MEDIA_DIR, f) for f in files[:1]]
    if not files:
        print("未找到下载文件")
        return 1
    print("已下载:", files[0])

    if args.no_run:
        return 0

    print("开始处理流程（转录 → 分析 → 剪辑 → 合并）...")
    sys.path.insert(0, os.path.join(ROOT, "app"))
    os.chdir(ROOT)
    # run.py 无参数时从 data/input/mediasource 读取；也可传文件: sys.argv = ["run.py", files[0]]
    sys.argv = ["run.py"]
    from main import main as run_main
    run_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())

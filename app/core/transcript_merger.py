"""
转录文件合并：将多个 *_transcript.json 合并为一份 merged_transcripts.txt。
"""

import glob
import json
import logging
import os

logger = logging.getLogger(__name__)

MERGED_FILENAME = "merged_transcripts.txt"


def merge_transcripts(
    temp_dir: str,
    output_dir: str,
    order_base_names: list[str] | None = None,
) -> str:
    """
    将 temp_dir 下 *_transcript.json 合并为 output_dir/merged_transcripts.txt。
    order_base_names: 若提供，按该顺序合并（与输入文件顺序一致）；否则按文件名排序。
    返回合并文件路径。
    """
    if order_base_names:
        files = []
        for base in order_base_names:
            path = os.path.join(temp_dir, f"{base}_transcript.json")
            if os.path.isfile(path):
                files.append(path)
    else:
        pattern = os.path.join(temp_dir, "*_transcript.json")
        files = sorted(glob.glob(pattern))
    logger.info("在 %s 下找到 %d 个转录文件", temp_dir, len(files))
    if not files:
        logger.warning("没有找到任何转录文件")
        return ""

    out_path = os.path.join(output_dir, MERGED_FILENAME)
    lines = []
    for path in files:
        base = os.path.basename(path).replace("_transcript.json", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lines.append(f"\n=== {base} ===\n")
            for seg in data:
                start = seg.get("start_time_formatted", "")
                end = seg.get("end_time_formatted", "")
                text = seg.get("text", "")
                lines.append(f"[{start} - {end}] {text}\n")
        except Exception as e:
            logger.error("读取转录文件 %s 失败: %s", path, e)

    if not lines:
        logger.warning("无有效转录内容，不写入合并文件")
        return ""
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    logger.info("已合并 %d 个转录文件到 %s", len(files), out_path)
    return out_path

"""
视频时间轴可视化工具：生成原始视频与剪辑后视频的对比图
"""

import os
import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import timedelta


@dataclass
class TimeSegment:
    """时间段"""
    start: float  # 秒
    end: float    # 秒
    label: str = ""
    color: str = "#4CAF50"  # 默认绿色表示保留


@dataclass
class TimelineData:
    """时间轴数据"""
    video_name: str
    total_duration: float  # 秒
    segments: List[TimeSegment]


class TimelineVisualizer:
    """时间轴可视化器"""

    def __init__(self, output_dir: str = "data/output"):
        self.output_dir = output_dir

    def parse_clip_order(self, clip_order_path: str) -> List[TimeSegment]:
        """
        解析 clip_order.txt 文件
        格式: 文件名\t开始时间\t结束时间
        """
        segments = []

        if not os.path.exists(clip_order_path):
            return segments

        with open(clip_order_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split('\t')
                if len(parts) >= 3:
                    # 解析时间格式 (00:00:00.000)
                    start_time = self._parse_time(parts[1])
                    end_time = self._parse_time(parts[2])

                    segments.append(TimeSegment(
                        start=start_time,
                        end=end_time,
                        label=f"Clip {len(segments) + 1}",
                        color="#4CAF50"  # 绿色表示保留
                    ))

        return segments

    def _parse_time(self, time_str: str) -> float:
        """将时间字符串转换为秒数"""
        # 处理 HH:MM:SS.mmm 格式
        parts = time_str.split(':')
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        else:
            return float(parts[0])

    def get_video_duration(self, video_path: str) -> float:
        """获取视频时长（秒）"""
        import subprocess

        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass

        return 0.0

    def generate_html_timeline(
        self,
        original_video: str,
        clip_order_path: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成 HTML 时间轴对比图

        Args:
            original_video: 原始视频路径
            clip_order_path: 剪辑顺序文件路径
            output_path: 输出HTML路径，默认保存到output_dir

        Returns:
            HTML文件路径
        """
        # 获取原始视频时长
        original_duration = self.get_video_duration(original_video)

        # 解析保留的片段
        kept_segments = self.parse_clip_order(clip_order_path)

        # 计算被裁剪的片段
        removed_segments = self._calculate_removed_segments(
            original_duration, kept_segments
        )

        # 生成HTML
        html_content = self._create_html_timeline(
            os.path.basename(original_video),
            original_duration,
            kept_segments,
            removed_segments
        )

        # 保存HTML
        if output_path is None:
            video_name = os.path.splitext(os.path.basename(original_video))[0]
            output_path = os.path.join(
                self.output_dir,
                f"{video_name}_timeline.html"
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path

    def generate_combined_html_timeline(
        self,
        video_paths: Dict[str, str],
        clip_order_path: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        生成包含多个视频时间轴的合并HTML报告

        Args:
            video_paths: 字典 {视频名: 视频路径}
            clip_order_path: 剪辑顺序文件路径
            output_path: 输出HTML路径

        Returns:
            HTML文件路径
        """
        # 解析clip_order，按视频分组
        video_segments = self._parse_clip_order_by_video(clip_order_path)

        # 为每个视频生成时间轴数据
        video_data = []
        total_kept = 0
        total_removed = 0
        total_duration = 0

        for video_name, segments in video_segments.items():
            if video_name not in video_paths:
                continue

            video_path = video_paths[video_name]
            duration = self.get_video_duration(video_path)
            removed = self._calculate_removed_segments(duration, segments)

            kept_duration = sum(s.end - s.start for s in segments)
            removed_duration = sum(r.end - r.start for r in removed)

            video_data.append({
                'name': video_name,
                'path': video_path,
                'duration': duration,
                'segments': segments,
                'removed': removed,
                'kept_duration': kept_duration,
                'removed_duration': removed_duration
            })

            total_kept += kept_duration
            total_removed += removed_duration
            total_duration += duration

        if not video_data:
            return ""

        # 生成合并HTML
        html_content = self._create_combined_html_timeline(
            video_data,
            total_duration,
            total_kept,
            total_removed
        )

        # 保存HTML
        if output_path is None:
            output_path = os.path.join(
                self.output_dir,
                "combined_timeline.html"
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path

    def _parse_clip_order_by_video(self, clip_order_path: str) -> Dict[str, List[TimeSegment]]:
        """解析clip_order.txt，按视频名分组"""
        video_segments = {}

        if not os.path.exists(clip_order_path):
            return video_segments

        with open(clip_order_path, 'r', encoding='utf-8') as f:
            clip_idx = 1
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split('\t')
                if len(parts) >= 3:
                    video_name = parts[0]
                    start_time = self._parse_time(parts[1])
                    end_time = self._parse_time(parts[2])

                    if video_name not in video_segments:
                        video_segments[video_name] = []

                    video_segments[video_name].append(TimeSegment(
                        start=start_time,
                        end=end_time,
                        label=f"Clip {clip_idx}",
                        color="#4CAF50"
                    ))
                    clip_idx += 1

        return video_segments

    def _create_combined_html_timeline(
        self,
        video_data: List[Dict],
        total_duration: float,
        total_kept: float,
        total_removed: float
    ) -> str:
        """创建合并的HTML时间轴"""

        overall_compression = (total_removed / total_duration * 100) if total_duration > 0 else 0

        # 生成每个视频的时间轴HTML
        video_sections = ""
        for i, video in enumerate(video_data, 1):
            segments_html = self._generate_segments_html(
                video['segments'] + video['removed'],
                video['duration']
            )

            compression = (video['removed_duration'] / video['duration'] * 100) if video['duration'] > 0 else 0

            video_sections += f"""
            <div class="video-section">
                <div class="video-header">
                    <h3>📹 {video['name']}</h3>
                    <div class="video-stats">
                        <span class="stat-badge kept">保留: {self._format_time(video['kept_duration'])}</span>
                        <span class="stat-badge removed">裁剪: {self._format_time(video['removed_duration'])}</span>
                        <span class="stat-badge info">压缩: {compression:.1f}%</span>
                    </div>
                </div>
                <div class="timeline-wrapper">
                    <div class="timeline">
                        {segments_html}
                    </div>
                    <div class="time-axis">
                        {self._generate_ticks(video['duration'])}
                    </div>
                </div>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>视频剪辑时间轴对比 - 多视频总览</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 20px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}

        h1 {{
            font-size: 32px;
            margin-bottom: 8px;
            color: #333;
        }}

        .subtitle {{
            color: #666;
            font-size: 16px;
        }}

        .overall-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 30px;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            text-align: center;
        }}

        .stat-card.kept {{
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
        }}

        .stat-card.removed {{
            background: linear-gradient(135deg, #F44336 0%, #d32f2f 100%);
        }}

        .stat-card.info {{
            background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%);
        }}

        .stat-value {{
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 8px;
        }}

        .stat-label {{
            font-size: 14px;
            opacity: 0.9;
        }}

        .video-section {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}

        .video-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }}

        .video-header h3 {{
            font-size: 20px;
            color: #333;
        }}

        .video-stats {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .stat-badge {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }}

        .stat-badge.kept {{
            background: #e8f5e9;
            color: #2e7d32;
        }}

        .stat-badge.removed {{
            background: #ffebee;
            color: #c62828;
        }}

        .stat-badge.info {{
            background: #e3f2fd;
            color: #1565c0;
        }}

        .timeline-wrapper {{
            margin-top: 20px;
        }}

        .timeline {{
            position: relative;
            height: 50px;
            background: #f0f0f0;
            border-radius: 8px;
            overflow: hidden;
        }}

        .segment {{
            position: absolute;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            color: white;
            font-weight: 500;
            transition: all 0.2s;
            cursor: pointer;
        }}

        .segment:hover {{
            transform: scaleY(1.1);
            z-index: 10;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}

        .segment.kept {{
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }}

        .segment.removed {{
            background: repeating-linear-gradient(
                45deg,
                #F44336,
                #F44336 8px,
                #d32f2f 8px,
                #d32f2f 16px
            );
        }}

        .time-axis {{
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 11px;
            color: #666;
            position: relative;
            height: 20px;
        }}

        .legend {{
            background: white;
            border-radius: 16px;
            padding: 25px 30px;
            margin-top: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            display: flex;
            gap: 30px;
            justify-content: center;
            flex-wrap: wrap;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .legend-color {{
            width: 24px;
            height: 24px;
            border-radius: 4px;
        }}

        .legend-color.kept {{
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }}

        .legend-color.removed {{
            background: repeating-linear-gradient(
                45deg,
                #F44336,
                #F44336 5px,
                #d32f2f 5px,
                #d32f2f 10px
            );
        }}

        @media (max-width: 768px) {{
            .video-header {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .stat-value {{
                font-size: 28px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 视频剪辑时间轴对比</h1>
            <p class="subtitle">多视频处理总览报告</p>

            <div class="overall-stats">
                <div class="stat-card">
                    <div class="stat-value">{self._format_time(total_duration)}</div>
                    <div class="stat-label">总原始时长</div>
                </div>
                <div class="stat-card kept">
                    <div class="stat-value">{self._format_time(total_kept)}</div>
                    <div class="stat-label">总保留时长</div>
                </div>
                <div class="stat-card removed">
                    <div class="stat-value">{self._format_time(total_removed)}</div>
                    <div class="stat-label">总裁剪时长</div>
                </div>
                <div class="stat-card info">
                    <div class="stat-value">{overall_compression:.1f}%</div>
                    <div class="stat-label">整体压缩率</div>
                </div>
                <div class="stat-card info">
                    <div class="stat-value">{len(video_data)}</div>
                    <div class="stat-label">视频数量</div>
                </div>
            </div>
        </div>

        {video_sections}

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color kept"></div>
                <span>保留片段 (Kept)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color removed"></div>
                <span>裁剪片段 (Removed)</span>
            </div>
        </div>
    </div>
</body>
</html>"""

        return html

    def _generate_segments_html(self, segments: List[TimeSegment], total_duration: float) -> str:
        """生成片段HTML"""
        html = ""
        all_segments = sorted(segments, key=lambda x: x.start)

        for seg in all_segments:
            left_pct = (seg.start / total_duration) * 100
            width_pct = ((seg.end - seg.start) / total_duration) * 100
            css_class = 'kept' if seg.color == '#4CAF50' else 'removed'

            html += f'''
            <div class="segment {css_class}"
                 style="left: {left_pct:.2f}%; width: {width_pct:.2f}%;"
                 title="{seg.label}: {self._format_time(seg.start)} - {self._format_time(seg.end)}">
            </div>
            '''

        return html

    def _calculate_removed_segments(
        self,
        total_duration: float,
        kept_segments: List[TimeSegment]
    ) -> List[TimeSegment]:
        """计算被裁剪的片段"""
        if not kept_segments:
            return []

        removed = []

        # 按开始时间排序
        sorted_segments = sorted(kept_segments, key=lambda x: x.start)

        # 检查开头
        if sorted_segments[0].start > 0:
            removed.append(TimeSegment(
                start=0,
                end=sorted_segments[0].start,
                label="Removed",
                color="#F44336"  # 红色表示删除
            ))

        # 检查片段之间的间隙
        for i in range(len(sorted_segments) - 1):
            gap_start = sorted_segments[i].end
            gap_end = sorted_segments[i + 1].start

            if gap_end - gap_start > 0.1:  # 大于0.1秒的间隙
                removed.append(TimeSegment(
                    start=gap_start,
                    end=gap_end,
                    label="Removed",
                    color="#F44336"
                ))

        # 检查结尾
        if sorted_segments[-1].end < total_duration:
            removed.append(TimeSegment(
                start=sorted_segments[-1].end,
                end=total_duration,
                label="Removed",
                color="#F44336"
            ))

        return removed

    def _create_html_timeline(
        self,
        video_name: str,
        total_duration: float,
        kept_segments: List[TimeSegment],
        removed_segments: List[TimeSegment]
    ) -> str:
        """创建HTML时间轴"""

        # 合并所有片段用于显示
        all_segments = kept_segments + removed_segments
        all_segments.sort(key=lambda x: x.start)

        # 计算统计数据
        kept_duration = sum(s.end - s.start for s in kept_segments)
        removed_duration = sum(s.end - s.start for s in removed_segments)
        compression_ratio = (1 - kept_duration / total_duration) * 100 if total_duration > 0 else 0

        # 生成时间轴刻度
        timeline_ticks = self._generate_ticks(total_duration)

        # 生成片段HTML
        segments_html = ""
        for seg in all_segments:
            left_pct = (seg.start / total_duration) * 100
            width_pct = ((seg.end - seg.start) / total_duration) * 100

            segments_html += f"""
            <div class="segment {('kept' if seg.color == '#4CAF50' else 'removed')}"
                 style="left: {left_pct:.2f}%; width: {width_pct:.2f}%;"
                 title="{seg.label}: {self._format_time(seg.start)} - {self._format_time(seg.end)}">
                <span class="segment-label">{seg.label}</span>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>视频剪辑时间轴对比 - {video_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            padding: 40px 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            padding: 30px;
        }}

        h1 {{
            font-size: 24px;
            margin-bottom: 8px;
            color: #333;
        }}

        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}

        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #4CAF50;
        }}

        .stat-card.removed {{
            border-left-color: #F44336;
        }}

        .stat-card.info {{
            border-left-color: #2196F3;
        }}

        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}

        .stat-label {{
            color: #666;
            margin-top: 4px;
        }}

        .timeline-wrapper {{
            margin: 40px 0;
        }}

        .timeline-label {{
            font-weight: 600;
            margin-bottom: 12px;
            color: #333;
        }}

        .timeline {{
            position: relative;
            height: 60px;
            background: #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 30px;
        }}

        .segment {{
            position: absolute;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: white;
            font-weight: 500;
            transition: opacity 0.2s;
            cursor: pointer;
        }}

        .segment:hover {{
            opacity: 0.8;
        }}

        .segment.kept {{
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }}

        .segment.removed {{
            background: repeating-linear-gradient(
                45deg,
                #F44336,
                #F44336 10px,
                #d32f2f 10px,
                #d32f2f 20px
            );
        }}

        .segment-label {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            padding: 0 4px;
        }}

        .time-axis {{
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            font-size: 12px;
            color: #666;
        }}

        .legend {{
            display: flex;
            gap: 30px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }}

        .legend-color.kept {{
            background: #4CAF50;
        }}

        .legend-color.removed {{
            background: repeating-linear-gradient(
                45deg,
                #F44336,
                #F44336 5px,
                #d32f2f 5px,
                #d32f2f 10px
            );
        }}

        .clip-list {{
            margin-top: 30px;
        }}

        .clip-list h3 {{
            margin-bottom: 15px;
            color: #333;
        }}

        .clip-item {{
            display: flex;
            justify-content: space-between;
            padding: 12px;
            background: #f8f9fa;
            margin-bottom: 8px;
            border-radius: 6px;
            border-left: 3px solid #4CAF50;
        }}

        .clip-time {{
            font-family: monospace;
            color: #666;
        }}

        .clip-duration {{
            color: #333;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📹 视频剪辑时间轴对比</h1>
        <p class="subtitle">{video_name}</p>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{self._format_time(total_duration)}</div>
                <div class="stat-label">原始时长</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{self._format_time(kept_duration)}</div>
                <div class="stat-label">保留时长</div>
            </div>
            <div class="stat-card removed">
                <div class="stat-value">{self._format_time(removed_duration)}</div>
                <div class="stat-label">裁剪时长</div>
            </div>
            <div class="stat-card info">
                <div class="stat-value">{compression_ratio:.1f}%</div>
                <div class="stat-label">压缩率</div>
            </div>
            <div class="stat-card info">
                <div class="stat-value">{len(kept_segments)}</div>
                <div class="stat-label">片段数量</div>
            </div>
        </div>

        <div class="timeline-wrapper">
            <div class="timeline-label">🎬 剪辑后时间轴</div>
            <div class="timeline">
                {segments_html}
            </div>
            <div class="time-axis">
                {timeline_ticks}
            </div>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color kept"></div>
                <span>保留片段 (Kept)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color removed"></div>
                <span>裁剪片段 (Removed)</span>
            </div>
        </div>

        <div class="clip-list">
            <h3>📋 保留片段列表</h3>
            {self._generate_clip_list(kept_segments)}
        </div>
    </div>
</body>
</html>"""

        return html

    def _generate_ticks(self, total_duration: float) -> str:
        """生成时间轴刻度"""
        ticks = []
        num_ticks = 10

        for i in range(num_ticks + 1):
            time = (total_duration / num_ticks) * i
            percentage = (i / num_ticks) * 100
            ticks.append(f'<span style="position: absolute; left: {percentage:.1f}%;">{self._format_time(time)}</span>')

        return ''.join(ticks)

    def _generate_clip_list(self, segments: List[TimeSegment]) -> str:
        """生成片段列表HTML"""
        if not segments:
            return "<p>无保留片段</p>"

        items = ""
        for i, seg in enumerate(segments, 1):
            duration = seg.end - seg.start
            items += f"""
            <div class="clip-item">
                <span>片段 {i}: <span class="clip-time">{self._format_time(seg.start)} - {self._format_time(seg.end)}</span></span>
                <span class="clip-duration">时长: {self._format_time(duration)}</span>
            </div>
            """

        return items

    def _format_time(self, seconds: float) -> str:
        """格式化时间为 MM:SS 或 HH:MM:SS"""
        td = timedelta(seconds=int(seconds))
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"


# 便捷函数
def generate_timeline_report(
    original_video: str,
    output_dir: str = "data/output",
    clip_order_file: str = "clip_order.txt"
) -> str:
    """
    为处理结果生成时间轴报告

    Args:
        original_video: 原始视频路径
        output_dir: 输出目录
        clip_order_file: 剪辑顺序文件名

    Returns:
        HTML报告文件路径
    """
    visualizer = TimelineVisualizer(output_dir)
    clip_order_path = os.path.join(output_dir, clip_order_file)

    if not os.path.exists(clip_order_path):
        print(f"警告: 找不到剪辑顺序文件 {clip_order_path}")
        return ""

    output_path = visualizer.generate_html_timeline(
        original_video,
        clip_order_path
    )

    print(f"✅ 时间轴对比图已生成: {output_path}")
    return output_path


def generate_combined_timeline_report(
    video_paths: Dict[str, str],
    output_dir: str = "data/output",
    clip_order_file: str = "clip_order.txt"
) -> str:
    """
    为多个视频生成合并的时间轴报告（单HTML文件）

    Args:
        video_paths: 字典 {视频名: 视频路径}
        output_dir: 输出目录
        clip_order_file: 剪辑顺序文件名

    Returns:
        HTML报告文件路径
    """
    visualizer = TimelineVisualizer(output_dir)
    clip_order_path = os.path.join(output_dir, clip_order_file)

    if not os.path.exists(clip_order_path):
        print(f"警告: 找不到剪辑顺序文件 {clip_order_path}")
        return ""

    output_path = visualizer.generate_combined_html_timeline(
        video_paths,
        clip_order_path
    )

    if output_path:
        print(f"✅ 合并时间轴对比图已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    # 测试
    import sys

    if len(sys.argv) < 2:
        print("用法: python timeline_visualizer.py <原始视频路径> [输出目录]")
        sys.exit(1)

    video_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/output"

    result = generate_timeline_report(video_path, output_dir)
    if result:
        print(f"请用浏览器打开查看: {result}")

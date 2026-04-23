"""尾部动画 — 素材选取或 FFmpeg 自动生成"""
import os
import random
import subprocess
import tempfile
from pathlib import Path


class TailAnimation:
    """提供尾部动画视频：优先从素材目录选取，为空则自动生成"""

    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}

    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path

    def get_tail_source(self, w: int, h: int, sr: int, fps: float,
                        overlay_dir: str) -> str | None:
        """返回尾部动画视频路径

        优先从 overlay_dir 随机选一个视频；目录为空则自动生成。
        返回 None 表示无法提供尾部动画。
        """
        # 优先从素材目录选
        if os.path.isdir(overlay_dir):
            files = [
                f for f in os.listdir(overlay_dir)
                if Path(f).suffix.lower() in self.VIDEO_EXTENSIONS
            ]
            if files:
                return os.path.join(overlay_dir, random.choice(files))

        # 目录为空 → FFmpeg 自动生成
        return self._generate(w, h, sr, fps)

    def _generate(self, w: int, h: int, sr: int, fps: float) -> str | None:
        """生成 1-3 秒随机动画到临时文件"""
        dur = round(random.uniform(1.0, 3.0), 2)
        tmp_path = tempfile.mktemp(suffix=".mp4")

        # 随机选一种动画方案（避免 noise，纯随机噪声不可压缩会导致文件暴涨）
        scheme = random.choice(["gradient", "color_fade", "fade_to_black"])

        if scheme == "gradient":
            color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            video_src = (
                f"color=c={color}:s={w}x{h}:d={dur}:r={fps:.6f},"
                f"format=yuv420p"
            )
        elif scheme == "color_fade":
            # 从随机色渐变到另一个随机色
            c1 = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            c2 = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            video_src = (
                f"color=c={c1}:s={w}x{h}:d={dur}:r={fps:.6f},"
                f"fade=t=out:st=0:d={dur}:color={c2},"
                f"format=yuv420p"
            )
        else:  # fade_to_black
            color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
            video_src = (
                f"color=c={color}:s={w}x{h}:d={dur}:r={fps:.6f},"
                f"fade=t=out:st=0:d={dur},"
                f"format=yuv420p"
            )

        # 生成静音音轨
        audio_src = f"anullsrc=r={sr}:cl=stereo"

        cmd = [
            self.ffmpeg_path, "-y",
            "-f", "lavfi", "-i", video_src,
            "-f", "lavfi", "-i", audio_src,
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac",
            "-shortest",
            tmp_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and os.path.exists(tmp_path):
                return tmp_path
        except Exception:
            pass

        # 生成失败，清理
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return None

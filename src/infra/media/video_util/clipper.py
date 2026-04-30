"""OverlayClipper — 将长视频切成若干短片作为尾部动画素材"""
import json
import os
import subprocess
from pathlib import Path

from utils.log import get_logger

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}


class OverlayClipper:
    """用 FFmpeg 将长视频切成若干段短片

    跳过片头 2s + 片尾 3s，有效区间内均匀取点，
    使用 -c copy 快速切片（不重编码）。
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def clip_dir(self, src_dir: str, output_dir: str,
                 clip_duration: float = 5.0,
                 max_clips: int = 5,
                 min_source_duration: float = 15.0) -> dict:
        """扫描 src_dir 下所有视频，逐个切片到 output_dir

        返回 {"total": N, "clipped": M, "skipped": K, "outputs": [...]}
        """
        os.makedirs(output_dir, exist_ok=True)

        src_files = sorted(
            p for p in Path(src_dir).iterdir()
            if p.suffix.lower() in VIDEO_EXTENSIONS
        )

        result = {"total": len(src_files), "clipped": 0, "skipped": 0, "outputs": []}

        for i, src_path in enumerate(src_files, 1):
            duration = self._get_duration(str(src_path))
            if duration is None:
                logger.warning(f"[{i}/{len(src_files)}] 探测时长失败，跳过: {src_path.name}")
                result["skipped"] += 1
                continue

            if duration < min_source_duration:
                logger.info(f"[{i}/{len(src_files)}] 时长 {duration:.1f}s < {min_source_duration}s，跳过: {src_path.name}")
                result["skipped"] += 1
                continue

            logger.info(f"[{i}/{len(src_files)}] 切片: {src_path.name} ({duration:.1f}s)")
            clips = self.clip(str(src_path), output_dir, clip_duration, max_clips)
            result["clipped"] += len(clips)
            result["outputs"].extend(clips)

        return result

    def clip(self, src_path: str, output_dir: str,
             clip_duration: float = 5.0,
             max_clips: int = 5) -> list[str]:
        """将单个视频切成若干段短片，返回生成的文件路径列表"""
        os.makedirs(output_dir, exist_ok=True)

        duration = self._get_duration(src_path)
        if duration is None:
            logger.warning(f"探测时长失败: {src_path}")
            return []

        HEAD_SKIP = 2.0   # 跳过片头
        TAIL_SKIP = 3.0   # 跳过片尾
        effective_start = HEAD_SKIP
        effective_end = duration - TAIL_SKIP

        if effective_end - effective_start < clip_duration:
            logger.warning(f"有效区间 {effective_end - effective_start:.1f}s 不足 {clip_duration}s，跳过")
            return []

        # 均匀取切点，起点间距至少 2s（允许片段内容重叠）
        MIN_START_GAP = 2.0
        available = effective_end - effective_start - clip_duration
        n_slots = int(available / MIN_START_GAP) + 1
        n_clips = min(max_clips, n_slots)

        if n_clips <= 0:
            return []

        gap = available / max(n_clips - 1, 1) if n_clips > 1 else 0
        starts = [effective_start + i * gap for i in range(n_clips)]

        stem = Path(src_path).stem
        outputs = []

        for idx, start in enumerate(starts):
            out_name = f"{stem}_clip_{idx:02d}.mp4"
            out_path = os.path.join(output_dir, out_name)

            # 已存在则跳过
            if os.path.isfile(out_path):
                logger.info(f"  已存在，跳过: {out_name}")
                outputs.append(out_path)
                continue

            cmd = [
                self.ffmpeg_path, "-y",
                "-ss", f"{start:.3f}",
                "-i", src_path,
                "-t", f"{clip_duration:.3f}",
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                out_path,
            ]

            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if proc.returncode == 0 and os.path.isfile(out_path):
                    size_kb = os.path.getsize(out_path) / 1024
                    logger.info(f"  clip_{idx:02d}: {start:.1f}s+{clip_duration}s → {size_kb:.0f}KB")
                    outputs.append(out_path)
                else:
                    logger.warning(f"  clip_{idx:02d} 失败: {proc.stderr[-200:]}")
            except subprocess.TimeoutExpired:
                logger.warning(f"  clip_{idx:02d} 超时")

        return outputs

    def _get_duration(self, path: str) -> float | None:
        """ffprobe 探测视频时长（秒）"""
        cmd = [
            self.ffprobe_path, "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format=duration",
            path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(proc.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return None

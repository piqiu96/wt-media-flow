"""关键帧检测 — 在指定时间范围内找 I-frame 作为自然插入点"""
import json
import random
import subprocess


class SceneDetector:
    """利用 ffprobe 检测关键帧位置"""

    def __init__(self, ffprobe_path: str):
        self.ffprobe_path = ffprobe_path

    def find_insert_point(self, video_path: str,
                          min_t: float = 10.0, max_t: float = 15.0,
                          duration: float = 0) -> float:
        """在 [min_t, max_t] 范围内找关键帧，返回最佳插入时间点

        策略：
        1. 视频时长 < max_t → 回退到 duration * 0.3
        2. 在范围内检测 I-frame → 选最接近 min_t 的关键帧
        3. 无关键帧 → 在 [min_t, max_t] 随机选点
        """
        # 视频太短，回退
        if 0 < duration < max_t:
            return min(min_t, duration * 0.3)

        try:
            keyframes = self._detect_keyframes(video_path, min_t, max_t)
            if keyframes:
                # 选最接近 min_t 的关键帧（偏前更自然）
                return min(keyframes, key=lambda t: abs(t - min_t))
        except Exception:
            pass

        # fallback: 随机选点
        return random.uniform(min_t, max_t)

    def _detect_keyframes(self, video_path: str,
                          min_t: float, max_t: float) -> list[float]:
        """用 ffprobe 检测指定范围内的 I-frame 时间点"""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-select_streams", "v",
            "-show_frames",
            "-read_intervals", f"{min_t}%{max_t}",
            "-show_entries", "frame=pts_time,pict_type",
            video_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        keyframes = []

        for frame in data.get("frames", []):
            if frame.get("pict_type") == "I":
                pts = frame.get("pts_time")
                if pts:
                    t = float(pts)
                    if min_t <= t <= max_t:
                        keyframes.append(t)

        return keyframes

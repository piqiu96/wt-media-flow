"""视频去重 filter 生成 — 返回 FFmpeg filter 字符串列表"""
import random


class VideoDedup:
    """生成随机轻量 FFmpeg filter，让每次合成产出的视频指纹不同"""

    @staticmethod
    def guide_dedup_filters() -> tuple[list[str], float]:
        """引导视频的随机轻量变换 filter

        返回: (video_filters, speed_ratio)
            - video_filters: FFmpeg video filter 字符串列表
            - speed_ratio: 速度系数（用于音频 atempo 同步）
        """
        filters = []

        # 亮度/对比度/饱和度微调（肉眼不可见）
        b = random.uniform(-0.03, 0.03)
        c = random.uniform(0.97, 1.03)
        s = random.uniform(0.97, 1.03)
        filters.append(f"eq=brightness={b:.4f}:contrast={c:.4f}:saturation={s:.4f}")

        # 边缘裁切（2-6 像素）
        dx = random.randint(2, 6)
        dy = random.randint(2, 6)
        filters.append(f"crop=iw-{dx}:ih-{dy}:{dx // 2}:{dy // 2}")

        # 播放速度微调（±2%）
        speed_ratio = random.uniform(0.98, 1.02)
        filters.append(f"setpts={speed_ratio:.4f}*PTS")

        return filters, speed_ratio

    @staticmethod
    def guide_audio_dedup_filter(speed_ratio: float) -> str:
        """引导音频的速度同步 filter

        参数:
            speed_ratio: 来自 guide_dedup_filters() 的速度系数
        返回: atempo filter 字符串
        """
        # atempo 是 PTS 的倒数（PTS 变慢 → 音频加速）
        atempo = 1.0 / speed_ratio
        return f"atempo={atempo:.4f}"

    @staticmethod
    def final_dedup_filters() -> list[str]:
        """最终视频的随机变换 filter"""
        filters = []

        # 色调偏移（±3 度）
        h = random.uniform(-3, 3)
        filters.append(f"hue=h={h:.2f}")

        # 亮度微调
        b = random.uniform(-0.02, 0.02)
        filters.append(f"eq=brightness={b:.4f}")

        # 轻微模糊或锐化
        sharp = random.uniform(-0.3, 0.3)
        filters.append(f"unsharp=3:3:{sharp:.2f}:3:3:0")

        return filters

"""视频处理工具库"""
from .dedup import VideoDedup
from .scene import SceneDetector
from .animation import TailAnimation
from .clipper import OverlayClipper

__all__ = ["VideoDedup", "SceneDetector", "TailAnimation", "OverlayClipper"]

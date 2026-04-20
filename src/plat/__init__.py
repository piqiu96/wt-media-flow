from typing import Dict, Type
from .base import BasePlatform
from .bilibili.upload import BilibiliPlatform
from .baijiahao.bjh import BaijiahaoPlatform
from .xiaohongshu.upload import XiaohongshuPlatform

_PLATFORM_REGISTRY: Dict[str, Type[BasePlatform]] = {
    "bilibili": BilibiliPlatform,
    "baijiahao": BaijiahaoPlatform,
    "xiaohongshu": XiaohongshuPlatform,
}

def get_platform(platform_name: str) -> Type[BasePlatform]:
    """获取平台类"""
    if platform_name not in _PLATFORM_REGISTRY:
        raise ValueError(f"不支持的平台: {platform_name}")
    return _PLATFORM_REGISTRY[platform_name]

def register_platform(name: str, platform_class: Type[BasePlatform]):
    """注册新平台"""
    _PLATFORM_REGISTRY[name] = platform_class

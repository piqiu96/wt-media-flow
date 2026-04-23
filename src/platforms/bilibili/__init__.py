"""
哔哩哔哩平台 — 自动注册发布器 + Mapper
"""
from platforms.registry import PlatformRegistry
from platforms.bilibili.publisher import BilibiliPublisher
from platforms.bilibili import mapper as bili_mapper

PlatformRegistry.register(
    "bilibili",
    publisher_cls=BilibiliPublisher,
    commenter_cls=None,  # 暂不支持评论
    mapper=bili_mapper,
)

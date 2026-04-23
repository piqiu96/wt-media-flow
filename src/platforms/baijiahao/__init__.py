"""
百家号平台 — 自动注册发布器 + 评论器 + Mapper
"""
from platforms.registry import PlatformRegistry
from platforms.baijiahao.publisher import BaijiahaoPublisher
from platforms.baijiahao.commenter import BaijiahaoCommenter
from platforms.baijiahao import mapper as bjh_mapper

PlatformRegistry.register(
    "baijiahao",
    publisher_cls=BaijiahaoPublisher,
    commenter_cls=BaijiahaoCommenter,
    mapper=bjh_mapper,
)

"""
PlatformRegistry — 平台注册表

注册和获取各平台的发布器、评论器、Mapper 实例。
"""
from platforms.base import (
    PublisherProtocol, CommenterProtocol, MapperProtocol,
    PlatformCapabilities,
)


class PlatformRegistry:
    """平台注册表（类级别单例）"""

    _publishers: dict[str, type] = {}
    _commenters: dict[str, type] = {}
    _mappers: dict[str, object] = {}  # mapper 可以是模块或类实例

    @classmethod
    def register(cls, platform_name: str, publisher_cls: type,
                 commenter_cls: type | None = None,
                 mapper=None):
        """注册平台的发布器、评论器类和 mapper"""
        cls._publishers[platform_name] = publisher_cls
        if commenter_cls:
            cls._commenters[platform_name] = commenter_cls
        if mapper:
            cls._mappers[platform_name] = mapper

    @classmethod
    def get_publisher(cls, name: str) -> PublisherProtocol:
        """获取平台发布器实例"""
        publisher_cls = cls._publishers.get(name)
        if not publisher_cls:
            available = ", ".join(cls._publishers.keys())
            raise ValueError(f"不支持的平台: {name}，可用: {available}")
        return publisher_cls()

    @classmethod
    def get_commenter(cls, name: str) -> CommenterProtocol:
        """获取平台评论器实例"""
        commenter_cls = cls._commenters.get(name)
        if not commenter_cls:
            available = ", ".join(cls._commenters.keys())
            raise ValueError(f"平台 {name} 不支持评论，可用: {available}")
        return commenter_cls()

    @classmethod
    def get_mapper(cls, name: str) -> MapperProtocol:
        """获取平台 Mapper（载荷构建器）"""
        mapper = cls._mappers.get(name)
        if not mapper:
            raise ValueError(f"平台 {name} 未注册 mapper")
        return mapper

    @classmethod
    def get_capabilities(cls, name: str) -> PlatformCapabilities:
        """获取平台能力声明"""
        pub = cls.get_publisher(name)
        return pub.capabilities

    @classmethod
    def has_commenter(cls, name: str) -> bool:
        return name in cls._commenters

    @classmethod
    def has_mapper(cls, name: str) -> bool:
        return name in cls._mappers

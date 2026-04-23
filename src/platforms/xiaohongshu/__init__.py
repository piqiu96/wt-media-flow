"""
小红书平台适配（待实现）

当前状态：枚举已定义，发布/评论逻辑尚未实现。
调用任何小红书发布接口会收到明确的 NotImplementedError。
"""
from platforms.base import (
    PlatformCapabilities, PublishPayload, FillResult, SubmitResult,
)
from platforms.registry import PlatformRegistry
from playwright.sync_api import Page


class XiaohongshuPublisher:
    """小红书发布器（待实现占位）"""

    platform_name = "xiaohongshu"
    capabilities = PlatformCapabilities(
        supports_video=True,
        supports_cover_upload=True,
        supports_comment=False,
        supports_scheduled_publish=False,
        requires_manual_confirm=True,
        allows_same_source_reuse=False,
    )

    def fill_form(self, page: Page, payload: PublishPayload) -> FillResult:
        raise NotImplementedError("小红书发布器尚未实现，请先完成 platforms/xiaohongshu/ 开发")

    def submit(self, page: Page) -> SubmitResult:
        raise NotImplementedError("小红书发布器尚未实现")

    def fetch_published_url(self, page: Page,
                            known_urls: set[str] | None = None) -> str:
        raise NotImplementedError("小红书发布器尚未实现")


# 注册到平台注册表
PlatformRegistry.register("xiaohongshu", XiaohongshuPublisher)

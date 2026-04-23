"""
平台适配层 — 统一协议定义

所有平台发布器/评论器需遵循此处定义的 Protocol。
上层 workflow 只依赖这些协议，不直接依赖具体平台实现。
"""
from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from playwright.sync_api import Page


# ── 数据对象 ──────────────────────────────────────────────

@dataclass
class PlatformCapabilities:
    """平台能力声明"""
    supports_video: bool = True
    supports_cover_upload: bool = False
    supports_comment: bool = False
    supports_scheduled_publish: bool = False
    requires_manual_confirm: bool = True      # 百家号=True
    allows_same_source_reuse: bool = False    # 哔哩哔哩=True, 百家号=False


@dataclass
class PublishPayload:
    """发布载荷 DTO — 平台层不碰 ORM 模型，只接收此对象"""
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cover_path: str | None = None
    topic: str | None = None
    category: str = ""


class FillResult(TypedDict, total=False):
    success: bool
    error: str | None
    message: str | None


class SubmitResult(TypedDict, total=False):
    success: bool
    error: str | None


class CommentResult(TypedDict, total=False):
    success: bool
    error: str | None
    message: str | None


# ── 发布器协议 ────────────────────────────────────────────

class PublisherProtocol(Protocol):
    """平台发布器统一协议

    三段式：fill_form → submit → fetch_published_url
    """
    platform_name: str
    capabilities: PlatformCapabilities

    def fill_form(self, page: Page, payload: PublishPayload) -> FillResult:
        """阶段1：填充表单（上传视频+填标题等），不提交"""
        ...

    def submit(self, page: Page) -> SubmitResult:
        """阶段2：提交发布（人工确认模式下为空操作）"""
        ...

    def fetch_published_url(self, page: Page, known_urls: set[str] | None = None) -> str:
        """阶段3：从内容列表页抓取最新发布链接"""
        ...


# ── 评论器协议 ────────────────────────────────────────────

class CommenterProtocol(Protocol):
    """平台评论器统一协议"""
    platform_name: str

    def fill_comment(self, page: Page, url: str, content: str) -> CommentResult:
        """导航到目标 URL 并填入评论内容（不提交）"""
        ...

    def submit_comment(self, page: Page) -> CommentResult:
        """点击提交评论"""
        ...

    def auto_comment(self, page: Page, url: str, content: str) -> CommentResult:
        """全自动评论：fill + submit 一步到位"""
        ...


# ── Mapper 协议 ─────────────────────────────────────────

class MapperProtocol(Protocol):
    """平台载荷构建器协议

    各平台根据自身规则（标题长度、标签数量、封面处理）构建 PublishPayload。
    """

    def build_payload(self, video_path: str, title: str,
                      description: str = "",
                      tags: list[str] | None = None,
                      cover_url: str | None = None,
                      topic: str | None = None,
                      category: str = "") -> PublishPayload:
        """根据平台规则构建发布载荷"""
        ...

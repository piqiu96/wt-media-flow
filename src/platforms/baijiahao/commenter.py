"""
百家号评论器 — 实现 CommenterProtocol

三步式：fill_comment → submit_comment → auto_comment (= fill + submit)
"""
import time
import random
from urllib.parse import urlparse

from playwright.sync_api import Page

from platforms.base import CommentResult
from utils.log import get_logger

logger = get_logger(__name__)

# 超时常量
_TIMEOUT = 300000        # 5 分钟
_IDLE_TIMEOUT = 5000     # 5 秒
_CMT_SEL_TIMEOUT = 5000  # 5 秒

# 评论框选择器（按优先级）
_COMMENT_SELECTORS = [
    'textarea[placeholder*="发表神评妙论"]',
    'textarea[placeholder*="评论"]',
    'textarea[placeholder*="说点什么"]',
    'div[contenteditable="true"][placeholder*="评论"]',
    '[class*="comment"] textarea',
    '[class*="commentInput"] textarea',
]

# 页面错误信号词
_ERROR_SIGNALS = [
    "错误", "not found", "404", "无法访问",
    "该内容暂时无法查看", "内容不存在", "已删除", "违规",
]

# 百家号合法域名
_VALID_HOSTS = ("baijiahao.baidu.com", "haokan.baidu.com", "baidu.com")


class BaijiahaoCommenter:
    """百家号评论器"""

    platform_name = "baijiahao"

    # ── fill_comment ──────────────────────────────────────────

    def fill_comment(self, page: Page, url: str, content: str) -> CommentResult:
        """导航到目标 URL，找到评论框并填入内容（不提交）"""
        try:
            self._navigate_and_validate(page, url)

            input_el = self._find_comment_input(page)
            if not input_el:
                self._debug_inputs(page)
                raise RuntimeError("未找到评论输入框")

            page.click(input_el)
            time.sleep(random.uniform(0.3, 0.8))
            page.keyboard.type(content)
            time.sleep(random.uniform(0.5, 1))
            logger.info(f"评论内容已填入: {content[:60]}")
            return CommentResult(success=True)

        except Exception as e:
            return CommentResult(success=False, error=str(e))

    # ── submit_comment ────────────────────────────────────────

    def submit_comment(self, page: Page) -> CommentResult:
        """点击评论提交按钮"""
        try:
            time.sleep(random.uniform(1.5, 2.5))

            submit_selectors = [
                'button:has-text("发布")',
                'button:has-text("评论")',
                '[class*="comment"] button[class*="submit"]',
                '[class*="commentInput"] button',
                '[class*="comment"] button:not([disabled])',
            ]
            submit_el = None
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible() and btn.is_enabled():
                        submit_el = sel
                        break
                except Exception:
                    pass
            if not submit_el:
                raise RuntimeError("未找到可点击的提交按钮")

            page.locator(submit_el).first.click()
            logger.info(f"已点击提交: {submit_el}")

            time.sleep(random.uniform(1, 2))
            return CommentResult(success=True)

        except Exception as e:
            return CommentResult(success=False, error=str(e))

    # ── auto_comment ──────────────────────────────────────────

    def auto_comment(self, page: Page, url: str, content: str) -> CommentResult:
        """全自动评论：fill + submit 一步到位"""
        result = self.fill_comment(page, url, content)
        if not result.get("success"):
            return result
        return self.submit_comment(page)

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _navigate_and_validate(page: Page, url: str):
        """导航到 URL 并验证页面有效性"""
        page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT)
        try:
            page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
        except Exception:
            pass
        time.sleep(random.uniform(2, 3))

        page_title = page.title()
        page_url = page.url
        logger.info(f"页面标题: {page_title}")
        logger.info(f"页面URL:  {page_url}")

        if any(s.lower() in page_title.lower() for s in _ERROR_SIGNALS):
            raise RuntimeError(f"页面不可评论（标题: {page_title}）")

        host = urlparse(page_url).hostname or ""
        if not any(host.endswith(h) for h in _VALID_HOSTS):
            raise RuntimeError(f"页面跳转到未知域名: {host}")

    @staticmethod
    def _find_comment_input(page: Page) -> str | None:
        """尝试定位评论输入框，返回匹配的选择器或 None"""
        for sel in _COMMENT_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=_CMT_SEL_TIMEOUT)
                logger.info(f"找到评论框: {sel}")
                return sel
            except Exception:
                pass
        return None

    @staticmethod
    def _debug_inputs(page: Page):
        """输出页面可输入元素用于调试"""
        els = page.query_selector_all(
            'input, textarea, div[contenteditable="true"]')
        logger.warning(f"[调试] 未找到评论框，页面共 {len(els)} 个可输入元素：")
        for el in els[:8]:
            ph = (el.get_attribute("placeholder")
                  or el.get_attribute("data-placeholder") or "")
            cls = (el.get_attribute("class") or "")[:80]
            tag = el.evaluate("e => e.tagName")
            logger.warning(f"  <{tag}> placeholder='{ph}' class='{cls}'")

"""
BrowserSessionService — 统一管理 BitBrowser + Playwright 生命周期

从 cmd/plan.py 和 cmd/comment.py 中提取的公共浏览器会话管理逻辑。
"""
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright, Playwright

from infra.browser.bit_api import BitBrowserAPI
from utils.log import get_logger

logger = get_logger(__name__)


@dataclass
class BrowserSession:
    """一次浏览器会话的上下文"""
    profile_id: str
    browser: Browser
    context: BrowserContext
    debug_port: str
    _playwright: Optional[Playwright] = field(default=None, repr=False)
    _page_count: int = field(default=0, repr=False)


class BrowserSessionService:
    """统一管理 BitBrowser + Playwright 生命周期

    用法:
        svc = BrowserSessionService()
        session = svc.open(profile_id)
        try:
            page = svc.new_page(session)
            # ... 操作 page ...
        finally:
            svc.close(session)
    """

    def __init__(self):
        self._bit_api = BitBrowserAPI()

    def open(self, profile_id: str) -> BrowserSession:
        """打开比特浏览器 → 连接 CDP → 清理残留 Tab → 返回会话"""
        # 1. 启动比特浏览器
        browser_info = self._bit_api.open_browser(profile_id)
        debug_port = browser_info.get("data", {}).get("http", "")
        if not debug_port:
            raise RuntimeError(f"比特浏览器未返回调试端口: profile_id={profile_id}")
        if not debug_port.startswith("http"):
            debug_port = f"http://{debug_port}"
        logger.info(f"比特浏览器已启动: profile_id={profile_id}, port={debug_port}")

        # 2. 连接 CDP
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(debug_port)
        ctx = browser.contexts[0]

        # 3. 挂诊断监听
        browser.on("disconnected",
                    lambda: logger.warning("[DIAG] browser disconnected (CDP dropped)"))
        ctx.on("close", lambda: logger.warning("[DIAG] BrowserContext closed"))
        for ep in ctx.pages:
            self._attach_page_diag(ep)
        ctx.on("page", lambda np: self._attach_page_diag(np))

        # 4. 清理残留 Tab，只保留第一个
        for old_page in list(ctx.pages)[1:]:
            try:
                old_page.close()
            except Exception:
                pass

        return BrowserSession(
            profile_id=profile_id,
            browser=browser,
            context=ctx,
            debug_port=debug_port,
            _playwright=pw,
        )

    def new_page(self, session: BrowserSession, reuse_first: bool = True) -> Page:
        """从会话获取一个页面

        Args:
            session: 浏览器会话
            reuse_first: 第一次调用时复用已有 Tab 而不是新建
        """
        session._page_count += 1
        if reuse_first and session._page_count == 1 and session.context.pages:
            page = session.context.pages[0]
        else:
            page = session.context.new_page()
        try:
            page.bring_to_front()
        except Exception:
            pass
        return page

    def close(self, session: BrowserSession):
        """关闭 Playwright → 关闭比特浏览器"""
        try:
            session.browser.close()
        except Exception as e:
            logger.warning(f"browser.close() 失败: {e}")
        try:
            if session._playwright:
                session._playwright.stop()
        except Exception:
            pass
        try:
            self._bit_api.close_browser(session.profile_id)
        except Exception as e:
            logger.warning(f"close_browser() 失败: {e}")

    @staticmethod
    def _attach_page_diag(page: Page):
        """为页面挂诊断事件"""
        page.on("close", lambda pg=page: logger.debug(f"[DIAG] page closed: {pg.url}"))
        page.on("crash", lambda pg=page: logger.warning(f"[DIAG] page CRASHED: {pg.url}"))

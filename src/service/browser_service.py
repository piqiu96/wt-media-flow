"""浏览器连接池管理"""
import threading
import time
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from playwright.sync_api import Browser, Page
from library.bit_api import BitBrowserAPI


@dataclass
class BrowserSession:
    profile_id: str
    ws_url: str
    browser: Browser
    last_used: datetime
    page: Optional[Page] = None


class BrowserService:
    def __init__(self, pool_size: int = 5, idle_timeout: int = 600):
        self.api = BitBrowserAPI()
        self.pool_size = pool_size
        self.idle_timeout = idle_timeout
        self._lock = threading.Lock()
        self._pool: Dict[str, BrowserSession] = {}
        self._page_cache: Dict[str, Page] = {}

    def open_browser(self, profile_id: str, playwright) -> BrowserSession:
        """打开浏览器，优先从池中获取"""
        with self._lock:
            if profile_id in self._pool:
                session = self._pool[profile_id]
                if (datetime.utcnow() - session.last_used).seconds < self.idle_timeout:
                    session.last_used = datetime.utcnow()
                    return session
                else:
                    self._close_session_unlocked(profile_id)

        # 打开新浏览器（不持锁，避免阻塞）
        result = self.api.open_browser(profile_id)
        if not result.get("success"):
            raise Exception(f"打开浏览器失败: {result}")

        ws_url = result["data"]["ws"]
        browser = playwright.chromium.connect_over_cdp(ws_url)

        session = BrowserSession(
            profile_id=profile_id,
            ws_url=ws_url,
            browser=browser,
            last_used=datetime.utcnow()
        )

        with self._lock:
            self._pool[profile_id] = session
        return session

    def get_page(self, profile_id: str, session: BrowserSession) -> Page:
        """获取或创建页面，支持复用"""
        with self._lock:
            if profile_id in self._page_cache:
                try:
                    page = self._page_cache[profile_id]
                    if not page.is_closed():
                        return page
                    del self._page_cache[profile_id]
                except:
                    del self._page_cache[profile_id]

        # 创建新页面
        if not session.browser.contexts:
            page = session.browser.new_page()
        else:
            page = session.browser.contexts[0].new_page()

        with self._lock:
            self._page_cache[profile_id] = page
        return page

    def close_browser(self, profile_id: str):
        """关闭浏览器（保留在池中供复用）"""
        with self._lock:
            if profile_id in self._pool:
                self._pool[profile_id].last_used = datetime.utcnow()

    def _close_session_unlocked(self, profile_id: str):
        """真正关闭浏览器会话（调用方已持锁）"""
        if profile_id in self._pool:
            session = self._pool[profile_id]
            try:
                session.browser.close()
            except:
                pass
            del self._pool[profile_id]
        if profile_id in self._page_cache:
            del self._page_cache[profile_id]

    def cleanup_expired(self):
        """清理过期的浏览器会话"""
        with self._lock:
            now = datetime.utcnow()
            expired_profiles = [
                pid for pid, session in self._pool.items()
                if (now - session.last_used).seconds >= self.idle_timeout
            ]
            for pid in expired_profiles:
                self._close_session_unlocked(pid)

    def shutdown(self):
        """关闭所有浏览器"""
        with self._lock:
            for profile_id in list(self._pool.keys()):
                self._close_session_unlocked(profile_id)
                self.api.close_browser(profile_id)

    def get_pool_status(self) -> Dict:
        """获取浏览器池状态"""
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "max_pool_size": self.pool_size,
                "profiles": list(self._pool.keys())
            }

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from playwright.sync_api import Page

class BasePlatform(ABC):
    """平台基类，所有平台插件需继承此类"""

    platform_name: str = "base"

    def __init__(self, page: Page):
        self.page = page

    @abstractmethod
    def upload_video(self, video_path: str, title: str,
                    description: str = "", tags: str = "",
                    cover_path: Optional[str] = None) -> Dict[str, Any]:
        """上传视频

        Returns:
            {
                "success": bool,
                "video_id": Optional[str],
                "url": Optional[str],
                "error": Optional[str],
                "message": Optional[str]
            }
        """
        pass

    def comment(self, content: str) -> Dict[str, Any]:
        """发表评论（可选功能）"""
        return {"success": False, "error": "not_implemented"}

    def like(self) -> Dict[str, Any]:
        """点赞（可选功能）"""
        return {"success": False, "error": "not_implemented"}

    def check_login(self) -> bool:
        """检查登录状态"""
        return True

    def wait_for_upload(self, timeout: int = 300) -> bool:
        """等待上传完成"""
        return True

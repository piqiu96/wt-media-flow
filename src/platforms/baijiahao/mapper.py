"""
百家号 Mapper — 封面下载/缩放 + 载荷构建

从 plan.py L372-396 提取的封面处理逻辑。
"""
import tempfile

import requests as _req
from PIL import Image

from platforms.base import PublishPayload
from utils.log import get_logger

logger = get_logger(__name__)

# 百家号封面最低要求
_MIN_COVER_WIDTH = 720
_MIN_COVER_HEIGHT = 405


def download_and_resize_cover(cover_url: str) -> str | None:
    """下载封面并确保尺寸不低于 720×405，返回本地临时文件路径"""
    if not cover_url:
        return None
    try:
        resp = _req.get(cover_url, timeout=30)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(resp.content)
        tmp.close()

        # 尺寸不足时等比放大
        try:
            img = Image.open(tmp.name)
            w, h = img.size
            scale = max(_MIN_COVER_WIDTH / w, _MIN_COVER_HEIGHT / h)
            if scale > 1:
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                img.save(tmp.name, "JPEG", quality=92)
                logger.info(f"封面放大: {w}×{h} → {new_w}×{new_h}")
        except Exception as e:
            logger.warning(f"封面 resize 失败（跳过）: {e}")

        return tmp.name
    except Exception as e:
        logger.warning(f"封面下载失败（跳过）: {e}")
        return None


def build_payload(video_path: str, title: str,
                  description: str = "",
                  tags: list[str] | None = None,
                  cover_url: str | None = None,
                  topic: str | None = None,
                  category: str = "") -> PublishPayload:
    """构建百家号发布载荷（含封面下载缩放）"""
    cover_path = download_and_resize_cover(cover_url) if cover_url else None
    return PublishPayload(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags or [],
        cover_path=cover_path,
        topic=topic,
        category=category,
    )

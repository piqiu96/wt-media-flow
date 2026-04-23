"""
哔哩哔哩 Mapper — 载荷构建 + 标题处理

B站特有规则：
- 标题最长 80 字符
- 标签最多 10 个
- 同素材可重复使用（allows_same_source_reuse=True）
"""
from platforms.base import PublishPayload
from utils.log import get_logger

logger = get_logger(__name__)

# B站标题最大长度
_MAX_TITLE_LEN = 80


def build_payload(video_path: str, title: str,
                  description: str = "",
                  tags: list[str] | None = None,
                  cover_url: str | None = None,
                  topic: str | None = None,
                  category: str = "") -> PublishPayload:
    """构建B站发布载荷"""
    # B站标题截断
    if len(title) > _MAX_TITLE_LEN:
        title = title[:_MAX_TITLE_LEN - 3] + "..."
        logger.info(f"B站标题截断至 {_MAX_TITLE_LEN} 字符")

    # B站标签限制 10 个
    clean_tags = []
    if tags:
        for t in tags[:10]:
            t = t.strip().lstrip("#")
            if t:
                clean_tags.append(t)

    return PublishPayload(
        video_path=video_path,
        title=title,
        description=description,
        tags=clean_tags,
        cover_path=None,  # B站封面暂不自动上传
        topic=topic,
        category=category,
    )

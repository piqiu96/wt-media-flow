"""素材采集编排器"""
import json
from datetime import datetime

from db.database import SessionLocal
from db.repositories import VideoRepository


class ClawProcessor:
    def run(self, items: list[dict], platform: str = "douyin", category: str = "") -> dict:
        """
        批量素材入库。

        Args:
            items: DouyinApi 返回的标准化 dict 列表
            platform: 来源平台
            category: 分类标签（如 '游戏'）

        Returns:
            {"total": N, "added": N, "skipped": N, "failed": N}
        """
        stats = {"total": len(items), "added": 0, "skipped": 0, "failed": 0}

        db = SessionLocal()
        try:
            repo = VideoRepository(db)

            for i, item in enumerate(items, 1):
                vid = item.get("vid", "")
                title = item.get("title", "")

                try:
                    # 去重检查
                    existing = repo.get_by_source_vid(platform, vid)
                    if existing:
                        print(f"  [{i}/{len(items)}] 跳过（已存在）: {vid} - {title[:40]}")
                        stats["skipped"] += 1
                        continue

                    # 入库
                    raw_data_str = json.dumps(item.get("raw_data", {}), ensure_ascii=False)
                    source_url = f"https://www.douyin.com/video/{vid}"

                    # 解析原视频发布时间
                    create_time = item.get("create_time", 0)
                    published_at = None
                    if create_time:
                        published_at = datetime.fromtimestamp(create_time)

                    video = repo.create_from_claw(
                        title=title,
                        description=item.get("description", ""),
                        tags=item.get("tags", ""),
                        video_url=item.get("video_url", ""),
                        cover_url=item.get("cover_url", ""),
                        source_url=source_url,
                        source_platform=platform,
                        source_vid=vid,
                        raw_data=raw_data_str,
                        published_at=published_at,
                        category=category,
                    )
                    print(f"  [{i}/{len(items)}] 入库成功: {vid} - {title[:40]} (id={video.id})")
                    stats["added"] += 1

                except Exception as e:
                    db.rollback()
                    print(f"  [{i}/{len(items)}] 入库失败: {vid} - {e}")
                    stats["failed"] += 1

        finally:
            db.close()

        return stats

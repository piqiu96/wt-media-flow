"""素材采集编排器"""
import json
import os
import requests
from datetime import datetime

from conf.settings import settings
from db.database import SessionLocal
from db.repositories import VideoRepository
from db.models import ClawStatusEnum


class ClawProcessor:
    def run(self, items: list[dict], platform: str = "douyin", category: str = "") -> dict:
        """
        默认模式：批量入库 + 逐条下载。

        Returns:
            {"total": N, "added": N, "skipped": N, "failed": N, "downloaded": N}
        """
        result = self.ingest(items, platform=platform, category=category)
        if result["added"] > 0:
            dl = self.download_pending(category=category)
            result["downloaded"] = dl["done"]
        return result

    def ingest(self, items: list[dict], platform: str = "douyin", category: str = "") -> dict:
        """
        阶段一：仅入库元数据，claw_status=pending，不下载文件。

        Returns:
            {"total": N, "added": N, "skipped": N, "failed": N, "downloaded": 0}
        """
        result = {"total": len(items), "added": 0, "skipped": 0, "failed": 0, "downloaded": 0}

        db = SessionLocal()
        try:
            repo = VideoRepository(db)

            for i, item in enumerate(items, 1):
                vid = item.get("vid", "")
                title = item.get("title", "")

                try:
                    existing = repo.get_by_source_vid(platform, vid)
                    if existing:
                        print(f"  [{i}/{len(items)}] 跳过（已存在）: {vid} - {title[:40]}")
                        result["skipped"] += 1
                        continue

                    raw_data_str = json.dumps(item.get("raw_data", {}), ensure_ascii=False)
                    source_url = f"https://www.douyin.com/video/{vid}"

                    create_time = item.get("create_time", 0)
                    published_at = datetime.fromtimestamp(create_time) if create_time else None

                    api_stats = item.get("statistics", {})
                    like_count    = api_stats.get("digg_count", 0) or 0
                    collect_count = api_stats.get("collect_count", 0) or 0
                    comment_count = api_stats.get("comment_count", 0) or 0

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
                        like_count=like_count,
                        collect_count=collect_count,
                        comment_count=comment_count,
                    )
                    print(f"  [{i}/{len(items)}] 入库成功: {vid} - {title[:40]} "
                          f"(id={video.id} 点赞={like_count} 收藏={collect_count})")
                    result["added"] += 1

                except Exception as e:
                    db.rollback()
                    print(f"  [{i}/{len(items)}] 入库失败: {vid} - {e}")
                    result["failed"] += 1

        finally:
            db.close()

        return result

    def download_pending(self, category: str = None, limit: int = 200,
                         retry_failed: bool = False) -> dict:
        """
        阶段二：下载 claw_status=pending 的视频。

        Args:
            category:      品类过滤
            limit:         每次最多处理条数
            retry_failed:  True 时先把 failed 重置为 pending 再下载

        Returns:
            {"total": N, "done": N, "failed": N}
        """
        db = SessionLocal()
        try:
            repo = VideoRepository(db)

            if retry_failed:
                failed_videos = repo.get_failed_claw(category=category)
                if failed_videos:
                    ids = [v.id for v in failed_videos]
                    repo.reset_failed_claw(ids)
                    print(f"已重置 {len(ids)} 条 failed → pending")

            videos = repo.get_pending_claw(category=category, limit=limit)
        finally:
            db.close()

        result = {"total": len(videos), "done": 0, "failed": 0}
        if not videos:
            print("没有待下载的视频")
            return result

        print(f"待下载: {len(videos)} 条")
        for i, video in enumerate(videos, 1):
            vid = video.source_vid or str(video.id)
            print(f"\n  [{i}/{len(videos)}] vid={vid} {(video.title or '')[:40]}")
            local_path = self._download_video(video)
            if local_path:
                db2 = SessionLocal()
                try:
                    VideoRepository(db2).mark_claw_done(video.id, local_path)
                finally:
                    db2.close()
                result["done"] += 1
            else:
                db2 = SessionLocal()
                try:
                    VideoRepository(db2).mark_claw_failed(video.id, "下载失败或无 URL")
                finally:
                    db2.close()
                result["failed"] += 1

        return result

    def _download_video(self, video) -> str | None:
        """下载单条视频，返回本地路径，失败返回 None。
        URL 过期（403）时自动通过 API 刷新后重试。
        """
        video_url = video.video_url
        if not video_url:
            print(f"    无远程 URL，跳过")
            return None

        vid = video.source_vid or str(video.id)
        date_str = video.created_at.strftime("%Y-%m-%d") if video.created_at else datetime.now().strftime("%Y-%m-%d")
        category = video.category if video.category else "未分类"
        safe_title = self._safe_filename(video.title, vid)
        filename = f"{vid}_{safe_title}.mp4"
        local_path = os.path.join(settings.DOWNLOAD_DIR, date_str, category, filename)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        if os.path.isfile(local_path):
            print(f"    本地已存在: {local_path}")
            return local_path

        def _do_download(url: str) -> str | None:
            try:
                resp = requests.get(url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT)
                if resp.status_code == 403:
                    return "403"
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_mb = os.path.getsize(local_path) / 1024 / 1024
                print(f"    下载完成: {local_path} ({size_mb:.1f}MB)")
                return local_path
            except Exception as e:
                print(f"    下载失败: {e}")
                return None

        result = _do_download(video_url)

        # URL 过期，重新拉取直链重试
        if result == "403":
            print(f"    URL 已过期，刷新直链中...")
            try:
                from library.douyin_api import DouyinApi
                fresh = DouyinApi().fetch_by_url(vid)
                fresh_url = fresh.get("video_url") if fresh else None
            except Exception as e:
                print(f"    刷新失败: {e}")
                fresh_url = None

            if fresh_url:
                # 更新数据库里的 video_url
                db2 = SessionLocal()
                try:
                    v = db2.query(__import__('db.models', fromlist=['Video']).Video).filter_by(id=video.id).first()
                    if v:
                        v.video_url = fresh_url
                        db2.commit()
                finally:
                    db2.close()
                result = _do_download(fresh_url)
            else:
                print(f"    无法获取新 URL")
                result = None

        return None if result in (None, "403") else result

    def _safe_filename(self, title: str, vid: str, max_len: int = 50) -> str:
        import re
        if not title:
            return vid
        name = re.sub(r"#\S+", "", title).strip()
        name = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", name).strip()
        name = re.sub(r"\s+", "_", name)
        return name[:max_len] if name else vid

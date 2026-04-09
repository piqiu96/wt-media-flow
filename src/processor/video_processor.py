"""视频业务处理器"""
from db.database import SessionLocal
from service.video_service import VideoService


class VideoProcessor:
    def add(self, path: str, title: str = None, description: str = None,
            cover_path: str = None, tags: str = None) -> dict:
        db = SessionLocal()
        try:
            return VideoService(db).add(path, title, description, cover_path, tags)
        finally:
            db.close()

    def list(self, limit: int = 50) -> dict:
        db = SessionLocal()
        try:
            videos = VideoService(db).list(limit=limit)
            return {"success": True, "videos": videos}
        finally:
            db.close()

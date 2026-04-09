"""视频数据业务"""
import os

from db.repositories import VideoRepository


class VideoService:
    def __init__(self, db):
        self.repo = VideoRepository(db)

    def add(self, path: str, title: str = None, description: str = None,
            cover_path: str = None, tags: str = None) -> dict:
        if not os.path.exists(path):
            return {"success": False, "message": f"视频文件不存在: {path}"}
        video = self.repo.create(path, title, description, cover_path, tags)
        return {"success": True, "message": f"视频添加成功: {path}", "id": video.id}

    def list(self, limit: int = 50):
        return self.repo.list_all(limit=limit)

    def add_from_file(self, path: str, title: str = None,
                      description: str = None, tags: str = None) -> dict:
        """从文件路径添加视频（pipeline 用）"""
        video = self.repo.create(path, title, description, tags=tags)
        return {"success": True, "id": video.id}

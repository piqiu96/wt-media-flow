from typing import List, Optional
from datetime import datetime, timedelta
import json
from sqlalchemy.orm import Session
from .models import Account, Video, PublishTask, TaskLog, TaskStatusEnum, TaskTypeEnum, VideoTask, VideoTaskStatusEnum

from typing import List, Optional
from datetime import datetime, timedelta
import json
from sqlalchemy.orm import Session
from .models import Account, Browser, Video, PublishTask, TaskLog, TaskStatusEnum, TaskTypeEnum, VideoTask, VideoTaskStatusEnum


class BrowserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, profile_id: str, seq: int = None, name: str = None) -> Browser:
        browser = Browser(profile_id=profile_id, seq=seq, name=name)
        self.db.add(browser)
        self.db.commit()
        self.db.refresh(browser)
        return browser

    def get_by_id(self, browser_id: int) -> Optional[Browser]:
        return self.db.query(Browser).filter(Browser.id == browser_id).first()

    def get_by_profile_id(self, profile_id: str) -> Optional[Browser]:
        return self.db.query(Browser).filter(Browser.profile_id == profile_id).first()

    def list_all(self) -> List[Browser]:
        return self.db.query(Browser).order_by(Browser.seq.asc()).all()

    def update_status(self, browser_id: int, status: str):
        b = self.get_by_id(browser_id)
        if b:
            b.status = status
            self.db.commit()


class AccountRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, account_id: int) -> Optional[Account]:
        return self.db.query(Account).filter(Account.id == account_id).first()

    def get_by_group(self, group_id: str) -> List[Account]:
        return self.db.query(Account).filter(
            Account.group_id == group_id,
            Account.status == "active"
        ).all()

    def get_active_accounts(self) -> List[Account]:
        return self.db.query(Account).filter(Account.status == "active").all()

    def get_by_browser_id(self, browser_id: int) -> List[Account]:
        return self.db.query(Account).filter(Account.browser_id == browser_id).all()

    def create(self, browser_id: int, platform: str, profile_id: str = None,
               name: str = None, username: str = None, tag: str = None,
               group_id: str = None, daily_limit: int = 3,
               is_new: bool = True) -> Account:
        account = Account(
            browser_id=browser_id,
            profile_id=profile_id,
            platform=platform,
            name=name,
            username=username,
            tag=tag,
            group_id=group_id,
            is_new=is_new,
            daily_limit=daily_limit,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def list_all(self) -> List[Account]:
        return self.db.query(Account).all()

class VideoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, video_id: int) -> Optional[Video]:
        return self.db.query(Video).filter(Video.id == video_id).first()

    def get_pending_videos(self, limit: int = 100) -> List[Video]:
        return self.db.query(Video).filter(Video.status == "pending").limit(limit).all()

    def update_status(self, video_id: int, status: str):
        video = self.get_by_id(video_id)
        if video:
            video.status = status
            self.db.commit()

    def create(self, path: str, title: str = None, description: str = None,
               cover_path: str = None, tags: str = None) -> Video:
        video = Video(
            path=path,
            title=title,
            description=description,
            cover_path=cover_path,
            tags=tags,
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video

    def list_all(self, limit: int = 50) -> List[Video]:
        return self.db.query(Video).order_by(Video.id.desc()).limit(limit).all()

    def get_by_source_vid(self, source_platform: str, source_vid: str) -> Optional[Video]:
        """去重查询：按平台+视频ID"""
        return self.db.query(Video).filter(
            Video.source_platform == source_platform,
            Video.source_vid == source_vid,
        ).first()

    def get_by_vid(self, source_vid: str) -> Optional[Video]:
        """按 source_vid 查询（不限平台）"""
        return self.db.query(Video).filter(
            Video.source_vid == source_vid,
        ).first()

    def update_path(self, video_id: int, path: str, cover_path: str = None):
        """下载完成后更新本地路径"""
        video = self.get_by_id(video_id)
        if video:
            video.path = path
            if cover_path:
                video.cover_path = cover_path
            self.db.commit()

    def create_from_claw(self, title: str = None, description: str = None,
                         tags: str = None, video_url: str = None,
                         cover_url: str = None, source_url: str = None,
                         source_platform: str = None, source_vid: str = None,
                         raw_data: str = None, published_at=None,
                         category: str = None) -> Video:
        """采集入库（无本地文件，仅元数据）"""
        video = Video(
            path="",
            title=title,
            description=description,
            tags=tags,
            category=category or "",
            video_url=video_url,
            cover_url=cover_url,
            source_url=source_url,
            source_platform=source_platform,
            source_vid=source_vid,
            raw_data=raw_data,
            published_at=published_at,
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video

class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, account_id: int, video_id: int, task_type: TaskTypeEnum,
               schedule_time: Optional[datetime] = None) -> PublishTask:
        task = PublishTask(
            account_id=account_id,
            video_id=video_id,
            task_type=task_type,
            schedule_time=schedule_time,
            status=TaskStatusEnum.PENDING
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, task_id: int) -> Optional[PublishTask]:
        return self.db.query(PublishTask).filter(PublishTask.id == task_id).first()

    def get_pending_tasks(self, limit: int = 5) -> List[PublishTask]:
        return self.db.query(PublishTask).filter(
            PublishTask.status == TaskStatusEnum.PENDING,
            PublishTask.schedule_time <= datetime.utcnow()
        ).limit(limit).all()

    def update_status(self, task_id: int, status: TaskStatusEnum,
                      error_message: Optional[str] = None):
        task = self.db.query(PublishTask).filter(PublishTask.id == task_id).first()
        if task:
            task.status = status
            if status == TaskStatusEnum.RUNNING:
                task.started_at = datetime.utcnow()
            elif status in [TaskStatusEnum.SUCCESS, TaskStatusEnum.FAILED]:
                task.completed_at = datetime.utcnow()
            if error_message:
                task.error_message = error_message
            self.db.commit()

    def increment_retry(self, task_id: int):
        task = self.db.query(PublishTask).filter(PublishTask.id == task_id).first()
        if task:
            task.retry_count += 1
            self.db.commit()

    def list_recent(self, limit: int = 20) -> List[PublishTask]:
        return self.db.query(PublishTask).order_by(PublishTask.id.desc()).limit(limit).all()

class LogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, task_id: int, level: str, message: str):
        log = TaskLog(task_id=task_id, level=level, message=message)
        self.db.add(log)
        self.db.commit()


class VideoTaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, video_id: int, title: str = None, tags: str = None,
               cover_url: str = None, video_url: str = None,
               guide_path: str = None) -> VideoTask:
        task = VideoTask(
            video_id=video_id,
            title=title,
            tags=tags,
            cover_url=cover_url,
            video_url=video_url,
            guide_path=guide_path,
            status=VideoTaskStatusEnum.PENDING,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_by_id(self, task_id: int) -> Optional[VideoTask]:
        return self.db.query(VideoTask).filter(VideoTask.id == task_id).first()

    def get_by_video_id(self, video_id: int) -> Optional[VideoTask]:
        return self.db.query(VideoTask).filter(
            VideoTask.video_id == video_id
        ).order_by(VideoTask.id.desc()).first()

    def start_composite(self, task_id: int):
        """PENDING → COMPOSITING，写入 started_at"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.COMPOSITING
            task.started_at = datetime.utcnow()
            self.db.commit()

    def complete_composite(self, task_id: int, output_path: str,
                           detail_update: dict = None):
        """COMPOSITING → COMPOSITED，填充 output_path"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.COMPOSITED
            task.output_path = output_path
            if detail_update:
                self.append_detail(task_id, detail_update)
            self.db.commit()

    def start_publish(self, task_id: int, account_id: int):
        """COMPOSITED → PUBLISHING"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.PUBLISHING
            task.account_id = account_id
            self.db.commit()

    def complete_publish(self, task_id: int, published_url: str = None,
                         detail_update: dict = None):
        """PUBLISHING → SUCCESS，写入 completed_at"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.SUCCESS
            task.published_url = published_url
            task.completed_at = datetime.utcnow()
            if detail_update:
                self.append_detail(task_id, detail_update)
            self.db.commit()

    def fail(self, task_id: int, message: str, detail_update: dict = None):
        """→ FAILED，写入 message + completed_at"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.FAILED
            task.message = message
            task.completed_at = datetime.utcnow()
            if detail_update:
                self.append_detail(task_id, detail_update)
            self.db.commit()

    def append_detail(self, task_id: int, patch: dict):
        """将 patch 合并写入 detail JSON 字段"""
        task = self.get_by_id(task_id)
        if not task:
            return
        existing = {}
        if task.detail:
            try:
                existing = json.loads(task.detail)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing.update(patch)
        task.detail = json.dumps(existing, ensure_ascii=False)
        self.db.commit()

    def get_pending_composite(self, limit: int = 10) -> List[VideoTask]:
        """查 status=pending 的待合成任务"""
        return self.db.query(VideoTask).filter(
            VideoTask.status == VideoTaskStatusEnum.PENDING
        ).order_by(VideoTask.id.asc()).limit(limit).all()

    def get_pending_publish(self, limit: int = 10) -> List[VideoTask]:
        """查 status=composited 的待发布任务"""
        return self.db.query(VideoTask).filter(
            VideoTask.status == VideoTaskStatusEnum.COMPOSITED
        ).order_by(VideoTask.id.asc()).limit(limit).all()

    def list_recent(self, limit: int = 50) -> List[VideoTask]:
        return self.db.query(VideoTask).order_by(VideoTask.id.desc()).limit(limit).all()

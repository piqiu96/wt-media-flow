from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Account, Video, PublishTask, TaskLog, TaskStatusEnum, TaskTypeEnum

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

    def get_by_profile_id(self, profile_id: str) -> Optional[Account]:
        return self.db.query(Account).filter(Account.profile_id == profile_id).first()

    def create(self, platform: str, username: str, profile_id: str,
               group_id: str = None, daily_limit: int = 3, is_new: bool = True) -> Account:
        account = Account(
            platform=platform,
            username=username,
            profile_id=profile_id,
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

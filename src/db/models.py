from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class PlatformEnum(str, enum.Enum):
    BILIBILI = "bilibili"
    BAIJIAHAO = "baijiahao"
    XIAOHONGSHU = "xiaohongshu"

class TaskStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class TaskTypeEnum(str, enum.Enum):
    PUBLISH = "publish"
    COMMENT = "comment"
    LIKE = "like"

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    username = Column(String(100), nullable=False)
    profile_id = Column(String(100), nullable=False, unique=True)
    group_id = Column(String(50), nullable=True)
    is_new = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=3)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String(500), nullable=False)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    cover_path = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

class PublishTask(Base):
    __tablename__ = "publish_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    task_type = Column(Enum(TaskTypeEnum), default=TaskTypeEnum.PUBLISH)
    status = Column(Enum(TaskStatusEnum), default=TaskStatusEnum.PENDING)
    schedule_time = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("publish_tasks.id"), nullable=False)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

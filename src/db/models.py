from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
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

class VideoTaskStatusEnum(str, enum.Enum):
    PENDING     = "pending"      # 待处理
    COMPOSITING = "compositing"  # 合成中
    COMPOSITED  = "composited"   # 合成完成，待发布
    PUBLISHING  = "publishing"   # 发布中
    SUCCESS     = "success"      # 发布成功
    FAILED      = "failed"       # 失败（合成或发布阶段均可）

class Browser(Base):
    """比特浏览器容器表：一个容器可挂多个平台账号"""
    __tablename__ = "browsers"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    profile_id  = Column(String(100), nullable=False, unique=True)  # 比特浏览器 ID
    seq         = Column(Integer, nullable=True)                     # 比特浏览器序号
    name        = Column(String(200), nullable=True)                 # 备注名（同步自比特）
    status      = Column(String(20), default="active")              # active / inactive
    created_at  = Column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    browser_id  = Column(Integer, ForeignKey("browsers.id"), nullable=False, index=True)
    profile_id  = Column(String(100), nullable=True, index=True)     # 冗余自 browsers.profile_id，便于直接查询
    platform    = Column(String(50), nullable=False)                 # baijiahao / bilibili / xiaohongshu
    name        = Column(String(200), nullable=True)                 # 账号在平台上的显示名称
    username    = Column(String(100), nullable=True)                 # 登录用户名（可选）
    tag         = Column(String(100), nullable=True)                 # 账号类型标签，如 "游戏"
    group_id    = Column(String(50), nullable=True)
    is_new      = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=3)
    status      = Column(String(20), default="active")
    created_at  = Column(DateTime, default=datetime.utcnow)

    browser     = relationship("Browser", backref="accounts")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String(500), nullable=True)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    cover_path = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    remark = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    # 分类标签（采集时指定）
    category = Column(String(50), nullable=True, default="")

    # 来源追踪
    source_url = Column(String(1000), nullable=True)
    source_platform = Column(String(50), nullable=True)
    source_vid = Column(String(200), nullable=True, index=True)

    # 远程资源 URL（合成阶段按需下载）
    video_url = Column(Text, nullable=True)
    cover_url = Column(Text, nullable=True)

    # 原视频发布时间
    published_at = Column(DateTime, nullable=True)

    # 原始 API 响应
    raw_data = Column(Text, nullable=True)

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


class VideoTask(Base):
    """视频任务表：追踪采集→合成→发布完整生命周期"""
    __tablename__ = "video_tasks"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    video_id    = Column(Integer, ForeignKey("videos.id"), nullable=False, index=True)

    # 采集素材快照（冗余存入，方便直接查阅，无需 join videos 表）
    title       = Column(String(500), nullable=True)   # 原视频标题
    tags        = Column(String(500), nullable=True)   # 原始标签（逗号分隔，利于游戏分类检索）
    cover_url   = Column(Text, nullable=True)          # 远程封面图 URL
    video_url   = Column(Text, nullable=True)          # 原始视频远程 URL（source 真实地址）

    # 合成信息
    guide_path  = Column(String(500), nullable=True)   # 使用的引导视频路径
    output_path = Column(String(500), nullable=True)   # 合成输出路径（成功后填充）

    # 状态追踪
    status      = Column(Enum(VideoTaskStatusEnum),
                         default=VideoTaskStatusEnum.PENDING, index=True)
    message     = Column(Text, nullable=True)          # 关键过程信息 / 失败原因
    detail      = Column(Text, nullable=True)          # JSON：执行过程中间状态快照
                                                       # {"download_size_mb":9.5,"output_size_mb":15.8,...}

    # 发布信息
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    published_url   = Column(String(500), nullable=True)  # 发布成功后的视频链接

    # 时间节点（只记录整体开始/结束）
    started_at  = Column(DateTime, nullable=True)      # 合成开始时写入
    completed_at= Column(DateTime, nullable=True)      # 最终成功或失败时写入
    created_at  = Column(DateTime, default=datetime.utcnow)

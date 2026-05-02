from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Enum, Date
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class User(Base):
    """运营用户表：管理账号归属和视频池绑定"""
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)             # 姓名/昵称，如"小王"
    username   = Column(String(100), nullable=True, unique=True) # 登录名（可空）
    role       = Column(String(50), default="operator")          # 角色：operator / admin / viewer
    pool       = Column(String(100), nullable=True)              # 视频池 key，如"pool-a"（对应 conf/pools/pool-a.json）
    status     = Column(String(20), default="active")            # active / inactive
    wecom_id   = Column(String(100), nullable=True)              # 企微 userid，定向通知用
    created_at = Column(DateTime, default=datetime.utcnow)

    accounts   = relationship("Account", back_populates="user")


class PlatformEnum(str, enum.Enum):
    BILIBILI = "bilibili"
    BAIJIAHAO = "baijiahao"
    XIAOHONGSHU = "xiaohongshu"

class VideoTaskStatusEnum(str, enum.Enum):
    PENDING     = "pending"      # 待处理
    COMPOSITING = "compositing"  # 合成中
    COMPOSITED  = "composited"   # 合成完成（终态，发布由 plan_items 管理）
    PUBLISHING  = "publishing"   # 发布中
    SUCCESS     = "success"      # 发布成功
    FAILED      = "failed"       # 合成/发布失败
    EXPIRED     = "expired"      # 已过期（素材发布时间超过5天，不再进入发布计划）


class PlanItemStatusEnum(str, enum.Enum):
    PENDING    = "pending"     # 待执行
    PUBLISHING = "publishing"  # 发布中
    PUBLISHED  = "published"   # 发布成功（已回填 published_url）
    FAILED     = "failed"      # 失败


class CommentTaskStatusEnum(str, enum.Enum):
    PENDING    = "pending"     # 待评论
    COMMENTING = "commenting"  # 评论中
    DONE       = "done"        # 完成
    FAILED     = "failed"      # 失败

class ClawStatusEnum(str, enum.Enum):
    PENDING = "pending"  # 已入库，待下载
    DONE    = "done"     # 已下载到本地
    FAILED  = "failed"   # 下载失败

class ReviewStatusEnum(str, enum.Enum):
    PENDING  = "pending"   # 待审核（采集后默认）
    APPROVED = "approved"  # 已通过
    REJECTED = "rejected"  # 已拒绝

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
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 归属运营用户
    is_new      = Column(Boolean, default=True)
    daily_limit = Column(Integer, default=3)
    status           = Column(String(20), default="active")
    disabled_reason  = Column(String(500), nullable=True)   # 禁用原因
    created_at       = Column(DateTime, default=datetime.utcnow)

    browser     = relationship("Browser", backref="accounts")
    user        = relationship("User", back_populates="accounts")

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String(500), nullable=True)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    cover_path = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    remark = Column(Text, nullable=True)
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

    # 原视频热度统计（采集时写入）
    like_count    = Column(Integer, default=0)   # 点赞数
    collect_count = Column(Integer, default=0)   # 收藏数
    comment_count = Column(Integer, default=0)   # 评论数

    # 原始 API 响应
    raw_data = Column(Text, nullable=True)

    # 文件是否已删除（cleanup 命令执行后标记）
    deleted = Column(Boolean, default=False)

    # 采集下载状态（两阶段采集用）
    claw_status   = Column(String(20), default=ClawStatusEnum.PENDING)  # pending / done / failed
    claw_error    = Column(Text, nullable=True)                          # 失败原因
    downloaded_at = Column(DateTime, nullable=True)                      # 下载完成时间

    # 内容审核状态（Web 端审核后变 approved，合成前可过滤）
    review_status = Column(String(20), default=ReviewStatusEnum.APPROVED)  # 默认 approved 保持向后兼容


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

    # 去重用冗余字段（来自 videos.source_vid，合成时写入）
    source_vid      = Column(String(200), nullable=True, index=True)

    # 视频池（合成时写入，对应 conf/pools/{pool}.json 的 id 字段）
    pool            = Column(String(100), nullable=True, index=True)

    # 发布信息
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    published_url   = Column(String(500), nullable=True)  # 发布成功后的视频链接
    category        = Column(String(50), nullable=True, default="")  # 游戏品类（来自 video.category）
    target_platform = Column(String(50), nullable=True)   # 目标平台（允许同素材多平台）

    # 时间节点（只记录整体开始/结束）
    started_at  = Column(DateTime, nullable=True)      # 合成开始时写入
    completed_at= Column(DateTime, nullable=True)      # 最终成功或失败时写入
    created_at  = Column(DateTime, default=datetime.utcnow)


class PublishPlan(Base):
    """发布计划表：一天/一批次的发布任务集合"""
    __tablename__ = "publish_plans"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(200), nullable=True)                  # 计划名称，如 "2026-04-14 小王 发布"
    date        = Column(Date, nullable=False, index=True)            # 计划日期
    status      = Column(String(20), default="pending")              # pending / running / done
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 所属运营用户
    created_at  = Column(DateTime, default=datetime.utcnow)

    items       = relationship("PlanItem", backref="plan", lazy="dynamic")


class PlanItem(Base):
    """发布计划条目：单条账号 × 视频的发布记录，同时追踪评论"""
    __tablename__ = "plan_items"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    plan_id         = Column(Integer, ForeignKey("publish_plans.id"), nullable=False, index=True)
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    video_task_id   = Column(Integer, ForeignKey("video_tasks.id"), nullable=False, index=True)
    order_idx       = Column(Integer, default=0)                      # 发布顺序

    # 发布
    publish_status  = Column(Enum(PlanItemStatusEnum),
                             default=PlanItemStatusEnum.PENDING, index=True)
    published_url   = Column(String(500), nullable=True)             # 发布后抓取回填
    published_at    = Column(DateTime, nullable=True)
    category        = Column(String(50), nullable=True, default="")  # 游戏品类（冗余自 video_task）
    platform        = Column(String(50), default="baijiahao")        # 目标平台
    publish_mode    = Column(String(30), default="manual_confirm")   # manual_confirm / auto_submit

    # 错误
    error_message   = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # 通知
    notified        = Column(Boolean, default=False)  # 是否已推送企微通知

    # 视频数据统计（定时从好看视频页抓取）
    view_count       = Column(Integer, nullable=True)   # 播放数
    like_count       = Column(Integer, nullable=True)   # 点赞数
    comment_count    = Column(Integer, nullable=True)   # 评论数
    stats_fetched_at = Column(DateTime, nullable=True)  # 最后抓取时间


class CommentTask(Base):
    """评论任务表：发布成功后自动创建，分配给不同账号"""
    __tablename__ = "comment_tasks"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    plan_item_id    = Column(Integer, ForeignKey("plan_items.id"), nullable=False, index=True)
    account_id      = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    url             = Column(String(500), nullable=False)             # 要评论的文章 URL
    content         = Column(Text, nullable=True)                     # 评论内容（确认后写回）
    category        = Column(String(50), nullable=True, default="")  # 游戏品类（冗余自 plan_item）
    status          = Column(Enum(CommentTaskStatusEnum),
                             default=CommentTaskStatusEnum.PENDING, index=True)
    error_message   = Column(Text, nullable=True)
    commented_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

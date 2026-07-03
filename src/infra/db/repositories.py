from typing import List, Optional
from datetime import datetime, date, timedelta
import json
from sqlalchemy.orm import Session
from .models import (Account, Browser, User, Video,
                     VideoTask, VideoTaskStatusEnum,
                     PublishPlan, PlanItem, PlanItemStatusEnum,
                     CommentTask, CommentTaskStatusEnum,
                     ClawStatusEnum)


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

    def get_active_accounts_by_user(self, user_id: int) -> List[Account]:
        """返回指定用户名下所有有效账号（含无浏览器容器的手动账号）"""
        return self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.status == "active",
        ).all()


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, username: str = None, role: str = "operator",
               pool: str = None, wecom_id: str = None) -> User:
        user = User(name=name, username=username, role=role,
                    pool=pool, wecom_id=wecom_id)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def list_active(self) -> List[User]:
        return self.db.query(User).filter(User.status == "active").all()

    def list_all(self) -> List[User]:
        return self.db.query(User).order_by(User.id.asc()).all()

class VideoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, video_id: int) -> Optional[Video]:
        return self.db.query(Video).filter(Video.id == video_id).first()

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

    def get_expired_for_cleanup(self, days: int = 5) -> List[Video]:
        """查 published_at 超过 N 天、文件未删除、有本地路径的视频"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return (
            self.db.query(Video)
            .filter(
                Video.published_at < cutoff,
                Video.deleted.is_(False),
                Video.path.isnot(None),
                Video.path != "",
            )
            .order_by(Video.published_at.asc())
            .all()
        )

    def mark_deleted(self, video_id: int):
        video = self.get_by_id(video_id)
        if video:
            video.deleted = True
            video.path = ""
            self.db.commit()

    def update_path(self, video_id: int, path: str, cover_path: str = None):
        """下载完成后更新本地路径"""
        video = self.get_by_id(video_id)
        if video:
            video.path = path
            if cover_path:
                video.cover_path = cover_path
            self.db.commit()

    def list_pending_review(self, category: str = None,
                            limit: int = 50) -> List[Video]:
        """查待审核视频"""
        from infra.db.models import ReviewStatusEnum
        q = self.db.query(Video).filter(
            Video.review_status == ReviewStatusEnum.PENDING,
            Video.deleted.is_(False),
        )
        if category:
            q = q.filter(Video.category == category)
        return q.order_by(Video.id.desc()).limit(limit).all()

    def set_review_status(self, video_id: int, status: str):
        """设置审核状态 (approved / rejected)"""
        video = self.get_by_id(video_id)
        if video:
            video.review_status = status
            self.db.commit()

    def create_from_claw(self, title: str = None, description: str = None,
                         tags: str = None, video_url: str = None,
                         cover_url: str = None, source_url: str = None,
                         source_platform: str = None, source_vid: str = None,
                         raw_data: str = None, published_at=None,
                         category: str = None,
                         like_count: int = 0, collect_count: int = 0,
                         comment_count: int = 0) -> Video:
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
            like_count=like_count or 0,
            collect_count=collect_count or 0,
            comment_count=comment_count or 0,
            claw_status=ClawStatusEnum.PENDING,
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video

    def mark_claw_done(self, video_id: int, local_path: str):
        """下载成功：更新 path + claw_status=done + downloaded_at"""
        video = self.get_by_id(video_id)
        if video:
            video.path = local_path
            video.claw_status = ClawStatusEnum.DONE
            video.downloaded_at = datetime.utcnow()
            video.claw_error = None
            self.db.commit()

    def mark_claw_failed(self, video_id: int, error: str):
        """下载失败：claw_status=failed + 记录原因"""
        video = self.get_by_id(video_id)
        if video:
            video.claw_status = ClawStatusEnum.FAILED
            video.claw_error = error
            self.db.commit()

    def get_pending_claw(self, category: str = None, limit: int = 200) -> List[Video]:
        """查 claw_status=pending 待下载的视频"""
        q = self.db.query(Video).filter(Video.claw_status == ClawStatusEnum.PENDING)
        if category:
            q = q.filter(Video.category == category)
        return q.order_by(Video.id.asc()).limit(limit).all()

    def get_failed_claw(self, category: str = None) -> List[Video]:
        """查 claw_status=failed 下载失败的视频"""
        q = self.db.query(Video).filter(Video.claw_status == ClawStatusEnum.FAILED)
        if category:
            q = q.filter(Video.category == category)
        return q.order_by(Video.id.asc()).all()

    def reset_failed_claw(self, video_ids: list[int]):
        """将指定 failed 视频重置为 pending"""
        self.db.query(Video).filter(
            Video.id.in_(video_ids),
            Video.claw_status == ClawStatusEnum.FAILED,
        ).update({
            "claw_status": ClawStatusEnum.PENDING,
            "claw_error": None,
        }, synchronize_session=False)
        self.db.commit()

    def get_unprocessed_vids(self, category: str, limit: int = 200,
                              max_age_days: int = 5,
                              target_platform: str = None) -> list[str]:
        """取已下载但未合成（或合成失败）的原始素材 source_vid 列表。

        指定 target_platform 时，同一素材允许为不同平台分别合成；仅排除
        同平台已有非失败合成任务或同平台计划引用的素材。

        排除条件：
        1. 已有非 FAILED 状态的 video_task（合成中/合成完成）
        2. 已进入过计划的 video_task 引用的 video（任意状态均算）
        3. 超过 max_age_days 天的老视频
        """
        from sqlalchemy import or_, and_
        composited_video_ids = self.db.query(VideoTask.video_id).filter(
            VideoTask.status != VideoTaskStatusEnum.FAILED
        )
        in_plan_video_ids = self.db.query(VideoTask.video_id).join(
            PlanItem, PlanItem.video_task_id == VideoTask.id
        )
        if target_platform:
            composited_video_ids = composited_video_ids.filter(
                VideoTask.target_platform == target_platform
            )
            in_plan_video_ids = in_plan_video_ids.filter(
                PlanItem.platform == target_platform
            )
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        rows = (
            self.db.query(Video.source_vid)
            .filter(
                Video.category == category,
                Video.claw_status == ClawStatusEnum.DONE,
                Video.deleted.is_(False),
                Video.path.isnot(None),
                Video.path != "",
                or_(
                    Video.published_at >= cutoff,
                    and_(Video.published_at.is_(None), Video.created_at >= cutoff),
                ),
                ~Video.id.in_(composited_video_ids),
                ~Video.id.in_(in_plan_video_ids),
            )
            .order_by((Video.like_count + Video.collect_count).desc())
            .limit(limit)
            .all()
        )
        return [r.source_vid for r in rows]


class VideoTaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, video_id: int, title: str = None, tags: str = None,
               cover_url: str = None, video_url: str = None,
               guide_path: str = None, category: str = "",
               source_vid: str = None, pool: str = None,
               target_platform: str = None) -> VideoTask:
        task = VideoTask(
            video_id=video_id,
            title=title,
            tags=tags,
            cover_url=cover_url,
            video_url=video_url,
            guide_path=guide_path,
            category=category or "",
            source_vid=source_vid,
            pool=pool,
            target_platform=target_platform,
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

    def get_latest_non_failed_by_source_vid(self, source_vid: str,
                                            target_platform: str = None) -> Optional[VideoTask]:
        """按 source_vid 查询最新的非失败任务，用于合成前去重。

        指定 target_platform 时，只在同平台内去重，允许同素材为不同平台
        生成不同引导视频版本。
        """
        if not source_vid:
            return None
        q = self.db.query(VideoTask).filter(
            VideoTask.source_vid == source_vid,
            VideoTask.status != VideoTaskStatusEnum.FAILED,
        )
        if target_platform:
            q = q.filter(VideoTask.target_platform == target_platform)
        return q.order_by(VideoTask.id.desc()).first()

    def get_all_by_video_id(self, video_id: int) -> List[VideoTask]:
        return self.db.query(VideoTask).filter(
            VideoTask.video_id == video_id
        ).all()

    def mark_output_expired(self, task_id: int):
        """合成产物文件删除后：output_path 清空，status → EXPIRED。
        候选池查询 status==COMPOSITED，EXPIRED 自动被排除。
        用 bulk update 绕过 ORM 枚举校验（DB 大写风格）。
        """
        self.db.query(VideoTask).filter(VideoTask.id == task_id).update(
            {"status": "EXPIRED", "output_path": ""},
            synchronize_session=False,
        )
        self.db.commit()

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

    def list_by_status(self, status: VideoTaskStatusEnum,
                       limit: int = 50) -> List[VideoTask]:
        return (self.db.query(VideoTask)
                .filter(VideoTask.status == status)
                .order_by(VideoTask.id.desc())
                .limit(limit).all())

    def get_videos_for_recomposite(self, days: int = 1,
                                   category: str = None) -> list:
        """查最近 N 天 published_at 的 videos，连带最新 VideoTask（可能为 None）
        返回: list of (Video, VideoTask | None)
        排序: (like_count + collect_count) DESC
        """
        from sqlalchemy import func
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = self.db.query(Video).filter(Video.published_at >= cutoff)
        if category:
            q = q.filter(Video.category == category)
        videos = q.filter(
            Video.deleted.is_(False)
        ).order_by(
            (Video.like_count + Video.collect_count).desc()
        ).all()

        result = []
        for video in videos:
            task = (
                self.db.query(VideoTask)
                .filter(VideoTask.video_id == video.id)
                .order_by(VideoTask.id.desc())
                .first()
            )
            result.append((video, task))
        return result

    def reset_for_recomposite(self, task_id: int):
        """原地重置 VideoTask 合成字段，状态回 PENDING"""
        task = self.get_by_id(task_id)
        if task:
            task.status = VideoTaskStatusEnum.PENDING
            task.output_path = None
            task.message = None
            task.started_at = None
            task.completed_at = None
            task.detail = None
            self.db.commit()

    def is_referenced_by_active_plan(self, task_id: int) -> bool:
        """检查 task 是否被 PENDING/PUBLISHING/PUBLISHED 的 plan_item 引用"""
        from sqlalchemy import exists
        return self.db.query(
            exists().where(
                PlanItem.video_task_id == task_id,
                PlanItem.publish_status.in_([
                    PlanItemStatusEnum.PENDING,
                    PlanItemStatusEnum.PUBLISHING,
                    PlanItemStatusEnum.PUBLISHED,
                ])
            )
        ).scalar()

    def get_unassigned_composited(self, limit: int = 100,
                                   max_age_days: int = 5) -> List[VideoTask]:
        """查未被 publishing/published/failed plan_item 引用过的 composited 任务

        去重粒度：source_vid 级别
        - PUBLISHING / PUBLISHED / FAILED：排除（发布中/已发布/失败均不再重入）
        - PENDING：不排除（计划未执行，允许重新进入新计划）

        排除条件：
        - 该 VideoTask.source_vid 已存在于任何 publishing/published/failed plan_item 引用的 VideoTask 中
        - videos.published_at 超过 max_age_days 天的过期素材排除（默认 5 天）
        排序：关联 videos 表的 (like_count + collect_count) DESC，优先高热度
        """
        from sqlalchemy import select, or_
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)

        # source_vid 级排除：PUBLISHING / PUBLISHED / FAILED 对应的 source_vid
        already_planned_svids = (
            select(VideoTask.source_vid)
            .join(PlanItem, PlanItem.video_task_id == VideoTask.id)
            .where(
                VideoTask.source_vid.isnot(None),
                PlanItem.publish_status.in_([
                    PlanItemStatusEnum.PUBLISHING,
                    PlanItemStatusEnum.PUBLISHED,
                    PlanItemStatusEnum.FAILED,
                ])
            )
        )
        return (
            self.db.query(VideoTask)
            .join(Video, VideoTask.video_id == Video.id)
            .filter(
                VideoTask.status == VideoTaskStatusEnum.COMPOSITED,
                VideoTask.source_vid.isnot(None),
                ~VideoTask.source_vid.in_(already_planned_svids),
                or_(Video.published_at.is_(None),
                    Video.published_at >= cutoff),
            )
            .order_by(
                (Video.like_count + Video.collect_count).desc()
            )
            .limit(limit)
            .all()
        )

    def get_composited_for_platform(self, platform: str,
                                     limit: int = 100,
                                     max_age_days: int = 5) -> List[VideoTask]:
        """查 composited 任务，仅排除已在指定平台上 publishing/published/failed 的

        用于 allows_same_source_reuse=True 的平台（如哔哩哔哩）：
        同一个 source_vid 可以在不同平台分别发布，但同一平台不重复。
        去重粒度：source_vid + platform 级别。
        """
        from sqlalchemy import select, or_

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)

        # 排除已在该平台 pending/publishing/published/failed 的 source_vid
        already_on_platform_svids = (
            select(VideoTask.source_vid)
            .join(PlanItem, PlanItem.video_task_id == VideoTask.id)
            .where(
                VideoTask.source_vid.isnot(None),
                PlanItem.platform == platform,
                PlanItem.publish_status.in_([
                    PlanItemStatusEnum.PENDING,
                    PlanItemStatusEnum.PUBLISHING,
                    PlanItemStatusEnum.PUBLISHED,
                    PlanItemStatusEnum.FAILED,
                ])
            )
        )
        return (
            self.db.query(VideoTask)
            .join(Video, VideoTask.video_id == Video.id)
            .filter(
                VideoTask.status == VideoTaskStatusEnum.COMPOSITED,
                VideoTask.source_vid.isnot(None),
                or_(VideoTask.target_platform.is_(None),
                    VideoTask.target_platform == platform),
                ~VideoTask.source_vid.in_(already_on_platform_svids),
                or_(Video.published_at.is_(None),
                    Video.published_at >= cutoff),
            )
            .order_by(
                (Video.like_count + Video.collect_count).desc()
            )
            .limit(limit)
            .all()
        )

    def get_composited_for_pool(self, pool: str, platform: str,
                                limit: int = 500,
                                max_age_days: int = 5) -> List[VideoTask]:
        """查属于指定视频池、且在指定平台上未 publishing/published/failed 的 composited 任务。

        去重粒度：source_vid + platform 级别，与 get_composited_for_platform 一致。
        额外过滤：VideoTask.pool == pool（只取该池子合成的视频）。
        """
        from sqlalchemy import select, or_

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)

        already_on_platform_svids = (
            select(VideoTask.source_vid)
            .join(PlanItem, PlanItem.video_task_id == VideoTask.id)
            .where(
                VideoTask.source_vid.isnot(None),
                PlanItem.platform == platform,
                PlanItem.publish_status.in_([
                    PlanItemStatusEnum.PENDING,
                    PlanItemStatusEnum.PUBLISHING,
                    PlanItemStatusEnum.PUBLISHED,
                    PlanItemStatusEnum.FAILED,
                ])
            )
        )
        return (
            self.db.query(VideoTask)
            .join(Video, VideoTask.video_id == Video.id)
            .filter(
                VideoTask.status == VideoTaskStatusEnum.COMPOSITED,
                VideoTask.pool == pool,
                VideoTask.source_vid.isnot(None),
                or_(VideoTask.target_platform.is_(None),
                    VideoTask.target_platform == platform),
                ~VideoTask.source_vid.in_(already_on_platform_svids),
                or_(Video.published_at.is_(None),
                    Video.published_at >= cutoff),
            )
            .order_by(
                (Video.like_count + Video.collect_count).desc()
            )
            .limit(limit)
            .all()
        )


class PublishPlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, plan_date: date, name: str = None, user_id: int = None) -> PublishPlan:
        plan = PublishPlan(
            date=plan_date,
            name=name or f"{plan_date} 发布计划",
            status="pending",
            user_id=user_id,
        )
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get_by_id(self, plan_id: int) -> Optional[PublishPlan]:
        return self.db.query(PublishPlan).filter(PublishPlan.id == plan_id).first()

    def list_by_date(self, plan_date: date) -> List[PublishPlan]:
        return self.db.query(PublishPlan).filter(PublishPlan.date == plan_date).all()

    def list_recent(self, limit: int = 20) -> List[PublishPlan]:
        return self.db.query(PublishPlan).order_by(PublishPlan.id.desc()).limit(limit).all()

    def set_status(self, plan_id: int, status: str):
        plan = self.get_by_id(plan_id)
        if plan:
            plan.status = status
            self.db.commit()


class PlanItemRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, plan_id: int, account_id: int, video_task_id: int,
               order_idx: int = 0, category: str = "",
               platform: str = "baijiahao",
               publish_mode: str = "manual_confirm") -> PlanItem:
        item = PlanItem(
            plan_id=plan_id,
            account_id=account_id,
            video_task_id=video_task_id,
            order_idx=order_idx,
            category=category or "",
            platform=platform,
            publish_mode=publish_mode,
            publish_status=PlanItemStatusEnum.PENDING,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def get_by_id(self, item_id: int) -> Optional[PlanItem]:
        return self.db.query(PlanItem).filter(PlanItem.id == item_id).first()

    def get_pending_by_account(self, plan_id: int, account_id: int) -> List[PlanItem]:
        return (
            self.db.query(PlanItem)
            .filter(
                PlanItem.plan_id == plan_id,
                PlanItem.account_id == account_id,
                PlanItem.publish_status == PlanItemStatusEnum.PENDING,
            )
            .order_by(PlanItem.order_idx.asc())
            .all()
        )

    def list_by_plan(self, plan_id: int) -> List[PlanItem]:
        return (
            self.db.query(PlanItem)
            .filter(PlanItem.plan_id == plan_id)
            .order_by(PlanItem.account_id.asc(), PlanItem.order_idx.asc())
            .all()
        )

    def start_publish(self, item_id: int):
        item = self.get_by_id(item_id)
        if item:
            item.publish_status = PlanItemStatusEnum.PUBLISHING
            self.db.commit()

    def complete_publish(self, item_id: int, published_url: str = None):
        item = self.get_by_id(item_id)
        if item:
            item.publish_status = PlanItemStatusEnum.PUBLISHED
            item.published_url = published_url
            item.published_at = datetime.utcnow()
            self.db.commit()

    def fail(self, item_id: int, error_message: str = None):
        item = self.get_by_id(item_id)
        if item:
            item.publish_status = PlanItemStatusEnum.FAILED
            item.error_message = error_message
            self.db.commit()

    def mark_notified(self, item_id: int):
        """标记 plan_item 已推送企微通知"""
        item = self.get_by_id(item_id)
        if item:
            item.notified = True
            self.db.commit()

    def get_published_not_notified(self, plan_id: int) -> List[PlanItem]:
        """获取已发布但未通知的条目（plan check 使用）"""
        return (
            self.db.query(PlanItem)
            .filter(
                PlanItem.plan_id == plan_id,
                PlanItem.publish_status == PlanItemStatusEnum.PUBLISHED,
                PlanItem.published_url.isnot(None),
                PlanItem.published_url != "",
                PlanItem.notified.is_(False),
            )
            .order_by(PlanItem.order_idx.asc())
            .all()
        )

    def get_published_for_stats(self, plan_id: int | None = None, since_date=None) -> List[PlanItem]:
        """获取已发布且有 URL 的条目，用于定时抓取统计数据。
        支持按 plan_id 或发布日期（since_date）筛选，两者均为可选。
        """
        from datetime import datetime, date as date_type
        query = self.db.query(PlanItem).filter(
            PlanItem.publish_status == PlanItemStatusEnum.PUBLISHED,
            PlanItem.published_url.isnot(None),
            PlanItem.published_url != "",
        )
        if plan_id is not None:
            query = query.filter(PlanItem.plan_id == plan_id)
        if since_date is not None:
            if isinstance(since_date, date_type):
                since_dt = datetime(since_date.year, since_date.month, since_date.day)
            else:
                since_dt = since_date
            query = query.filter(PlanItem.published_at >= since_dt)
        return query.order_by(PlanItem.plan_id.asc(), PlanItem.order_idx.asc()).all()

    def update_stats(self, item_id: int, view_count: int | None,
                     like_count: int | None, comment_count: int | None):
        """写入统计数据（播放/点赞/评论）及抓取时间"""
        from datetime import datetime
        item = self.get_by_id(item_id)
        if item:
            item.view_count    = view_count
            item.like_count    = like_count
            item.comment_count = comment_count
            item.stats_fetched_at = datetime.utcnow()
            self.db.commit()

    def reset_failed(self, plan_id: int, account_id: int | None = None) -> int:
        """重置技术性失败条目为 PENDING，返回重置数量"""
        query = self.db.query(PlanItem).filter(
            PlanItem.plan_id == plan_id,
            PlanItem.publish_status == PlanItemStatusEnum.FAILED,
            PlanItem.error_message != "人工标记失败",
        )
        if account_id:
            query = query.filter(PlanItem.account_id == account_id)

        items = query.all()
        for item in items:
            item.publish_status = PlanItemStatusEnum.PENDING
            item.error_message = None
        self.db.commit()
        return len(items)

    def fail_pending_by_task(self, video_task_id: int):
        """退场时：将该 task 的 PENDING plan_items 置为 FAILED。
        PUBLISHING / PUBLISHED / FAILED 状态不动。
        """
        self.db.query(PlanItem).filter(
            PlanItem.video_task_id == video_task_id,
            PlanItem.publish_status == PlanItemStatusEnum.PENDING,
        ).update(
            {"publish_status": PlanItemStatusEnum.FAILED,
             "error_message": "视频已退场，合成产物已删除"},
            synchronize_session=False,
        )
        self.db.commit()


class CommentTaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, plan_item_id: int, account_id: int, url: str,
               content: str = None, category: str = "") -> CommentTask:
        task = CommentTask(
            plan_item_id=plan_item_id,
            account_id=account_id,
            url=url,
            content=content,
            category=category or "",
            status=CommentTaskStatusEnum.PENDING,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_pending_by_account(self, account_id: int,
                               limit: int = 50) -> List[CommentTask]:
        return (
            self.db.query(CommentTask)
            .filter(
                CommentTask.account_id == account_id,
                CommentTask.status == CommentTaskStatusEnum.PENDING,
                CommentTask.url.isnot(None),
                CommentTask.content.isnot(None),
            )
            .order_by(CommentTask.id.asc())
            .limit(limit)
            .all()
        )

    def start(self, task_id: int):
        t = self.db.query(CommentTask).filter(CommentTask.id == task_id).first()
        if t:
            t.status = CommentTaskStatusEnum.COMMENTING
            self.db.commit()

    def complete(self, task_id: int):
        t = self.db.query(CommentTask).filter(CommentTask.id == task_id).first()
        if t:
            t.status = CommentTaskStatusEnum.DONE
            t.commented_at = datetime.utcnow()
            self.db.commit()

    def fail(self, task_id: int, error: str = None):
        t = self.db.query(CommentTask).filter(CommentTask.id == task_id).first()
        if t:
            t.status = CommentTaskStatusEnum.FAILED
            t.error_message = error
            self.db.commit()

    def update_content(self, task_id: int, content: str):
        t = self.db.query(CommentTask).filter(CommentTask.id == task_id).first()
        if t:
            t.content = content
            self.db.commit()

    def update_url(self, task_id: int, url: str):
        t = self.db.query(CommentTask).filter(CommentTask.id == task_id).first()
        if t:
            t.url = url
            self.db.commit()

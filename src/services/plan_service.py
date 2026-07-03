"""PlanService — 计划管理业务逻辑（create / list / reset-failed / check）。"""
import random
from datetime import date as date_type

from utils.log import get_logger

logger = get_logger(__name__)


class PlanService:
    """发布计划管理"""

    def __init__(self, db):
        from infra.db.repositories import (
            AccountRepository, VideoTaskRepository,
            PublishPlanRepository, PlanItemRepository,
        )
        self.db = db
        self.acc_repo = AccountRepository(db)
        self.vt_repo = VideoTaskRepository(db)
        self.plan_repo = PublishPlanRepository(db)
        self.item_repo = PlanItemRepository(db)

    def get_active_accounts(self):
        return self.acc_repo.get_active_accounts()

    def get_unassigned_composited(self, limit: int = 500):
        return self.vt_repo.get_unassigned_composited(limit=limit)

    def get_composited_for_platform(self, platform: str, limit: int = 500):
        return self.vt_repo.get_composited_for_platform(platform=platform, limit=limit)

    def get_composited_for_pool(self, pool: str, platform: str, limit: int = 500):
        return self.vt_repo.get_composited_for_pool(pool=pool, platform=platform, limit=limit)

    def create_plan(self, plan_date: date_type, name: str = None, user_id: int = None):
        return self.plan_repo.create(plan_date=plan_date, name=name, user_id=user_id)

    def create_plan_item(self, plan_id: int, account_id: int,
                         video_task_id: int, order_idx: int,
                         category: str = "",
                         platform: str = "baijiahao",
                         publish_mode: str = "manual_confirm"):
        return self.item_repo.create(
            plan_id=plan_id,
            account_id=account_id,
            video_task_id=video_task_id,
            order_idx=order_idx,
            category=category,
            platform=platform,
            publish_mode=publish_mode,
        )

    def list_plans(self, filter_date: date_type | None = None):
        if filter_date:
            return self.plan_repo.list_by_date(filter_date)
        return self.plan_repo.list_recent(20)

    def list_items_by_plan(self, plan_id: int):
        return self.item_repo.list_by_plan(plan_id)

    def reset_failed(self, plan_id: int, account_id: int | None = None) -> int:
        """重置技术性失败条目为 PENDING，返回重置数量"""
        return self.item_repo.reset_failed(plan_id, account_id)

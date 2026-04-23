"""
PublishService — 发布业务操作（状态流转 + 数据持久化 + 通知）

从 cmd/plan.py 提取的数据层操作逻辑。
"""
import random

from utils.log import get_logger

logger = get_logger(__name__)


class PublishService:
    """发布相关的业务操作"""

    def __init__(self, db):
        from infra.db.repositories import (
            AccountRepository, BrowserRepository,
            PlanItemRepository, PublishPlanRepository,
            VideoTaskRepository, CommentTaskRepository,
        )
        self.db = db
        self.acc_repo = AccountRepository(db)
        self.item_repo = PlanItemRepository(db)
        self.plan_repo = PublishPlanRepository(db)
        self.vt_repo = VideoTaskRepository(db)
        self.cmt_repo = CommentTaskRepository(db)
        self.br_repo = BrowserRepository(db)

    # ── 查询 ──────────────────────────────────────────────────

    def get_plan(self, plan_id: int):
        return self.plan_repo.get_by_id(plan_id)

    def get_account(self, account_id: int):
        return self.acc_repo.get_by_id(account_id)

    def get_pending_items(self, plan_id: int, account_id: int):
        return self.item_repo.get_pending_by_account(plan_id, account_id)

    def get_video_task(self, vt_id: int):
        return self.vt_repo.get_by_id(vt_id)

    def get_item(self, item_id: int):
        return self.item_repo.get_by_id(item_id)

    # ── 浏览器 profile 解析 ───────────────────────────────────

    def resolve_browser_profile(self, account) -> str | None:
        """从 account 或关联 browser 获取 bit_profile_id"""
        pid = account.profile_id
        if not pid and account.browser_id:
            br = self.br_repo.get_by_id(account.browser_id)
            pid = br.profile_id if br else None
        return pid

    # ── 状态流转 ──────────────────────────────────────────────

    def set_plan_status(self, plan_id: int, status: str):
        self.plan_repo.set_status(plan_id, status)

    def start_publish(self, item_id: int):
        self.item_repo.start_publish(item_id)

    def complete_publish(self, item_id: int, published_url: str):
        self.item_repo.complete_publish(item_id, published_url=published_url)

    def fail_publish(self, item_id: int, error: str):
        self.item_repo.fail(item_id, error)

    # ── 评论任务创建 ──────────────────────────────────────────

    def create_comment_task(self, item, account_id: int,
                            published_url: str, vt):
        """发布成功后创建账号互评任务"""
        from utils.comment_helper import get_random_comment

        other_accs = [
            a for a in self.acc_repo.get_active_accounts()
            if a.id != account_id
        ]
        comment_acc = random.choice(other_accs) if other_accs else self.get_account(account_id)
        cat = (vt.tags or "").split(",")[0].strip()
        self.cmt_repo.create(
            plan_item_id=item.id,
            account_id=comment_acc.id,
            url=published_url,
            content=get_random_comment(cat),
            category=vt.category or "",
        )
        logger.info(f"评论任务已创建 → 账号: {comment_acc.name or comment_acc.id}")

    # ── 企微通知 ──────────────────────────────────────────────

    def send_publish_report(self, plan_id: int, plan_date,
                            account_name: str, results: list):
        """发送企微发布汇报"""
        from conf.settings import settings
        from utils.wecom import send_publish_report

        if not settings.WECOM_WEBHOOK_URL:
            return
        items_info = []
        for r in results:
            item_id = r.get("item_id")
            vt_title = ""
            if item_id:
                item = self.get_item(item_id)
                if item:
                    vt = self.get_video_task(item.video_task_id)
                    vt_title = (vt.title or "") if vt else ""
            items_info.append({
                "title": vt_title,
                "url": r.get("url") or "",
                "success": r.get("success", False),
                "error": r.get("error") or "",
            })
        send_publish_report(
            webhook_url=settings.WECOM_WEBHOOK_URL,
            plan_id=plan_id,
            plan_date=str(plan_date),
            account_name=account_name,
            items_info=items_info,
        )

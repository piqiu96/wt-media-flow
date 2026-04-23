"""
PlanWorkflow — 计划管理流程编排（create / list / reset-failed / check）

从 cmd/plan.py 的 _create / _list / _reset_failed / _check 搬迁。
"""
import random
from datetime import date as date_type

from services.plan_service import PlanService
from utils.log import get_logger

logger = get_logger(__name__)


class PlanWorkflow:
    """计划管理流程"""

    # ── create ────────────────────────────────────────────────

    def create(self, date: str = "today", dry_run: bool = False) -> dict:
        from infra.db.database import SessionLocal

        import platforms  # noqa: F401  触发注册
        from platforms.registry import PlatformRegistry

        plan_date = (date_type.today() if date in ("today", None)
                     else date_type.fromisoformat(date))

        db = SessionLocal()
        try:
            svc = PlanService(db)

            accounts = svc.get_active_accounts()
            if not accounts:
                logger.warning("没有 active 账号")
                return {"success": False, "message": "没有 active 账号"}

            # 按平台 capabilities 分组账号
            strict_accounts = []   # allows_same_source_reuse=False（百家号等）
            reuse_accounts = []    # allows_same_source_reuse=True（哔哩哔哩等）
            for a in accounts:
                plat = a.platform or "baijiahao"
                try:
                    caps = PlatformRegistry.get_capabilities(plat)
                    if caps.allows_same_source_reuse:
                        reuse_accounts.append(a)
                    else:
                        strict_accounts.append(a)
                except ValueError:
                    strict_accounts.append(a)

            acc_quota = {a.id: a.daily_limit for a in accounts}
            acc_tags: dict[int, set] = {
                a.id: {t.strip() for t in (a.tag or "").split(",") if t.strip()}
                for a in accounts
            }
            assignments: list[tuple] = []

            # ── 第一轮：strict 账号（source_vid 全局去重）──
            if strict_accounts:
                available = svc.get_unassigned_composited(limit=500)
                if available:
                    vt_pool = list(available)
                    random.shuffle(vt_pool)
                    for vt in vt_pool:
                        vt_cat = (vt.category or "").strip()
                        candidates = [
                            a for a in strict_accounts
                            if acc_quota.get(a.id, 0) > 0
                            and (not vt_cat or vt_cat in acc_tags.get(a.id, set()))
                        ]
                        if not candidates:
                            if all(acc_quota.get(a.id, 0) == 0 for a in strict_accounts):
                                break
                            continue
                        acc = random.choice(candidates)
                        assignments.append((acc, vt))
                        acc_quota[acc.id] -= 1

            # ── 第二轮：reuse 账号（按平台级去重，允许跨平台复用 source_vid）──
            if reuse_accounts:
                # 按平台分组
                plat_groups: dict[str, list] = {}
                for a in reuse_accounts:
                    plat = a.platform or "bilibili"
                    plat_groups.setdefault(plat, []).append(a)

                for plat, plat_accs in plat_groups.items():
                    available = svc.get_composited_for_platform(plat, limit=500)
                    if not available:
                        continue
                    vt_pool = list(available)
                    random.shuffle(vt_pool)
                    for vt in vt_pool:
                        vt_cat = (vt.category or "").strip()
                        candidates = [
                            a for a in plat_accs
                            if acc_quota.get(a.id, 0) > 0
                            and (not vt_cat or vt_cat in acc_tags.get(a.id, set()))
                        ]
                        if not candidates:
                            if all(acc_quota.get(a.id, 0) == 0 for a in plat_accs):
                                break
                            continue
                        acc = random.choice(candidates)
                        assignments.append((acc, vt))
                        acc_quota[acc.id] -= 1

            if not assignments:
                logger.warning("所有账号今日配额已满或无可用视频")
                return {"success": False, "message": "无法分配"}

            # 预览
            logger.info(f"发布计划预览 — {plan_date}  "
                        f"{'dry-run，不写库' if dry_run else '将写入数据库'}")
            acc_summary: dict[int, list] = {}
            for acc, vt in assignments:
                acc_summary.setdefault(acc.id, []).append(vt)
            for acc in accounts:
                tasks = acc_summary.get(acc.id, [])
                if tasks:
                    plat = acc.platform or "baijiahao"
                    cats = ", ".join(
                        f"{k}×{v}" for k, v in _count_categories(tasks).items()
                    )
                    logger.info(f"  账号 {acc.name or acc.id}(id={acc.id}) [{plat}]  "
                                f"→ {len(tasks)} 条  [{cats}]")
            logger.info(f"共分配 {len(assignments)} 条发布任务")

            if dry_run:
                return {"success": True, "message": "dry-run 预览完成",
                        "count": len(assignments)}

            # 写库
            plan = svc.create_plan(plan_date)
            order_counters: dict[int, int] = {}
            for acc, vt in assignments:
                idx = order_counters.get(acc.id, 0)
                # 从账号平台 + capabilities 推导 publish_mode
                plat = acc.platform or "baijiahao"
                try:
                    caps = PlatformRegistry.get_capabilities(plat)
                    mode = "manual_confirm" if caps.requires_manual_confirm else "auto_submit"
                except ValueError:
                    mode = "manual_confirm"
                svc.create_plan_item(
                    plan_id=plan.id,
                    account_id=acc.id,
                    video_task_id=vt.id,
                    order_idx=idx,
                    category=vt.category or "",
                    platform=plat,
                    publish_mode=mode,
                )
                order_counters[acc.id] = idx + 1

            msg = (f"计划创建成功: plan_id={plan.id}，"
                   f"{len(assignments)} 条发布（评论任务将在发布成功后自动创建）")
            logger.info(msg)
            return {"success": True, "message": msg, "plan_id": plan.id}

        finally:
            db.close()

    # ── list ──────────────────────────────────────────────────

    def list_plans(self, date: str | None = None) -> dict:
        from infra.db.database import SessionLocal

        filter_date = date_type.fromisoformat(date) if date else None
        db = SessionLocal()
        try:
            svc = PlanService(db)
            plans = svc.list_plans(filter_date)
            if not plans:
                logger.info("没有计划")
                return {"success": True, "message": "没有计划"}

            for p in plans:
                items = svc.list_items_by_plan(p.id)
                done = sum(1 for i in items if i.publish_status.value == "published")
                failed = sum(1 for i in items if i.publish_status.value == "failed")
                pending = len(items) - done - failed
                logger.info(f"plan_id={p.id} date={p.date} status={p.status} "
                            f"共{len(items)}条 (成功{done} 失败{failed} 待{pending})")
            return {"success": True, "message": f"共 {len(plans)} 个计划"}
        finally:
            db.close()

    # ── reset-failed ──────────────────────────────────────────

    def reset_failed(self, plan_id: int,
                     account_id: int | None = None) -> dict:
        from infra.db.database import SessionLocal

        db = SessionLocal()
        try:
            svc = PlanService(db)
            count = svc.reset_failed(plan_id, account_id)
            if count == 0:
                logger.info("没有可重置的技术性失败条目")
                return {"success": True, "message": "没有可重置的条目", "count": 0}
            scope = f"账号 {account_id}" if account_id else "全部账号"
            msg = f"已重置 {count} 条失败任务（{scope}）→ PENDING"
            logger.info(msg)
            return {"success": True, "message": msg, "count": count}
        finally:
            db.close()

    # ── check ─────────────────────────────────────────────────

    def check(self, plan_id: int) -> dict:
        from infra.db.database import SessionLocal
        from infra.db.repositories import (
            PublishPlanRepository, PlanItemRepository,
            AccountRepository, VideoTaskRepository, BrowserRepository,
        )
        from conf.settings import settings
        from utils.wecom import check_url_accessible, send_check_report
        from services.browser_session_service import BrowserSessionService

        db = SessionLocal()
        try:
            plan_repo = PublishPlanRepository(db)
            item_repo = PlanItemRepository(db)
            acc_repo = AccountRepository(db)
            vt_repo = VideoTaskRepository(db)

            plan = plan_repo.get_by_id(plan_id)
            if not plan:
                return {"success": False, "message": f"计划不存在: plan_id={plan_id}"}

            items = item_repo.get_published_not_notified(plan_id)
            if not items:
                logger.info(f"计划 {plan_id}：所有已发布条目均已通知，或暂无已发布链接")
                return {"success": True, "message": "无待检查条目"}

            logger.info(f"计划 {plan_id}（{plan.date}）— 检查 {len(items)} 条未通知链接")

            # 取任意一个 active 账号的比特浏览器
            accounts = acc_repo.get_active_accounts()
            bit_profile_id = None
            for acc in accounts:
                pid = acc.profile_id
                if not pid and acc.browser_id:
                    br = BrowserRepository(db).get_by_id(acc.browser_id)
                    pid = br.profile_id if br else None
                if pid:
                    bit_profile_id = pid
                    break

            acc_passed: dict[int, list] = {}
            passed_count = 0
            not_passed_count = 0

            def _check_item(item, page):
                nonlocal passed_count, not_passed_count
                vt = vt_repo.get_by_id(item.video_task_id)
                title = (vt.title or "")[:50] if vt else ""
                url = item.published_url or ""
                logger.info(f"检查: {title[:40]} | {url}")
                accessible = check_url_accessible(url, page=page)
                if accessible:
                    passed_count += 1
                    item_repo.mark_notified(item.id)
                    acc_passed.setdefault(item.account_id, []).append(
                        {"title": title, "url": url})
                    logger.info("  过审")
                else:
                    not_passed_count += 1
                    logger.info("  未过审")

            if bit_profile_id:
                browser_svc = BrowserSessionService()
                session = browser_svc.open(bit_profile_id)
                try:
                    page = browser_svc.new_page(session)
                    for item in items:
                        _check_item(item, page)
                finally:
                    browser_svc.close(session)
            else:
                logger.warning("未找到可用比特浏览器，降级用 requests 检查")
                for item in items:
                    _check_item(item, None)

            logger.info(f"结果: 过审 {passed_count} 条 / "
                        f"未过审 {not_passed_count} 条 / 共检查 {len(items)} 条")

            if settings.WECOM_WEBHOOK_URL and acc_passed:
                for acc_id, passed_items in acc_passed.items():
                    acc = acc_repo.get_by_id(acc_id)
                    acc_name = acc.name if acc else str(acc_id)
                    send_check_report(
                        webhook_url=settings.WECOM_WEBHOOK_URL,
                        plan_id=plan_id,
                        account_name=acc_name,
                        passed_items=passed_items,
                    )

            return {
                "success": True,
                "message": f"过审 {passed_count} / 未过审 {not_passed_count} / 共 {len(items)} 条",
                "passed": passed_count,
                "not_passed": not_passed_count,
            }

        finally:
            db.close()


def _count_categories(tasks) -> dict:
    counts: dict = {}
    for vt in tasks:
        cat = (vt.tags or "未分类").split(",")[0].strip() or "未分类"
        counts[cat] = counts.get(cat, 0) + 1
    return counts

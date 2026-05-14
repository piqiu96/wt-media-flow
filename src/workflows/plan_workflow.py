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

    def create(self, user_id: int, date: str = "today", dry_run: bool = False) -> dict:
        from infra.db.database import SessionLocal

        import platforms  # noqa: F401  触发注册
        from platforms.registry import PlatformRegistry

        plan_date = (date_type.today() if date in ("today", None)
                     else date_type.fromisoformat(date))

        db = SessionLocal()
        try:
            svc = PlanService(db)
            from infra.db.repositories import UserRepository, AccountRepository

            # 加载用户
            user = UserRepository(db).get_by_id(user_id)
            if not user:
                return {"success": False, "message": f"用户不存在: user_id={user_id}"}

            # 取该用户名下所有有效账号
            accounts = AccountRepository(db).get_active_accounts_by_user(user_id)
            if not accounts:
                logger.warning(f"用户 {user.name}(id={user_id}) 下没有有效账号（status=active）")
                return {"success": False, "message": f"用户 {user.name} 下没有有效账号"}

            pool_key = user.pool
            plan_name = f"{plan_date} {user.name} 发布计划"

            acc_quota = {a.id: a.daily_limit for a in accounts}
            acc_tags: dict[int, set] = {
                a.id: {t.strip() for t in (a.tag or "").split(",") if t.strip()}
                for a in accounts
            }
            assignments: list[tuple] = []

            # ── 按平台分组，每个平台独立去重 ──
            plat_groups: dict[str, list] = {}
            for a in accounts:
                plat = a.platform or "baijiahao"
                plat_groups.setdefault(plat, []).append(a)

            for plat, plat_accs in plat_groups.items():
                if pool_key:
                    available = svc.get_composited_for_pool(pool_key, plat, limit=500)
                else:
                    available = svc.get_composited_for_platform(plat, limit=500)
                if not available:
                    continue
                vt_pool = list(available)
                random.shuffle(vt_pool)
                used_source_vids: set[str] = set()
                for vt in vt_pool:
                    source_vid = (vt.source_vid or "").strip()
                    if source_vid in used_source_vids:
                        logger.info(f"跳过本轮重复素材: platform={plat} source_vid={source_vid}")
                        continue
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
                    if source_vid:
                        used_source_vids.add(source_vid)
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
            plan = svc.create_plan(plan_date, name=plan_name, user_id=user_id)
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

    # ── stats ─────────────────────────────────────────────────

    def stats(self, plan_id: int | None = None, since_date=None) -> dict:
        """抓取已发布视频的播放/点赞/评论数，写入 plan_items 统计字段。
        plan_id 和 since_date 至少传一个，也可同时传。
        平台支持：baijiahao（好看视频页）、bilibili；其他平台跳过。
        """
        import re
        from infra.db.database import SessionLocal
        from infra.db.repositories import PlanItemRepository, AccountRepository, BrowserRepository
        from services.browser_session_service import BrowserSessionService

        db = SessionLocal()
        try:
            item_repo = PlanItemRepository(db)
            acc_repo  = AccountRepository(db)

            items = item_repo.get_published_for_stats(plan_id=plan_id, since_date=since_date)
            if not items:
                msg = "无已发布条目可抓取"
                logger.info(msg)
                return {"success": True, "message": msg, "updated": 0}

            logger.info(f"共 {len(items)} 条已发布记录待抓取统计")

            # 取一个有 profile_id 的 active 账号
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

            if not bit_profile_id:
                return {"success": False, "message": "未找到可用比特浏览器，无法抓取统计数据"}

            def _fetch_haokan(url: str, page) -> dict:
                """从好看视频页面抓取播放/点赞/评论数"""
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                raw = page.evaluate(r"""() => {
                    const get = sel => {
                        const el = document.querySelector(sel);
                        return el ? el.innerText.trim() : "";
                    };
                    return {
                        play_raw: get(".extrainfo-playnums"),
                        like:     get(".extrainfo-zan"),
                        comment:  get(".extrainfo-comments"),
                    };
                }""")
                m = re.search(r"(\d[\d,]*)", raw.get("play_raw", ""))
                view  = int(m.group(1).replace(",", "")) if m else None
                like  = int(raw["like"])  if raw.get("like",  "").isdigit() else None
                comm  = int(raw["comment"]) if raw.get("comment", "").isdigit() else None
                return {"view_count": view, "like_count": like, "comment_count": comm}

            def _fetch_bilibili(url: str, page) -> dict:
                """从 B站视频页面抓取播放/点赞/评论数"""
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                raw = page.evaluate(r"""() => {
                    const get = sel => {
                        const el = document.querySelector(sel);
                        return el ? el.innerText.trim() : "";
                    };
                    return {
                        play:    get(".view.item span") || get("[class*='play'] .num") || get(".bpx-player-ctrl-view .num"),
                        like:    get(".video-like-info") || get("[class*='like'] .num"),
                        comment: get(".total-reply") || get("[class*='comment'] .total-reply"),
                    };
                }""")
                def parse_num(s):
                    if not s:
                        return None
                    s = s.replace(",", "").replace("万", "0000").strip()
                    m = re.search(r"(\d+)", s)
                    return int(m.group(1)) if m else None
                return {
                    "view_count":    parse_num(raw.get("play")),
                    "like_count":    parse_num(raw.get("like")),
                    "comment_count": parse_num(raw.get("comment")),
                }

            updated = 0
            skipped = 0
            browser_svc = BrowserSessionService()
            session = browser_svc.open(bit_profile_id)
            try:
                page = browser_svc.new_page(session)
                for item in items:
                    url      = item.published_url or ""
                    platform = item.platform or "baijiahao"
                    try:
                        if "baijiahao" in url or "haokan" in url:
                            s = _fetch_haokan(url, page)
                        elif "bilibili" in url:
                            s = _fetch_bilibili(url, page)
                        else:
                            logger.warning(f"  跳过不支持的平台 url={url}")
                            skipped += 1
                            continue

                        item_repo.update_stats(
                            item.id,
                            view_count=s["view_count"],
                            like_count=s["like_count"],
                            comment_count=s["comment_count"],
                        )
                        logger.info(
                            f"  item={item.id} [{platform}] "
                            f"播放={s['view_count']} 点赞={s['like_count']} 评论={s['comment_count']}"
                        )
                        updated += 1
                    except Exception as e:
                        logger.warning(f"  item={item.id} 抓取失败: {e}")
                        skipped += 1
            finally:
                browser_svc.close(session)

            msg = f"统计更新完成: 成功 {updated} 条 / 跳过/失败 {skipped} 条"
            logger.info(msg)
            return {"success": True, "message": msg, "updated": updated, "skipped": skipped}

        finally:
            db.close()


def _count_categories(tasks) -> dict:
    counts: dict = {}
    for vt in tasks:
        cat = (vt.tags or "未分类").split(",")[0].strip() or "未分类"
        counts[cat] = counts.get(cat, 0) + 1
    return counts

"""
PlanCommand - 发布计划管理（create / list / run）

create  从 composited 库存按账号日限自动分配，生成发布计划 + 评论任务
list    查看计划列表
run     单账号批量发布（一次浏览器 session，人工逐一确认）
"""
import random
import time
from datetime import date as date_type, datetime

from cmd import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class PlanCommand(BaseCommand):
    command_name = "plan"
    command_help = "发布计划管理（create / list / run）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        # plan create
        cp = sub.add_parser("create", help="创建发布计划")
        cp.add_argument("--date", default="today", help="计划日期 YYYY-MM-DD，默认 today")
        cp.add_argument("--dry-run", action="store_true", help="仅预览，不写库")

        # plan list
        lp = sub.add_parser("list", help="查看计划列表")
        lp.add_argument("--date", default=None, help="按日期筛选 YYYY-MM-DD")

        # plan run
        rp = sub.add_parser("run", help="执行发布计划（单账号批量）")
        rp.add_argument("--plan-id", type=int, required=True)
        rp.add_argument("--account-id", type=int, required=True)

        # plan reset-failed
        rp2 = sub.add_parser("reset-failed", help="将技术性失败（非人工拒绝）的条目重置为 PENDING")
        rp2.add_argument("--plan-id", type=int, required=True)
        rp2.add_argument("--account-id", type=int, default=None, help="只重置指定账号（不填则全部账号）")

        # plan check
        ck = sub.add_parser("check", help="检查已发布链接过审情况并推送企微通知")
        ck.add_argument("--plan-id", type=int, required=True)

    # ------------------------------------------------------------------
    def execute(self, args) -> dict:
        action = getattr(args, "sub_action", None)
        if action == "create":
            return self._create(args)
        elif action == "list":
            return self._list(args)
        elif action == "run":
            return self._run(args)
        elif action == "reset-failed":
            return self._reset_failed(args)
        elif action == "check":
            return self._check(args)
        else:
            print("请指定子命令: plan create / plan list / plan run")
            return {"success": False, "message": "缺少子命令"}

    # ------------------------------------------------------------------
    # plan create
    # ------------------------------------------------------------------
    def _create(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import (AccountRepository, VideoTaskRepository,
                                      PublishPlanRepository, PlanItemRepository)
        from utils.comment_helper import get_random_comment

        raw_date = args.date
        if raw_date == "today" or raw_date is None:
            plan_date = date_type.today()
        else:
            plan_date = date_type.fromisoformat(raw_date)

        dry_run = getattr(args, "dry_run", False)

        db = SessionLocal()
        try:
            acc_repo  = AccountRepository(db)
            vt_repo   = VideoTaskRepository(db)
            plan_repo = PublishPlanRepository(db)
            item_repo = PlanItemRepository(db)

            # 取所有 active 账号
            accounts = acc_repo.get_active_accounts()
            if not accounts:
                print("没有 active 账号")
                return {"success": False, "message": "没有 active 账号"}

            # 取所有未分配的 composited 任务
            available = vt_repo.get_unassigned_composited(limit=500)
            if not available:
                print("没有可分配的 composited 视频任务")
                return {"success": False, "message": "没有可分配的视频"}

            # 按 category 分组
            by_cat: dict[str, list] = {}
            for vt in available:
                cat = (vt.tags or "未分类").split(",")[0].strip() or "未分类"
                by_cat.setdefault(cat, []).append(vt)

            # 分配：video category 必须在账号 tag 中，每个账号按 daily_limit 轮流取
            assignments: list[tuple] = []  # (account, video_task)
            vt_pool = list(available)
            random.shuffle(vt_pool)

            acc_quota = {a.id: a.daily_limit for a in accounts}
            # 预处理账号 tag 集合，方便快速匹配
            acc_tags: dict[int, set] = {
                a.id: {t.strip() for t in (a.tag or "").split(",") if t.strip()}
                for a in accounts
            }
            for vt in vt_pool:
                vt_cat = (vt.category or "").strip()
                # 找有余量且 tag 包含此 category 的账号
                candidates = [
                    a for a in accounts
                    if acc_quota.get(a.id, 0) > 0
                    and (not vt_cat or vt_cat in acc_tags.get(a.id, set()))
                ]
                if not candidates:
                    if all(acc_quota.get(a.id, 0) == 0 for a in accounts):
                        break  # 所有账号配额已满，提前退出
                    continue   # 当前视频无匹配账号，跳过继续处理后续视频
                acc = random.choice(candidates)
                assignments.append((acc, vt))
                acc_quota[acc.id] -= 1

            if not assignments:
                print("所有账号今日配额已满或无可用视频")
                return {"success": False, "message": "无法分配"}

            # 打印预览
            print(f"\n{'='*60}")
            print(f"  发布计划预览 — {plan_date}  ({'dry-run，不写库' if dry_run else '将写入数据库'})")
            print(f"{'='*60}")
            acc_summary: dict[int, list] = {}
            for acc, vt in assignments:
                acc_summary.setdefault(acc.id, []).append(vt)
            for acc in accounts:
                tasks = acc_summary.get(acc.id, [])
                if tasks:
                    cats = ", ".join(
                        f"{k}×{v}" for k, v in
                        _count_categories(tasks).items()
                    )
                    print(f"  账号 {acc.name or acc.id}(id={acc.id})  → {len(tasks)} 条  [{cats}]")
            print(f"\n  共分配 {len(assignments)} 条发布任务")
            print(f"  评论任务: {len(assignments)} 条（账号互评）")

            if dry_run:
                return {"success": True, "message": "dry-run 预览完成",
                        "count": len(assignments)}

            # 写库
            plan = plan_repo.create(plan_date=plan_date)

            order_counters: dict[int, int] = {}
            item_list = []
            for acc, vt in assignments:
                idx = order_counters.get(acc.id, 0)
                item = item_repo.create(
                    plan_id=plan.id,
                    account_id=acc.id,
                    video_task_id=vt.id,
                    order_idx=idx,
                    category=vt.category or "",
                )
                order_counters[acc.id] = idx + 1
                item_list.append((acc, vt, item))

            msg = f"计划创建成功: plan_id={plan.id}，{len(assignments)} 条发布（评论任务将在发布成功后自动创建）"
            print(f"\n  {msg}")
            return {"success": True, "message": msg, "plan_id": plan.id}

        finally:
            db.close()

    # ------------------------------------------------------------------
    # plan reset-failed
    # ------------------------------------------------------------------
    def _reset_failed(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import PlanItemRepository
        from db.models import PlanItem, PlanItemStatusEnum

        plan_id    = args.plan_id
        account_id = getattr(args, "account_id", None)

        db = SessionLocal()
        try:
            item_repo = PlanItemRepository(db)

            query = db.query(PlanItem).filter(
                PlanItem.plan_id == plan_id,
                PlanItem.publish_status == PlanItemStatusEnum.FAILED,
                PlanItem.error_message != "人工标记失败",
            )
            if account_id:
                query = query.filter(PlanItem.account_id == account_id)

            items = query.all()
            if not items:
                print("没有可重置的技术性失败条目")
                return {"success": True, "message": "没有可重置的条目", "count": 0}

            for item in items:
                item.publish_status = PlanItemStatusEnum.PENDING
                item.error_message  = None
            db.commit()

            scope = f"账号 {account_id}" if account_id else "全部账号"
            msg = f"已重置 {len(items)} 条失败任务（{scope}）→ PENDING"
            print(msg)
            return {"success": True, "message": msg, "count": len(items)}

        finally:
            db.close()

    # ------------------------------------------------------------------
    # plan list
    # ------------------------------------------------------------------
    def _list(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import PublishPlanRepository, PlanItemRepository

        db = SessionLocal()
        try:
            plan_repo = PublishPlanRepository(db)
            item_repo = PlanItemRepository(db)

            raw_date = getattr(args, "date", None)
            if raw_date:
                plans = plan_repo.list_by_date(date_type.fromisoformat(raw_date))
            else:
                plans = plan_repo.list_recent(20)

            if not plans:
                print("没有计划")
                return {"success": True, "message": "没有计划"}

            print(f"\n{'ID':<6} {'日期':<12} {'状态':<12} {'条目数'}")
            print("-" * 50)
            for p in plans:
                items = item_repo.list_by_plan(p.id)
                done = sum(1 for i in items if i.publish_status.value == "published")
                failed = sum(1 for i in items if i.publish_status.value == "failed")
                print(f"{p.id:<6} {str(p.date):<12} {p.status:<12} "
                      f"共{len(items)}条 (成功{done} 失败{failed} 待{len(items)-done-failed})")
            return {"success": True, "message": f"共 {len(plans)} 个计划"}
        finally:
            db.close()

    # ------------------------------------------------------------------
    # plan run
    # ------------------------------------------------------------------
    def _run(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import (AccountRepository, BrowserRepository,
                                      PlanItemRepository, PublishPlanRepository,
                                      VideoTaskRepository, CommentTaskRepository)
        from db.models import VideoTask
        from library.bit_api import BitBrowserAPI
        from plat import get_platform
        from utils.confirm import wait_confirm
        from utils.comment_helper import get_random_comment
        from playwright.sync_api import sync_playwright

        plan_id    = args.plan_id
        account_id = args.account_id

        db = SessionLocal()
        try:
            plan_repo = PublishPlanRepository(db)
            item_repo = PlanItemRepository(db)
            acc_repo  = AccountRepository(db)
            vt_repo   = VideoTaskRepository(db)
            cmt_repo  = CommentTaskRepository(db)

            plan = plan_repo.get_by_id(plan_id)
            if not plan:
                return {"success": False, "message": f"计划不存在: plan_id={plan_id}"}

            account = acc_repo.get_by_id(account_id)
            if not account:
                return {"success": False, "message": f"账号不存在: account_id={account_id}"}

            items = item_repo.get_pending_by_account(plan_id, account_id)
            if not items:
                print(f"账号 {account.name or account_id} 在计划 {plan_id} 中没有待发布任务")
                return {"success": True, "message": "没有待发布任务"}

            # 取 bit_profile_id
            bit_profile_id = account.profile_id
            if not bit_profile_id and account.browser_id:
                br = BrowserRepository(db).get_by_id(account.browser_id)
                bit_profile_id = br.profile_id if br else None
            if not bit_profile_id:
                return {"success": False, "message": f"账号未关联比特浏览器"}

            platform_name = account.platform
            try:
                platform_cls = get_platform(platform_name)
            except ValueError as e:
                return {"success": False, "message": str(e)}

            print(f"\n账号: {account.name or account_id} ({platform_name})")
            print(f"计划: plan_id={plan_id}  待发布: {len(items)} 条")
            plan_repo.set_status(plan_id, "running")

            bit_api = BitBrowserAPI()
            results = []

            # -------- 一次浏览器 session --------
            browser_info = bit_api.open_browser(bit_profile_id)
            debug_port = browser_info.get("data", {}).get("http", "")
            if not debug_port:
                return {"success": False, "message": f"比特浏览器未返回调试端口"}
            if not debug_port.startswith("http"):
                debug_port = f"http://{debug_port}"
            print(f"比特浏览器已启动，调试端口: {debug_port}\n")

            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(debug_port)
                    ctx = browser.contexts[0]
                    import os, tempfile, requests as _req

                    # 清理残留 Tab，只保留第一个
                    for old_page in list(ctx.pages)[1:]:
                        try:
                            old_page.close()
                        except Exception:
                            pass

                    # ---- 阶段1：串行填充（每条填完不等确认，间隔后继续下一条）----
                    filled = []  # [(item, page, vt, cover_tmp), ...]
                    for i, item in enumerate(items, 1):
                        vt = vt_repo.get_by_id(item.video_task_id)
                        if not vt:
                            item_repo.fail(item.id, "video_task 不存在")
                            continue

                        print(f"--- 填充 [{i}/{len(items)}] plan_item={item.id} ---")
                        print(f"  标题: {(vt.title or '')[:60]}")

                        if not vt.output_path or not os.path.isfile(vt.output_path):
                            msg = "output_path 为空" if not vt.output_path else f"文件不存在: {vt.output_path}"
                            item_repo.fail(item.id, msg)
                            results.append({"success": False, "item_id": item.id})
                            continue

                        # 下载封面到临时文件
                        cover_tmp = None
                        if vt.cover_url:
                            try:
                                resp = _req.get(vt.cover_url, timeout=30)
                                cover_tmp = tempfile.NamedTemporaryFile(
                                    delete=False, suffix=".jpg")
                                cover_tmp.write(resp.content)
                                cover_tmp.close()
                                # 尺寸不足 720×405 时等比放大
                                try:
                                    from PIL import Image
                                    img = Image.open(cover_tmp.name)
                                    w, h = img.size
                                    scale = max(720 / w, 405 / h)
                                    if scale > 1:
                                        new_w, new_h = int(w * scale), int(h * scale)
                                        img = img.resize((new_w, new_h), Image.LANCZOS)
                                        img.save(cover_tmp.name, "JPEG", quality=92)
                                        print(f"  封面放大: {w}×{h} → {new_w}×{new_h}")
                                except Exception as e:
                                    print(f"  封面 resize 失败（跳过）: {e}")
                            except Exception as e:
                                print(f"  封面下载失败（跳过）: {e}")
                                cover_tmp = None

                        # 每条用独立 Tab（第一条复用已有 Tab）
                        try:
                            page = ctx.new_page() if i > 1 else (ctx.pages[0] if ctx.pages else ctx.new_page())
                        except Exception as e:
                            print(f"  无法创建 Tab: {e}")
                            item_repo.fail(item.id, f"浏览器断开: {e}")
                            if cover_tmp:
                                try:
                                    os.unlink(cover_tmp.name)
                                except Exception:
                                    pass
                            continue
                        try:
                            page.bring_to_front()
                        except Exception:
                            pass
                        platform = platform_cls(page)

                        try:
                            fill_result = platform.fill_only(
                                video_path=vt.output_path,
                                title=vt.title or "",
                                description="",
                                tags=vt.tags or "",
                                cover_path=cover_tmp.name if cover_tmp else None,
                            )
                        except Exception as e:
                            fill_result = {"success": False, "error": f"fill异常: {e}"}

                        if fill_result.get("success"):
                            filled.append((item, page, vt, cover_tmp))
                            print(f"  填充完毕 ✓")
                        else:
                            err = fill_result.get("error", "")
                            item_repo.fail(item.id, err)
                            results.append({"success": False, "item_id": item.id, "error": err})
                            print(f"  填充失败: {err}")
                            if cover_tmp:
                                try:
                                    os.unlink(cover_tmp.name)
                                except Exception:
                                    pass

                        # 任务间随机间隔（降低并发上传压力，最后一条不等）
                        if i < len(items):
                            time.sleep(random.uniform(5, 10))

                    if not filled:
                        try:
                            browser.close()
                        except Exception:
                            pass
                    else:
                        # 打印填充汇总，方便人工切换 Tab 检查
                        print(f"\n{'='*60}")
                        print(f"  已填充 {len(filled)} 条，进入逐条确认发布阶段")
                        print(f"{'='*60}")
                        for idx, (item, page, vt, _) in enumerate(filled, 1):
                            print(f"  [{idx}] {(vt.title or '')[:50]}")

                        # ---- 阶段2：逐 Tab 串行确认 ----
                        published_urls: set = set()  # 已发布 URL 集合，用于去重
                        for idx, (item, page, vt, cover_tmp) in enumerate(filled, 1):
                            try:
                                try:
                                    page.bring_to_front()
                                except Exception:
                                    print("  （自动切 Tab 失败，请手动切换到对应标签页）")
                                print(f"\n--- 确认 [{idx}/{len(filled)}] plan_item={item.id} ---")
                                print(f"  标题: {(vt.title or '')[:60]}")

                                item_repo.start_publish(item.id)
                                success = wait_confirm("人工点击发布后按 Enter 确认")

                                if success:
                                    published_url = ""
                                    try:
                                        published_url = platform_cls(page).fetch_latest_published_url(
                                            known_urls=published_urls
                                        )
                                        print(f"  已获取发布链接: {published_url}")
                                        if published_url:
                                            published_urls.add(published_url)
                                    except Exception as e:
                                        print(f"  获取链接失败（跳过）: {e}")

                                    item_repo.complete_publish(item.id, published_url=published_url)
                                    results.append({"success": True, "item_id": item.id,
                                                    "url": published_url})

                                    # 发布成功 → 即时创建评论任务（url/content 均已就绪）
                                    if published_url:
                                        other_accs = [a for a in acc_repo.get_active_accounts()
                                                      if a.id != account_id]
                                        comment_acc = random.choice(other_accs) if other_accs else account
                                        cat = (vt.tags or "").split(",")[0].strip()
                                        cmt_repo.create(
                                            plan_item_id=item.id,
                                            account_id=comment_acc.id,
                                            url=published_url,
                                            content=get_random_comment(cat),
                                            category=vt.category or "",
                                        )
                                        print(f"  评论任务已创建 → 账号: {comment_acc.name or comment_acc.id}")
                                else:
                                    item_repo.fail(item.id, "人工标记失败")
                                    results.append({"success": False, "item_id": item.id,
                                                    "error": "人工标记失败"})
                                    print(f"  已标记失败")

                            except Exception as e:
                                print(f"  [确认阶段] 异常: {e}")
                                item_repo.fail(item.id, f"确认阶段异常: {e}")
                                results.append({"success": False, "item_id": item.id, "error": str(e)})
                            finally:
                                # 清理封面临时文件
                                if cover_tmp:
                                    try:
                                        os.unlink(cover_tmp.name)
                                    except Exception:
                                        pass

                        try:
                            browser.close()
                        except Exception:
                            pass

            finally:
                try:
                    bit_api.close_browser(bit_profile_id)
                except Exception:
                    pass

            success_count = sum(1 for r in results if r.get("success"))
            if all(r.get("success") for r in results):
                plan_repo.set_status(plan_id, "done")
            print(f"\n发布完成: {success_count}/{len(results)} 成功")

            # 推送企微发布汇报
            from conf.settings import settings
            from utils.wecom import send_publish_report
            if settings.WECOM_WEBHOOK_URL:
                items_info = []
                for r in results:
                    item_id = r.get("item_id")
                    vt_title = ""
                    if item_id:
                        item = item_repo.get_by_id(item_id)
                        if item:
                            vt = vt_repo.get_by_id(item.video_task_id)
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
                    plan_date=str(plan.date),
                    account_name=account.name or str(account_id),
                    items_info=items_info,
                )

            return {
                "success": success_count > 0,
                "message": f"发布: {success_count}/{len(results)} 成功",
                "results": results,
            }

        finally:
            db.close()

    # ------------------------------------------------------------------
    # plan check
    # ------------------------------------------------------------------
    def _check(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import (PublishPlanRepository, PlanItemRepository,
                                      AccountRepository, VideoTaskRepository,
                                      BrowserRepository)
        from conf.settings import settings
        from utils.wecom import check_url_accessible, send_check_report
        from library.bit_api import BitBrowserAPI
        from playwright.sync_api import sync_playwright

        plan_id = args.plan_id

        db = SessionLocal()
        try:
            plan_repo = PublishPlanRepository(db)
            item_repo = PlanItemRepository(db)
            acc_repo  = AccountRepository(db)
            vt_repo   = VideoTaskRepository(db)

            plan = plan_repo.get_by_id(plan_id)
            if not plan:
                return {"success": False, "message": f"计划不存在: plan_id={plan_id}"}

            items = item_repo.get_published_not_notified(plan_id)

            if not items:
                print(f"计划 {plan_id}：所有已发布条目均已通知，或暂无已发布链接")
                return {"success": True, "message": "无待检查条目"}

            print(f"\n计划 {plan_id}（{plan.date}）— 检查 {len(items)} 条未通知链接")
            print(f"{'='*60}")

            # 取任意一个 active 账号的比特浏览器来借用登录态
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

            if not bit_profile_id:
                print("  警告：未找到可用比特浏览器，降级用 requests 检查（可能误判）")

            def _do_check(items_to_check):
                nonlocal passed_count, not_passed_count
                if bit_profile_id:
                    bit_api = BitBrowserAPI()
                    browser_info = bit_api.open_browser(bit_profile_id)
                    debug_port = browser_info.get("data", {}).get("http", "")
                    if debug_port and not debug_port.startswith("http"):
                        debug_port = f"http://{debug_port}"
                    try:
                        with sync_playwright() as p:
                            browser = p.chromium.connect_over_cdp(debug_port)
                            ctx = browser.contexts[0]
                            page = ctx.new_page()
                            for item in items_to_check:
                                _check_item(item, page)
                            browser.close()
                    finally:
                        try:
                            bit_api.close_browser(bit_profile_id)
                        except Exception:
                            pass
                else:
                    for item in items_to_check:
                        _check_item(item, None)

            def _check_item(item, page):
                nonlocal passed_count, not_passed_count
                vt = vt_repo.get_by_id(item.video_task_id)
                title = (vt.title or "")[:50] if vt else ""
                url = item.published_url or ""
                print(f"  检查: {title[:40]} | {url}")
                accessible = check_url_accessible(url, page=page)
                if accessible:
                    passed_count += 1
                    item_repo.mark_notified(item.id)
                    acc_passed.setdefault(item.account_id, []).append(
                        {"title": title, "url": url}
                    )
                    print(f"    ✅ 已过审")
                else:
                    not_passed_count += 1
                    print(f"    ⏳ 未过审")

            _do_check(items)

            print(f"\n结果: 过审 {passed_count} 条 / 未过审 {not_passed_count} 条 / 共检查 {len(items)} 条")

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

"""
CommentCommand - 评论管理（single / batch）

single  打开指定帖子 URL，填入评论内容，等待人工确认提交
batch   批量执行 comment_tasks 队列（一次浏览器 session）
"""
from cmd import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class CommentCommand(BaseCommand):
    command_name = "comment"
    command_help = "评论管理（single 单条 / batch 批量队列）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        # comment single（原有功能）
        sp = sub.add_parser("single", help="打开指定 URL 评论一条")
        sp.add_argument("--account-id", type=int, required=True)
        sp.add_argument("--url", required=True)
        sp.add_argument("--content", required=True)
        sp.add_argument("--wait", type=int, default=120,
                        help="人工确认等待秒数（非交互环境使用，默认 120）")

        # comment batch（从 comment_tasks 队列，单账号执行）
        bp = sub.add_parser("batch", help="批量执行 comment_tasks 队列（单账号）")
        bp.add_argument("--account-id", type=int, required=True)
        bp.add_argument("--limit", type=int, default=20, help="本次最多处理条数（默认 20）")

        # comment fire（从 comment_tasks 队列，随机多账号执行）
        fp = sub.add_parser("fire", help="随机选多个账号批量执行 comment_tasks 队列")
        fp.add_argument("--count", type=int, default=4, help="每条任务随机选取账号数量（默认 4）")
        fp.add_argument("--tasks", type=int, default=0, help="处理任务条数（默认 0=全部 pending）")

    def execute(self, args) -> dict:
        action = getattr(args, "sub_action", None)
        if action == "batch":
            return self._batch(args)
        elif action == "fire":
            return self._fire(args)
        else:
            # single 或无子命令（兼容旧版直接 comment --url）
            return self._single(args)

    # ------------------------------------------------------------------
    # single
    # ------------------------------------------------------------------
    def _single(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import AccountRepository, BrowserRepository
        from library.bit_api import BitBrowserAPI
        from plat.baijiahao.bjh import BaijiahaoPlatform
        from playwright.sync_api import sync_playwright

        account_id  = args.account_id
        url         = args.url
        content     = args.content
        wait_seconds = getattr(args, "wait", 120)

        db = SessionLocal()
        try:
            account = AccountRepository(db).get_by_id(account_id)
            if not account:
                return {"success": False, "message": f"账号不存在: account_id={account_id}"}
            bit_profile_id = account.profile_id
            if not bit_profile_id and account.browser_id:
                br = BrowserRepository(db).get_by_id(account.browser_id)
                bit_profile_id = br.profile_id if br else None
            if not bit_profile_id:
                return {"success": False, "message": "账号未关联比特浏览器"}
        finally:
            db.close()

        print(f"账号: {account.name or account_id} | 帖子: {url}")
        print(f"评论: {content[:60]}")

        bit_api = BitBrowserAPI()
        result = {}
        try:
            browser_info = bit_api.open_browser(bit_profile_id)
            debug_port = browser_info.get("data", {}).get("http", "")
            if not debug_port:
                return {"success": False, "message": "比特浏览器未返回调试端口"}
            if not debug_port.startswith("http"):
                debug_port = f"http://{debug_port}"
            print(f"比特浏览器已启动，调试端口: {debug_port}")

            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(debug_port)
                    page = browser.contexts[0].pages[0] if browser.contexts[0].pages \
                        else browser.contexts[0].new_page()
                    platform = BaijiahaoPlatform(page)
                    result = platform.comment_on(url, content, wait_seconds=wait_seconds)
                    try:
                        page.close()
                    except Exception:
                        pass
                    browser.close()
            except Exception as e:
                result = {"success": False, "error": str(e)}
                logger.error(f"Playwright 评论异常: {e}")
        finally:
            try:
                bit_api.close_browser(bit_profile_id)
            except Exception:
                pass

        success = result.get("success", False)
        msg = result.get("message") or result.get("error", "")
        print(f"评论{'完成' if success else '失败'}: {msg}")
        return {"success": success, "message": msg}

    # ------------------------------------------------------------------
    # batch
    # ------------------------------------------------------------------
    def _batch(self, args) -> dict:
        import random
        from db.database import SessionLocal
        from db.repositories import (AccountRepository, BrowserRepository,
                                      CommentTaskRepository)
        from library.bit_api import BitBrowserAPI
        from plat.baijiahao.bjh import BaijiahaoPlatform
        from playwright.sync_api import sync_playwright
        from utils.comment_helper import get_random_comment

        account_id = args.account_id
        limit = getattr(args, "limit", 20)

        db = SessionLocal()
        try:
            acc_repo = AccountRepository(db)
            cmt_repo = CommentTaskRepository(db)

            account = acc_repo.get_by_id(account_id)
            if not account:
                return {"success": False, "message": f"账号不存在: account_id={account_id}"}

            bit_profile_id = account.profile_id
            if not bit_profile_id and account.browser_id:
                br = BrowserRepository(db).get_by_id(account.browser_id)
                bit_profile_id = br.profile_id if br else None
            if not bit_profile_id:
                return {"success": False, "message": "账号未关联比特浏览器"}

            tasks = cmt_repo.get_pending_by_account(account_id, limit=limit)

            # 执行前按 comment_task.category 随机选文案
            task_contents = {
                t.id: get_random_comment(t.category or "default")
                for t in tasks
            }
        finally:
            db.close()

        if not tasks:
            print(f"账号 {account.name or account_id} 没有待评论任务")
            return {"success": True, "message": "没有待评论任务"}

        print(f"\n账号: {account.name or account_id}  待评论: {len(tasks)} 条")

        bit_api = BitBrowserAPI()
        results = []

        browser_info = bit_api.open_browser(bit_profile_id)
        debug_port = browser_info.get("data", {}).get("http", "")
        if not debug_port:
            return {"success": False, "message": "比特浏览器未返回调试端口"}
        if not debug_port.startswith("http"):
            debug_port = f"http://{debug_port}"
        print(f"比特浏览器已启动，调试端口: {debug_port}\n")

        db2 = SessionLocal()
        try:
            cmt_repo2 = CommentTaskRepository(db2)

            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(debug_port)
                    ctx = browser.contexts[0]
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    platform = BaijiahaoPlatform(page)

                    for i, task in enumerate(tasks, 1):
                        content = task_contents.get(task.id, "")
                        print(f"--- [{i}/{len(tasks)}] comment_task={task.id} ---")
                        print(f"  URL:     {task.url}")
                        print(f"  评论内容: {content[:60]}")

                        cmt_repo2.start(task.id)
                        try:
                            result = platform.comment_on(task.url, content)
                        except Exception as e:
                            result = {"success": False, "error": str(e)}

                        if result.get("success"):
                            # 确认成功后把实际使用的文案写回库
                            cmt_repo2.update_content(task.id, content)
                            cmt_repo2.complete(task.id)
                            results.append({"success": True, "task_id": task.id})
                            print(f"  评论完成")
                        else:
                            err = result.get("error", "")
                            cmt_repo2.fail(task.id, err)
                            results.append({"success": False, "task_id": task.id, "error": err})
                            print(f"  评论失败: {err}")

                    try:
                        page.close()
                    except Exception:
                        pass
                    browser.close()

            finally:
                try:
                    bit_api.close_browser(bit_profile_id)
                except Exception:
                    pass

        finally:
            db2.close()

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n评论完成: {success_count}/{len(results)} 成功")
        return {
            "success": success_count > 0,
            "message": f"评论: {success_count}/{len(results)} 成功",
            "results": results,
        }

    # ------------------------------------------------------------------
    # fire：循环取 pending 任务，每条随机 N 个账号全自动评论
    # ------------------------------------------------------------------
    def _fire(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import CommentTaskRepository
        from db.models import CommentTask, CommentTaskStatusEnum

        count      = getattr(args, "count", 4)
        max_tasks  = getattr(args, "tasks", 0)   # 0 = 全部

        # 预取所有 pending 任务 id 列表（按 id 升序）
        db = SessionLocal()
        try:
            pending_ids = [
                row[0] for row in
                db.query(CommentTask.id)
                  .filter(CommentTask.status == CommentTaskStatusEnum.PENDING,
                          CommentTask.url.isnot(None), CommentTask.url != "")
                  .order_by(CommentTask.id.asc())
                  .all()
            ]
        finally:
            db.close()

        if not pending_ids:
            print("没有待评论任务")
            return {"success": True, "message": "没有待评论任务"}

        if max_tasks > 0:
            pending_ids = pending_ids[:max_tasks]

        print(f"\n共 {len(pending_ids)} 条待评论任务，每条随机选 {count} 个账号")

        total_done = 0
        total_fail = 0
        for idx, task_id in enumerate(pending_ids, 1):
            print(f"\n{'#'*60}")
            print(f"  任务 [{idx}/{len(pending_ids)}]  comment_task={task_id}")
            r = self._fire_one(task_id, count)
            if r.get("success"):
                total_done += 1
            else:
                total_fail += 1

        print(f"\n{'='*60}")
        print(f"  全部完成: 成功 {total_done} / 失败 {total_fail} / 共 {len(pending_ids)} 条")
        return {
            "success": total_done > 0,
            "message": f"fire: 成功 {total_done} / 失败 {total_fail} / 共 {len(pending_ids)} 条",
        }

    def _fire_one(self, task_id: int, count: int) -> dict:
        """对单条 comment_task 随机选 N 个账号全自动评论"""
        import random, yaml
        from pathlib import Path
        from db.database import SessionLocal
        from db.repositories import (AccountRepository, BrowserRepository,
                                      CommentTaskRepository)
        from db.models import CommentTask
        from library.bit_api import BitBrowserAPI
        from plat.baijiahao.bjh import BaijiahaoPlatform
        from playwright.sync_api import sync_playwright

        # ---- 读任务 ----
        db = SessionLocal()
        try:
            task = db.query(CommentTask).filter(CommentTask.id == task_id).first()
            if not task:
                return {"success": False, "message": f"任务不存在: {task_id}"}
            target_url = task.url
            category   = task.category or "default"

            all_accounts = AccountRepository(db).get_active_accounts()
            selected     = random.sample(all_accounts, min(count, len(all_accounts)))

            account_plans = []
            for acc in selected:
                pid = acc.profile_id
                if not pid and acc.browser_id:
                    br = BrowserRepository(db).get_by_id(acc.browser_id)
                    pid = br.profile_id if br else None
                if pid:
                    account_plans.append({"account": acc, "profile_id": pid})
        finally:
            db.close()

        if not account_plans:
            return {"success": False, "message": "无可用账号"}

        print(f"  URL:    {target_url}")
        print(f"  品类:   {category}")
        print(f"  账号:   {[p['account'].name or p['account'].id for p in account_plans]}")

        # ---- 抽文案（shuffle 后轮取，尽量不重复）----
        _tpl = {}
        _tpl_path = Path("conf/comment_templates.yaml")
        if _tpl_path.exists():
            with open(_tpl_path, encoding="utf-8") as f:
                _tpl = yaml.safe_load(f) or {}
        pool = list(_tpl.get(category) or _tpl.get("default") or ["内容不错，收藏了！"])
        random.shuffle(pool)
        contents = [pool[i % len(pool)] for i in range(len(account_plans))]

        # ---- 逐账号全自动评论 ----
        bit_api = BitBrowserAPI()
        results = []
        for i, plan in enumerate(account_plans):
            acc     = plan["account"]
            content = contents[i]
            print(f"\n  [{i+1}/{len(account_plans)}] {acc.name or acc.id} | 文案: {content[:50]}")

            browser_info = bit_api.open_browser(plan["profile_id"])
            debug_port   = browser_info.get("data", {}).get("http", "")
            if not debug_port:
                results.append({"success": False, "content": content, "error": "浏览器启动失败"})
                continue
            if not debug_port.startswith("http"):
                debug_port = f"http://{debug_port}"

            try:
                with sync_playwright() as pw:
                    browser  = pw.chromium.connect_over_cdp(debug_port)
                    ctx      = browser.contexts[0]
                    page     = ctx.pages[0] if ctx.pages else ctx.new_page()
                    r        = BaijiahaoPlatform(page).auto_comment(target_url, content)
                    try:
                        page.close()
                    except Exception:
                        pass
                    browser.close()
            except Exception as e:
                r = {"success": False, "error": str(e)}
            finally:
                try:
                    bit_api.close_browser(plan["profile_id"])
                except Exception:
                    pass

            ok = r.get("success", False)
            print(f"  {'✅ 成功' if ok else '❌ 失败: ' + r.get('error', '')}")
            results.append({"success": ok, "content": content, "error": r.get("error", "")})

        # ---- 写库 ----
        success_n = sum(1 for r in results if r["success"])
        final_success = success_n / len(results) >= 0.5 if results else False

        print(f"\n  结果: {success_n}/{len(results)} 成功 → {'✅ 标记完成' if final_success else '❌ 标记失败（成功率不足50%）'}")
        for i, r in enumerate(results):
            acc_name = account_plans[i]["account"].name or str(account_plans[i]["account"].id)
            print(f"    {'✅' if r['success'] else '❌'} {acc_name}: {r['error'] or '成功'}")

        db2 = SessionLocal()
        try:
            cmt_repo2 = CommentTaskRepository(db2)
            used_content = next((r["content"] for r in results if r["success"]), "")
            if final_success:
                if used_content:
                    cmt_repo2.update_content(task_id, used_content)
                cmt_repo2.complete(task_id)
            else:
                errors = "; ".join(r["error"] for r in results if r["error"])
                cmt_repo2.fail(task_id, errors[:200])
        finally:
            db2.close()

        # ---- 企微通知 ----
        try:
            from conf.settings import settings
            from utils.wecom import send_text
            success_n = sum(1 for r in results if r["success"])
            status_icon = "✅" if final_success else "❌"
            lines = [
                f"**{status_icon} 评论{'完成' if final_success else '失败'} | comment_task={task_id}**",
                f"目标：[{target_url}]({target_url})",
                f"账号数：{len(account_plans)}  成功：{success_n}",
                "",
            ]
            for i, r in enumerate(results):
                acc_name = account_plans[i]["account"].name or str(account_plans[i]["account"].id)
                icon = "✅" if r["success"] else "❌"
                lines.append(f"{icon} {acc_name}：{r['content'][:30]}" +
                              (f"  — {r['error'][:30]}" if r.get("error") else ""))
            send_text(settings.WECOM_WEBHOOK_URL, "\n".join(lines))
        except Exception as _e:
            print(f"  [企微通知失败] {_e}")

        return {"success": final_success}

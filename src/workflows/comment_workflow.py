"""
CommentWorkflow — 评论流程编排

从 cmd/comment.py 搬迁 single / batch / fire 逻辑。
"""
import random
import yaml
from pathlib import Path

from services.browser_session_service import BrowserSessionService
from utils.log import get_logger

logger = get_logger(__name__)


class CommentWorkflow:
    """评论流程编排"""

    def single(self, account_id: int, url: str, content: str,
               wait_seconds: int = 120) -> dict:
        """单条评论（人工确认模式）"""
        from infra.db.database import SessionLocal
        from infra.db.repositories import AccountRepository, BrowserRepository

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

        logger.info(f"账号: {account.name or account_id} | 帖子: {url}")
        logger.info(f"评论: {content[:60]}")

        browser_svc = BrowserSessionService()
        session = browser_svc.open(bit_profile_id)
        try:
            page = browser_svc.new_page(session)

            import platforms  # noqa: F401
            from platforms.registry import PlatformRegistry

            commenter = PlatformRegistry.get_commenter("baijiahao")
            result = commenter.fill_comment(page, url, content)

            if result.get("success"):
                from utils.confirm import wait_confirm
                success = wait_confirm("评论内容已填入，请在浏览器中手动点击提交")
                if not success:
                    result = {"success": False, "error": "人工标记失败"}
                else:
                    result = {"success": True, "message": "评论完成"}
        except Exception as e:
            result = {"success": False, "error": str(e)}
            logger.error(f"评论异常: {e}")
        finally:
            browser_svc.close(session)

        success = result.get("success", False)
        msg = result.get("message") or result.get("error", "")
        logger.info(f"评论{'完成' if success else '失败'}: {msg}")
        return {"success": success, "message": msg}

    def batch(self, account_id: int, limit: int = 20) -> dict:
        """批量评论（单账号，从 comment_tasks 队列）"""
        from infra.db.database import SessionLocal
        from infra.db.repositories import (AccountRepository, BrowserRepository,
                                      CommentTaskRepository)
        from utils.comment_helper import get_random_comment

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
            task_contents = {
                t.id: get_random_comment(t.category or "default")
                for t in tasks
            }
        finally:
            db.close()

        if not tasks:
            logger.info(f"账号 {account.name or account_id} 没有待评论任务")
            return {"success": True, "message": "没有待评论任务"}

        logger.info(f"账号: {account.name or account_id}  待评论: {len(tasks)} 条")

        # 使用 platforms 层评论器
        from platforms.baijiahao.commenter import BaijiahaoCommenter
        from utils.confirm import wait_confirm

        browser_svc = BrowserSessionService()
        session = browser_svc.open(bit_profile_id)
        results = []

        db2 = SessionLocal()
        try:
            cmt_repo2 = CommentTaskRepository(db2)

            page = browser_svc.new_page(session)
            commenter = BaijiahaoCommenter()

            for i, task in enumerate(tasks, 1):
                content = task_contents.get(task.id, "")
                logger.info(f"[{i}/{len(tasks)}] comment_task={task.id} url={task.url}")
                logger.info(f"  评论内容: {content[:60]}")

                cmt_repo2.start(task.id)
                try:
                    fill_result = commenter.fill_comment(page, task.url, content)
                    if fill_result.get("success"):
                        success = wait_confirm("评论内容已填入，请在浏览器中手动点击提交")
                        if success:
                            result = {"success": True, "message": "评论完成"}
                        else:
                            result = {"success": False, "error": "人工标记失败"}
                    else:
                        result = {"success": False, "error": fill_result.get("error", "填充失败")}
                except Exception as e:
                    result = {"success": False, "error": str(e)}

                if result.get("success"):
                    cmt_repo2.update_content(task.id, content)
                    cmt_repo2.complete(task.id)
                    results.append({"success": True, "task_id": task.id})
                    logger.info("  评论完成")
                else:
                    err = result.get("error", "")
                    cmt_repo2.fail(task.id, err)
                    results.append({"success": False, "task_id": task.id, "error": err})
                    logger.error(f"  评论失败: {err}")

        finally:
            browser_svc.close(session)
            db2.close()

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"评论完成: {success_count}/{len(results)} 成功")
        return {
            "success": success_count > 0,
            "message": f"评论: {success_count}/{len(results)} 成功",
            "results": results,
        }

    def fire(self, count: int = 4, max_tasks: int = 0) -> dict:
        """随机多账号全自动评论"""
        from infra.db.database import SessionLocal
        from infra.db.models import CommentTask, CommentTaskStatusEnum

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
            logger.info("没有待评论任务")
            return {"success": True, "message": "没有待评论任务"}

        if max_tasks > 0:
            pending_ids = pending_ids[:max_tasks]

        logger.info(f"共 {len(pending_ids)} 条待评论任务，每条随机选 {count} 个账号")

        total_done = 0
        total_fail = 0
        for idx, task_id in enumerate(pending_ids, 1):
            logger.info(f"任务 [{idx}/{len(pending_ids)}]  comment_task={task_id}")
            r = self._fire_one(task_id, count)
            if r.get("success"):
                total_done += 1
            else:
                total_fail += 1

        logger.info(f"全部完成: 成功 {total_done} / 失败 {total_fail} / 共 {len(pending_ids)} 条")
        return {
            "success": total_done > 0,
            "message": f"fire: 成功 {total_done} / 失败 {total_fail} / 共 {len(pending_ids)} 条",
        }

    def _fire_one(self, task_id: int, count: int) -> dict:
        """对单条 comment_task 随机选 N 个账号全自动评论"""
        from infra.db.database import SessionLocal
        from infra.db.repositories import (AccountRepository, BrowserRepository,
                                      CommentTaskRepository)
        from infra.db.models import CommentTask

        import platforms  # noqa: F401
        from platforms.registry import PlatformRegistry

        db = SessionLocal()
        try:
            task = db.query(CommentTask).filter(CommentTask.id == task_id).first()
            if not task:
                return {"success": False, "message": f"任务不存在: {task_id}"}
            target_url = task.url
            category = task.category or "default"

            all_accounts = AccountRepository(db).get_active_accounts()
            selected = random.sample(all_accounts, min(count, len(all_accounts)))

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

        logger.info(f"URL: {target_url}")
        logger.info(f"品类: {category}")
        logger.info(f"账号: {[p['account'].name or p['account'].id for p in account_plans]}")

        # 抽文案
        _tpl = {}
        _tpl_path = Path("conf/comment_templates.yaml")
        if _tpl_path.exists():
            with open(_tpl_path, encoding="utf-8") as f:
                _tpl = yaml.safe_load(f) or {}
        pool = list(_tpl.get(category) or _tpl.get("default") or ["内容不错，收藏了！"])
        random.shuffle(pool)
        contents = [pool[i % len(pool)] for i in range(len(account_plans))]

        # 逐账号全自动评论
        browser_svc = BrowserSessionService()
        results = []
        for i, plan in enumerate(account_plans):
            acc = plan["account"]
            content = contents[i]
            logger.info(f"[{i+1}/{len(account_plans)}] {acc.name or acc.id} | 文案: {content[:50]}")

            session = browser_svc.open(plan["profile_id"])
            try:
                page = browser_svc.new_page(session)
                commenter = PlatformRegistry.get_commenter("baijiahao")
                r = commenter.auto_comment(page, target_url, content)
            except Exception as e:
                r = {"success": False, "error": str(e)}
            finally:
                browser_svc.close(session)

            ok = r.get("success", False)
            if ok:
                logger.info(f"  成功")
            else:
                logger.error(f"  失败: {r.get('error', '')}")
            results.append({"success": ok, "content": content, "error": r.get("error", "")})

        # 写库
        success_n = sum(1 for r in results if r["success"])
        final_success = success_n / len(results) >= 0.5 if results else False

        logger.info(f"结果: {success_n}/{len(results)} 成功")

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

        # 企微通知
        try:
            from conf.settings import settings
            from utils.wecom import send_text
            status_icon = "OK" if final_success else "FAIL"
            lines = [
                f"**{status_icon} 评论{'完成' if final_success else '失败'} | comment_task={task_id}**",
                f"目标：{target_url}",
                f"账号数：{len(account_plans)}  成功：{success_n}",
                "",
            ]
            for i, r in enumerate(results):
                acc_name = account_plans[i]["account"].name or str(account_plans[i]["account"].id)
                icon = "OK" if r["success"] else "FAIL"
                lines.append(f"{icon} {acc_name}：{r['content'][:30]}" +
                              (f"  — {r['error'][:30]}" if r.get("error") else ""))
            send_text(settings.WECOM_WEBHOOK_URL, "\n".join(lines))
        except Exception as _e:
            logger.warning(f"企微通知失败: {_e}")

        return {"success": final_success}

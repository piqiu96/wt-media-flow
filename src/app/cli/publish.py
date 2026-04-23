"""
PublishCommand - 视频发布命令（调试/直接发布用）

注意：这是面向 video_tasks 表的独立直接发布命令，用于调试或单次手动发布。
日常批量发布应走 plan create → plan run 的计划发布流程（通过 PublishWorkflow）。
"""
from app.cli import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class PublishCommand(BaseCommand):
    command_name = "publish"
    command_help = "从合成队列取任务，通过比特浏览器自动发布到指定平台"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--account-id", type=int, required=True,
                            help="发布账号 ID（对应 accounts 表）")
        parser.add_argument("--platform", type=str, default=None,
                            help="目标平台（bilibili / baijiahao / xiaohongshu），不填则读账号的 platform 字段")
        parser.add_argument("--task-id", type=int, default=None,
                            help="指定单个 video_task ID 发布（不填则取所有 composited 任务）")
        parser.add_argument("--limit", type=int, default=5,
                            help="本次最多发布数量（默认 5）")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def execute(self, args) -> dict:
        from infra.db.database import SessionLocal
        from infra.db.repositories import AccountRepository, VideoTaskRepository
        from infra.db.models import VideoTaskStatusEnum
        from infra.browser.bit_api import BitBrowserAPI
        from platforms.registry import PlatformRegistry
        import platforms  # noqa: F401 — 触发平台注册

        config = self.load_config(args)
        account_id = args.account_id
        platform_override = getattr(args, "platform", None) or config.get("platform")
        task_id = getattr(args, "task_id", None)
        limit = getattr(args, "limit", 5)

        db = SessionLocal()
        try:
            account_repo = AccountRepository(db)
            vt_repo = VideoTaskRepository(db)

            account = account_repo.get_by_id(account_id)
            if not account:
                return {"success": False, "message": f"账号不存在: account_id={account_id}"}

            # 取比特浏览器 profile_id（优先用账号冗余字段，fallback 查 browsers 表）
            bit_profile_id = account.profile_id
            if not bit_profile_id and account.browser_id:
                from infra.db.repositories import BrowserRepository
                browser = BrowserRepository(db).get_by_id(account.browser_id)
                bit_profile_id = browser.profile_id if browser else None
            if not bit_profile_id:
                return {"success": False, "message": f"账号 id={account_id} 未关联比特浏览器容器"}

            platform_name = platform_override or account.platform
            try:
                publisher = PlatformRegistry.get_publisher(platform_name)
            except (ValueError, KeyError) as e:
                return {"success": False, "message": str(e)}

            # 取任务列表
            if task_id:
                task = vt_repo.get_by_id(task_id)
                if not task:
                    return {"success": False, "message": f"任务不存在: task_id={task_id}"}
                if task.status != VideoTaskStatusEnum.COMPOSITED:
                    return {"success": False,
                            "message": f"任务状态不是 composited，当前: {task.status}"}
                tasks = [task]
            else:
                tasks = vt_repo.get_pending_publish(limit=limit)

            if not tasks:
                return {"success": True, "message": "没有待发布的任务"}

            print(f"待发布任务数: {len(tasks)}，账号: {account.name or account.username}，平台: {platform_name}")

            bit_api = BitBrowserAPI()
            results = []

            for i, task in enumerate(tasks, 1):
                print(f"\n--- [{i}/{len(tasks)}] task_id={task.id} vid={task.video_id} ---")
                print(f"  标题: {(task.title or '')[:60]}")

                if not task.output_path:
                    msg = "合成输出路径为空，跳过"
                    print(f"  {msg}")
                    vt_repo.fail(task.id, message=msg)
                    results.append({"success": False, "task_id": task.id, "error": msg})
                    continue

                import os
                if not os.path.isfile(task.output_path):
                    msg = f"合成文件不存在: {task.output_path}"
                    print(f"  {msg}")
                    vt_repo.fail(task.id, message=msg)
                    results.append({"success": False, "task_id": task.id, "error": msg})
                    continue

                # 标记发布中
                vt_repo.start_publish(task.id, account_id)

                # 打开比特浏览器
                browser_info = None
                try:
                    browser_info = bit_api.open_browser(bit_profile_id)
                    debug_port = browser_info.get("data", {}).get("http", "")
                    if not debug_port:
                        raise RuntimeError(f"比特浏览器未返回调试端口: {browser_info}")
                    if not debug_port.startswith("http"):
                        debug_port = f"http://{debug_port}"
                    print(f"  比特浏览器已启动，调试端口: {debug_port}")
                except Exception as e:
                    msg = f"比特浏览器启动失败: {e}"
                    logger.error(msg)
                    vt_repo.fail(task.id, message=msg,
                                 detail_update={"bit_error": str(e)})
                    results.append({"success": False, "task_id": task.id, "error": msg})
                    continue

                # Playwright 连接 CDP
                upload_result = {}
                cover_tmp = None
                try:
                    # 下载封面图到临时文件
                    if task.cover_url:
                        import tempfile, requests as _req
                        try:
                            resp = _req.get(task.cover_url, timeout=30)
                            suffix = ".jpg"
                            cover_tmp = tempfile.NamedTemporaryFile(
                                delete=False, suffix=suffix)
                            cover_tmp.write(resp.content)
                            cover_tmp.close()
                            print(f"  封面图已下载: {cover_tmp.name}")
                        except Exception as e:
                            print(f"  封面图下载失败（跳过）: {e}")
                            cover_tmp = None

                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        browser = p.chromium.connect_over_cdp(debug_port)
                        page = browser.contexts[0].pages[0] if browser.contexts[0].pages \
                            else browser.contexts[0].new_page()

                        from platforms.base import PublishPayload
                        payload = PublishPayload(
                            video_path=task.output_path,
                            title=task.title or "",
                            description="",
                            tags=(task.tags or "").split(",") if task.tags else [],
                            cover_path=cover_tmp.name if cover_tmp else None,
                        )
                        fill_result = publisher.fill_form(page, payload)
                        if fill_result.get("success"):
                            caps = PlatformRegistry.get_capabilities(platform_name)
                            if caps.requires_manual_confirm:
                                from utils.confirm import wait_confirm
                                confirmed = wait_confirm("表单已填写，请在浏览器中手动点击发布按钮，完成后按 Enter")
                                if confirmed:
                                    pub_url = publisher.fetch_published_url(page)
                                    upload_result = {"success": True, "url": pub_url}
                                else:
                                    upload_result = {"success": False, "error": "人工标记失败"}
                            else:
                                submit_result = publisher.submit(page)
                                if submit_result.get("success"):
                                    pub_url = publisher.fetch_published_url(page)
                                    upload_result = {"success": True, "url": pub_url}
                                else:
                                    upload_result = {"success": False, "error": submit_result.get("error") or "提交失败"}
                        else:
                            upload_result = {"success": False, "error": fill_result.get("error") or "表单填写失败"}
                        browser.close()
                except Exception as e:
                    upload_result = {"success": False, "error": str(e)}
                    logger.error(f"  Playwright 发布异常: {e}")
                finally:
                    # 清理封面临时文件
                    if cover_tmp:
                        import os as _os
                        try:
                            _os.unlink(cover_tmp.name)
                        except Exception:
                            pass
                    # 关闭比特浏览器
                    try:
                        bit_api.close_browser(bit_profile_id)
                    except Exception:
                        pass

                if upload_result.get("success"):
                    published_url = upload_result.get("url", "")
                    vt_repo.complete_publish(
                        task.id,
                        published_url=published_url,
                        detail_update={"publish_resp": upload_result,
                                       "platform": platform_name},
                    )
                    print(f"  发布成功: {published_url or '（待确认）'}")
                    results.append({"success": True, "task_id": task.id,
                                    "url": published_url})
                else:
                    err = upload_result.get("error", upload_result.get("message", ""))
                    vt_repo.fail(
                        task.id,
                        message=f"发布失败: {err}",
                        detail_update={"publish_error": err, "platform": platform_name},
                    )
                    print(f"  发布失败: {err}")
                    results.append({"success": False, "task_id": task.id, "error": err})

        finally:
            db.close()

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n发布完成: {success_count}/{len(results)} 成功")
        return {
            "success": success_count > 0,
            "message": f"发布: {success_count}/{len(results)} 成功",
            "results": results,
        }

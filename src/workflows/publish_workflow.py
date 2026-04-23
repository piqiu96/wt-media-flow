"""
PublishWorkflow — 单账号发布流程编排

从 cmd/plan.py _run() (L263-571) 搬迁。
两阶段：串行填充 → 逐 Tab 人工确认 + 回链。
"""
import os
import time
import random

from services.browser_session_service import BrowserSessionService
from services.publish_service import PublishService
from utils.log import get_logger

logger = get_logger(__name__)


class PublishWorkflow:
    """单账号批量发布流程"""

    def execute(self, plan_id: int, account_id: int) -> dict:
        from infra.db.database import SessionLocal
        from utils.confirm import wait_confirm

        import platforms  # noqa: F401  触发平台注册
        from platforms.registry import PlatformRegistry

        db = SessionLocal()
        try:
            pub_svc = PublishService(db)
            browser_svc = BrowserSessionService()

            # 校验
            plan = pub_svc.get_plan(plan_id)
            if not plan:
                return {"success": False, "message": f"计划不存在: plan_id={plan_id}"}

            account = pub_svc.get_account(account_id)
            if not account:
                return {"success": False, "message": f"账号不存在: account_id={account_id}"}

            items = pub_svc.get_pending_items(plan_id, account_id)
            if not items:
                logger.info(f"账号 {account.name or account_id} 在计划 {plan_id} 中没有待发布任务")
                return {"success": True, "message": "没有待发布任务"}

            bit_profile_id = pub_svc.resolve_browser_profile(account)
            if not bit_profile_id:
                return {"success": False, "message": "账号未关联比特浏览器"}

            # 从 items 推导平台（同一账号同一 plan 平台一致）
            platform_name = getattr(items[0], 'platform', None) or account.platform
            publisher = PlatformRegistry.get_publisher(platform_name)
            caps = publisher.capabilities

            logger.info(f"账号: {account.name or account_id} ({platform_name})")
            logger.info(f"计划: plan_id={plan_id}  待发布: {len(items)} 条")
            pub_svc.set_plan_status(plan_id, "running")

            results = []

            # ── 打开浏览器会话 ─────────────────────────────────
            session = browser_svc.open(bit_profile_id)
            try:
                # ── 阶段1：串行填充 ───────────────────────────
                filled = []  # [(item, page, vt, cover_tmp_path), ...]
                for i, item in enumerate(items, 1):
                    vt = pub_svc.get_video_task(item.video_task_id)
                    if not vt:
                        pub_svc.fail_publish(item.id, "video_task 不存在")
                        continue

                    logger.info(f"--- 填充 [{i}/{len(items)}] plan_item={item.id} ---")
                    logger.info(f"  标题: {(vt.title or '')[:60]}")

                    if not vt.output_path or not os.path.isfile(vt.output_path):
                        msg = "output_path 为空" if not vt.output_path else f"文件不存在: {vt.output_path}"
                        pub_svc.fail_publish(item.id, msg)
                        results.append({"success": False, "item_id": item.id})
                        continue

                    # 通过平台 Mapper 构建载荷（封面下载/标题处理等由各平台 Mapper 处理）
                    mapper = PlatformRegistry.get_mapper(platform_name)
                    payload = mapper.build_payload(
                        video_path=vt.output_path,
                        title=vt.title or "",
                        description="",
                        tags=(vt.tags or "").split(",") if vt.tags else [],
                        cover_url=vt.cover_url,
                        topic=None,
                        category=vt.category or "",
                    )
                    cover_tmp_path = payload.cover_path

                    # 获取页面（第一条复用已有 Tab）
                    try:
                        page = browser_svc.new_page(session, reuse_first=(i == 1))
                    except Exception as e:
                        logger.error(f"无法创建 Tab: {e}")
                        pub_svc.fail_publish(item.id, f"浏览器断开: {e}")
                        self._cleanup_cover(cover_tmp_path)
                        continue

                    try:
                        fill_result = publisher.fill_form(page, payload)
                    except Exception as e:
                        fill_result = {"success": False, "error": f"fill异常: {e}"}

                    if fill_result.get("success"):
                        filled.append((item, page, vt, cover_tmp_path))
                        logger.info("  填充完毕")
                    else:
                        err = fill_result.get("error", "")
                        pub_svc.fail_publish(item.id, err)
                        results.append({"success": False, "item_id": item.id, "error": err})
                        logger.warning(f"  填充失败: {err}")
                        self._cleanup_cover(cover_tmp_path)

                    # 任务间随机间隔
                    if i < len(items):
                        time.sleep(random.uniform(5, 10))

                if not filled:
                    logger.info("没有成功填充的条目")
                else:
                    # 打印汇总
                    logger.info(f"\n{'='*60}")
                    logger.info(f"  已填充 {len(filled)} 条，进入逐条确认发布阶段")
                    logger.info(f"{'='*60}")
                    for idx, (item, page, vt, _) in enumerate(filled, 1):
                        logger.info(f"  [{idx}] {(vt.title or '')[:50]}")

                    # ── 阶段2：逐 Tab 串行确认/自动提交 ────────
                    published_urls: set = set()
                    for idx, (item, page, vt, cover_tmp_path) in enumerate(filled, 1):
                        try:
                            try:
                                page.bring_to_front()
                            except Exception:
                                logger.info("  （自动切 Tab 失败，请手动切换）")
                            logger.info(f"\n--- 确认 [{idx}/{len(filled)}] plan_item={item.id} ---")
                            logger.info(f"  标题: {(vt.title or '')[:60]}")

                            pub_svc.start_publish(item.id)

                            if caps.requires_manual_confirm:
                                # 人工确认模式（百家号等）
                                success = wait_confirm("人工点击发布后按 Enter 确认")
                            else:
                                # 自动提交模式（哔哩哔哩等）
                                submit_result = publisher.submit(page)
                                success = submit_result.get("success", False)
                                if not success:
                                    logger.warning(f"  自动提交失败: {submit_result.get('error', '')}")

                            if success:
                                published_url = ""
                                try:
                                    published_url = publisher.fetch_published_url(
                                        page, known_urls=published_urls)
                                    logger.info(f"  已获取发布链接: {published_url}")
                                    if published_url:
                                        published_urls.add(published_url)
                                except Exception as e:
                                    logger.warning(f"  获取链接失败（跳过）: {e}")

                                pub_svc.complete_publish(item.id, published_url)
                                results.append({"success": True, "item_id": item.id,
                                                "url": published_url})

                                if published_url and caps.supports_comment:
                                    pub_svc.create_comment_task(
                                        item, account_id, published_url, vt)
                            else:
                                fail_msg = "人工标记失败" if caps.requires_manual_confirm else "自动提交失败"
                                pub_svc.fail_publish(item.id, fail_msg)
                                results.append({"success": False, "item_id": item.id,
                                                "error": fail_msg})
                                logger.info(f"  已标记失败: {fail_msg}")

                        except Exception as e:
                            logger.error(f"  [确认阶段] 异常: {e}")
                            pub_svc.fail_publish(item.id, f"确认阶段异常: {e}")
                            results.append({"success": False, "item_id": item.id,
                                            "error": str(e)})
                        finally:
                            self._cleanup_cover(cover_tmp_path)

            finally:
                browser_svc.close(session)

            # ── 汇总 + 通知 ───────────────────────────────────
            success_count = sum(1 for r in results if r.get("success"))
            if results and all(r.get("success") for r in results):
                pub_svc.set_plan_status(plan_id, "done")
            logger.info(f"\n发布完成: {success_count}/{len(results)} 成功")

            pub_svc.send_publish_report(
                plan_id, plan.date, account.name or str(account_id), results)

            return {
                "success": success_count > 0,
                "message": f"发布: {success_count}/{len(results)} 成功",
                "results": results,
            }

        finally:
            db.close()

    @staticmethod
    def _cleanup_cover(cover_path: str | None):
        if cover_path:
            try:
                os.unlink(cover_path)
            except Exception:
                pass

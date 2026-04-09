"""任务执行器"""
from typing import Dict, Any
from playwright.sync_api import sync_playwright
from db.database import SessionLocal
from db.repositories import TaskRepository, LogRepository, AccountRepository, VideoRepository
from db.models import TaskStatusEnum, TaskTypeEnum
from plat import get_platform
from utils.anti_risk import AntiRiskStrategy
from conf.settings import settings


class Worker:
    def __init__(self, browser_service):
        self.browser_service = browser_service
        self.anti_risk = AntiRiskStrategy()

    def execute_task(self, task_id: int):
        """执行任务（每次创建独立 session）"""
        db = SessionLocal()

        try:
            task_repo = TaskRepository(db)
            log_repo = LogRepository(db)
            account_repo = AccountRepository(db)
            video_repo = VideoRepository(db)

            task = task_repo.get_by_id(task_id)
            if not task:
                log_repo.create(task_id, "ERROR", f"任务 {task_id} 不存在")
                return

            log_repo.create(task.id, "INFO", f"开始执行任务 {task.id}")

            # 获取账号和视频信息
            account = account_repo.get_by_id(task.account_id)
            video = video_repo.get_by_id(task.video_id)

            if not account or not video:
                raise Exception("账号或视频不存在")

            # 连接浏览器
            with sync_playwright() as p:
                session = self.browser_service.open_browser(account.profile_id, p)
                page = self.browser_service.get_page(account.profile_id, session)

                # 反风控：模拟浏览
                self.anti_risk.simulate_behavior(page)

                # 执行任务
                result = self._execute_by_type(page, task, account, video)

                if result["success"]:
                    task_repo.update_status(task.id, TaskStatusEnum.SUCCESS)
                    log_repo.create(task.id, "INFO", f"任务执行成功: {result.get('message')}")
                else:
                    raise Exception(result.get("error", "未知错误"))

            # 更新浏览器使用时间
            self.browser_service.close_browser(account.profile_id)

        except Exception as e:
            try:
                task_repo = TaskRepository(db)
                log_repo = LogRepository(db)
                task_repo.update_status(task_id, TaskStatusEnum.FAILED, str(e))
                task_repo.increment_retry(task_id)
                log_repo.create(task_id, "ERROR", f"任务执行失败: {e}")
            except:
                pass

        finally:
            db.close()

    def _execute_by_type(self, page, task, account, video) -> Dict[str, Any]:
        """根据任务类型执行"""
        platform_class = get_platform(account.platform)
        platform = platform_class(page)

        if task.task_type == TaskTypeEnum.PUBLISH:
            return platform.upload_video(
                video_path=video.path,
                title=video.title or "默认标题",
                description=video.description or "",
                tags=video.tags or "",
                cover_path=video.cover_path
            )

        elif task.task_type == TaskTypeEnum.COMMENT:
            return platform.comment("精彩内容！")

        elif task.task_type == TaskTypeEnum.LIKE:
            return platform.like()

        else:
            return {"success": False, "error": "不支持的任务类型"}

"""任务调度器"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from db.database import SessionLocal
from db.repositories import TaskRepository, LogRepository
from db.models import TaskStatusEnum
from worker.worker import Worker
from conf.settings import settings


class Scheduler:
    def __init__(self, browser_service):
        self.browser_service = browser_service
        self.max_workers = settings.MAX_CONCURRENT_TASKS
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.worker = Worker(browser_service)
        self._running = False
        self._thread = None

    def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        db = SessionLocal()
        try:
            LogRepository(db).create(0, "INFO", "调度器已启动")
        finally:
            db.close()

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._executor.shutdown(wait=False)

        db = SessionLocal()
        try:
            LogRepository(db).create(0, "INFO", "调度器已停止")
        finally:
            db.close()

    def _run_loop(self):
        """调度循环"""
        while self._running:
            try:
                # 清理过期浏览器
                self.browser_service.cleanup_expired()

                # 获取待执行任务（独立 session）
                db = SessionLocal()
                try:
                    task_repo = TaskRepository(db)
                    tasks = task_repo.get_pending_tasks(limit=self.max_workers)

                    if tasks:
                        log_repo = LogRepository(db)
                        log_repo.create(0, "INFO", f"获取到 {len(tasks)} 个待执行任务")

                        # 标记为 running
                        task_ids = []
                        for task in tasks:
                            task_repo.update_status(task.id, TaskStatusEnum.RUNNING)
                            task_ids.append(task.id)
                finally:
                    db.close()

                # 提交到线程池执行
                if tasks:
                    for tid in task_ids:
                        self._executor.submit(self.worker.execute_task, tid)

            except Exception as e:
                try:
                    db = SessionLocal()
                    LogRepository(db).create(0, "ERROR", f"调度异常: {e}")
                    db.close()
                except:
                    pass

            time.sleep(settings.SCHEDULER_INTERVAL)

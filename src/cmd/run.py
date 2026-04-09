"""
RunCommand - 启动调度器
"""
import time
from cmd import BaseCommand, register_command


@register_command
class RunCommand(BaseCommand):
    command_name = "run"
    command_help = "启动任务调度器"

    def setup_parser(self, parser) -> None:
        pass

    def execute(self, args) -> dict:
        from db.database import init_db
        from service.browser_service import BrowserService
        from scheduler.scheduler import Scheduler
        from conf.settings import settings

        # 初始化数据库
        init_db()

        browser_service = BrowserService(
            pool_size=settings.BROWSER_POOL_SIZE,
            idle_timeout=settings.BROWSER_IDLE_TIMEOUT,
        )

        scheduler = Scheduler(browser_service)
        scheduler.start()

        print("调度器已启动，按 Ctrl+C 停止...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止调度器...")
            scheduler.stop()
            browser_service.shutdown()

        return {"success": True, "message": "调度器已停止"}

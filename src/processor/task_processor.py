"""任务业务处理器"""
from db.database import SessionLocal
from service.task_service import TaskService


class TaskProcessor:
    def list_recent(self, limit: int = 20) -> dict:
        db = SessionLocal()
        try:
            tasks = TaskService(db).list_recent(limit=limit)
            return {"success": True, "tasks": tasks}
        finally:
            db.close()

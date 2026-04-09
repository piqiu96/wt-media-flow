"""任务数据业务"""
from db.repositories import TaskRepository


class TaskService:
    def __init__(self, db):
        self.repo = TaskRepository(db)

    def list_recent(self, limit: int = 20):
        return self.repo.list_recent(limit=limit)

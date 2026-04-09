"""账号数据业务"""
from db.repositories import AccountRepository


class AccountService:
    def __init__(self, db):
        self.repo = AccountRepository(db)

    def add(self, platform: str, username: str, profile_id: str,
            group_id: str = None, daily_limit: int = 3) -> dict:
        if self.repo.get_by_profile_id(profile_id):
            return {"success": False, "message": f"profile_id {profile_id} 已存在"}
        account = self.repo.create(platform, username, profile_id, group_id, daily_limit)
        return {"success": True, "message": f"账号 {username} 添加成功", "id": account.id}

    def list(self):
        return self.repo.list_all()

    def list_active(self):
        return self.repo.get_active_accounts()

"""账号业务处理器"""
from db.database import SessionLocal
from service.account_service import AccountService


class AccountProcessor:
    def add(self, platform: str, username: str, profile_id: str,
            group_id: str = None, daily_limit: int = 3) -> dict:
        db = SessionLocal()
        try:
            return AccountService(db).add(platform, username, profile_id, group_id, daily_limit)
        finally:
            db.close()

    def list(self) -> dict:
        db = SessionLocal()
        try:
            accounts = AccountService(db).list()
            return {"success": True, "accounts": accounts}
        finally:
            db.close()

    def list_active(self) -> dict:
        db = SessionLocal()
        try:
            accounts = AccountService(db).list_active()
            return {"success": True, "accounts": accounts}
        finally:
            db.close()

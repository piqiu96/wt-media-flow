#!/usr/bin/env python3
"""
Example script to create a new user (user_id 4)
"""
from infra.db.database import SessionLocal
from infra.db.repositories import UserRepository

def create_user():
    db = SessionLocal()
    try:
        user_repo = UserRepository(db)
        
        # Create user with ID 4
        user = user_repo.create(
            name="测试用户4",
            username="test_user4",
            role="operator",
            pool="pool-a",
            wecom_id="wecom_user4"
        )
        
        print(f"用户创建成功: id={user.id}, name={user.name}, username={user.username}")
        print(f"这将是 user_id={user.id}")
        
        return user
    finally:
        db.close()

if __name__ == "__main__":
    create_user()

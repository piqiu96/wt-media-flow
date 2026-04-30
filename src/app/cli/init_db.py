"""
InitCommand - 初始化数据库
"""
from app.cli import BaseCommand, register_command


@register_command
class InitCommand(BaseCommand):
    command_name = "init"
    command_help = "初始化数据库"

    def setup_parser(self, parser) -> None:
        pass

    def execute(self, args) -> dict:
        from sqlalchemy import text
        from infra.db.database import init_db, engine

        init_db()
        print("数据库表创建完成")

        # 迁移：为已有 videos 表添加新列
        migrations = [
            "ALTER TABLE videos ADD COLUMN remark TEXT",
            "ALTER TABLE videos ADD COLUMN source_url VARCHAR(1000)",
            "ALTER TABLE videos ADD COLUMN source_platform VARCHAR(50)",
            "ALTER TABLE videos ADD COLUMN source_vid VARCHAR(200)",
            "ALTER TABLE videos ADD COLUMN video_url TEXT",
            "ALTER TABLE videos ADD COLUMN cover_url TEXT",
            "ALTER TABLE videos ADD COLUMN raw_data TEXT",
            "ALTER TABLE videos ADD COLUMN published_at DATETIME",
            "ALTER TABLE videos ADD COLUMN category VARCHAR(50) DEFAULT ''",
            # 热度统计字段
            "ALTER TABLE videos ADD COLUMN like_count INTEGER DEFAULT 0",
            "ALTER TABLE videos ADD COLUMN collect_count INTEGER DEFAULT 0",
            "ALTER TABLE videos ADD COLUMN comment_count INTEGER DEFAULT 0",
            # 清理旧轨表
            "DROP TABLE IF EXISTS task_logs",
            "DROP TABLE IF EXISTS publish_tasks",
            # plan_items 新增 notified 字段
            "ALTER TABLE plan_items ADD COLUMN notified BOOLEAN DEFAULT 0",
            # videos 新增 deleted 字段
            "ALTER TABLE videos ADD COLUMN deleted BOOLEAN DEFAULT 0",
            # videos 新增两阶段采集字段
            "ALTER TABLE videos ADD COLUMN claw_status VARCHAR(20) DEFAULT 'done'",
            "ALTER TABLE videos ADD COLUMN claw_error TEXT",
            "ALTER TABLE videos ADD COLUMN downloaded_at DATETIME",
            # video_tasks 新增 source_vid 冗余字段（用于 source_vid 级去重）
            "ALTER TABLE video_tasks ADD COLUMN source_vid VARCHAR(200)",
            # video_tasks 新增 target_platform 字段（多平台支持）
            "ALTER TABLE video_tasks ADD COLUMN target_platform VARCHAR(50)",
            # plan_items 新增 platform / publish_mode 字段（多平台支持）
            "ALTER TABLE plan_items ADD COLUMN platform VARCHAR(50) DEFAULT 'baijiahao'",
            "ALTER TABLE plan_items ADD COLUMN publish_mode VARCHAR(30) DEFAULT 'manual_confirm'",
            # videos 新增审核状态（默认 approved 保持向后兼容）
            "ALTER TABLE videos ADD COLUMN review_status VARCHAR(20) DEFAULT 'approved'",
            # users 表：运营用户管理
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(100) NOT NULL, username VARCHAR(100) UNIQUE, role VARCHAR(50) DEFAULT 'operator', pool VARCHAR(100), status VARCHAR(20) DEFAULT 'active', wecom_id VARCHAR(100), created_at DATETIME DEFAULT (CURRENT_TIMESTAMP))",
            # accounts 新增 user_id 外键
            "ALTER TABLE accounts ADD COLUMN user_id INTEGER REFERENCES users(id)",
            # publish_plans 新增 user_id 外键
            "ALTER TABLE publish_plans ADD COLUMN user_id INTEGER REFERENCES users(id)",
            # video_tasks 新增 pool 字段（对应 conf/pools/{pool}.json 的 id 字段）
            "ALTER TABLE video_tasks ADD COLUMN pool VARCHAR(100)",
        ]
        with engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # 列已存在
            try:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_videos_source_vid ON videos(source_vid)"
                ))
                conn.commit()
            except Exception:
                pass
            # backfill video_tasks.source_vid（从 videos 表冗余填入）
            try:
                conn.execute(text("""
                    UPDATE video_tasks
                    SET source_vid = (
                        SELECT source_vid FROM videos WHERE videos.id = video_tasks.video_id
                    )
                    WHERE source_vid IS NULL
                """))
                conn.commit()
                print("已 backfill video_tasks.source_vid")
            except Exception as e:
                print(f"backfill 跳过: {e}")

        print("数据库迁移完成")
        return {"success": True, "message": "数据库初始化完成"}

"""
InitCommand - 初始化数据库
"""
from cmd import BaseCommand, register_command


@register_command
class InitCommand(BaseCommand):
    command_name = "init"
    command_help = "初始化数据库"

    def setup_parser(self, parser) -> None:
        pass

    def execute(self, args) -> dict:
        from sqlalchemy import text
        from db.database import init_db, engine

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

        print("数据库迁移完成")
        return {"success": True, "message": "数据库初始化完成"}

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
        from db.database import init_db
        init_db()
        print("数据库初始化完成")
        return {"success": True, "message": "数据库初始化完成"}

"""
TaskCommand - 任务管理（list）
"""
from cmd import BaseCommand, register_command


@register_command
class TaskCommand(BaseCommand):
    command_name = "task"
    command_help = "任务管理（list）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")
        sub.add_parser("list", help="列出所有任务")

    def execute(self, args) -> dict:
        from processor.task_processor import TaskProcessor
        proc = TaskProcessor()
        action = getattr(args, "sub_action", None)

        if action == "list":
            result = proc.list_recent()
            if not result["success"]:
                return result
            tasks = result["tasks"]
            if not tasks:
                print("没有任务")
                return {"success": True, "message": "没有任务"}
            print(f"{'ID':<5} {'账号ID':<10} {'视频ID':<10} {'类型':<10} {'状态':<12} {'调度时间':<20}")
            print("-" * 80)
            for task in tasks:
                schedule_time = task.schedule_time.strftime("%Y-%m-%d %H:%M:%S") if task.schedule_time else "N/A"
                print(f"{task.id:<5} {task.account_id:<10} {task.video_id:<10} "
                      f"{task.task_type.value:<10} {task.status.value:<12} {schedule_time:<20}")
            return {"success": True, "message": f"共 {len(tasks)} 个任务"}
        else:
            print("请指定子命令: task list")
            return {"success": False, "message": "缺少子命令"}

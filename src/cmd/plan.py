"""
PlanCommand - 生成发布计划
"""
from cmd import BaseCommand, register_command


@register_command
class PlanCommand(BaseCommand):
    command_name = "plan"
    command_help = "生成发布计划"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--group", help="分组 ID，不指定则使用所有账号")
        parser.add_argument("--count", type=int, default=100, help="目标任务数量（默认 100）")
        parser.add_argument("--comment", action="store_true", help="包含评论任务")
        parser.add_argument("--like", action="store_true", help="包含点赞任务")

    def execute(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import AccountRepository, VideoRepository, TaskRepository
        from planner.publish_planner import PublishPlanner

        db = SessionLocal()
        try:
            account_repo = AccountRepository(db)
            video_repo = VideoRepository(db)
            task_repo = TaskRepository(db)

            planner = PublishPlanner(account_repo, video_repo, task_repo)
            result = planner.generate_plan(
                group_id=args.group,
                target_count=args.count,
                include_comment=args.comment,
                include_like=args.like,
            )

            if result["success"]:
                print(f"{result['message']}")
                print(f"  发布任务: {result['publish_tasks']}")
                print(f"  评论任务: {result['comment_tasks']}")
                print(f"  点赞任务: {result['like_tasks']}")
            else:
                print(f"生成失败: {result['message']}")
            return result
        except Exception as e:
            print(f"生成计划失败: {e}")
            return {"success": False, "message": str(e)}
        finally:
            db.close()

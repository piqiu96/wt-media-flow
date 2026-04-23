"""
VideoCommand - 视频管理（add / list）
"""
from app.cli import BaseCommand, register_command


@register_command
class VideoCommand(BaseCommand):
    command_name = "video"
    command_help = "视频管理（add / list）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        # video add
        add_p = sub.add_parser("add", help="添加视频")
        add_p.add_argument("--path", required=True, help="视频文件路径")
        add_p.add_argument("--title", help="视频标题")
        add_p.add_argument("--desc", help="视频描述")
        add_p.add_argument("--tags", help="视频标签，逗号分隔")
        add_p.add_argument("--cover", help="封面图片路径")

        # video list
        sub.add_parser("list", help="列出所有视频")

    def execute(self, args) -> dict:
        from infra.db.database import SessionLocal
        from services.video_service import VideoService

        action = getattr(args, "sub_action", None)

        if action == "add":
            db = SessionLocal()
            try:
                svc = VideoService(db)
                result = svc.add(
                    path=args.path,
                    title=args.title,
                    description=getattr(args, "desc", None),
                    cover_path=getattr(args, "cover", None),
                    tags=args.tags,
                )
                print(result["message"])
                return result
            finally:
                db.close()

        elif action == "list":
            db = SessionLocal()
            try:
                svc = VideoService(db)
                videos = svc.list()
                if not videos:
                    print("没有视频")
                    return {"success": True, "message": "没有视频"}
                print(f"{'ID':<5} {'标题':<30} {'路径':<50}")
                print("-" * 85)
                for vid in videos:
                    title = (vid.title or "N/A")[:30]
                    path = vid.path[:50] + "..." if len(vid.path) > 50 else vid.path
                    print(f"{vid.id:<5} {title:<30} {path:<50}")
                return {"success": True, "message": f"共 {len(videos)} 个视频"}
            finally:
                db.close()

        else:
            print("请指定子命令: video add / video list")
            return {"success": False, "message": "缺少子命令"}

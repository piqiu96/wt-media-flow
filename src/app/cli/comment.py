"""
CommentCommand — 评论管理（single / batch / fire）

薄壳：参数解析 + 委托 CommentWorkflow。
"""
from app.cli import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class CommentCommand(BaseCommand):
    command_name = "comment"
    command_help = "评论管理（single 单条 / batch 批量队列）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        sp = sub.add_parser("single", help="打开指定 URL 评论一条")
        sp.add_argument("--account-id", type=int, required=True)
        sp.add_argument("--url", required=True)
        sp.add_argument("--content", required=True)
        sp.add_argument("--wait", type=int, default=120)

        bp = sub.add_parser("batch", help="批量执行 comment_tasks 队列")
        bp.add_argument("--account-id", type=int, required=True)
        bp.add_argument("--limit", type=int, default=20)

        fp = sub.add_parser("fire", help="随机多账号批量全自动评论")
        fp.add_argument("--count", type=int, default=4)
        fp.add_argument("--tasks", type=int, default=0)

    def execute(self, args) -> dict:
        from workflows.comment_workflow import CommentWorkflow

        action = getattr(args, "sub_action", None)
        wf = CommentWorkflow()

        if action == "batch":
            return wf.batch(
                account_id=args.account_id,
                limit=getattr(args, "limit", 20),
            )
        elif action == "fire":
            return wf.fire(
                count=getattr(args, "count", 4),
                max_tasks=getattr(args, "tasks", 0),
            )
        else:
            return wf.single(
                account_id=args.account_id,
                url=args.url,
                content=args.content,
                wait_seconds=getattr(args, "wait", 120),
            )

"""
PlanCommand — 发布计划管理（create / list / run / reset-failed / check / stats）

薄壳：只做参数解析，逻辑委托 workflows。
"""
from app.cli import BaseCommand, register_command


@register_command
class PlanCommand(BaseCommand):
    command_name = "plan"
    command_help = "发布计划管理（create / list / run）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        cp = sub.add_parser("create", help="创建发布计划")
        cp.add_argument("--user-id", type=int, required=True,
                        help="用户 ID（必填），只使用该用户名下绑定了浏览器容器的账号")
        cp.add_argument("--date", default="today", help="计划日期 YYYY-MM-DD，默认 today")
        cp.add_argument("--dry-run", action="store_true", help="仅预览，不写库")

        lp = sub.add_parser("list", help="查看计划列表")
        lp.add_argument("--date", default=None, help="按日期筛选 YYYY-MM-DD")

        rp = sub.add_parser("run", help="执行发布计划（单账号批量）")
        rp.add_argument("--plan-id", type=int, required=True)
        rp.add_argument("--account-id", type=int, required=True)

        rp2 = sub.add_parser("reset-failed", help="将技术性失败条目重置为 PENDING")
        rp2.add_argument("--plan-id", type=int, required=True)
        rp2.add_argument("--account-id", type=int, default=None)

        ck = sub.add_parser("check", help="检查已发布链接过审情况")
        ck.add_argument("--plan-id", type=int, required=True)

        sp = sub.add_parser("stats", help="抓取已发布视频的播放/点赞/评论数")
        sp.add_argument("--plan-id", type=int, default=None, help="按计划 ID 筛选")
        sp.add_argument("--since", type=str, default=None, help="按发布日期筛选 YYYY-MM-DD")

    def execute(self, args) -> dict:
        from workflows.plan_workflow import PlanWorkflow
        from workflows.publish_workflow import PublishWorkflow

        action = getattr(args, "sub_action", None)
        if action == "create":
            return PlanWorkflow().create(
                user_id=args.user_id,
                date=args.date,
                dry_run=getattr(args, "dry_run", False),
            )
        elif action == "list":
            return PlanWorkflow().list_plans(
                date=getattr(args, "date", None),
            )
        elif action == "run":
            return PublishWorkflow().execute(
                plan_id=args.plan_id,
                account_id=args.account_id,
            )
        elif action == "reset-failed":
            return PlanWorkflow().reset_failed(
                plan_id=args.plan_id,
                account_id=getattr(args, "account_id", None),
            )
        elif action == "check":
            return PlanWorkflow().check(plan_id=args.plan_id)
        elif action == "stats":
            from datetime import date
            since_date = date.fromisoformat(args.since) if getattr(args, "since", None) else None
            return PlanWorkflow().stats(
                plan_id=getattr(args, "plan_id", None),
                since_date=since_date,
            )
        else:
            print("请指定子命令: plan create / plan list / plan run")
            return {"success": False, "message": "缺少子命令"}

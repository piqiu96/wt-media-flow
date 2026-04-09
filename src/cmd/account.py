"""
AccountCommand - 账号管理（add / list）
"""
from cmd import BaseCommand, register_command


@register_command
class AccountCommand(BaseCommand):
    command_name = "account"
    command_help = "账号管理（add / list）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")

        # account add
        add_p = sub.add_parser("add", help="添加账号")
        add_p.add_argument("--platform", required=True,
                           choices=["bilibili", "baijiahao", "xiaohongshu"],
                           help="平台名称")
        add_p.add_argument("--username", required=True, help="账号用户名")
        add_p.add_argument("--profile-id", required=True, help="比特浏览器 Profile ID")
        add_p.add_argument("--group", help="分组 ID")
        add_p.add_argument("--daily-limit", type=int, default=3, help="每日发布限制（默认 3）")

        # account list
        sub.add_parser("list", help="列出所有账号")

    def execute(self, args) -> dict:
        from processor.account_processor import AccountProcessor
        proc = AccountProcessor()
        action = getattr(args, "sub_action", None)

        if action == "add":
            result = proc.add(
                platform=args.platform,
                username=args.username,
                profile_id=args.profile_id,
                group_id=args.group,
                daily_limit=args.daily_limit,
            )
            print(result["message"])
            return result
        elif action == "list":
            result = proc.list_active()
            if not result["success"]:
                return result
            accounts = result["accounts"]
            if not accounts:
                print("没有账号")
                return {"success": True, "message": "没有账号"}
            print(f"{'ID':<5} {'平台':<12} {'用户名':<20} {'分组':<15} {'Profile ID':<35} {'每日限制':<10} {'新账号':<8}")
            print("-" * 120)
            for acc in accounts:
                print(f"{acc.id:<5} {acc.platform:<12} {acc.username:<20} "
                      f"{acc.group_id or 'N/A':<15} {acc.profile_id:<35} "
                      f"{acc.daily_limit:<10} {str(acc.is_new):<8}")
            return {"success": True, "message": f"共 {len(accounts)} 个账号"}
        else:
            print("请指定子命令: account add / account list")
            return {"success": False, "message": "缺少子命令"}

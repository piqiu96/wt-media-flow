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
        add_p.add_argument("--browser-id", type=int, required=True,
                           help="比特浏览器容器 ID（对应 browsers 表）")
        add_p.add_argument("--platform", required=True,
                           choices=["bilibili", "baijiahao", "xiaohongshu"],
                           help="平台名称")
        add_p.add_argument("--name", help="账号在平台上的显示名称")
        add_p.add_argument("--username", help="登录用户名（可选）")
        add_p.add_argument("--tag", help="账号类型标签，如 '游戏'")
        add_p.add_argument("--group", help="分组 ID")
        add_p.add_argument("--daily-limit", type=int, default=3, help="每日发布限制（默认 3）")

        # account list
        sub.add_parser("list", help="列出所有账号")

    def execute(self, args) -> dict:
        from db.database import SessionLocal
        from db.repositories import AccountRepository, BrowserRepository

        action = getattr(args, "sub_action", None)

        if action == "add":
            db = SessionLocal()
            try:
                browser_repo = BrowserRepository(db)
                account_repo = AccountRepository(db)

                browser = browser_repo.get_by_id(args.browser_id)
                if not browser:
                    return {"success": False, "message": f"容器不存在: browser_id={args.browser_id}"}

                account = account_repo.create(
                    browser_id=browser.id,
                    profile_id=browser.profile_id,   # 冗余写入
                    platform=args.platform,
                    name=getattr(args, "name", None),
                    username=getattr(args, "username", None),
                    tag=getattr(args, "tag", None),
                    group_id=getattr(args, "group", None),
                    daily_limit=args.daily_limit,
                )
                msg = (f"账号添加成功: id={account.id} "
                       f"[{account.platform}] {account.name or account.username} "
                       f"tag={account.tag} → 容器{browser.seq}({browser.name})")
                print(msg)
                return {"success": True, "message": msg, "account_id": account.id}
            finally:
                db.close()

        elif action == "list":
            db = SessionLocal()
            try:
                accounts = AccountRepository(db).list_all()
                browser_map = {b.id: b for b in __import__(
                    'db.repositories', fromlist=['BrowserRepository']
                ).BrowserRepository(db).list_all()}
                if not accounts:
                    print("没有账号")
                    return {"success": True, "message": "没有账号"}
                print(f"{'ID':<5} {'平台':<12} {'账号名':<20} {'tag':<12} {'用户名':<15} {'容器seq':<8} {'每日限制':<8} {'状态'}")
                print("-" * 100)
                for acc in accounts:
                    b = browser_map.get(acc.browser_id)
                    seq = b.seq if b else "?"
                    print(f"{acc.id:<5} {acc.platform:<12} {(acc.name or ''):<20} "
                          f"{(acc.tag or ''):<12} {(acc.username or ''):<15} "
                          f"{str(seq):<8} {acc.daily_limit:<8} {acc.status}")
                return {"success": True, "message": f"共 {len(accounts)} 个账号"}
            finally:
                db.close()

        else:
            print("请指定子命令: account add / account list")
            return {"success": False, "message": "缺少子命令"}

"""
pack 命令 — 视频打包导出（供运营人工发布）
"""
from app.cli import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class PackCommand(BaseCommand):
    command_name = "pack"
    command_help = "将发布计划的视频+封面打包成 zip，附 AI 优化标题清单"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--plan-id", type=int, required=True,
                            help="发布计划 ID")
        parser.add_argument("--account-id", type=int, default=None,
                            help="只打包指定账号（可选）")
        parser.add_argument("--ai-titles", action="store_true", default=False,
                            help="启用 AI 标题生成（需配置 ANTHROPIC_API_KEY）")

    def execute(self, args) -> dict:
        from workflows.pack_workflow import PackWorkflow
        result = PackWorkflow().pack(
            plan_id=args.plan_id,
            account_id=getattr(args, "account_id", None),
            ai_titles=getattr(args, "ai_titles", False),
        )
        print(result.get("message", ""))
        return result

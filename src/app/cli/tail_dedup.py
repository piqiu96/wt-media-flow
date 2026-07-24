"""
TailDedupCommand — 为成品视频拼接尾部动画去重素材

用法:
  .venv/bin/python3 src/main.py tail-dedup --input-dir data/tmp_video/0702_发财游戏
"""
from app.cli import BaseCommand, register_command
from conf.settings import settings


@register_command
class TailDedupCommand(BaseCommand):
    command_name = "tail-dedup"
    command_help = "为视频拼接尾部动画去重素材（尾插 + 贴纸 + 去重滤镜）"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--input-dir", default="data/tmp_video/0702_发财游戏",
                            help="输入视频目录（默认 data/tmp_video/0702_发财游戏）")
        parser.add_argument("--output-dir", default="data/output/tail_dedup",
                            help="输出目录（默认 data/output/tail_dedup）")
        parser.add_argument("--overlay-dir", default=settings.OVERLAY_DIR,
                            help=f"尾部动画目录（默认 {settings.OVERLAY_DIR}）")
        parser.add_argument("--no-dedup", action="store_true",
                            help="关闭去重滤镜（hue/brightness/unsharp）")
        parser.add_argument("--no-stickers", action="store_true",
                            help="关闭贴纸叠加")
        parser.add_argument("--max-duration", type=float, default=0,
                            help="最大时长（秒），0=不限")

    def execute(self, args) -> dict:
        from workflows.tail_dedup_workflow import TailDedupWorkflow

        wf = TailDedupWorkflow()
        return wf.batch_dedup(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            overlay_dir=args.overlay_dir,
            enable_dedup=not args.no_dedup,
            enable_stickers=not args.no_stickers,
            max_duration=args.max_duration,
        )

"""
PipelineCommand - 全流程命令（下载 → 合成 → 发布）
"""
from cmd import BaseCommand, register_command


@register_command
class PipelineCommand(BaseCommand):
    command_name = "pipeline"
    command_help = "全流程：下载 → 合成 → 发布（可配置步骤）"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--config", required=True,
                            help="Pipeline YAML 配置文件路径（必须）")

    def execute(self, args) -> dict:
        from processor.pipeline_processor import PipelineProcessor

        config = self.load_config(args)
        if not config:
            return {"success": False, "message": "请指定有效的 --config 配置文件"}

        proc = PipelineProcessor()
        return proc.run(config)

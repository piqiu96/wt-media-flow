"""
CompositeCommand - 视频合成命令
"""
import os
from cmd import BaseCommand, register_command
from processor.compositor import VideoCompositor
from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class CompositeCommand(BaseCommand):
    command_name = "composite"
    command_help = "在视频指定位置插入引导视频"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--input", dest="input_path",
                            help="输入视频文件或目录")
        parser.add_argument("--guide", help="引导视频路径")
        parser.add_argument("--insert-at", type=float,
                            help=f"插入位置（秒），默认 {settings.DEFAULT_INSERT_AT}")
        parser.add_argument("--insert-range", type=str,
                            help="自适应插入范围（如 10-15），在范围内找关键帧插入")
        parser.add_argument("--guide-duration", type=float, default=0,
                            help="截取引导视频前 N 秒（默认使用完整引导视频）")
        parser.add_argument("--output", help=f"输出目录（默认 {settings.OUTPUT_DIR}）")
        parser.add_argument("--no-dedup", action="store_true",
                            help="关闭去重处理")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def execute(self, args) -> dict:
        config = self.load_config(args)

        # 合并参数
        input_path = self.merge_args(args, config, "input_path") or config.get("input_dir") or config.get("input_file")
        guide = self.merge_args(args, config, "guide") or config.get("guide_video")
        insert_at = self.merge_args(args, config, "insert_at") or config.get("insert_at", settings.DEFAULT_INSERT_AT)
        guide_duration = self.merge_args(args, config, "guide_duration") or config.get("guide_duration", 0)
        output_dir = self.merge_args(args, config, "output") or config.get("output_dir", settings.OUTPUT_DIR)

        insert_at = float(insert_at)
        guide_duration = float(guide_duration)

        # 去重参数
        no_dedup = getattr(args, "no_dedup", False)
        dedup = not no_dedup and config.get("dedup", True)

        # 自适应插入范围
        insert_range_str = self.merge_args(args, config, "insert_range") or config.get("insert_range")
        insert_range = None
        if insert_range_str:
            try:
                parts = str(insert_range_str).split("-")
                insert_range = (float(parts[0]), float(parts[1]))
            except (ValueError, IndexError):
                logger.warning(f"insert_range 格式错误: {insert_range_str}，应为 '10-15'")

        if not input_path:
            return {"success": False, "message": "请指定 --input（视频文件或目录）"}
        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}

        logger.info(f"引导视频: {guide}")
        if insert_range:
            logger.info(f"插入范围: {insert_range[0]}-{insert_range[1]}s（自适应）")
        else:
            logger.info(f"插入位置: {insert_at}s")
        if guide_duration > 0:
            logger.info(f"引导时长: {guide_duration}s")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"去重: {'开启' if dedup else '关闭'}")

        compositor = VideoCompositor()

        if os.path.isdir(input_path):
            results = compositor.batch_composite(
                input_path, guide, insert_at, output_dir, guide_duration,
                dedup=dedup, insert_range=insert_range
            )
            success_count = sum(1 for r in results if r.get("success"))
            return {
                "success": success_count > 0,
                "message": f"批量合成: {success_count}/{len(results)} 成功",
                "results": results,
            }
        else:
            filename = os.path.basename(input_path)
            output_path = os.path.join(output_dir, filename)

            result = compositor.composite(
                input_path, guide, insert_at, output_path, guide_duration,
                dedup=dedup, insert_range=insert_range
            )
            if result["success"]:
                logger.info(f"合成成功: {result['output_path']}")
            else:
                logger.error(f"合成失败: {result.get('error', '')}")
            return result

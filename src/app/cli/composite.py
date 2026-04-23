"""
CompositeCommand — 视频合成命令

参数解析保持不变，核心合成逻辑委托 CompositeWorkflow。
"""
import os
import random
from app.cli import BaseCommand, register_command
from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class CompositeCommand(BaseCommand):
    command_name = "composite"
    command_help = "在视频指定位置插入引导视频"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--input", dest="input_path", help="输入视频文件或目录")
        parser.add_argument("--vid", help="素材库 source_vid")
        parser.add_argument("--vids", nargs="+", help="多个 source_vid")
        parser.add_argument("--guide", help="引导视频路径")
        parser.add_argument("--insert-at", type=float, help="插入位置（秒）")
        parser.add_argument("--insert-range", type=str, help="自适应插入范围（如 10-15）")
        parser.add_argument("--max-duration", type=float,
                            help=f"最终视频最大时长（秒），默认 {settings.DEFAULT_MAX_DURATION}")
        parser.add_argument("--guide-duration", type=float, default=0,
                            help="截取引导视频前 N 秒")
        parser.add_argument("--output", help=f"输出目录（默认 {settings.OUTPUT_DIR}）")
        parser.add_argument("--no-dedup", action="store_true", help="关闭去重处理")
        parser.add_argument("--workers", type=int, default=1, help="并发数")
        parser.add_argument("--auto-publish", action="store_true", help="合成后自动创建发布任务")
        parser.add_argument("--account-id", type=int, default=None, help="自动发布账号 ID")
        parser.add_argument("--config", help="YAML 配置文件路径")
        parser.add_argument("--recomposite", type=int, metavar="DAYS",
                            help="重新合成最近 N 天视频")
        parser.add_argument("--category", help="品类过滤")

    def _resolve_insert_at(self, args, config) -> tuple[float, tuple | None]:
        insert_range_str = self.merge_args(args, config, "insert_range") or config.get("insert_range")
        user_insert_at = self.merge_args(args, config, "insert_at")

        if insert_range_str:
            try:
                parts = str(insert_range_str).split("-")
                insert_range = (float(parts[0]), float(parts[1]))
                insert_at = float(parts[0])
                return insert_at, insert_range
            except (ValueError, IndexError):
                logger.warning(f"insert_range 格式错误: {insert_range_str}")

        if user_insert_at:
            return float(user_insert_at), None

        default_range = settings.DEFAULT_INSERT_RANGE
        try:
            parts = default_range.split("-")
            min_t, max_t = float(parts[0]), float(parts[1])
            insert_at = round(random.uniform(min_t, max_t), 2)
            logger.info(f"插入位置随机: {insert_at:.2f}s（范围 {min_t}-{max_t}s）")
            return insert_at, None
        except (ValueError, IndexError):
            return settings.DEFAULT_INSERT_AT, None

    def execute(self, args) -> dict:
        from workflows.composite_workflow import CompositeWorkflow
        from infra.media.compositor import VideoCompositor

        config = self.load_config(args)
        wf = CompositeWorkflow()

        # 合并参数
        vid = self.merge_args(args, config, "vid")
        vids = getattr(args, "vids", None) or config.get("vids")
        input_path = self.merge_args(args, config, "input_path") or config.get("input_dir") or config.get("input_file")

        category_for_guide = getattr(args, "category", None) or config.get("category")
        guide_by_cat = config.get("guide_by_category", {})
        if getattr(args, "guide", None):
            guide = args.guide
        elif category_for_guide and category_for_guide in guide_by_cat:
            guide = guide_by_cat[category_for_guide]
        else:
            guide = config.get("guide_video")

        guide_duration = float(self.merge_args(args, config, "guide_duration") or config.get("guide_duration", 0))
        output_dir = self.merge_args(args, config, "output") or config.get("output_dir", settings.OUTPUT_DIR)
        insert_at, insert_range = self._resolve_insert_at(args, config)

        max_duration_val = self.merge_args(args, config, "max_duration")
        max_duration = float(max_duration_val) if max_duration_val is not None else config.get("max_duration", settings.DEFAULT_MAX_DURATION)

        no_dedup = getattr(args, "no_dedup", False)
        dedup = not no_dedup and config.get("dedup", True)
        workers = getattr(args, "workers", 1) or config.get("workers", 1)
        auto_publish = getattr(args, "auto_publish", False) or config.get("auto_publish", False)
        account_id = getattr(args, "account_id", None) or config.get("account_id")

        # --recomposite
        recomposite_days = getattr(args, "recomposite", None)
        if recomposite_days:
            return wf.recomposite_recent(
                days=recomposite_days,
                category=getattr(args, "category", None),
                guide=guide, insert_at=insert_at, output_dir=output_dir,
                guide_duration=guide_duration, dedup=dedup,
                insert_range=insert_range, max_duration=max_duration,
                workers=workers,
            )

        # --vids
        if vids:
            return wf.composite_by_vids(
                vids, guide, insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration,
                workers=workers, auto_publish=auto_publish, account_id=account_id,
            )

        # --vid
        if vid:
            return wf.composite_by_vid(
                vid, guide, insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration,
                auto_publish=auto_publish, account_id=account_id,
            )

        # --input
        if not input_path:
            return {"success": False, "message": "请指定 --input 或 --vid"}
        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}

        logger.info(f"引导视频: {guide}")
        if insert_range:
            logger.info(f"插入范围: {insert_range[0]}-{insert_range[1]}s")
        else:
            logger.info(f"插入位置: {insert_at}s")
        logger.info(f"输出目录: {output_dir}")

        compositor = VideoCompositor()

        if os.path.isdir(input_path):
            results = compositor.batch_composite(
                input_path, guide, insert_at, output_dir, guide_duration,
                dedup=dedup, insert_range=insert_range, max_duration=max_duration
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
                dedup=dedup, insert_range=insert_range, max_duration=max_duration
            )
            if result["success"]:
                logger.info(f"合成成功: {result['output_path']}")
            else:
                logger.error(f"合成失败: {result.get('error', '')}")
            return result

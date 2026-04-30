"""
OverlayCommand — 尾部动画素材采集与切片

子命令：
  overlay fetch   从抖音搜索并下载源视频
  overlay clip    将源视频切成短片
  overlay run     fetch + clip 一步完成（默认）
"""
import yaml
from app.cli import BaseCommand, register_command
from conf.settings import settings


@register_command
class OverlayCommand(BaseCommand):
    command_name = "overlay"
    command_help = "尾部动画素材采集与切片（fetch / clip / run）"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="overlay_action")

        # --- fetch ---
        fp = sub.add_parser("fetch", help="从抖音搜索并下载源视频")
        fp.add_argument("--keywords", nargs="+", help="搜索关键词（覆盖配置文件）")
        fp.add_argument("--category", default="dance",
                        help="素材分类，决定存储子目录（默认 dance）")
        fp.add_argument("--count", type=int, default=10, help="每个关键词获取数量（默认 10）")
        fp.add_argument("--config", help="YAML 配置文件路径（含 overlay_keywords）")

        # --- clip ---
        cp = sub.add_parser("clip", help="将源视频切成若干短片")
        cp.add_argument("--category", default="dance", help="素材分类（默认 dance）")
        cp.add_argument("--clip-duration", type=float, default=5.0,
                        help="每段时长（秒，默认 5）")
        cp.add_argument("--max-clips", type=int, default=5,
                        help="每个源视频最多切几段（默认 5）")
        cp.add_argument("--min-source-duration", type=float, default=10.0,
                        help="源视频最短时长（秒，默认 10）")

        # --- run（fetch + clip）---
        rp = sub.add_parser("run", help="采集 + 切片一步完成")
        rp.add_argument("--keywords", nargs="+", help="搜索关键词（覆盖配置文件）")
        rp.add_argument("--category", default="dance", help="素材分类（默认 dance）")
        rp.add_argument("--count", type=int, default=10, help="每关键词获取数量（默认 10）")
        rp.add_argument("--clip-duration", type=float, default=5.0, help="每段时长（秒）")
        rp.add_argument("--max-clips", type=int, default=5, help="每源文件最多切几段")
        rp.add_argument("--min-source-duration", type=float, default=10.0,
                        help="源视频最短时长（秒）")
        rp.add_argument("--config", help="YAML 配置文件路径")

    def _resolve_keywords(self, args, action: str) -> list[str]:
        """从 CLI 参数或 YAML 配置文件读取关键词"""
        if getattr(args, "keywords", None):
            return args.keywords

        config_path = getattr(args, "config", None)
        if config_path:
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            category = getattr(args, "category", "dance")
            kw_map = cfg.get("overlay_keywords", {})
            if category in kw_map:
                return kw_map[category]
            # 所有品类合并
            merged = []
            for kws in kw_map.values():
                merged.extend(kws)
            return merged

        # 降级：用 category 本身作为关键词
        category = getattr(args, "category", "dance")
        return [category]

    def execute(self, args) -> dict:
        from workflows.overlay_workflow import OverlayWorkflow
        wf = OverlayWorkflow()

        action = getattr(args, "overlay_action", None) or "run"
        category = getattr(args, "category", "dance")

        if action == "fetch":
            keywords = self._resolve_keywords(args, action)
            return wf.fetch(
                keywords=keywords,
                count=getattr(args, "count", 10),
                category=category,
            )

        elif action == "clip":
            return wf.clip(
                category=category,
                clip_duration=getattr(args, "clip_duration", 5.0),
                max_clips=getattr(args, "max_clips", 5),
                min_source_duration=getattr(args, "min_source_duration", 15.0),
            )

        else:  # run
            keywords = self._resolve_keywords(args, action)
            return wf.run(
                keywords=keywords,
                count=getattr(args, "count", 10),
                category=category,
                clip_duration=getattr(args, "clip_duration", 5.0),
                max_clips=getattr(args, "max_clips", 5),
                min_source_duration=getattr(args, "min_source_duration", 15.0),
            )

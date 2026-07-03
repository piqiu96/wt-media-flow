"""
BlendCommand — 实验性画中画融合命令

将 guides 主视频叠到 downloads 底层视频上，主视频结束后继续拼接底层视频剩余部分。
"""
import os
import random
import time
from pathlib import Path

from app.cli import BaseCommand, register_command
from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class BlendCommand(BaseCommand):
    command_name = "blend"
    command_help = "实验性画中画融合：主视频叠底层视频，并拼接底层剩余部分"

    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}

    def setup_parser(self, parser) -> None:
        parser.add_argument("--background", help="底层视频路径（默认从 data/downloads 自动挑横屏视频）")
        parser.add_argument("--main", help="主视频路径（默认从 data/guides 自动挑横屏视频）")
        parser.add_argument("--category", help="按品类限制 guides/downloads 搜索目录")
        parser.add_argument("--background-dir", default=settings.DOWNLOAD_DIR,
                            help=f"底层视频搜索目录（默认 {settings.DOWNLOAD_DIR}）")
        parser.add_argument("--main-dir", default=settings.GUIDE_DIR,
                            help=f"主视频搜索目录（默认 {settings.GUIDE_DIR}）")
        parser.add_argument("--output", help=f"输出文件路径或目录（默认 {settings.OUTPUT_DIR}）")
        parser.add_argument("--canvas", default="auto",
                            help="输出画布，如 1920x1080；默认 auto 跟随底层视频")
        parser.add_argument("--main-width-ratio", type=float, default=0.80,
                            help="画中画宽度占画布宽度比例（默认 0.80）")
        parser.add_argument("--random-style", action="store_true",
                            help="随机使用折中样式参数（广告宽度/背景缩放/模糊/暗层）")
        parser.add_argument("--insert-range", default="10-15",
                            help="画中画随机插入范围，如 10-15（默认）")
        parser.add_argument("--background-zoom", type=float, default=1.12,
                            help="画中画期间底层视频放大倍数（默认 1.12）")
        parser.add_argument("--main-x", type=int,
                            help="画中画左上角 x 坐标（默认居中）")
        parser.add_argument("--main-y", type=int,
                            help="画中画左上角 y 坐标（默认居中）")
        parser.add_argument("--max-duration", type=float, default=0,
                            help="限制最终输出时长，0 表示使用底层视频完整时长")
        parser.add_argument("--blur", action="store_true",
                            help="前段底层视频做模糊/降亮处理")

    def _iter_videos(self, root: str, category: str = ""):
        base = Path(root)
        if category:
            candidates = [base / category]
            candidates.extend(base.glob(f"*/{category}"))
        else:
            candidates = [base]

        seen = set()
        for folder in candidates:
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if path in seen or path.suffix.lower() not in self.VIDEO_EXTENSIONS:
                    continue
                seen.add(path)
                yield str(path)

    def _find_landscape_video(self, root: str, category: str, compositor) -> str:
        videos = list(self._iter_videos(root, category))
        random.shuffle(videos)
        for path in videos:
            try:
                info = compositor.get_video_info(path)
            except Exception as e:
                logger.warning(f"跳过无法探测的视频: {path} ({e})")
                continue
            if info["width"] > info["height"]:
                logger.info(
                    f"自动选择横屏视频: {path} "
                    f"({info['width']}x{info['height']}, {info['duration']:.1f}s)"
                )
                return path
        return ""

    @staticmethod
    def _resolve_insert_at(value: str) -> float:
        try:
            start, end = (float(part) for part in value.split("-", 1))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("--insert-range 格式应为 起始秒-结束秒，例如 10-15")
        if start < 0 or end < start:
            raise ValueError("--insert-range 必须满足 0 <= 起始秒 <= 结束秒")
        return round(random.uniform(start, end), 2)

    @staticmethod
    def _parse_canvas(canvas: str) -> tuple[int, int]:
        try:
            w, h = canvas.lower().split("x", 1)
            return int(w), int(h)
        except (ValueError, AttributeError):
            raise ValueError("--canvas 格式应为 宽x高，例如 1080x1920")

    @staticmethod
    def _resolve_output(output_arg: str, background: str) -> str:
        if output_arg and Path(output_arg).suffix:
            return output_arg

        out_dir = output_arg or settings.OUTPUT_DIR
        ts = time.strftime("%Y%m%d_%H%M%S")
        stem = Path(background).stem[:40]
        return str(Path(out_dir) / f"blend_{ts}_{stem}.mp4")

    def execute(self, args) -> dict:
        from infra.media.compositor import VideoCompositor

        compositor = VideoCompositor()
        category = getattr(args, "category", "") or ""

        background = getattr(args, "background", None)
        if not background:
            background = self._find_landscape_video(args.background_dir, category, compositor)
        if not background:
            return {"success": False, "message": "未找到可用的横屏底层视频，请指定 --background"}

        main = getattr(args, "main", None)
        if not main:
            main = self._find_landscape_video(args.main_dir, category, compositor)
        if not main:
            return {"success": False, "message": "未找到可用的横屏主视频，请指定 --main"}

        if args.canvas == "auto":
            bg_info = compositor.get_video_info(background)
            canvas_w, canvas_h = bg_info["width"], bg_info["height"]
        else:
            canvas_w, canvas_h = self._parse_canvas(args.canvas)
        insert_at = self._resolve_insert_at(args.insert_range)
        main_width_ratio = args.main_width_ratio
        background_zoom = args.background_zoom
        blur_radius = 10
        shade_opacity = 0.28
        if args.random_style:
            main_width_ratio = round(random.uniform(0.82, 0.88), 3)
            background_zoom = round(random.uniform(1.14, 1.22), 3)
            blur_radius = random.randint(4, 7)
            shade_opacity = round(random.uniform(0.18, 0.25), 3)
        output_path = self._resolve_output(getattr(args, "output", None), background)

        logger.info(f"底层视频: {background}")
        logger.info(f"主视频: {main}")
        logger.info(f"随机插入位置: {insert_at:.2f}s（范围 {args.insert_range}s）")
        logger.info(
            f"样式参数: 广告宽度={main_width_ratio:.3f}, "
            f"背景缩放={background_zoom:.3f}, 模糊={blur_radius}, "
            f"底部暗层={shade_opacity:.3f}"
        )
        logger.info(f"输出: {output_path}")

        result = compositor.blend_with_background(
            background_video=background,
            main_video=main,
            output_path=output_path,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            main_width_ratio=main_width_ratio,
            main_x=args.main_x,
            main_y=args.main_y,
            insert_at=insert_at,
            background_zoom=background_zoom,
            background_blur_radius=blur_radius,
            background_shade_opacity=shade_opacity,
            max_duration=args.max_duration,
            background_blur=args.blur,
        )

        if result.get("success"):
            logger.info(f"融合成功: {result['output_path']}")
        else:
            logger.error(f"融合失败: {result.get('error', result.get('message', ''))}")
        return result

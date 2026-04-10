"""
CompositeCommand - 视频合成命令
"""
import os
import random
import re
import requests
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
        parser.add_argument("--vid", help="素材库 source_vid，自动下载远程视频并合成")
        parser.add_argument("--vids", nargs="+", help="多个 source_vid，批量合成")
        parser.add_argument("--guide", help="引导视频路径")
        parser.add_argument("--insert-at", type=float,
                            help="插入位置（秒），不指定则在默认范围内随机")
        parser.add_argument("--insert-range", type=str,
                            help="自适应插入范围（如 10-15），在范围内找关键帧插入")
        parser.add_argument("--max-duration", type=float,
                            help=f"最终视频最大时长（秒），默认 {settings.DEFAULT_MAX_DURATION}，0=不限")
        parser.add_argument("--guide-duration", type=float, default=0,
                            help="截取引导视频前 N 秒（默认使用完整引导视频）")
        parser.add_argument("--output", help=f"输出目录（默认 {settings.OUTPUT_DIR}）")
        parser.add_argument("--no-dedup", action="store_true",
                            help="关闭去重处理")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def _resolve_insert_at(self, args, config) -> tuple[float, tuple | None]:
        """解析 insert_at / insert_range，返回 (insert_at, insert_range)

        优先级：--insert-range > --insert-at > 默认随机范围
        """
        insert_range_str = self.merge_args(args, config, "insert_range") or config.get("insert_range")
        user_insert_at = self.merge_args(args, config, "insert_at")

        # 用户指定了 insert_range
        if insert_range_str:
            try:
                parts = str(insert_range_str).split("-")
                insert_range = (float(parts[0]), float(parts[1]))
                insert_at = float(parts[0])  # 作为 fallback
                return insert_at, insert_range
            except (ValueError, IndexError):
                logger.warning(f"insert_range 格式错误: {insert_range_str}，应为 '10-15'")

        # 用户指定了固定 insert_at
        if user_insert_at:
            return float(user_insert_at), None

        # 都没指定 → 默认随机范围
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
        config = self.load_config(args)

        # 合并参数
        vid = self.merge_args(args, config, "vid")
        vids = getattr(args, "vids", None) or config.get("vids")
        input_path = self.merge_args(args, config, "input_path") or config.get("input_dir") or config.get("input_file")
        guide = self.merge_args(args, config, "guide") or config.get("guide_video")
        guide_duration = self.merge_args(args, config, "guide_duration") or config.get("guide_duration", 0)
        output_dir = self.merge_args(args, config, "output") or config.get("output_dir", settings.OUTPUT_DIR)

        guide_duration = float(guide_duration)

        # insert_at / insert_range 解析
        insert_at, insert_range = self._resolve_insert_at(args, config)

        # max_duration
        max_duration_val = self.merge_args(args, config, "max_duration")
        if max_duration_val is not None:
            max_duration = float(max_duration_val)
        else:
            max_duration = config.get("max_duration", settings.DEFAULT_MAX_DURATION)

        # 去重参数
        no_dedup = getattr(args, "no_dedup", False)
        dedup = not no_dedup and config.get("dedup", True)

        # --vids 批量模式
        if vids:
            return self._composite_by_vids(
                vids, guide, insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration
            )

        # --vid 单个模式
        if vid:
            return self._composite_by_vid(
                vid, guide, insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration
            )

        if not input_path:
            return {"success": False, "message": "请指定 --input（视频文件或目录）或 --vid（素材库 vid）"}
        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}

        logger.info(f"引导视频: {guide}")
        if insert_range:
            logger.info(f"插入范围: {insert_range[0]}-{insert_range[1]}s（自适应）")
        else:
            logger.info(f"插入位置: {insert_at}s")
        if guide_duration > 0:
            logger.info(f"引导时长: {guide_duration}s")
        if max_duration > 0:
            logger.info(f"最大时长: {max_duration}s")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"去重: {'开启' if dedup else '关闭'}")

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

    def _safe_filename(self, title: str, vid: str, max_len: int = 20) -> str:
        """从标题生成安全文件名"""
        if not title:
            return vid
        name = re.sub(r"#\S+", "", title).strip()
        name = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", name).strip()
        name = re.sub(r"\s+", "_", name)
        if not name:
            return vid
        return name[:max_len]

    def _download_video(self, video, vid: str, repo) -> str | None:
        """下载远程视频，返回本地路径，失败返回 None"""
        if video.path and os.path.isfile(video.path):
            print(f"使用本地文件: {video.path}")
            return video.path

        if not video.video_url:
            print(f"  素材 vid={vid} 无远程视频 URL，无法下载")
            return None

        download_dir = settings.DOWNLOAD_DIR
        os.makedirs(download_dir, exist_ok=True)
        filename = f"{vid}.mp4"
        input_path = os.path.join(download_dir, filename)

        if os.path.isfile(input_path):
            print(f"本地已存在: {input_path}")
        else:
            print(f"下载远程视频...")
            try:
                resp = requests.get(video.video_url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT)
                resp.raise_for_status()
                with open(input_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_mb = os.path.getsize(input_path) / 1024 / 1024
                print(f"下载完成: {input_path} ({size_mb:.1f}MB)")
            except Exception as e:
                print(f"  下载失败: {e}")
                return None

        repo.update_path(video.id, input_path)
        return input_path

    def _composite_by_vid(self, vid: str, guide: str,
                          insert_at: float, output_dir: str,
                          guide_duration: float, dedup: bool,
                          insert_range, max_duration: float) -> dict:
        """通过 source_vid 从素材库查询，下载远程视频后合成"""
        from db.database import SessionLocal
        from db.repositories import VideoRepository

        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}

        db = SessionLocal()
        try:
            repo = VideoRepository(db)
            video = repo.get_by_vid(vid)

            if not video:
                return {"success": False, "message": f"素材库中未找到 vid={vid}"}

            title = video.title or ""
            print(f"素材: {title[:60] if title else vid}")

            input_path = self._download_video(video, vid, repo)
            if not input_path:
                return {"success": False, "message": f"素材 vid={vid} 下载失败或无远程 URL"}

            os.makedirs(output_dir, exist_ok=True)
            safe_name = self._safe_filename(title, vid)
            output_path = os.path.join(output_dir, f"{safe_name}.mp4")

            logger.info(f"引导视频: {guide}")
            if insert_range:
                logger.info(f"插入范围: {insert_range[0]}-{insert_range[1]}s（自适应）")
            else:
                logger.info(f"插入位置: {insert_at}s")
            if max_duration > 0:
                logger.info(f"最大时长: {max_duration}s")
            logger.info(f"去重: {'开启' if dedup else '关闭'}")

            compositor = VideoCompositor()
            result = compositor.composite(
                input_path, guide, insert_at, output_path, guide_duration,
                dedup=dedup, insert_range=insert_range, max_duration=max_duration
            )

            if result["success"]:
                logger.info(f"合成成功: {result['output_path']}")
            else:
                logger.error(f"合成失败: {result.get('error', '')}")

            return result

        finally:
            db.close()

    def _composite_by_vids(self, vids: list[str], guide: str,
                           insert_at: float, output_dir: str,
                           guide_duration: float, dedup: bool,
                           insert_range, max_duration: float) -> dict:
        """批量通过 source_vid 下载并合成"""
        from db.database import SessionLocal
        from db.repositories import VideoRepository

        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}

        os.makedirs(output_dir, exist_ok=True)
        compositor = VideoCompositor()

        db = SessionLocal()
        results = []
        try:
            repo = VideoRepository(db)

            for i, vid in enumerate(vids, 1):
                vid = vid.strip()
                print(f"\n--- [{i}/{len(vids)}] vid={vid} ---")

                video = repo.get_by_vid(vid)
                if not video:
                    print(f"  素材库中未找到")
                    results.append({"success": False, "vid": vid, "error": "未找到"})
                    continue

                title = video.title or ""
                print(f"素材: {title[:60] if title else vid}")

                input_path = self._download_video(video, vid, repo)
                if not input_path:
                    results.append({"success": False, "vid": vid, "error": "下载失败"})
                    continue

                safe_name = self._safe_filename(title, vid)
                output_path = os.path.join(output_dir, f"{safe_name}.mp4")

                # 每个视频独立随机 insert_at
                cur_insert_at = insert_at
                if not insert_range and not getattr(self, '_user_fixed_insert', False):
                    try:
                        parts = settings.DEFAULT_INSERT_RANGE.split("-")
                        cur_insert_at = round(random.uniform(float(parts[0]), float(parts[1])), 2)
                    except (ValueError, IndexError):
                        pass

                result = compositor.composite(
                    input_path, guide, cur_insert_at, output_path, guide_duration,
                    dedup=dedup, insert_range=insert_range, max_duration=max_duration
                )
                result["vid"] = vid
                results.append(result)

                status = "成功" if result.get("success") else "失败"
                logger.info(f"  [{i}/{len(vids)}] {status}: {safe_name}")

        finally:
            db.close()

        success_count = sum(1 for r in results if r.get("success"))
        print(f"\n批量合成完成: {success_count}/{len(results)} 成功")
        return {
            "success": success_count > 0,
            "message": f"批量合成: {success_count}/{len(results)} 成功",
            "results": results,
        }

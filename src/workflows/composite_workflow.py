"""
CompositeWorkflow — 视频合成流程编排

从 cmd/composite.py 搬迁核心合成逻辑。
composite 命令逻辑比较自洽（不像 plan 那样混杂浏览器管理），
这里主要是 _composite_by_vid / _composite_by_vids / _recomposite_recent 三个方法。
"""
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


class CompositeWorkflow:
    """视频合成流程"""

    def composite_by_vid(self, vid: str, guide: str,
                         insert_at: float, output_dir: str,
                         guide_duration: float, dedup: bool,
                         insert_range, max_duration: float,
                         auto_publish: bool = False,
                         account_id: int = None,
                         existing_task_id: int = None) -> dict:
        """通过 source_vid 从素材库查询，下载远程视频后合成"""
        from infra.db.database import SessionLocal
        from infra.db.repositories import VideoRepository, VideoTaskRepository
        from infra.media.compositor import VideoCompositor

        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}
        if not os.path.isfile(guide):
            return {"success": False, "message": f"引导视频不存在: {guide}\n请先将引导视频放到该路径，或使用 --guide 指定其他路径"}

        db = SessionLocal()
        try:
            repo = VideoRepository(db)
            vt_repo = VideoTaskRepository(db)

            video = repo.get_by_source_vid("douyin", vid)

            if not video:
                return {"success": False, "message": f"素材库中未找到 vid={vid}"}

            title = video.title or ""
            logger.info(f"素材: {title[:60] if title else vid}")

            # 创建或复用 VideoTask 记录
            if existing_task_id:
                vt = vt_repo.get_by_id(existing_task_id)
                vt.guide_path = guide
                db.commit()
            else:
                vt = vt_repo.create(
                    video_id=video.id,
                    title=video.title,
                    tags=video.tags,
                    cover_url=video.cover_url,
                    video_url=video.video_url,
                    guide_path=guide,
                    category=video.category or "",
                    source_vid=video.source_vid,
                )
            vt_repo.start_composite(vt.id)

            input_path = self._download_video(video, vid, repo)
            if not input_path:
                vt_repo.fail(vt.id, message=f"下载失败：vid={vid} 无远程 URL 或下载出错")
                return {"success": False, "message": f"素材 vid={vid} 下载失败或无远程 URL"}

            output_path = self._build_path(output_dir, video, vid)

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
                out_size_mb = round(os.path.getsize(result["output_path"]) / 1024 / 1024, 1) \
                    if os.path.isfile(result.get("output_path", "")) else None
                vt_repo.complete_composite(
                    vt.id,
                    output_path=result["output_path"],
                    detail_update={"output_size_mb": out_size_mb,
                                   "input_path": input_path},
                )
                logger.info(f"合成成功: {result['output_path']}")

                if auto_publish and account_id:
                    vt_repo.start_publish(vt.id, account_id)
                    logger.info(f"已标记待发布: task_id={vt.id}, account_id={account_id}")
            else:
                vt_repo.fail(
                    vt.id,
                    message=f"合成失败: {result.get('error', '')}",
                    detail_update={"ffmpeg_error": result.get("error")},
                )
                logger.error(f"合成失败: {result.get('error', '')}")

            return result

        finally:
            db.close()

    def composite_by_vids(self, vids: list[str], guide: str,
                          insert_at: float, output_dir: str,
                          guide_duration: float, dedup: bool,
                          insert_range, max_duration: float,
                          workers: int = 1,
                          auto_publish: bool = False,
                          account_id: int = None) -> dict:
        """批量通过 source_vid 下载并合成"""
        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}
        if not os.path.isfile(guide):
            return {"success": False, "message": f"引导视频不存在: {guide}\n请先将引导视频放到该路径，或使用 --guide 指定其他路径"}

        def _do_one(i: int, vid: str) -> dict:
            vid = vid.strip()
            logger.info(f"[{i}/{len(vids)}] vid={vid}")

            cur_insert_at = insert_at
            if not insert_range:
                try:
                    parts = settings.DEFAULT_INSERT_RANGE.split("-")
                    cur_insert_at = round(random.uniform(float(parts[0]), float(parts[1])), 2)
                except (ValueError, IndexError):
                    pass

            result = self.composite_by_vid(
                vid, guide, cur_insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration,
                auto_publish=auto_publish, account_id=account_id,
            )
            result["vid"] = vid
            status = "成功" if result.get("success") else "失败"
            logger.info(f"[{i}/{len(vids)}] {status}: {vid}")
            return result

        results = []
        if workers and workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_do_one, i, vid): vid
                           for i, vid in enumerate(vids, 1)}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        vid = futures[future]
                        logger.error(f"vid={vid} 合成异常: {e}")
                        results.append({"success": False, "vid": vid, "error": str(e)})
        else:
            for i, vid in enumerate(vids, 1):
                results.append(_do_one(i, vid))

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"批量合成完成: {success_count}/{len(results)} 成功")
        return {
            "success": success_count > 0,
            "message": f"批量合成: {success_count}/{len(results)} 成功",
            "results": results,
        }

    def recomposite_recent(self, days: int, category: str,
                           guide: str, insert_at: float, output_dir: str,
                           guide_duration: float, dedup: bool,
                           insert_range, max_duration: float,
                           workers: int = 1) -> dict:
        """重新合成最近 N 天 published_at 的视频"""
        from infra.db.database import SessionLocal
        from infra.db.repositories import VideoTaskRepository
        from infra.db.models import VideoTaskStatusEnum

        if not guide:
            return {"success": False, "message": "请指定 --guide（引导视频路径）"}
        if not os.path.isfile(guide):
            return {"success": False, "message": f"引导视频不存在: {guide}\n请先将引导视频放到该路径，或使用 --guide 指定其他路径"}

        db = SessionLocal()
        try:
            vt_repo = VideoTaskRepository(db)
            pairs = vt_repo.get_videos_for_recomposite(days=days, category=category)
        finally:
            db.close()

        if not pairs:
            msg = f"最近 {days} 天内无符合条件的视频"
            if category:
                msg += f"（品类: {category}）"
            logger.info(msg)
            return {"success": True, "message": msg, "results": []}

        cat_label = f" [{category}]" if category else ""
        logger.info(f"找到 {len(pairs)} 条视频（最近 {days} 天 published_at{cat_label}），开始重新合成...")

        skip_count = 0
        todo_vids = []

        for video, task in pairs:
            vid = video.source_vid
            if task is None:
                todo_vids.append((vid, None))
                continue

            if task.status == VideoTaskStatusEnum.COMPOSITING:
                logger.info(f"[跳过] vid={vid} 合成中（task_id={task.id}）")
                skip_count += 1
                continue

            db2 = SessionLocal()
            try:
                vt_repo2 = VideoTaskRepository(db2)
                referenced = vt_repo2.is_referenced_by_active_plan(task.id)
                if referenced:
                    logger.info(f"[跳过] vid={vid} 已在发布计划中（task_id={task.id}）")
                    skip_count += 1
                    continue
                vt_repo2.reset_for_recomposite(task.id)
            finally:
                db2.close()

            todo_vids.append((vid, task.id))

        if not todo_vids:
            return {"success": True, "message": f"全部 {skip_count} 条视频已跳过", "results": []}

        logger.info(f"将重新合成 {len(todo_vids)} 条，跳过 {skip_count} 条")

        def _do_one(i: int, vid: str, existing_task_id) -> dict:
            logger.info(f"[{i}/{len(todo_vids)}] vid={vid}")
            cur_insert_at = insert_at
            if not insert_range:
                try:
                    parts = settings.DEFAULT_INSERT_RANGE.split("-")
                    cur_insert_at = round(random.uniform(float(parts[0]), float(parts[1])), 2)
                except (ValueError, IndexError):
                    pass
            result = self.composite_by_vid(
                vid, guide, cur_insert_at, output_dir, guide_duration,
                dedup, insert_range, max_duration,
                existing_task_id=existing_task_id,
            )
            result["vid"] = vid
            status = "成功" if result.get("success") else "失败"
            logger.info(f"[{i}/{len(todo_vids)}] {status}: {vid}")
            return result

        results = []
        if workers and workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_do_one, i, vid, tid): vid
                           for i, (vid, tid) in enumerate(todo_vids, 1)}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        vid = futures[future]
                        logger.error(f"vid={vid} 合成异常: {e}")
                        results.append({"success": False, "vid": vid, "error": str(e)})
        else:
            for i, (vid, tid) in enumerate(todo_vids, 1):
                results.append(_do_one(i, vid, tid))

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"重新合成完成: {success_count}/{len(results)} 成功，{skip_count} 条跳过")
        return {
            "success": success_count > 0,
            "message": f"重新合成: {success_count}/{len(results)} 成功，{skip_count} 条跳过",
            "results": results,
        }

    # ── 内部辅助方法 ──────────────────────────────────────────

    @staticmethod
    def _safe_filename(title: str, vid: str, max_len: int = 50) -> str:
        if not title:
            return vid
        name = re.sub(r"#\S+", "", title).strip()
        name = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", name).strip()
        name = re.sub(r"\s+", "_", name)
        if not name:
            return vid
        return name[:max_len]

    def _build_path(self, base_dir: str, video, vid: str) -> str:
        date_str = video.created_at.strftime("%Y-%m-%d") if video.created_at else datetime.now().strftime("%Y-%m-%d")
        category = video.category if video.category else "未分类"
        safe_title = self._safe_filename(video.title, vid)
        filename = f"{vid}_{safe_title}.mp4"
        path = os.path.join(base_dir, date_str, category, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _download_video(self, video, vid: str, repo) -> str | None:
        import requests

        if video.path and os.path.isfile(video.path):
            logger.info(f"使用本地文件: {video.path}")
            return video.path

        if not video.video_url:
            logger.warning(f"素材 vid={vid} 无远程视频 URL，无法下载")
            return None

        input_path = self._build_path(settings.DOWNLOAD_DIR, video, vid)

        if os.path.isfile(input_path):
            logger.info(f"本地已存在: {input_path}")
        else:
            logger.info("下载远程视频...")
            try:
                resp = requests.get(video.video_url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT)
                resp.raise_for_status()
                with open(input_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_mb = os.path.getsize(input_path) / 1024 / 1024
                logger.info(f"下载完成: {input_path} ({size_mb:.1f}MB)")
            except Exception as e:
                logger.error(f"下载失败: {e}")
                return None

        repo.update_path(video.id, input_path)
        return input_path

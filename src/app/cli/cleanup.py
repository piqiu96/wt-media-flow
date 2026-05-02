"""
CleanupCommand - 清理过期视频文件
"""
import os
from app.cli import BaseCommand, register_command
from utils.log import get_logger

logger = get_logger(__name__)


@register_command
class CleanupCommand(BaseCommand):
    command_name = "cleanup"
    command_help = "删除过期视频的磁盘文件并标记数据库"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--days", type=int, default=5,
                            help="published_at 在 N 天前之前的视频视为过期（默认 5）")
        parser.add_argument("--dry-run", action="store_true",
                            help="预览模式，不实际删除")

    def execute(self, args) -> dict:
        from infra.db.database import SessionLocal
        from infra.db.repositories import VideoRepository, VideoTaskRepository, PlanItemRepository

        days = args.days
        dry_run = args.dry_run

        db = SessionLocal()
        try:
            videos = VideoRepository(db).get_expired_for_cleanup(days=days)
        finally:
            db.close()

        if not videos:
            msg = f"无过期视频（published_at 在 {days} 天前之前）"
            print(msg)
            return {"success": True, "message": msg}

        print(f"找到 {len(videos)} 条过期视频（published_at 在 {days} 天前之前）"
              + ("  【预览模式，不实际删除】" if dry_run else ""))
        print()

        # ── 阶段一：级联处理合成产物（video_tasks + plan_items） ──────────────
        print("── 阶段一：合成产物 ──")
        tasks_deleted = 0
        tasks_mb = 0.0

        for video in videos:
            vid = video.source_vid or str(video.id)

            db2 = SessionLocal()
            try:
                tasks = VideoTaskRepository(db2).get_all_by_video_id(video.id)
            finally:
                db2.close()

            for task in tasks:
                path = task.output_path
                size_mb = 0.0
                if path and os.path.isfile(path):
                    size_mb = os.path.getsize(path) / 1024 / 1024
                    tasks_mb += size_mb

                if dry_run:
                    print(f"  [预览] task_id={task.id}  vid={vid}  {size_mb:.1f}MB  {path or '(无路径)'}")
                    tasks_deleted += 1
                    continue

                if path and os.path.isfile(path):
                    try:
                        os.remove(path)
                        print(f"  [删除] task_id={task.id}  vid={vid}  ({size_mb:.1f}MB)  {path}")
                    except Exception as e:
                        logger.error(f"合成产物删除失败 {path}: {e}")
                        continue
                else:
                    print(f"  [标记] task_id={task.id}  vid={vid}  文件不存在，仅标记数据库")

                db3 = SessionLocal()
                try:
                    PlanItemRepository(db3).fail_pending_by_task(task.id)
                    VideoTaskRepository(db3).mark_output_expired(task.id)
                finally:
                    db3.close()

                tasks_deleted += 1

        # ── 阶段二：删除原始下载（videos） ──────────────────────────────────
        print("\n── 阶段二：原始下载 ──")
        deleted_count = 0
        skipped_count = 0
        src_mb = 0.0

        for video in videos:
            vid = video.source_vid or str(video.id)
            path = video.path
            pub_at = video.published_at.strftime("%Y-%m-%d %H:%M") if video.published_at else "未知"

            size_mb = 0.0
            if path and os.path.isfile(path):
                size_mb = os.path.getsize(path) / 1024 / 1024
                src_mb += size_mb

            if dry_run:
                title = (video.title or "")[:30]
                print(f"  [预览] {pub_at}  {size_mb:.1f}MB  {title}  {path}")
                deleted_count += 1
                continue

            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                    print(f"  [删除] vid={vid}  ({size_mb:.1f}MB)  {path}")
                except Exception as e:
                    logger.error(f"原始文件删除失败 {path}: {e}")
                    skipped_count += 1
                    continue
            else:
                print(f"  [标记] vid={vid} 文件不存在，仅标记数据库")

            db2 = SessionLocal()
            try:
                VideoRepository(db2).mark_deleted(video.id)
            finally:
                db2.close()

            deleted_count += 1

        total_mb = tasks_mb + src_mb
        action = "预览" if dry_run else "删除"
        msg = (f"{action}完成: 合成产物 {tasks_deleted} 条({tasks_mb:.1f}MB)，"
               f"原始下载 {deleted_count} 条({src_mb:.1f}MB)，"
               f"合计释放 {total_mb:.1f}MB"
               + (f"，跳过 {skipped_count} 条" if skipped_count else ""))
        print(f"\n{msg}")
        return {"success": True, "message": msg,
                "tasks_deleted": tasks_deleted, "deleted": deleted_count,
                "skipped": skipped_count, "freed_mb": round(total_mb, 1)}

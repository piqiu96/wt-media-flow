"""只读诊断命令。"""
from app.cli import BaseCommand, register_command


@register_command
class DiagnoseCommand(BaseCommand):
    command_name = "diagnose"
    command_help = "只读诊断数据库中的重复和状态异常"

    def setup_parser(self, parser) -> None:
        sub = parser.add_subparsers(dest="sub_action")
        dedup = sub.add_parser("dedup", help="检查视频采集、合成、计划去重状态")
        dedup.add_argument("--limit", type=int, default=20, help="每类最多输出条数")

    def execute(self, args) -> dict:
        action = getattr(args, "sub_action", None)
        if action != "dedup":
            print("请指定子命令: diagnose dedup")
            return {"success": False, "message": "缺少子命令"}

        from infra.db.database import SessionLocal
        from sqlalchemy import text

        limit = getattr(args, "limit", 20) or 20
        db = SessionLocal()
        try:
            reports = [
                (
                    "videos 重复 source_platform + source_vid",
                    """
                    SELECT source_platform, source_vid, COUNT(*) AS count,
                           GROUP_CONCAT(id) AS ids
                    FROM videos
                    WHERE COALESCE(source_vid, '') != ''
                    GROUP BY source_platform, source_vid
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                    LIMIT :limit
                    """,
                ),
                (
                    "video_tasks 重复 source_vid",
                    """
                    SELECT source_vid, COUNT(*) AS count,
                           GROUP_CONCAT(id) AS task_ids,
                           GROUP_CONCAT(status) AS statuses
                    FROM video_tasks
                    WHERE COALESCE(source_vid, '') != ''
                    GROUP BY source_vid
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                    LIMIT :limit
                    """,
                ),
                (
                    "plan_items 重复 platform + source_vid",
                    """
                    SELECT pi.platform, vt.source_vid, COUNT(*) AS count,
                           GROUP_CONCAT(pi.id) AS item_ids,
                           GROUP_CONCAT(pi.plan_id) AS plan_ids,
                           GROUP_CONCAT(pi.publish_status) AS statuses
                    FROM plan_items pi
                    JOIN video_tasks vt ON vt.id = pi.video_task_id
                    WHERE COALESCE(vt.source_vid, '') != ''
                    GROUP BY pi.platform, vt.source_vid
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                    LIMIT :limit
                    """,
                ),
            ]

            total_findings = 0
            for title, sql in reports:
                rows = db.execute(text(sql), {"limit": limit}).mappings().all()
                total_findings += len(rows)
                print(f"\n## {title}")
                if not rows:
                    print("无")
                    continue
                for row in rows:
                    print(dict(row))

            abnormal_sql = text(
                """
                SELECT
                    SUM(CASE WHEN LOWER(claw_status) = 'done'
                              AND COALESCE(path, '') = '' THEN 1 ELSE 0 END) AS done_without_path,
                    SUM(CASE WHEN LOWER(claw_status) = 'pending'
                              AND COALESCE(path, '') != '' THEN 1 ELSE 0 END) AS pending_with_path
                FROM videos
                """
            )
            abnormal = db.execute(abnormal_sql).mappings().first()
            print("\n## 下载状态异常")
            print(dict(abnormal or {}))
            total_findings += (abnormal or {}).get("done_without_path") or 0
            total_findings += (abnormal or {}).get("pending_with_path") or 0

            return {
                "success": True,
                "message": f"诊断完成，发现 {total_findings} 类/条异常结果",
                "findings": total_findings,
            }
        finally:
            db.close()

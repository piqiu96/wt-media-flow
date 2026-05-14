import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from infra.db.models import (  # noqa: E402
    Account,
    Base,
    Browser,
    ClawStatusEnum,
    PublishPlan,
    PlanItem,
    PlanItemStatusEnum,
    User,
    Video,
    VideoTask,
    VideoTaskStatusEnum,
)
from infra.db.repositories import VideoRepository, VideoTaskRepository  # noqa: E402


class DedupeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.tmp.cleanup()

    def _video(self, db, source_vid="vid-1", category="", path=""):
        video = Video(
            path=path,
            title=f"title-{source_vid}",
            category=category,
            source_platform="douyin",
            source_vid=source_vid,
            video_url="https://example.invalid/video.mp4",
            claw_status=ClawStatusEnum.DONE if path else ClawStatusEnum.PENDING,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return video

    def test_claw_ingest_skips_duplicate_source_vid(self):
        from workflows.claw_workflow import ClawWorkflow

        items = [
            {"vid": "same-vid", "title": "first", "raw_data": {}, "statistics": {}},
            {"vid": "same-vid", "title": "second", "raw_data": {}, "statistics": {}},
        ]
        with patch("workflows.claw_workflow.SessionLocal", self.SessionLocal):
            result = ClawWorkflow().ingest(items, platform="douyin", category="三角洲")

        db = self.SessionLocal()
        try:
            count = db.query(Video).filter(Video.source_vid == "same-vid").count()
        finally:
            db.close()

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(count, 1)

    def test_download_pending_only_marks_pending_done(self):
        db = self.SessionLocal()
        try:
            pending = self._video(db, source_vid="pending")
            done = self._video(db, source_vid="done", path="/tmp/done.mp4")
            repo = VideoRepository(db)
            rows = repo.get_pending_claw()
            self.assertEqual([v.source_vid for v in rows], ["pending"])
            repo.mark_claw_done(pending.id, "/tmp/pending.mp4")
            db.refresh(pending)
            db.refresh(done)
            self.assertEqual(pending.claw_status, "done")
            self.assertEqual(done.claw_status, "done")
        finally:
            db.close()

    def test_composite_existing_composited_task_is_skipped(self):
        from workflows.composite_workflow import CompositeWorkflow

        guide = os.path.join(self.tmp.name, "guide.mp4")
        Path(guide).write_bytes(b"guide")
        input_path = os.path.join(self.tmp.name, "input.mp4")
        Path(input_path).write_bytes(b"video")

        db = self.SessionLocal()
        try:
            video = self._video(db, source_vid="dup-vid", path=input_path)
            task = VideoTask(
                video_id=video.id,
                title=video.title,
                source_vid=video.source_vid,
                status=VideoTaskStatusEnum.COMPOSITED,
                output_path="/tmp/out.mp4",
            )
            db.add(task)
            db.commit()
            task_id = task.id
        finally:
            db.close()

        with patch("infra.db.database.SessionLocal", self.SessionLocal), \
             patch("infra.media.compositor.VideoCompositor") as compositor_cls:
            result = CompositeWorkflow().composite_by_vid(
                "dup-vid", guide, 10, self.tmp.name, 0, True, None, 180
            )

        db = self.SessionLocal()
        try:
            task_count = db.query(VideoTask).filter(VideoTask.source_vid == "dup-vid").count()
        finally:
            db.close()

        self.assertTrue(result["success"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["task_id"], task_id)
        self.assertEqual(task_count, 1)
        compositor_cls.assert_not_called()

    def test_composite_existing_failed_task_allows_new_attempt(self):
        from workflows.composite_workflow import CompositeWorkflow

        guide = os.path.join(self.tmp.name, "guide.mp4")
        Path(guide).write_bytes(b"guide")
        input_path = os.path.join(self.tmp.name, "input.mp4")
        Path(input_path).write_bytes(b"video")
        output_path = os.path.join(self.tmp.name, "out.mp4")
        Path(output_path).write_bytes(b"out")

        db = self.SessionLocal()
        try:
            video = self._video(db, source_vid="retry-vid", path=input_path)
            db.add(VideoTask(
                video_id=video.id,
                title=video.title,
                source_vid=video.source_vid,
                status=VideoTaskStatusEnum.FAILED,
            ))
            db.commit()
        finally:
            db.close()

        with patch("infra.db.database.SessionLocal", self.SessionLocal), \
             patch("infra.media.compositor.VideoCompositor") as compositor_cls:
            compositor_cls.return_value.composite.return_value = {
                "success": True,
                "output_path": output_path,
            }
            result = CompositeWorkflow().composite_by_vid(
                "retry-vid", guide, 10, self.tmp.name, 0, True, None, 180
            )

        db = self.SessionLocal()
        try:
            tasks = db.query(VideoTask).filter(VideoTask.source_vid == "retry-vid").all()
            statuses = sorted(str(t.status) for t in tasks)
        finally:
            db.close()

        self.assertTrue(result["success"])
        self.assertEqual(len(tasks), 2)
        self.assertIn("VideoTaskStatusEnum.COMPOSITED", statuses)
        self.assertIn("VideoTaskStatusEnum.FAILED", statuses)

    def test_repository_finds_latest_non_failed_source_vid(self):
        db = self.SessionLocal()
        try:
            video = self._video(db, source_vid="lookup")
            failed = VideoTask(
                video_id=video.id,
                source_vid="lookup",
                status=VideoTaskStatusEnum.FAILED,
            )
            composited = VideoTask(
                video_id=video.id,
                source_vid="lookup",
                status=VideoTaskStatusEnum.COMPOSITED,
            )
            db.add_all([failed, composited])
            db.commit()
            found = VideoTaskRepository(db).get_latest_non_failed_by_source_vid("lookup")
            self.assertEqual(found.id, composited.id)
        finally:
            db.close()

    def test_plan_create_dedupes_same_platform_but_allows_cross_platform(self):
        from workflows.plan_workflow import PlanWorkflow

        db = self.SessionLocal()
        try:
            user = User(name="operator")
            browser = Browser(profile_id="profile-1")
            db.add_all([user, browser])
            db.commit()
            db.refresh(user)
            db.refresh(browser)

            baijiahao = Account(
                browser_id=browser.id,
                platform="baijiahao",
                name="baijiahao",
                user_id=user.id,
                daily_limit=5,
                status="active",
            )
            bilibili = Account(
                browser_id=browser.id,
                platform="bilibili",
                name="bilibili",
                user_id=user.id,
                daily_limit=5,
                status="active",
            )
            db.add_all([baijiahao, bilibili])
            db.commit()

            video_a = self._video(db, source_vid="same-source")
            video_b = self._video(db, source_vid="same-source")
            video_c = self._video(db, source_vid="unique-source")
            db.add_all([
                VideoTask(video_id=video_a.id, source_vid="same-source", status=VideoTaskStatusEnum.COMPOSITED),
                VideoTask(video_id=video_b.id, source_vid="same-source", status=VideoTaskStatusEnum.COMPOSITED),
                VideoTask(video_id=video_c.id, source_vid="unique-source", status=VideoTaskStatusEnum.COMPOSITED),
            ])
            db.commit()
            user_id = user.id
        finally:
            db.close()

        with patch("infra.db.database.SessionLocal", self.SessionLocal):
            result = PlanWorkflow().create(user_id=user_id, date=str(date.today()), dry_run=False)

        self.assertTrue(result["success"])

        db = self.SessionLocal()
        try:
            rows = (
                db.query(PlanItem.platform, VideoTask.source_vid)
                .join(VideoTask, VideoTask.id == PlanItem.video_task_id)
                .all()
            )
            counts = {}
            for platform, source_vid in rows:
                counts[(platform, source_vid)] = counts.get((platform, source_vid), 0) + 1
            plans = db.query(PublishPlan).count()
        finally:
            db.close()

        self.assertEqual(plans, 1)
        self.assertEqual(counts[("baijiahao", "same-source")], 1)
        self.assertEqual(counts[("bilibili", "same-source")], 1)
        self.assertLessEqual(max(counts.values()), 1)


if __name__ == "__main__":
    unittest.main()

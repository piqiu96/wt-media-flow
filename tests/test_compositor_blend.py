import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from infra.media.compositor import VideoCompositor  # noqa: E402


class CompositorBlendTestCase(unittest.TestCase):
    def test_blend_builds_blurred_scaled_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / "background.mp4"
            main = Path(tmp) / "guide.mp4"
            output = Path(tmp) / "output.mp4"
            background.touch()
            main.touch()

            compositor = VideoCompositor()
            infos = [
                {"duration": 30.0, "fps": 30.0, "sample_rate": 44100},
                {"duration": 5.0, "fps": 30.0, "sample_rate": 44100},
            ]
            with patch.object(compositor, "get_video_info", side_effect=infos), \
                 patch("infra.media.compositor.subprocess.run") as run:
                run.return_value.returncode = 0
                result = compositor.blend_with_background(
                    str(background),
                    str(main),
                    str(output),
                    insert_at=10,
                    background_blur=True,
                )

            self.assertTrue(result["success"])
            command = run.call_args.args[0]
            filters = command[command.index("-filter_complex") + 1]
            self.assertIn("boxblur=7:1", filters)
            self.assertIn("scale=1440:972:force_original_aspect_ratio=decrease", filters)
            self.assertIn("overlay=(W-w)/2:(H-h)/2", filters)
            self.assertIn("[0:v]trim=10.000:30.000", filters)
            self.assertEqual(result["final_duration"], 35.0)

    def test_blend_uses_scene_point_from_insert_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            background = Path(tmp) / "background.mp4"
            main = Path(tmp) / "guide.mp4"
            output = Path(tmp) / "output.mp4"
            background.touch()
            main.touch()

            compositor = VideoCompositor()
            infos = [
                {"duration": 30.0, "fps": 30.0, "sample_rate": 44100},
                {"duration": 5.0, "fps": 30.0, "sample_rate": 44100},
            ]
            with patch.object(compositor, "get_video_info", side_effect=infos), \
                 patch("infra.media.compositor.SceneDetector") as detector, \
                 patch("infra.media.compositor.subprocess.run") as run:
                detector.return_value.find_insert_point.return_value = 13.25
                run.return_value.returncode = 0
                result = compositor.blend_with_background(
                    str(background),
                    str(main),
                    str(output),
                    insert_range=(10.0, 15.0),
                )

            self.assertEqual(result["insert_at"], 13.25)
            detector.return_value.find_insert_point.assert_called_once_with(
                str(background), 10.0, 15.0, 30.0
            )


if __name__ == "__main__":
    unittest.main()

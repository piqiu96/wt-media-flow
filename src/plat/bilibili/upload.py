import time
import random
from ..base import BasePlatform
from typing import Optional, Dict, Any

class BilibiliPlatform(BasePlatform):
    platform_name = "bilibili"

    def upload_video(self, video_path: str, title: str,
                    description: str = "", tags: str = "",
                    cover_path: Optional[str] = None) -> Dict[str, Any]:
        try:
            # 1. 进入上传页面
            self.page.goto("https://member.bilibili.com/platform/upload/video/frame")
            self.page.wait_for_load_state("networkidle")
            time.sleep(random.uniform(2, 4))

            # 2. 上传视频
            with self.page.expect_file_chooser(timeout=10000) as fc_info:
                self.page.click("text=上传视频")
            file_chooser = fc_info.value
            file_chooser.set_files(video_path)

            print("等待视频上传完成...")
            self.wait_for_upload()
            time.sleep(random.uniform(2, 4))

            # 3. 填写标题
            self.page.fill("#title", title)
            time.sleep(random.uniform(0.5, 1))

            # 4. 填写简介
            self.page.fill("#desc", description)
            time.sleep(random.uniform(0.5, 1))

            # 5. 填写标签（根据B站实际选择器调整）
            if tags:
                tag_list = [t.strip() for t in tags.split(",")]
                for tag in tag_list[:5]:  # 最多5个标签
                    self.page.click(".tag-input")
                    self.page.keyboard.type(tag)
                    time.sleep(random.uniform(0.3, 0.6))
                    self.page.keyboard.press("Enter")

            # 6. 上传封面（可选）
            if cover_path:
                with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    self.page.click(".cover-upload")
                fc_info.value.set_files(cover_path)

            # 7. 随机滚动
            self.page.mouse.wheel(0, random.randint(100, 300))
            time.sleep(random.uniform(1, 2))

            # 8. 发布（注意：实际发布可能需要手动确认）
            return {"success": True, "message": "填写完成，请手动确认发布"}

        except Exception as e:
            return {"success": False, "error": str(e)}

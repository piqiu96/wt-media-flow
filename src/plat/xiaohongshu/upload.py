import time
import random
from ..base import BasePlatform
from typing import Optional, Dict, Any

class XiaohongshuPlatform(BasePlatform):
    platform_name = "xiaohongshu"

    def upload_video(self, video_path: str, title: str,
                    description: str = "", tags: str = "",
                    cover_path: Optional[str] = None) -> Dict[str, Any]:
        try:
            # 1. 进入小红书创作者中心
            self.page.goto("https://creator.xiaohongshu.com/publish/publish")
            self.page.wait_for_load_state("networkidle")
            time.sleep(random.uniform(2, 4))

            # 2. 检查登录
            print("请确认已登录小红书账号...")
            time.sleep(2)

            # 3. 上传视频
            upload_area = self.page.locator("text=上传视频, .upload-area").first
            with self.page.expect_file_chooser(timeout=10000) as fc_info:
                upload_area.click()
            fc_info.value.set_files(video_path)

            print("等待视频上传完成...")
            self.wait_for_upload()
            time.sleep(random.uniform(2, 4))

            # 4. 填写标题
            self.page.fill('input[placeholder*="标题"], .title-input', title)
            time.sleep(random.uniform(0.5, 1))

            # 5. 填写描述
            self.page.click('div[contenteditable="true"], textarea')
            self.page.keyboard.type(description)
            time.sleep(random.uniform(0.5, 1))

            # 6. 上传封面
            if cover_path:
                cover_area = self.page.locator(".cover-upload, text=上传封面").first
                with self.page.expect_file_chooser(timeout=10000) as fc_info:
                    cover_area.click()
                fc_info.value.set_files(cover_path)

            # 7. 添加标签
            if tags:
                tag_list = [tag.strip() for tag in tags.split(",")]
                tags_text = " ".join([f"#{tag}" for tag in tag_list])
                self.page.click('div[contenteditable="true"]')
                self.page.keyboard.press("End")
                for char in tags_text:
                    self.page.keyboard.type(char, delay=random.randint(20, 60))

            # 8. 随机滚动
            self.page.mouse.wheel(0, random.randint(100, 300))
            time.sleep(random.uniform(1, 2))

            return {"success": True, "message": "填写完成，请手动确认发布"}

        except Exception as e:
            return {"success": False, "error": str(e)}

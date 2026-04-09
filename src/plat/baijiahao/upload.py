import time
import random
from ..base import BasePlatform
from typing import Optional, Dict, Any

class BaijiahaoPlatform(BasePlatform):
    platform_name = "baijiahao"

    def upload_video(self, video_path: str, title: str,
                    description: str = "", tags: str = "",
                    cover_path: Optional[str] = None) -> Dict[str, Any]:
        try:
            # 1. 进入百家号发布页面
            self.page.goto("https://baijiahao.baidu.com/builder/rc/edit?type=videoV2")
            self.page.wait_for_load_state("networkidle")
            time.sleep(random.uniform(2, 4))

            # 2. 上传视频
            with self.page.expect_file_chooser(timeout=10000) as fc_info:
                self.page.click(".upload-area")
            fc_info.value.set_files(video_path)

            print("等待视频上传完成...")
            self.wait_for_upload()
            time.sleep(random.uniform(2, 4))

            # 3. 填写标题
            self.page.fill('input[placeholder*="标题"]', title)
            time.sleep(random.uniform(0.5, 1))

            # 4. 填写简介
            self.page.click('div[contenteditable="true"]')
            self.page.keyboard.type(description)
            time.sleep(random.uniform(0.5, 1))

            # 5. 发布（注意：实际发布可能需要手动确认）
            return {"success": True, "message": "填写完成，请手动确认发布"}

        except Exception as e:
            return {"success": False, "error": str(e)}

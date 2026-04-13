import time
import random
from ..base import BasePlatform
from typing import Optional, Dict, Any


class BaijiahaoPlatform(BasePlatform):
    platform_name = "baijiahao"

    def wait_for_upload(self, timeout: int = 900) -> bool:
        """等待视频上传完成：以封面区出现（coverWrap）为信号"""
        deadline = time.time() + timeout
        print("  等待视频上传完成...", flush=True)
        while time.time() < deadline:
            try:
                el = self.page.wait_for_selector('[class*="coverWrap"]', timeout=8000)
                if el and el.is_visible():
                    print("  上传完成，封面区已出现")
                    return True
            except Exception:
                pass
            elapsed = int(time.time() - (deadline - timeout))
            print(f"  上传中... {elapsed}s", flush=True)
        return False

    def upload_video(self, video_path: str, title: str,
                     description: str = "", tags: str = "",
                     cover_path: Optional[str] = None) -> Dict[str, Any]:
        try:
            # 1. 进入百家号视频发布页
            self.page.goto("https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                           wait_until="domcontentloaded", timeout=30000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(random.uniform(3, 5))
            print(f"  页面标题: {self.page.title()}")
            print(f"  页面URL:  {self.page.url}")

            # 2. 找上传按钮并选择视频文件
            upload_selectors = [
                '[data-testid="video-upload-btn"]',
                'input[type="file"][accept*="video"]',
                'input[type="file"]',
            ]
            upload_el = None
            for sel in upload_selectors:
                try:
                    self.page.wait_for_selector(sel, timeout=5000)
                    upload_el = sel
                    break
                except Exception:
                    pass
            if not upload_el:
                raise RuntimeError("未找到视频上传区域")

            print(f"  找到上传元素: {upload_el}")
            if 'input' in upload_el and 'file' in upload_el:
                self.page.locator(upload_el).set_input_files(video_path)
            else:
                with self.page.expect_file_chooser(timeout=15000) as fc_info:
                    self.page.click(upload_el)
                fc_info.value.set_files(video_path)
            print(f"  视频文件已选择: {video_path}")

            # 3. 等待上传完成（coverWrap 出现）
            if not self.wait_for_upload(timeout=900):
                raise RuntimeError("视频上传超时（900s）")
            time.sleep(random.uniform(1, 2))

            # 4. 填写标题（editorArea 是 contenteditable 编辑器）
            title_sel = '[class*="editorArea"]'
            try:
                self.page.wait_for_selector(title_sel, timeout=5000)
                self.page.click(title_sel)
                # 全选清空现有内容后输入
                self.page.keyboard.press("Control+a")
                self.page.keyboard.type(title[:100])
                time.sleep(random.uniform(0.5, 1))
                print(f"  标题已填写: {title[:50]}")
            except Exception as e:
                print(f"  警告: 标题填写失败 - {e}")

            # 5. 封面处理：横版 + 竖版各上传一张
            # 百家号封面区结构：[class*="coverWrap"] > div:nth-child(1/2) 内有隐藏 file input
            if cover_path:
                for idx, label in [(1, "横版"), (2, "竖版")]:
                    try:
                        # 在对应封面槽内找 file input
                        slot_sel = f'[class*="coverWrap"] > div:nth-child({idx})'
                        self.page.wait_for_selector(slot_sel, timeout=5000)
                        file_input = self.page.locator(
                            f'{slot_sel} input[type="file"]'
                        )
                        file_input.set_input_files(cover_path)
                        print(f"  {label}封面已上传: {cover_path}")
                        time.sleep(random.uniform(1, 1.5))
                    except Exception as e:
                        print(f"  {label}封面上传失败（跳过）: {e}")
            else:
                print("  无封面图，跳过封面上传")

            # 6. 等待人工检查并确认发布（固定等待，用户在浏览器操作）
            wait_seconds = 300  # 等待 5 分钟
            print("\n" + "=" * 60)
            print(f"  内容已填充完毕，请在浏览器中检查标题/封面后手动点击发布。")
            print(f"  程序将等待 {wait_seconds} 秒后自动标记为成功完成。")
            print("=" * 60)
            for remaining in range(wait_seconds, 0, -10):
                print(f"  剩余等待: {remaining}s ...", flush=True)
                time.sleep(10)
            return {"success": True, "message": "人工发布等待完成", "url": self.page.url}

        except Exception as e:
            return {"success": False, "error": str(e)}

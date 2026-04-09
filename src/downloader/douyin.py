"""
抖音无水印视频下载器
"""
import os
import re
import time
import hashlib

import requests

from downloader import BaseDownloader, register_downloader
from conf.settings import settings

# 抖音分享链接的 User-Agent
DOUYIN_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.6 Mobile/15E148 Safari/604.1"
)

# 抖音 API headers
DOUYIN_HEADERS = {
    "User-Agent": DOUYIN_UA,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json",
}


@register_downloader
class DouyinDownloader(BaseDownloader):
    source_name = "douyin"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DOUYIN_HEADERS)

    def download(self, url: str, output_dir: str, **kwargs) -> dict:
        """
        下载抖音视频（无水印）

        流程：分享链接 → 302重定向 → 提取video_id → API获取无水印URL → 下载
        """
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Step 1: 解析分享链接，获取真实 URL
            print(f"  [1/3] 解析链接: {url}")
            video_id = self._extract_video_id(url)
            if not video_id:
                return {"success": False, "error": f"无法从链接中提取视频ID: {url}"}

            print(f"  [2/3] 获取视频信息 (video_id: {video_id})")

            # Step 2: 通过 API 获取无水印视频地址
            video_info = self._get_video_info(video_id)
            if not video_info:
                return {"success": False, "error": "无法获取视频信息"}

            video_url = video_info.get("video_url")
            title = video_info.get("title", video_id)
            if not video_url:
                return {"success": False, "error": "无法获取无水印视频地址"}

            # Step 3: 下载视频文件
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
            filename = f"{safe_title}_{video_id}.mp4"
            file_path = os.path.join(output_dir, filename)

            print(f"  [3/3] 下载视频: {filename}")
            self._download_file(video_url, file_path)

            return {
                "success": True,
                "file_path": file_path,
                "title": title,
                "video_id": video_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_video_id(self, url: str) -> str:
        """从分享链接中提取视频 ID"""
        try:
            # 处理短链接（v.douyin.com）
            if "v.douyin.com" in url or "vm.tiktok.com" in url:
                resp = self.session.get(url, allow_redirects=False, timeout=10)
                if resp.status_code in (301, 302):
                    url = resp.headers.get("Location", url)

            # 从 URL 中提取 video_id
            # 格式1: /video/1234567890
            match = re.search(r'/video/(\d+)', url)
            if match:
                return match.group(1)

            # 格式2: /note/1234567890
            match = re.search(r'/note/(\d+)', url)
            if match:
                return match.group(1)

            # 格式3: modal_id=1234567890
            match = re.search(r'modal_id=(\d+)', url)
            if match:
                return match.group(1)

            return ""
        except Exception:
            return ""

    def _get_video_info(self, video_id: str) -> dict:
        """通过抖音 Web API 获取视频信息"""
        api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}"

        try:
            resp = self.session.get(api_url, timeout=15)
            data = resp.json()

            aweme_detail = data.get("aweme_detail", {})
            if not aweme_detail:
                return {}

            # 提取标题
            title = aweme_detail.get("desc", "")

            # 提取无水印视频地址
            video = aweme_detail.get("video", {})
            play_addr = video.get("play_addr", {})
            url_list = play_addr.get("url_list", [])

            # 尝试获取无水印地址
            video_url = ""
            if url_list:
                video_url = url_list[0]
                # 替换为无水印地址
                video_url = video_url.replace("playwm", "play")

            return {
                "title": title,
                "video_url": video_url,
                "video_id": video_id,
            }
        except Exception as e:
            print(f"  获取视频信息失败: {e}")
            return {}

    def _download_file(self, url: str, file_path: str) -> None:
        """下载文件到指定路径"""
        headers = {
            "User-Agent": DOUYIN_UA,
            "Referer": "https://www.douyin.com/",
        }
        resp = requests.get(url, headers=headers, stream=True, timeout=settings.DOWNLOAD_TIMEOUT)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(file_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 // total
                    print(f"\r  下载进度: {pct}% ({downloaded}/{total})", end="", flush=True)

        print()  # 换行

"""
B站视频下载器（基于 yt-dlp）
"""
import json
import os
import subprocess

from infra.downloader import BaseDownloader, register_downloader
from utils.tool_finder import find_tool
from conf.settings import settings


@register_downloader
class BilibiliDownloader(BaseDownloader):
    source_name = "bilibili"

    def __init__(self):
        self.ytdlp_path = find_tool("yt-dlp", settings.YTDLP_PATH)
        self.ffmpeg_path = find_tool("ffmpeg", settings.FFMPEG_PATH)

    def download(self, url: str, output_dir: str, **kwargs) -> dict:
        """
        使用 yt-dlp 下载 B站视频
        """
        if not self.ytdlp_path:
            return {"success": False, "error": "yt-dlp 未找到，请先运行: python main.py cmd setup"}

        os.makedirs(output_dir, exist_ok=True)

        cookies = kwargs.get("cookies", "")
        quality = kwargs.get("quality", "best")

        # 输出模板
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")

        try:
            info = self._get_info(url, cookies)
            title = info.get("title", "未知") if info else "未知"

            # 下载
            cmd = [
                self.ytdlp_path,
                "-o", output_template,
                "--no-playlist",
                "--merge-output-format", "mp4",
            ]

            if self.ffmpeg_path:
                cmd.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])

            if cookies:
                cmd.extend(["--cookies", cookies])

            # 画质选择
            if quality == "best":
                cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"])
            elif quality == "1080p":
                cmd.extend(["-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"])
            elif quality == "720p":
                cmd.extend(["-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"])

            cmd.append(url)

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=settings.DOWNLOAD_TIMEOUT
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "yt-dlp 执行失败"
                return {"success": False, "error": error_msg}

            # 查找下载的文件
            file_path = self._find_downloaded_file(output_dir, url, info)

            return {
                "success": True,
                "file_path": file_path,
                "title": title,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"下载超时（{settings.DOWNLOAD_TIMEOUT}s）"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_info(self, url: str, cookies: str = "") -> dict:
        """用 yt-dlp --dump-json 获取视频信息"""
        cmd = [self.ytdlp_path, "--dump-json", "--no-playlist", url]
        if cookies:
            cmd.extend(["--cookies", cookies])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}

    def _find_downloaded_file(self, output_dir: str, url: str, info: dict) -> str:
        """查找 yt-dlp 下载的文件"""
        # 尝试根据 info 中的 id 匹配
        video_id = info.get("id", "") if info else ""

        if video_id:
            for f in os.listdir(output_dir):
                if video_id in f and f.endswith(".mp4"):
                    return os.path.join(output_dir, f)

        # 回退：返回目录中最新的 .mp4 文件
        mp4_files = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.endswith(".mp4")
        ]
        if mp4_files:
            return max(mp4_files, key=os.path.getmtime)

        return ""

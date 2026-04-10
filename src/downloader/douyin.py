"""
抖音视频下载器（基于 yt-dlp）
"""
import json
import os
import subprocess
import tempfile
from typing import Optional

from downloader import BaseDownloader, register_downloader
from utils.tool_finder import find_tool
from conf.settings import settings


@register_downloader
class DouyinDownloader(BaseDownloader):
    source_name = "douyin"

    def __init__(self):
        self.ytdlp_path = find_tool("yt-dlp", settings.YTDLP_PATH)
        self.ffmpeg_path = find_tool("ffmpeg", settings.FFMPEG_PATH)

    def download(self, url: str, output_dir: str, **kwargs) -> dict:
        """
        使用 yt-dlp 下载抖音视频（无水印）
        """
        if not self.ytdlp_path:
            return {"success": False, "error": "yt-dlp 未找到，请先运行: python main.py setup"}

        os.makedirs(output_dir, exist_ok=True)

        cookies = kwargs.get("cookies", "")
        cookies_from_browser = kwargs.get("cookies_from_browser", "")
        cookie_header = kwargs.get("cookie_header", "")
        quality = kwargs.get("quality", "best")
        temp_cookie_file = ""

        # 输出模板
        output_template = os.path.join(output_dir, "%(title).80s_%(id)s.%(ext)s")

        try:
            # Step 1: 获取视频信息
            print(f"  [1/2] 获取视频信息...")
            # 支持直接传浏览器 Cookie 字符串，自动转成 Netscape cookies 文件。
            if cookie_header and not cookies and not cookies_from_browser:
                temp_cookie_file = self._create_temp_cookie_file(cookie_header)
                cookies = temp_cookie_file

            info = self._get_info(url, cookies, cookies_from_browser)
            title = info.get("title", "未知") if info else "未知"
            video_id = info.get("id", "") if info else ""
            print(f"  标题: {title}")

            # Step 2: 下载
            print(f"  [2/2] 下载视频...")
            result = self._run_download(
                url=url,
                output_template=output_template,
                quality=quality,
                cookies=cookies,
                cookies_from_browser=cookies_from_browser,
                with_format=True
            )

            # 某些抖音链接的格式信息不稳定，先按格式下载，失败则降级重试。
            if result.returncode != 0 and self._can_retry_without_format(result.stderr):
                print("  画质筛选失败，自动降级重试...")
                result = self._run_download(
                    url=url,
                    output_template=output_template,
                    quality=quality,
                    cookies=cookies,
                    cookies_from_browser=cookies_from_browser,
                    with_format=False
                )

            if result.returncode != 0:
                error_msg = self._build_error_message(result.stderr, bool(cookies or cookies_from_browser))
                return {"success": False, "error": error_msg}

            # 查找下载的文件
            file_path = self._find_downloaded_file(output_dir, video_id)
            if not file_path:
                return {"success": False, "error": "下载完成但未找到输出文件，请检查 ffmpeg/格式参数"}

            return {
                "success": True,
                "file_path": file_path,
                "title": title,
                "video_id": video_id,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"下载超时（{settings.DOWNLOAD_TIMEOUT}s）"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if temp_cookie_file:
                try:
                    os.remove(temp_cookie_file)
                except Exception:
                    pass

    def _run_download(
        self,
        url: str,
        output_template: str,
        quality: str,
        cookies: str,
        cookies_from_browser: str,
        with_format: bool = True
    ) -> subprocess.CompletedProcess:
        cmd = [
            self.ytdlp_path,
            "-o", output_template,
            "--no-playlist",
            "--merge-output-format", "mp4",
        ]

        if self.ffmpeg_path:
            cmd.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])

        if cookies_from_browser:
            cmd.extend(["--cookies-from-browser", cookies_from_browser])
        elif cookies:
            cmd.extend(["--cookies", cookies])

        if with_format:
            format_selector = self._build_format_selector(quality)
            if format_selector:
                cmd.extend(["-f", format_selector])

        cmd.append(url)
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.DOWNLOAD_TIMEOUT
        )

    def _build_format_selector(self, quality: str) -> Optional[str]:
        if quality == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        if quality == "1080p":
            return "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]"
        if quality == "720p":
            return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]"
        return None

    def _can_retry_without_format(self, stderr: str) -> bool:
        if not stderr:
            return False
        hint = stderr.lower()
        return (
            "requested format is not available" in hint
            or "no video formats" in hint
            or "unsupported url" in hint
        )

    def _build_error_message(self, stderr: str, has_cookies: bool) -> str:
        if not stderr:
            return "yt-dlp 执行失败"

        error = stderr.strip()
        hint = error.lower()
        if ("fresh cookies are needed" in hint or "login" in hint or "sign in" in hint) and not has_cookies:
            return (
                f"{error}\n"
                "建议：抖音通常需要登录态，重试时增加 --cookies-from-browser chrome（或 edge/safari/firefox）"
            )
        return error

    def _get_info(self, url: str, cookies: str = "", cookies_from_browser: str = "") -> dict:
        """用 yt-dlp --dump-json 获取视频信息"""
        cmd = [self.ytdlp_path, "--dump-json", "--no-playlist", url]
        if cookies_from_browser:
            cmd.extend(["--cookies-from-browser", cookies_from_browser])
        elif cookies:
            cmd.extend(["--cookies", cookies])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}

    def _find_downloaded_file(self, output_dir: str, video_id: str) -> str:
        """查找 yt-dlp 下载的文件"""
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

    def _create_temp_cookie_file(self, cookie_header: str) -> str:
        """把 'k=v; k2=v2' 转换成 yt-dlp 可读的 Netscape cookies 文件。"""
        fd, path = tempfile.mkstemp(prefix="douyin_cookie_", suffix=".txt")
        os.close(fd)

        lines = ["# Netscape HTTP Cookie File\n"]
        for part in cookie_header.split(";"):
            pair = part.strip()
            if not pair or "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue

            # 让 cookie 同时可用于主站和内容域。
            lines.append(f".douyin.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}\n")
            lines.append(f".iesdouyin.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}\n")

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return path

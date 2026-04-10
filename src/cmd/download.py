"""
DownloadCommand - 视频下载命令
"""
from cmd import BaseCommand, register_command
from downloader import get_downloader
from conf.settings import settings


@register_command
class DownloadCommand(BaseCommand):
    command_name = "download"
    command_help = "从抖音/B站下载视频"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--source", choices=["douyin", "bilibili"],
                            help="来源平台")
        parser.add_argument("--url", help="单个视频链接")
        parser.add_argument("--urls-file", help="批量链接文件（每行一个 URL）")
        parser.add_argument("--output", help=f"输出目录（默认 {settings.DOWNLOAD_DIR}）")
        parser.add_argument("--cookies", help="cookies 文件路径（B站高画质需要）")
        parser.add_argument("--cookies-from-browser",
                            help="从浏览器读取 cookies（如 chrome/edge/safari/firefox）")
        parser.add_argument("--cookie-header",
                            help="原始 Cookie 字符串（浏览器请求头里的 'k=v; k2=v2'）")
        parser.add_argument("--cookie-header-file",
                            help="原始 Cookie 字符串文件路径（建议用于超长 cookie）")
        parser.add_argument("--quality", default="best",
                            choices=["best", "1080p", "720p"],
                            help="画质选择（默认 best）")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def execute(self, args) -> dict:
        config = self.load_config(args)

        # 合并参数
        source = self.merge_args(args, config, "source")
        url = self.merge_args(args, config, "url")
        urls_file = self.merge_args(args, config, "urls_file")
        output_dir = self.merge_args(args, config, "output", settings.DOWNLOAD_DIR)
        cookies = self.merge_args(args, config, "cookies", "")
        cookies_from_browser = self.merge_args(args, config, "cookies_from_browser", "")
        cookie_header = self.merge_args(args, config, "cookie_header", "")
        cookie_header_file = self.merge_args(args, config, "cookie_header_file", "")
        quality = self.merge_args(args, config, "quality", "best")

        # 从配置文件中读取 URL 列表
        urls = config.get("urls", [])

        if not source:
            return {"success": False, "message": "请指定 --source（douyin/bilibili）"}

        # 收集所有 URL
        if url:
            urls.append(url)
        if urls_file:
            urls.extend(self._read_urls_file(urls_file))

        if not urls:
            return {"success": False, "message": "请指定 --url 或 --urls-file，或在配置文件中提供 urls"}

        # 平台特定参数
        platform_config = config.get(source, {})
        if not cookies and platform_config.get("cookies"):
            cookies = platform_config["cookies"]
        if not cookies_from_browser and platform_config.get("cookies_from_browser"):
            cookies_from_browser = platform_config["cookies_from_browser"]
        if not cookie_header and platform_config.get("cookie_header"):
            cookie_header = platform_config["cookie_header"]
        if not cookie_header_file and platform_config.get("cookie_header_file"):
            cookie_header_file = platform_config["cookie_header_file"]
        if not cookie_header and cookie_header_file:
            cookie_header = self._read_cookie_header_file(cookie_header_file)
        if quality == "best" and platform_config.get("quality"):
            quality = platform_config["quality"]

        print(f"下载源: {source}")
        print(f"视频数: {len(urls)}")
        print(f"输出到: {output_dir}")
        print()

        downloader = get_downloader(source)
        kwargs = {
            "cookies": cookies,
            "cookies_from_browser": cookies_from_browser,
            "cookie_header": cookie_header,
            "quality": quality
        }

        if len(urls) == 1:
            result = downloader.download(urls[0], output_dir, **kwargs)
            if result["success"]:
                print(f"\n下载成功: {result['file_path']}")
            else:
                print(f"\n下载失败: {result.get('error', '')}")
            return result
        else:
            results = downloader.batch_download(urls, output_dir, **kwargs)
            success_count = sum(1 for r in results if r.get("success"))
            print(f"\n批量下载完成: {success_count}/{len(results)} 成功")
            return {
                "success": success_count > 0,
                "message": f"{success_count}/{len(results)} 下载成功",
                "results": results,
            }

    def _read_urls_file(self, file_path: str) -> list[str]:
        """从文件读取 URL 列表"""
        urls = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        except FileNotFoundError:
            print(f"  URL 文件不存在: {file_path}")
        return urls

    def _read_cookie_header_file(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            print(f"  Cookie 文件不存在: {file_path}")
        except Exception as e:
            print(f"  读取 Cookie 文件失败: {e}")
        return ""

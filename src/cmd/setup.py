"""
SetupCommand - 一键下载/配置外部工具到 bin/ 目录
"""
import os
import platform
import stat
import subprocess
import urllib.request
from pathlib import Path

from cmd import BaseCommand, register_command
from utils.tool_finder import find_tool
from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


# yt-dlp GitHub Releases 下载地址
YTDLP_RELEASES = {
    "Darwin": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
    "Linux": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
}

# ffmpeg/ffprobe 静态构建下载地址
FFMPEG_RELEASES = {
    ("Darwin", "arm64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffmpeg-darwin-arm64",
    ("Darwin", "x86_64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffmpeg-darwin-x64",
    ("Linux", "x86_64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffmpeg-linux-x64",
    ("Linux", "aarch64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffmpeg-linux-arm64",
}

FFPROBE_RELEASES = {
    ("Darwin", "arm64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffprobe-darwin-arm64",
    ("Darwin", "x86_64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffprobe-darwin-x64",
    ("Linux", "x86_64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffprobe-linux-x64",
    ("Linux", "aarch64"): "https://github.com/eugeneware/ffmpeg-static/releases/latest/download/ffprobe-linux-arm64",
}


@register_command
class SetupCommand(BaseCommand):
    command_name = "setup"
    command_help = "一键下载/配置外部工具（ffmpeg, yt-dlp）到 bin/ 目录"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--tool", choices=["ffmpeg", "yt-dlp", "all"],
                            default="all", help="指定要安装的工具（默认 all）")
        parser.add_argument("--check", action="store_true",
                            help="只检查工具是否可用，不执行安装")

    def execute(self, args) -> dict:
        tool = getattr(args, "tool", "all")
        check_only = getattr(args, "check", False)

        bin_dir = Path(settings.BIN_DIR)
        bin_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        if check_only:
            results["ffmpeg"] = self._check_tool("ffmpeg")
            results["ffprobe"] = self._check_tool("ffprobe")
            results["yt-dlp"] = self._check_tool("yt-dlp")
            return {"success": True, "message": "工具检查完成", "tools": results}

        if tool in ("ffmpeg", "all"):
            results["ffmpeg"] = self._setup_ffmpeg(bin_dir)

        if tool in ("yt-dlp", "all"):
            results["yt-dlp"] = self._setup_ytdlp(bin_dir)

        # 安装后验证
        logger.info("--- 验证安装 ---")
        for name in results:
            check = self._check_tool(name)
            status = "OK" if check["available"] else "FAILED"
            version = check.get("version", "未知")
            logger.info(f"  {name}: {status} (版本: {version})")

        all_ok = all(r.get("success", False) for r in results.values())
        return {
            "success": all_ok,
            "message": "工具安装完成" if all_ok else "部分工具安装失败",
            "tools": results,
        }

    def _check_tool(self, tool_name: str) -> dict:
        """检查工具是否可用，返回版本信息"""
        settings_path = ""
        if tool_name == "ffmpeg":
            settings_path = settings.FFMPEG_PATH
        elif tool_name == "yt-dlp":
            settings_path = settings.YTDLP_PATH

        path = find_tool(tool_name, settings_path)
        if not path:
            logger.warning(f"  [X] {tool_name}: 未找到")
            return {"available": False, "path": ""}

        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            version = result.stdout.strip().split("\n")[0] if result.stdout else "未知"
            logger.info(f"  [OK] {tool_name}: {path} ({version})")
            return {"available": True, "path": path, "version": version}
        except Exception as e:
            logger.error(f"  [X] {tool_name}: 找到 {path} 但无法执行 ({e})")
            return {"available": False, "path": path, "error": str(e)}

    def _setup_ffmpeg(self, bin_dir: Path) -> dict:
        """下载 ffmpeg + ffprobe 静态构建到 bin/ 目录"""
        system = platform.system()
        machine = platform.machine()
        all_ok = True

        for tool_name, releases in [("ffmpeg", FFMPEG_RELEASES), ("ffprobe", FFPROBE_RELEASES)]:
            target = bin_dir / tool_name
            if target.exists() and os.access(str(target), os.X_OK):
                logger.info(f"[{tool_name}] 已存在: {target}")
                continue

            url = releases.get((system, machine))
            if not url:
                logger.warning(f"[{tool_name}] 不支持当前系统 ({system}/{machine})，请手动下载放入 bin/ 目录")
                all_ok = False
                continue

            logger.info(f"[{tool_name}] 正在从 GitHub 下载...")
            logger.info(f"  URL: {url}")
            try:
                urllib.request.urlretrieve(url, str(target))
                target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                logger.info(f"[{tool_name}] 下载完成: {target}")
            except Exception as e:
                logger.error(f"[{tool_name}] 下载失败: {e}")
                all_ok = False

        return {
            "success": all_ok,
            "path": str(bin_dir / "ffmpeg"),
            "action": "downloaded",
        }

    def _setup_ytdlp(self, bin_dir: Path) -> dict:
        """下载 yt-dlp 到 bin/ 目录"""
        target = bin_dir / "yt-dlp"

        # 已存在且可用，跳过
        if target.exists() and os.access(str(target), os.X_OK):
            logger.info(f"[yt-dlp] 已存在: {target}")
            return {"success": True, "path": str(target), "action": "already_exists"}

        system = platform.system()
        url = YTDLP_RELEASES.get(system)
        if not url:
            logger.warning(f"[yt-dlp] 不支持当前系统 ({system})，请手动下载放入 bin/ 目录")
            return {"success": False, "error": f"不支持的系统: {system}"}

        logger.info(f"[yt-dlp] 正在从 GitHub 下载...")
        logger.info(f"  URL: {url}")
        try:
            urllib.request.urlretrieve(url, str(target))
            # 添加执行权限
            target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            logger.info(f"[yt-dlp] 下载完成: {target}")
            return {"success": True, "path": str(target), "action": "downloaded"}
        except Exception as e:
            logger.error(f"[yt-dlp] 下载失败: {e}")
            logger.error("  请手动下载 yt-dlp 并放入 bin/ 目录")
            return {"success": False, "error": str(e)}

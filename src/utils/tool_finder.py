"""外部工具路径查找"""
import os
import shutil
from pathlib import Path

from conf.settings import settings


def find_tool(tool_name: str, settings_path: str = "") -> str:
    """
    查找外部工具路径

    优先级：settings 显式配置 > bin/ 目录 > 系统 PATH
    """
    # 1. settings 显式指定
    if settings_path:
        if os.path.isfile(settings_path) and os.access(settings_path, os.X_OK):
            return settings_path

    # 2. bin/ 目录
    bin_path = Path(settings.BIN_DIR) / tool_name
    if bin_path.is_file() and os.access(str(bin_path), os.X_OK):
        return str(bin_path)

    # 3. 系统 PATH
    sys_path = shutil.which(tool_name)
    if sys_path:
        return sys_path

    return ""

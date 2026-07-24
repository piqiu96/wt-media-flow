"""命令分发框架。

采用 ABC + 注册表模式，每个命令独立注册，通过 cmd_name 分发执行。
"""
import os
from abc import ABC, abstractmethod

import yaml


class BaseCommand(ABC):
    """命令基类"""
    command_name: str = ""
    command_help: str = ""

    @abstractmethod
    def setup_parser(self, parser) -> None:
        pass

    @abstractmethod
    def execute(self, args) -> dict:
        pass

    def load_config(self, args) -> dict:
        config_path = getattr(args, "config", None)
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def merge_args(self, args, config: dict, key: str, default=None):
        cli_val = getattr(args, key, None)
        if cli_val is not None:
            return cli_val
        if key in config:
            return config[key]
        return default


# 命令注册表
_COMMAND_REGISTRY: dict[str, type[BaseCommand]] = {}


def register_command(cmd_class: type[BaseCommand]):
    """装饰器：注册命令到注册表"""
    _COMMAND_REGISTRY[cmd_class.command_name] = cmd_class
    return cmd_class


def get_command(name: str) -> BaseCommand:
    cls = _COMMAND_REGISTRY.get(name)
    if not cls:
        available = ", ".join(_COMMAND_REGISTRY.keys())
        raise ValueError(f"未知命令: {name}，可用命令: {available}")
    return cls()


def get_all_commands() -> dict[str, type[BaseCommand]]:
    return _COMMAND_REGISTRY


# 自动导入所有命令模块以触发 @register_command
from app.cli.setup import SetupCommand          # noqa: E402,F401
from app.cli.download import DownloadCommand     # noqa: E402,F401
from app.cli.composite import CompositeCommand   # noqa: E402,F401
from app.cli.init_db import InitCommand          # noqa: E402,F401
from app.cli.account import AccountCommand       # noqa: E402,F401
from app.cli.video import VideoCommand           # noqa: E402,F401
from app.cli.plan import PlanCommand             # noqa: E402,F401
from app.cli.claw import ClawCommand             # noqa: E402,F401
from app.cli.publish import PublishCommand       # noqa: E402,F401
from app.cli.comment import CommentCommand       # noqa: E402,F401
from app.cli.cleanup import CleanupCommand       # noqa: E402,F401
from app.cli.serve import ServeCommand           # noqa: E402,F401
from app.cli.pack import PackCommand             # noqa: E402,F401
from app.cli.overlay import OverlayCommand       # noqa: E402,F401
from app.cli.diagnose import DiagnoseCommand     # noqa: E402,F401
from app.cli.tail_dedup import TailDedupCommand  # noqa: E402,F401

"""
命令分发框架

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
        """向 argparse subparser 注册本命令的参数"""
        pass

    @abstractmethod
    def execute(self, args) -> dict:
        """执行命令，返回 {"success": bool, "message": str, ...}"""
        pass

    def load_config(self, args) -> dict:
        """加载配置文件（如果指定了 --config）"""
        config_path = getattr(args, "config", None)
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def merge_args(self, args, config: dict, key: str, default=None):
        """合并参数：命令行 > 配置文件 > 默认值"""
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
    """通过名称获取命令实例"""
    cls = _COMMAND_REGISTRY.get(name)
    if not cls:
        available = ", ".join(_COMMAND_REGISTRY.keys())
        raise ValueError(f"未知命令: {name}，可用命令: {available}")
    return cls()


def get_all_commands() -> dict[str, type[BaseCommand]]:
    """获取所有已注册命令"""
    return _COMMAND_REGISTRY


# 自动导入所有命令模块以触发 @register_command
from cmd.setup import SetupCommand
from cmd.download import DownloadCommand
from cmd.composite import CompositeCommand
from cmd.pipeline import PipelineCommand
from cmd.init_db import InitCommand
from cmd.account import AccountCommand
from cmd.video import VideoCommand
from cmd.task import TaskCommand
from cmd.plan import PlanCommand
from cmd.run import RunCommand

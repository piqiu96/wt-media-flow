#!/usr/bin/env python3
"""
矩阵视频自动发布系统

支持哔哩哔哩和百家号视频自动发布，小红书适配器待实现
"""
import argparse
import sys
import os

# 将 src/ 目录加入 Python 路径
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# 将项目根目录也加入（兼容从根目录运行）
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.cli import get_all_commands, get_command


def main():
    parser = argparse.ArgumentParser(
        description="矩阵视频自动发布系统 - 支持哔哩哔哩/百家号发布，小红书待实现",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  环境检查:     .venv/bin/python3 src/main.py setup --check
  采集素材:     .venv/bin/python3 src/main.py claw --category 三角洲 --config conf/claw.yaml
  合成视频:     .venv/bin/python3 src/main.py composite --batch --category 三角洲 --platform baijiahao --pool pool-yy --config conf/composite.yaml
  初始化数据库: .venv/bin/python3 src/main.py init
  账号管理:     .venv/bin/python3 src/main.py account add --platform bilibili --username u1 --browser-id 1
  生成计划:     .venv/bin/python3 src/main.py plan create --user-id 1 --dry-run
  执行计划:     .venv/bin/python3 src/main.py plan run --plan-id 1 --account-id 1
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 自动注册所有命令的 parser
    for cmd_name, cmd_class in get_all_commands().items():
        cmd_instance = cmd_class()
        sub = subparsers.add_parser(cmd_name, help=cmd_instance.command_help)
        cmd_instance.setup_parser(sub)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        command = get_command(args.command)
        result = command.execute(args)
        if result and not result.get("success"):
            msg = result.get("message", result.get("error", ""))
            if msg:
                print(f"\n命令执行失败: {msg}")
            sys.exit(1)
    except Exception as e:
        print(f"\n命令执行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
矩阵视频自动发布系统

支持多平台（哔哩哔哩/百家号/小红书）视频自动发布
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
        description="矩阵视频自动发布系统 - 支持哔哩哔哩/百家号/小红书多平台发布",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  环境初始化:   python src/main.py setup
  下载视频:     python src/main.py download --source douyin --url "https://..."
  合成视频:     python src/main.py composite --input video.mp4 --guide guide.mp4 --insert-at 10
  全流程:       python src/main.py pipeline --config conf/pipeline.yaml
  初始化数据库: python src/main.py init
  账号管理:     python src/main.py account add --platform bilibili --username u1 --profile-id xxx
  视频管理:     python src/main.py video add --path /path/to/video.mp4 --title "标题"
  生成计划:     python src/main.py plan --group group_1 --count 100
  运行调度:     python src/main.py run
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

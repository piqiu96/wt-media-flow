#!/usr/bin/env python3
"""One-shot scheduler wrapper with non-overlap locks.

Use this from crontab instead of calling the underlying main.py commands
directly. If the previous same job is still running, this script skips the
current window.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
LOCK_DIR = ROOT / "store" / "locks"


def _setup_project_path() -> None:
    for path in (str(ROOT / "src"), str(ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动任务总控：带锁执行采集/合成，避免窗口重叠")
    parser.add_argument("job", choices=["claw", "composite"], help="要执行的任务")

    claw = parser.add_argument_group("claw options")
    claw.add_argument("--max-games", type=int, default=2, help="采集游戏并发，默认 2")
    claw.add_argument("--claw-config", default="conf/claw.yaml", help="采集配置，默认 conf/claw.yaml")

    comp = parser.add_argument_group("composite options")
    comp.add_argument("--limit", type=int, default=50, help="合成全局数量，默认 50")
    comp.add_argument("--workers", type=int, default=4, help="合成并发，默认 4")
    comp.add_argument("--composite-config", default="conf/composite.yaml", help="合成配置")
    comp.add_argument("--max-age-days", type=int, default=5, help="合成素材最大天数，默认 5")

    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的 main.py 命令")
    return parser.parse_args()


def _categories(config_path: str) -> list[str]:
    path = Path(config_path)
    if not path.is_absolute():
        path = ROOT / path
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return list((config.get("keywords_by_category") or {}).keys())


def _main_cmd(*parts: str) -> list[str]:
    return [sys.executable, str(ROOT / "src" / "main.py"), *parts]


def _run_cmd(cmd: list[str], dry_run: bool) -> int:
    print(" ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=ROOT).returncode


def _run_claw(args: argparse.Namespace) -> int:
    categories = _categories(args.claw_config)
    if not categories:
        print(f"未在 {args.claw_config} 找到 keywords_by_category")
        return 1

    def one(category: str) -> tuple[str, int]:
        cmd = _main_cmd("claw", "--category", category, "--config", args.claw_config)
        return category, _run_cmd(cmd, args.dry_run)

    max_games = max(1, args.max_games)
    failed = 0
    with ThreadPoolExecutor(max_workers=max_games) as executor:
        futures = {executor.submit(one, category): category for category in categories}
        for future in as_completed(futures):
            category, code = future.result()
            print(f"[claw] {category} exit={code}")
            if code != 0:
                failed += 1
    return 0 if failed == 0 else 1


def _send_composite_notify(started_at: datetime, target: int, exit_code: int) -> None:
    _setup_project_path()
    from conf.settings import settings
    from infra.db.database import SessionLocal
    from infra.db.models import VideoTask, VideoTaskStatusEnum
    from utils.wecom import send_text

    if not settings.WECOM_WEBHOOK_URL:
        return

    db = SessionLocal()
    try:
        recent_tasks = (
            db.query(VideoTask)
            .filter(VideoTask.created_at >= started_at)
            .order_by(VideoTask.id.desc())
            .all()
        )
        composited = [t for t in recent_tasks if t.status == VideoTaskStatusEnum.COMPOSITED]
        failed = [t for t in recent_tasks if t.status == VideoTaskStatusEnum.FAILED]
        packable = (
            db.query(VideoTask)
            .filter(VideoTask.status == VideoTaskStatusEnum.COMPOSITED)
            .count()
        )
    finally:
        db.close()

    by_category: dict[str, int] = {}
    for task in composited:
        category = task.category or "未分类"
        by_category[category] = by_category.get(category, 0) + 1

    lines = [
        "**自动合成完成**",
        "",
        f"目标 {target} 条 / 本轮成功 {len(composited)} 条 / 失败 {len(failed)} 条",
        f"当前可打包视频：{packable} 条",
        f"总控退出码：{exit_code}",
        "",
        "各游戏成功：",
    ]
    if by_category:
        for category, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- 无")

    if failed:
        lines.extend(["", "失败原因 TOP5："])
        for task in failed[:5]:
            title = (task.title or task.source_vid or str(task.id))[:24]
            msg = (task.message or "")[:60]
            lines.append(f"- {task.category or '未分类'} {title}: {msg or '未知错误'}")

    send_text(settings.WECOM_WEBHOOK_URL, "\n".join(lines))


def _run_composite(args: argparse.Namespace) -> int:
    categories = _categories(args.claw_config)
    if not categories:
        print(f"未在 {args.claw_config} 找到 keywords_by_category")
        return 1

    # main.py composite --batch is category-scoped, so distribute the global
    # target evenly across configured categories. This keeps orchestration in
    # main.py while avoiding one category consuming the whole window.
    limit = max(1, args.limit)
    per_category = max(1, (limit + len(categories) - 1) // len(categories))

    run_started_at = datetime.now(UTC).replace(tzinfo=None)
    failed = 0
    for category in categories:
        cmd = _main_cmd(
            "composite",
            "--batch",
            "--category",
            category,
            "--config",
            args.composite_config,
            "--limit",
            str(per_category),
            "--workers",
            str(max(1, args.workers)),
        )
        code = _run_cmd(cmd, args.dry_run)
        print(f"[composite] {category} exit={code}")
        if code != 0:
            failed += 1
    exit_code = 0 if failed == 0 else 1
    if not args.dry_run:
        _send_composite_notify(run_started_at, limit, exit_code)
    return exit_code


def main() -> int:
    args = parse_args()
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f"auto_{args.job}.lock"

    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] {args.job} 上一轮仍在执行，本窗口跳过")
            return 0

        started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{started}] start {args.job}")
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"job={args.job}\nstarted_at={started}\n")
        lock_file.flush()

        if args.job == "claw":
            code = _run_claw(args)
        else:
            code = _run_composite(args)
        ended = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ended}] end {args.job}: exit={code}")
        return code


if __name__ == "__main__":
    raise SystemExit(main())

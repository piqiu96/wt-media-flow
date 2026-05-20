# scripts/

## sync_skills.py — Codex ↔ Claude skills 同步

```bash
# Codex → Claude（常用，把 .codex/skills/ 同步到 .claude/skills/）
.venv/bin/python3 scripts/sync_skills.py

# 预览不写入
.venv/bin/python3 scripts/sync_skills.py --dry-run

# 覆盖已有
.venv/bin/python3 scripts/sync_skills.py --force

# Claude → Codex（反向）
.venv/bin/python3 scripts/sync_skills.py --reverse
.venv/bin/python3 scripts/sync_skills.py --reverse --force

# 预览 + 覆盖
.venv/bin/python3 scripts/sync_skills.py --dry-run --force
```

| 参数 | 说明 |
|------|------|
| `--dry-run` | 只预览，不写文件 |
| `--force` | 覆盖已有 skill（默认跳过） |
| `--reverse` | 反向同步：claude → codex |

## auto_run.py — 定时任务总控

crontab 推荐调用总控脚本。它会对同类任务加锁：上一轮还没结束时，本轮直接跳过，避免下载限流时重复叠加。

总控直接调用项目正式入口：

- 采集：`src/main.py claw --category <游戏> --config conf/claw.yaml`
- 合成：`src/main.py composite --batch --category <游戏> --config conf/composite.yaml`

```bash
.venv/bin/python3 scripts/auto_run.py claw --max-games 2
.venv/bin/python3 scripts/auto_run.py composite --limit 50 --workers 4
```

crontab 示例见 `scripts/crontab.auto.example`。

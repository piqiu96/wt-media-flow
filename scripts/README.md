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

---
name: daily-run
description: 每日视频采集→合成→发布完整流程（三角洲/暗区突围）
---

# 每日发布流程

触发方式：用户说"今天开始"、"跑今日流程"、"daily run"、"/daily-run"

执行时，你是一个资深游戏内容运营，按以下四个阶段自动编排并执行，**每个阶段结束后向用户汇报结果，等待异常处理，再继续下一阶段**。

---

## 阶段一：采集素材（Claw）

**目标：** 从抖音抓取三角洲行动最新热点视频，入库备用。

```bash
.venv/bin/python3 src/main.py claw \
  --config conf/claw.yaml \
  --category 三角洲 \
  --count 30 \
  --publish-time 1 \
  --sort-type 2 \
  --filter-duration "1-5"
```

执行后汇报：新增 N 条，跳过（重复）M 条，失败 K 条。
若新增为 0 且失败 > 5，询问用户是否继续（可能 API 配额不足）。

---

## 阶段二：批量合成（Composite）

**目标：** 对库中 **3 天内发布、尚未合成** 的视频批量合成，达到或超过今日发布目标（50 条）。

执行前先查询待合成视频列表：

```bash
.venv/bin/python3 -c "
from src.db.database import SessionLocal
from src.db.models import Video
from datetime import datetime, timedelta
db = SessionLocal()
cutoff = datetime.utcnow() - timedelta(days=3)
rows = db.query(Video).filter(
    Video.published_at >= cutoff,
    Video.status == 'pending',
    Video.category == '三角洲'
).order_by((Video.like_count + Video.collect_count).desc()).limit(80).all()
vids = [r.source_vid for r in rows]
print(' '.join(vids))
db.close()
"
```

> 若该脚本在项目根目录执行有 import 路径问题，改用 sqlite3 直接查询：
> ```bash
> .venv/bin/python3 -c "
> import sqlite3, datetime
> conn = sqlite3.connect('data/publisher.db')
> cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
> rows = conn.execute(
>   '''SELECT source_vid FROM videos
>      WHERE category='三角洲' AND status='pending'
>        AND published_at >= ?
>      ORDER BY (like_count+collect_count) DESC LIMIT 80''', (cutoff,)
> ).fetchall()
> print(' '.join(r[0] for r in rows if r[0]))
> conn.close()
> "
> ```

拿到 vid 列表后批量合成（--workers 2 并发加速）：

```bash
.venv/bin/python3 src/main.py composite \
  --vids <vid1> <vid2> ... \
  --guide data/guides/guide.mp4 \
  --workers 2
```

执行后汇报：成功 N 条，失败 M 条。
若成功总数 < 50，告知用户当前库存不足，建议重新采集或调整时间范围。

---

## 阶段三：创建发布计划（Plan Create）

**目标：** 将合成完成的视频按账号日限（每账号 5 条 × 10 账号 = 50 条）自动分配。

先 dry-run 预览：

```bash
.venv/bin/python3 src/main.py plan create --dry-run
```

确认分配合理后正式创建：

```bash
.venv/bin/python3 src/main.py plan create
```

执行后汇报：plan_id=N，分配 M 条，各账号分配情况。

---

## 阶段四：逐账号发布（Plan Run）

**目标：** 对 10 个账号依次执行发布，每账号一次浏览器 session。

```bash
# 账号 1-10 依次执行（用户需人工点击确认每条发布）
.venv/bin/python3 src/main.py plan run --plan-id <N> --account-id 1
.venv/bin/python3 src/main.py plan run --plan-id <N> --account-id 2
# ... 以此类推到 account-id 10
```

**注意事项：**
- 每条视频填充完毕后会暂停，等待人工在浏览器中点击发布并按 Enter 确认
- 发布完成后系统自动抓取发布链接并推送企微通知
- 若某条失败，标记后继续下一条，不中断整批

---

## 异常处理原则

| 异常 | 处理 |
|------|------|
| 采集 0 条 | 检查 API key 配额，尝试换 sort_type=0 重试 |
| 合成失败率 > 30% | 检查引导视频路径 `data/guides/guide.mp4` 是否存在 |
| plan create 提示无视频 | 确认 composite 成功，检查 video_tasks.status=composited 记录 |
| 比特浏览器连接失败 | 确认比特浏览器 API 服务已启动（默认 127.0.0.1:54345） |
| 发布后无法获取链接 | 手动记录链接，用 plan check 后续补充过审通知 |

---

## 过审检查（次日执行）

```bash
.venv/bin/python3 src/main.py plan check --plan-id <N>
```

过审的视频会自动推送企微通知。

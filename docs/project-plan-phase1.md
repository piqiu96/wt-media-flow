# wt-media-flow 一期工程项目计划书

> 版本：v1.0 | 日期：2026-04-14

---

## 一、背景与目标

### 现状

系统已具备完整链路：

```
采集(claw) → 合成(composite) → 发布(publish) → 评论(comment)
```

但存在关键断点：
- 发布后无法自动获取文章 URL，评论链路只能人工操作
- 每次发布都单独开关浏览器，批量效率低
- 没有发布计划管理，账号分配全靠人工记忆

### 目标

构建**完整运营闭环**，人工每天只需约 30 分钟操作：

```
采集+合成（全自动） → 创建发布计划（全自动）
→ 批量发布（人工在浏览器逐一确认）
→ URL 自动回填 + 评论任务生成（全自动）
→ 批量评论（人工逐一确认）
```

---

## 二、架构设计

### 2.1 表职责划分

| 表 | 职责 | 状态范围 |
|----|------|---------|
| `video_tasks`（已有） | 内容生产生命周期，**只到合成完成** | pending / compositing / composited / failed |
| `publish_plans`（新增） | 批次计划（一天的发布任务集合） | pending / running / done |
| `plan_items`（新增） | 单条发布记录（账号 × 视频），**负责发布全流程** | pending / publishing / published / failed |
| `comment_tasks`（新增） | 评论任务队列，发布成功后自动创建 | pending / commenting / done / failed |

### 2.2 plan_items 状态机

```
                   plan run 开始执行
                         ↓
pending ──────────────→ publishing
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
          published              failed
    (写入 published_url,        (写入 error)
     自动创建 comment_tasks)
```

### 2.3 comment_tasks 状态机

```
            plan_item → published 时自动创建
                         ↓
pending ──────────────→ commenting
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
            done                 failed
```

### 2.4 核心规则

1. 一条 `video_task` 同一时刻只能被**一个** pending/publishing `plan_item` 引用（防重复发布）
2. `plan create` 只从**未被引用**的 composited 任务中选取
3. 评论账号 ≠ 发布账号（从同平台其他活跃账号随机分配）
4. `video_tasks.status` 不再追踪发布阶段，发布状态的权威来源是 `plan_items`

---

## 三、话术库设计

**方案：YAML 配置文件**，运营人员直接编辑，无需操作数据库。

路径：`conf/comment_templates.yaml`

```yaml
三角洲行动:
  - "这个打法真的太绝了，学到了！"
  - "感谢分享，收藏起来慢慢研究"
  - "操作骚气，求带！"
  - "这期内容质量很高，讲得很清楚"
  - "一直在找这种教学，终于找到了"

原神:
  - "这个阵容搭配有点厉害"
  - "学到了，马上去试试"
  - "感谢up，更新了这么多期了"

default:
  - "内容不错，收藏了！"
  - "讲得很好，感谢分享"
  - "质量很高，期待更新"
```

生成规则：取 `video_task.category` → 匹配 YAML key → 随机取一条 → 找不到则用 `default`。

---

## 四、命令设计

### `plan create` — 创建发布计划

```bash
python src/main.py plan create [--date today] [--dry-run]
```

执行逻辑：
1. 查所有 active 账号，按 `account.daily_limit` 确定每人当天发布配额
2. 从 `video_tasks.status=composited` 且无活跃 plan_item 的任务中，按 `category` 分配给各账号
3. 创建 `publish_plans` + `plan_items` 记录（含 order_idx）
4. 同时为每条 plan_item 预创建 `comment_tasks`（分配给不同账号，content 暂留空）
5. `--dry-run` 只打印预览，不写库

```
输出示例：
今日发布计划（2026-04-14）
账号: 战地游侠(id=1)  分配 5 条 [三角洲行动 ×5]
账号: 星河战士(id=2)  分配 5 条 [三角洲行动 ×3, 原神 ×2]
评论任务: 共 10 条（账号互评）
```

### `plan list` — 查看计划

```bash
python src/main.py plan list [--date today]
```

### `plan run` — 执行发布（批量）

```bash
python src/main.py plan run --plan-id 1 --account-id 1
```

执行流程（**一次浏览器 session**）：
1. `open_browser(profile_id)`
2. 按 order_idx 循环处理所有 pending plan_items：
   - `plan_item.status → publishing`
   - 导航到发布页，填充视频/标题/封面
   - **人工在浏览器确认发布**
   - CLI 等待确认（Enter=成功，`failed`=失败）
   - 导航到创作者后台，抓取 `published_url` 回填
   - 从话术库取评论内容，填充 `comment_task.content`
   - `plan_item.status → published`
   - 继续下一条
3. 全部完成后 `close_browser`

### `comment-batch` — 批量评论

```bash
python src/main.py comment-batch --account-id 2 [--date today]
```

执行流程（**一次浏览器 session**）：
1. 查 `comment_tasks.status=pending AND account_id=X`
2. `open_browser(profile_id)`
3. 循环：打开 `published_url` → 填入 `content` → 人工确认提交 → `status=done`
4. `close_browser`

---

## 五、关键技术实现

### 5.1 人工确认统一工具

```python
# src/utils/confirm.py
def wait_confirm(prompt: str = "操作完成后按 Enter 确认") -> bool:
    print(f"\n{'='*60}")
    print(f"  {prompt}")
    print("  Enter=确认成功 | 输入 failed=标记失败")
    print('='*60)
    try:
        return input("  > ").strip().lower() != "failed"
    except EOFError:
        # VSCode/非交互环境：固定等待 300s
        import time
        for r in range(300, 0, -10):
            print(f"  剩余等待: {r}s ...", flush=True)
            time.sleep(10)
        return True
```

### 5.2 发布后抓 published_url

```python
# src/plat/baijiahao/upload.py 新增
def fetch_latest_published_url(self) -> str:
    self.page.goto("https://baijiahao.baidu.com/builder/rc/home",
                   wait_until="domcontentloaded", timeout=30000)
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    # 取内容列表第一条链接（选择器待发布后调试确认）
    link = self.page.locator(
        '[class*="item"] a[href*="baijiahao"], '
        '[class*="article"] a[href*="baijiahao"]'
    ).first
    return link.get_attribute("href") or self.page.url
```

### 5.3 话术库随机取

```python
# src/utils/comment_helper.py
import yaml, random
from pathlib import Path

def get_random_comment(category: str,
                       templates_path: str = "conf/comment_templates.yaml") -> str:
    path = Path(templates_path)
    if not path.exists():
        return "内容不错，收藏了！"
    with open(path, encoding="utf-8") as f:
        tpl = yaml.safe_load(f) or {}
    pool = tpl.get(category) or tpl.get("default") or ["内容不错，收藏了！"]
    return random.choice(pool)
```

---

## 六、数据库变更

执行 `python src/main.py init` 自动建表：

| 新增表 | 关键字段 |
|--------|---------|
| `publish_plans` | id, name, date, status, created_at |
| `plan_items` | id, plan_id, account_id, video_task_id, order_idx, publish_status, published_url, error_message |
| `comment_tasks` | id, plan_item_id, account_id, url, content, status, error_message, created_at |

---

## 七、文件改动清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/db/models.py` | 修改 | 新增 `PublishPlan`, `PlanItem`, `CommentTask` 模型 |
| `src/db/repositories.py` | 修改 | 新增 `PlanRepository`, `PlanItemRepository`, `CommentTaskRepository` |
| `src/cmd/plan.py` | 新建 | create / list / run 子命令 |
| `src/cmd/comment.py` | 修改 | 升级增加 `comment-batch` 子命令 |
| `src/cmd/__init__.py` | 修改 | 注册新命令 |
| `src/plat/baijiahao/upload.py` | 修改 | 新增 `fetch_latest_published_url()` |
| `src/utils/confirm.py` | 新建 | 人工确认统一工具函数 |
| `src/utils/comment_helper.py` | 新建 | 话术库随机取 |
| `conf/comment_templates.yaml` | 新建 | 运营维护话术 |

---

## 八、验证流程

```bash
# 1. 初始化新表
.venv/bin/python3 src/main.py init

# 2. 预览计划（不写库）
.venv/bin/python3 src/main.py plan create --dry-run

# 3. 创建计划
.venv/bin/python3 src/main.py plan create

# 4. 查看计划
.venv/bin/python3 src/main.py plan list

# 5. 单账号批量发布
.venv/bin/python3 src/main.py plan run --plan-id 1 --account-id 1

# 6. 批量评论
.venv/bin/python3 src/main.py comment-batch --account-id 2
```

---

## 九、每日运营标准流程

```
07:00  定时采集 + 合成（全自动后台）

10:00  plan create
         └→ 自动分配视频给账号，生成发布顺序 + 评论任务 (~1min)

10:05  plan run --account-id 1
         └→ 5 个视频内容填充完毕，逐一等人工在浏览器确认发布 (~10min)
         └→ 每条发布后自动抓 URL、填充评论内容

10:15  plan run --account-id 2   (另开终端并行)
         ...

11:00  所有发布完成

11:05  comment-batch --account-id 2   (用账号2评论账号1发的视频)
11:10  comment-batch --account-id 1   (用账号1评论账号2发的视频)

总人工操作时间：~30-40 分钟/天
```

# wt-media-flow 架构重整实施方案

> 基于 [architecture-refactor.md](architecture-refactor.md) 的审判建议，结合当前系统现状制定的落地方案。
> 创建日期：2026-04-22

## Context

系统已跑通 MVP 全流程（采集→合成→发布→评论→通知），现在需要架构重整以支持：
- 多平台扩展（哔哩哔哩/快手）
- 不同平台的合成策略和发布策略
- 未来 Web 入口 + 定时任务 + 审核流程
- 生产环境可观测性

核心问题：cmd 层过厚（plan.py 702行直接操作 DB/Playwright/BitBrowser）、中间层空心、平台抽象不完整、浏览器管理散落。

## 方针

**三步走**：先简化瘦身 → 逐步迁移新分层并验证 → 最后抽象策略层

**采用 architecture-refactor.md 的最薄架构分层**，废弃现有 `processor/` + `service/` 目录名。

---

## 当前架构 vs 目标架构

### 当前架构

```
src/
├── main.py
├── cmd/                 # 命令层（过厚：plan.py 702行, composite.py 514行）
├── processor/           # 处理器（compositor.py 有用，其余薄包装）
├── service/             # 服务层（基本是 repo 包装，空心）
├── db/                  # 数据库（models + repositories）
├── library/             # 外部客户端（douyin_api, bit_api, video_util）
├── downloader/          # 下载器（douyin, bilibili）
├── plat/                # 平台发布（baijiahao 428行，bilibili/xhs stub）
└── utils/               # 工具函数
```

### 目标架构

```
src/
├── main.py                         # CLI 入口（保留）
├── conf/settings.py                # 配置（不变）
│
├── app/                            # 应用入口层
│   └── cli/                        # argparse 命令（从 cmd/ 迁入，只做参数解析）
│       ├── __init__.py             # BaseCommand + @register_command + 自动导入
│       ├── plan.py                 # ~80行：解析参数 → 调 workflows
│       ├── composite.py            # ~80行
│       ├── claw.py                 # ~60行
│       ├── comment.py              # ~60行
│       └── ...                     # account, video, cleanup, download, setup, init_db, pipeline
│
├── workflows/                      # 流程编排层
│   ├── __init__.py
│   ├── publish_workflow.py         # 单账号发布流程
│   ├── plan_workflow.py            # 计划 create/list/reset-failed/check
│   ├── composite_workflow.py       # 合成流程（单条/批量/重合成）
│   ├── claw_workflow.py            # 采集流程（入库+下载）
│   └── comment_workflow.py         # 评论流程（batch/fire）
│
├── services/                       # 业务服务层（真正承接业务逻辑）
│   ├── __init__.py
│   ├── publish_service.py          # 发布动作：prepare_item / mark_success / mark_fail
│   ├── plan_service.py             # 计划分配逻辑 + 查询
│   ├── composite_service.py        # 合成任务管理（创建/重置/状态流转）
│   ├── video_service.py            # 素材查询/过滤/下载
│   └── browser_session_service.py  # BitBrowser + Playwright 会话管理
│
├── platforms/                      # 平台适配层（从 plat/ 迁移+增强）
│   ├── __init__.py                 # PlatformRegistry
│   ├── base.py                     # PublisherProtocol + CommenterProtocol + Capabilities + PublishPayload
│   ├── registry.py                 # 注册表实现
│   ├── baijiahao/
│   │   ├── __init__.py
│   │   ├── publisher.py            # fill_form / submit / fetch_url（从 bjh.py 拆出）
│   │   ├── commenter.py            # fill_comment / submit_comment（从 bjh.py 拆出）
│   │   └── mapper.py               # 标题处理/封面下载缩放（从 plan.py/composite.py 收拢）
│   ├── bilibili/
│   │   ├── __init__.py
│   │   ├── publisher.py
│   │   └── mapper.py
│   └── xiaohongshu/
│       └── ...
│
├── infra/                          # 基础设施层
│   ├── db/                         # 从 db/ 迁入
│   │   ├── database.py
│   │   ├── models.py
│   │   └── repositories.py
│   ├── browser/                    # BitBrowser API 封装（从 library/bit_api.py 迁入）
│   │   └── bit_api.py
│   ├── media/                      # FFmpeg 合成引擎 + 视频工具
│   │   ├── compositor.py           # 从 processor/compositor.py 迁入
│   │   └── video_util/             # 从 library/video_util/ 迁入
│   ├── http/                       # 外部 API 客户端
│   │   └── douyin_api.py           # 从 library/douyin_api.py 迁入
│   └── downloader/                 # 下载器（从 downloader/ 迁入）
│       ├── __init__.py
│       ├── douyin.py
│       └── bilibili.py
│
└── utils/                          # 工具函数（保留，增强日志）
    ├── log.py                      # 增强：结构化日志 + trace context
    ├── wecom.py
    ├── anti_risk.py
    ├── comment_helper.py
    ├── confirm.py
    ├── random_utils.py
    └── tool_finder.py
```

**废弃目录**：`cmd/`、`processor/`、`service/`、`plat/`、`library/`、`downloader/`、`db/`（内容全部迁移到新位置）

---

## 第一期：瘦身简化

> 目标：建立新目录骨架，把最厚的 plan.py 发布链路搬迁到 workflows + services + platforms，验证新分层可正常工作。其他命令暂时保持原样。

### Step 1.1：搭建骨架 + 基础设施迁移

创建新目录结构，把底层模块原样搬迁（改 import 路径但不改逻辑）。

| 操作 | 源 | 目标 | 说明 |
|------|-----|------|------|
| 迁移 | `src/db/` | `src/infra/db/` | database.py, models.py, repositories.py 原样迁移 |
| 迁移 | `src/library/bit_api.py` | `src/infra/browser/bit_api.py` | 原样迁移 |
| 迁移 | `src/library/douyin_api.py` | `src/infra/http/douyin_api.py` | 原样迁移 |
| 迁移 | `src/processor/compositor.py` | `src/infra/media/compositor.py` | 原样迁移 |
| 迁移 | `src/library/video_util/` | `src/infra/media/video_util/` | 原样迁移 |
| 迁移 | `src/downloader/` | `src/infra/downloader/` | 原样迁移 |
| 新建 | - | `src/app/cli/__init__.py` | 从 cmd/__init__.py 复制，修改 import 路径 |
| 新建 | - | `src/workflows/__init__.py` | 空 |
| 新建 | - | `src/services/__init__.py` | 空 |
| 新建 | - | `src/platforms/__init__.py` | 空 |

**兼容方案**：在旧目录放置 re-export 模块（`from infra.db.models import *`），确保未迁移的命令仍能 `from db.models import ...`。迁移完成后删除。

**验证**：
```bash
.venv/bin/python3 -c "from infra.db.models import Video; print('OK')"
.venv/bin/python3 -c "from infra.media.compositor import VideoCompositor; print('OK')"
.venv/bin/python3 src/main.py claw --help  # 旧命令仍可用
```

### Step 1.2：BrowserSessionService（最痛点）

从 plan.py / comment.py 中提取浏览器会话管理。

**新建**：`src/services/browser_session_service.py`

```python
@dataclass
class BrowserSession:
    profile_id: str
    browser: Browser          # playwright Browser
    context: BrowserContext
    debug_port: str

class BrowserSessionService:
    """统一管理 BitBrowser + Playwright 生命周期"""

    def __init__(self):
        self._bit_api = BitBrowserAPI()

    def open(self, profile_id: str) -> BrowserSession:
        """打开比特浏览器 → 连接 CDP → 挂诊断监听 → 清理残留 Tab"""
        # 从 plan.py L317-353 搬迁
        browser_info = self._bit_api.open_browser(profile_id)
        debug_port = browser_info["data"]["http"]
        ...
        return BrowserSession(profile_id, browser, ctx, debug_port)

    def new_page(self, session: BrowserSession, reuse_first: bool = False) -> Page:
        """创建或复用页面"""

    def close(self, session: BrowserSession):
        """关闭 Playwright → 关闭 BitBrowser"""
        browser.close()
        self._bit_api.close_browser(session.profile_id)
```

**提取来源**：
- `cmd/plan.py` L317-353 — BitBrowser 启动 + CDP 连接 + DIAG 监听
- `cmd/plan.py` L349-353 — 残留 Tab 清理
- `cmd/plan.py` L398-414 — new_page / reuse 逻辑
- `cmd/plan.py` L526-530 — 关闭逻辑

### Step 1.3：platforms 三段式 + 百家号拆分

定义平台统一协议，把 bjh.py 按协议拆分。

**新建**：`src/platforms/base.py`

```python
@dataclass
class PlatformCapabilities:
    supports_video: bool = True
    supports_cover_upload: bool = False
    supports_comment: bool = False
    requires_manual_confirm: bool = True
    allows_same_source_reuse: bool = False  # 合成策略相关

@dataclass
class PublishPayload:
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cover_path: str | None = None
    topic: str | None = None
    category: str = ""

class FillResult(TypedDict):
    success: bool
    error: str | None

class PublisherProtocol(Protocol):
    platform_name: str
    capabilities: PlatformCapabilities

    def fill_form(self, page: Page, payload: PublishPayload) -> FillResult: ...
    def submit(self, page: Page) -> dict: ...
    def fetch_published_url(self, page: Page, known_urls: set[str]) -> str: ...

class CommenterProtocol(Protocol):
    platform_name: str

    def fill_comment(self, page: Page, url: str, content: str) -> dict: ...
    def submit_comment(self, page: Page) -> dict: ...
```

**新建**：`src/platforms/registry.py`

```python
class PlatformRegistry:
    _publishers: dict[str, type] = {}
    _commenters: dict[str, type] = {}

    @classmethod
    def register(cls, platform_name, publisher_cls, commenter_cls=None): ...

    @classmethod
    def get_publisher(cls, name) -> PublisherProtocol: ...

    @classmethod
    def get_commenter(cls, name) -> CommenterProtocol: ...

    @classmethod
    def get_capabilities(cls, name) -> PlatformCapabilities: ...
```

**拆分** `plat/baijiahao/bjh.py`(428行) 为：

| 新文件 | 来源 | 说明 |
|--------|------|------|
| `platforms/baijiahao/publisher.py` | bjh.py L45-135, L150-203 | fill_form 接收 `(page, payload)` 而非散装参数；submit 百家号为人工确认空操作 |
| `platforms/baijiahao/commenter.py` | bjh.py L205-295, L297-352 | 拆为 fill_comment + submit_comment 两步 |
| `platforms/baijiahao/mapper.py` | plan.py L372-396 | 封面下载+缩放逻辑收拢到此 |

**验证**：
```bash
.venv/bin/python3 -c "
from platforms.registry import PlatformRegistry
pub = PlatformRegistry.get_publisher('baijiahao')
print(pub.capabilities)
"
```

### Step 1.4：PublishWorkflow（最大搬迁）

把 plan.py `_run()` 方法(L263-571)拆解到 workflow + service。

**新建**：`src/services/publish_service.py`

```python
class PublishService:
    """发布业务操作（状态流转 + 数据持久化）"""

    def get_pending_items(self, plan_id, account_id) -> list[PlanItem]: ...
    def resolve_browser_profile(self, account) -> str: ...
    def prepare_payload(self, item, vt, platform_name) -> PublishPayload:
        """构建发布载荷，包括封面下载缩放（调用平台 mapper）"""
    def start_publish(self, item_id): ...
    def complete_publish(self, item_id, url): ...
    def fail_publish(self, item_id, error): ...
    def create_comment_task(self, item, account_id, url): ...
    def send_report(self, plan_id, account_name, results): ...
```

**新建**：`src/workflows/publish_workflow.py`

```python
class PublishWorkflow:
    """单账号发布流程编排 — 从 plan.py _run() 搬迁"""

    def __init__(self):
        self.publish_svc = PublishService()
        self.browser_svc = BrowserSessionService()

    def execute(self, plan_id: int, account_id: int) -> dict:
        # 1. 查询待发布 items + 校验
        items = self.publish_svc.get_pending_items(plan_id, account_id)
        profile_id = self.publish_svc.resolve_browser_profile(account)
        publisher = PlatformRegistry.get_publisher(account.platform)

        # 2. 打开浏览器会话
        session = self.browser_svc.open(profile_id)
        try:
            # 3. 阶段1：逐条填充
            filled = []
            for item in items:
                page = self.browser_svc.new_page(session)
                payload = self.publish_svc.prepare_payload(item, vt, account.platform)
                result = publisher.fill_form(page, payload)
                if result["success"]:
                    filled.append((item, page, vt))

            # 4. 阶段2：逐条人工确认 + 回链
            for item, page, vt in filled:
                self.publish_svc.start_publish(item.id)
                success = wait_confirm("人工点击发布后按 Enter")
                if success:
                    url = publisher.fetch_published_url(page, known_urls)
                    self.publish_svc.complete_publish(item.id, url)
                    self.publish_svc.create_comment_task(item, account_id, url)
                else:
                    self.publish_svc.fail_publish(item.id, "人工标记失败")

            # 5. 发送通知
            self.publish_svc.send_report(plan_id, account.name, results)
        finally:
            self.browser_svc.close(session)
```

**新建**：`src/workflows/plan_workflow.py`

```python
class PlanWorkflow:
    def create(self, date="today", dry_run=False) -> dict:
        """从 plan.py _create() 搬迁"""
    def list_plans(self, date=None) -> dict:
        """从 plan.py _list() 搬迁"""
    def reset_failed(self, plan_id, account_id=None) -> dict:
        """从 plan.py _reset_failed() 搬迁"""
    def check(self, plan_id) -> dict:
        """从 plan.py _check() 搬迁"""
```

**瘦身**：`cmd/plan.py` → `app/cli/plan.py`（702行 → ~80行）

```python
@register_command
class PlanCommand(BaseCommand):
    command_name = "plan"
    def setup_parser(self, parser): ...  # 参数定义保持不变
    def execute(self, args):
        if action == "create":
            return PlanWorkflow().create(date=args.date, dry_run=args.dry_run)
        elif action == "run":
            return PublishWorkflow().execute(plan_id=args.plan_id, account_id=args.account_id)
        elif action == "list":
            return PlanWorkflow().list_plans(date=args.date)
        # ...
```

**验证**：
```bash
.venv/bin/python3 src/main.py plan create --dry-run
.venv/bin/python3 src/main.py plan list
.venv/bin/python3 src/main.py plan run --plan-id <id> --account-id 1
```

### Step 1.5：其余命令迁移 + 日志增强

把 composite/claw/comment 命令同样搬迁到 workflows，完成 cmd/ → app/cli/ 全部迁移。

**新建**：
- `src/workflows/composite_workflow.py` — 从 composite.py 抽出 _composite_by_vid / _composite_by_vids / _recomposite_recent
- `src/workflows/claw_workflow.py` — 封装 ClawProcessor 调用
- `src/workflows/comment_workflow.py` — 从 comment.py 抽出 batch/fire 逻辑
- `src/services/composite_service.py` — VideoTask 创建/状态流转/下载管理
- `src/services/video_service.py` — 素材查询/过滤

**迁移**：所有 `src/cmd/*.py` → `src/app/cli/*.py`，每个只保留参数解析

**增强日志**：`src/utils/log.py`

```python
import contextvars

trace_ctx = contextvars.ContextVar('trace_ctx', default={})

def with_context(**kwargs):
    """设置链路上下文：plan_id, account_id, item_id"""
    ctx = trace_ctx.get().copy()
    ctx.update(kwargs)
    trace_ctx.set(ctx)

class ContextFilter(logging.Filter):
    def filter(self, record):
        ctx = trace_ctx.get()
        for key in ('plan_id', 'account_id', 'item_id'):
            setattr(record, key, ctx.get(key, '-'))
        return True

# 格式：[2026-04-22 14:00:00] INFO plan=3 acc=1 item=12 publish_workflow -- 填充完成
```

**清理**：删除旧目录原始文件（保留 re-export 兼容层直到全部迁移完成后删除）

**修改** `src/main.py`：import 路径从 `cmd` 改为 `app.cli`

**验证**：全流程回归测试
```bash
.venv/bin/python3 src/main.py claw --category 三角洲 --config conf/claw.yaml
.venv/bin/python3 src/main.py composite --vid <vid> --config conf/composite.yaml --category 三角洲
.venv/bin/python3 src/main.py plan create
.venv/bin/python3 src/main.py plan run --plan-id <id> --account-id 1
.venv/bin/python3 src/main.py comment fire --account-id 1
.venv/bin/python3 src/main.py plan check --plan-id <id>
grep "plan=" log/publisher.log  # 验证结构化日志
```

---

## 第二期：多平台迁移验证

> 目标：接入哔哩哔哩平台，验证 platforms 抽象和 workflow 分层在真正多平台场景下能跑通。

### Step 2.1：数据模型增强

**改动**：`src/infra/db/models.py`

```python
class PlanItem(Base):
    # ... 现有字段 ...
    platform = Column(String(50), default="baijiahao")        # 新增：目标平台
    publish_mode = Column(String(30), default="manual_confirm") # 新增：发布模式

class VideoTask(Base):
    # ... 现有字段 ...
    target_platform = Column(String(50), nullable=True)        # 新增：允许同素材多平台
```

**改动**：`src/app/cli/init_db.py` — 增加 ALTER TABLE 迁移

### Step 2.2：哔哩哔哩平台实现

**新建**：
- `src/platforms/bilibili/publisher.py` — 实现 PublisherProtocol
- `src/platforms/bilibili/mapper.py` — 哔哩哔哩标题格式/分区映射/标签处理
- `src/platforms/bilibili/commenter.py`（可选，优先级低）

**改动**：`src/platforms/registry.py` — 注册哔哩哔哩

### Step 2.3：plan create 多平台分配

**改动**：`src/workflows/plan_workflow.py`

```python
# 当前：account.platform 全是 baijiahao，只按 tag 匹配品类
# 新增：按 account.platform 查对应 capabilities
#   - baijiahao: allows_same_source_reuse=False → source_vid 粒度去重
#   - bilibili: allows_same_source_reuse=True → 同素材可多次分配
```

### Step 2.4：composite 多平台策略

**改动**：`src/workflows/composite_workflow.py`

```python
# 百家号：一个 source_vid 只合成一次
# 哔哩哔哩：同 source_vid 每次用不同去重种子重新合成
caps = PlatformRegistry.get_capabilities(target_platform)
if caps.allows_same_source_reuse:
    # 不做 source_vid 去重检查，每次全新 dedup 参数
    ...
```

**验证**：
```bash
# 1. 添加哔哩哔哩测试账号
.venv/bin/python3 src/main.py account add --platform bilibili --browser-id 1 --tag 三角洲

# 2. plan create 能同时为百家号和哔哩哔哩账号分配
.venv/bin/python3 src/main.py plan create --dry-run

# 3. plan run 对哔哩哔哩使用正确的发布流程
.venv/bin/python3 src/main.py plan run --plan-id <id> --account-id <bili_acc_id>
```

---

## 第三期：策略抽象 + 生产化

> 目标：把多平台差异正式抽象为策略接口，并为 Web/定时预留入口。

### Step 3.1：策略层正式化

**新建**：`src/strategies/`（第二期中内联在 workflow 里的平台差异逻辑提取到独立策略类）

```python
# src/strategies/composite_strategy.py
class CompositeStrategy(Protocol):
    def can_composite(self, video: Video, platform: str) -> bool: ...
    def get_dedup_params(self) -> dict: ...

# src/strategies/publish_strategy.py
class PublishStrategy(Protocol):
    def build_payload(self, vt: VideoTask, account: Account) -> PublishPayload: ...
    def should_auto_submit(self) -> bool: ...
```

### Step 3.2：Web API 入口

**新建**：`src/app/api.py` — FastAPI 路由

```python
@router.post("/plans")
async def create_plan(req: CreatePlanRequest):
    return PlanWorkflow().create(date=req.date, dry_run=req.dry_run)

@router.post("/plans/{plan_id}/run")
async def run_plan(plan_id: int, account_id: int):
    return PublishWorkflow().execute(plan_id=plan_id, account_id=account_id)

@router.get("/videos")
async def list_videos(category: str = None, status: str = None):
    return VideoService().list(category=category, status=status)
```

### Step 3.3：素材审核 + 定时任务

- Video 模型增加 `review_status`（pending_review / approved / rejected）
- 采集后默认 pending_review，Web 端审核后变 approved
- APScheduler 或 cron 调用 workflow 层

---

## 关键设计决策

### 1. re-export 兼容层过渡

迁移期间，在旧目录放置 re-export 文件：
```python
# src/db/__init__.py（过渡期）
from infra.db.database import *
from infra.db.models import *
from infra.db.repositories import *
```

所有命令迁移完成后删除旧目录。

### 2. workflow 不依赖 argparse

workflow 方法签名全部使用普通参数（int, str, bool），不接收 `args` 对象。这样 CLI、API、定时任务都能直接调用。

### 3. 平台层不碰 ORM 模型

平台层通过 PublishPayload DTO 接收数据，不直接 import VideoTask/PlanItem。这样平台实现可以独立开发和测试。

### 4. Session 管理

当前各 workflow 内部 `SessionLocal()` + try/finally。暂时保持这个模式，第三期引入 FastAPI 时再考虑依赖注入。

---

## 不变的部分

- `src/conf/settings.py` — 配置结构
- `src/processor/compositor.py`（内容迁移到 infra/media/，逻辑不变）
- `src/processor/claw_processor.py`（内容迁移到 workflows/claw_workflow.py，逻辑不变）
- `src/db/repositories.py`（迁移到 infra/db/，仅按需新增方法）
- `src/db/models.py`（迁移到 infra/db/，第二期增加字段）
- `src/utils/` — 工具函数逻辑不变（log.py 增强格式）
- `conf/*.yaml` — 配置文件格式不变
- `data/` — 数据目录结构不变

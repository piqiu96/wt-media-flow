# wt-media-flow 架构重整建议

## 目标

这份文档不是重新发明一套空中楼阁，而是基于当前项目的真实现状，整理出一版适合继续演进的架构分层。

核心目标：

1. 让采集、下载、合成、计划、发布、评论几个阶段边界清晰。
2. 让多平台发布成为标准扩展点，而不是每加一个平台就复制一套大流程。
3. 让浏览器自动化从命令层剥离，降低 `plan run` 这类链路的脆弱性。
4. 为后续扩展到哔哩哔哩、百家号、小红书之外的平台留出统一接口。

---

## 当前项目的真实问题

当前目录已经有分层雏形，但实际运行时仍然存在几个结构性问题：

- `cmd` 层过厚，直接操作数据库、浏览器、Playwright、平台页面逻辑。
- `processor` 和 `service` 有一部分只是“转发层”，没有真正承接业务规则。
- 平台发布逻辑和任务编排强耦合，尤其是人工确认 + 多 Tab + 长时间会话保持这一段。
- `pipeline`、`publish`、`plan run` 三条链路的职责重叠，导致状态模型不够统一。
- 平台抽象不完整，目前更像“文件隔离”，还不是“能力隔离”。

所以后续不是简单继续堆功能，而是要先把“流程编排”和“平台执行”拆开。

---

## 建议的新分层

建议把项目收敛成下面这套分层：

```text
src/
├── app/               # 应用入口层（CLI/API/定时任务入口）
├── orchestrator/      # 流程编排层：采集流、合成流、发布流、评论流
├── domain/            # 领域模型、状态机、业务规则
├── services/          # 用例服务：视频、计划、发布、评论、账号、素材
├── infra/             # 基础设施：db、bitbrowser、playwright、http、ffmpeg、downloader
├── platforms/         # 平台适配器：baijiahao / bilibili / xiaohongshu / ...
├── repositories/      # 仓储接口或实现
├── schemas/           # DTO / 配置对象 / 输入输出对象
├── utils/             # 纯工具函数
└── conf/              # 配置
```

如果你不想一次性大改目录，也可以先保留原目录名，但职责按这个思路重排。

---

## 每层职责

### 1. `app` 入口层

只做这些事：

- 解析命令行参数
- 组装依赖
- 调用具体用例
- 打印结果

不应该再做：

- 数据库查询
- Playwright 操作
- 比特浏览器生命周期管理
- 平台页面细节

对应当前项目，`src/cmd/*` 未来应该逐步收缩到这一层。

### 2. `orchestrator` 流程编排层

它负责“流程顺序”，不负责“页面细节”。

典型编排器：

- `ClawWorkflow`
- `CompositeWorkflow`
- `PlanWorkflow`
- `PublishWorkflow`
- `CommentWorkflow`

例如 `PublishWorkflow` 只关心：

1. 取待发布计划项
2. 锁定条目
3. 获取账号和平台
4. 调用平台执行器完成“填充/提交/回链”
5. 更新状态
6. 创建评论任务

它不应该关心：

- 百家号上传按钮长什么样
- 哔哩哔哩标题框 selector 是什么
- 当前 Playwright page 是否需要 `bring_to_front`

### 3. `domain` 领域层

这里放业务规则和状态机，不掺杂 IO。

建议重点抽离：

- `VideoTaskStatus`
- `PlanItemStatus`
- `CommentTaskStatus`
- 发布任务允许的状态流转
- “一个 source_vid 是否允许再次进入计划”
- “发布成功后是否立即派生评论任务”
- “失败是否允许重试，重试条件是什么”

这一层的价值是：把你项目真正复杂的地方从脚本式代码里拎出来。

### 4. `services` 用例服务层

这一层承接“一个可理解的业务动作”。

建议拆成：

- `VideoService`
- `MaterialService`
- `CompositeService`
- `PlanService`
- `PublishService`
- `CommentService`
- `AccountService`
- `BrowserSessionService`

这里的 service 是真正有业务含义的 service，不只是 repo 包装器。

例子：

- `PublishService.prepare_plan_item(...)`
- `PublishService.mark_publish_success(...)`
- `PlanService.create_daily_plan(...)`
- `CompositeService.create_or_reset_video_task(...)`

### 5. `infra` 基础设施层

这一层封装所有外部依赖：

- SQLite / SQLAlchemy
- BitBrowser API
- Playwright
- FFmpeg / ffprobe
- requests / 外部 HTTP API
- downloader

建议至少拆出：

- `infra/db/`
- `infra/browser/`
- `infra/media/`
- `infra/http/`
- `infra/downloader/`

这样将来哪怕不用 BitBrowser，改 Puppeteer 或纯 Playwright，也不需要改业务层。

### 6. `platforms` 平台适配层

这是未来扩展哔哩哔哩、小红书、百家号、知乎、视频号的核心。

每个平台应该实现统一协议，而不是各自自由发挥。

---

## 多平台发布的统一抽象

建议定义三层接口。

### A. 平台能力声明

```python
class PlatformCapabilities:
    supports_video_publish: bool
    supports_cover_upload: bool
    supports_comment: bool
    supports_like: bool
    requires_manual_confirm: bool
```

作用：

- 发布流程在运行前就知道平台支持什么
- 避免把“是否支持封面”“是否支持评论”散落在 if/else 里

### B. 平台执行器接口

```python
class PublisherPlatform(Protocol):
    name: str

    def fill_form(self, session, payload) -> FillResult: ...
    def submit(self, session) -> SubmitResult: ...
    def fetch_published_url(self, session, context) -> FetchUrlResult: ...
    def comment(self, session, payload) -> CommentResult: ...
```

这里最关键的是把 `fill_form`、`submit`、`fetch_published_url` 分开。

原因：

- 百家号现在就是“先填，再人工发布，再回抓链接”
- 哔哩哔哩未来可能也需要“填完等待人工确认”
- 有些平台可以全自动提交，有些不行

统一拆开以后，流程就能配置化。

### C. 平台载荷对象

```python
class PublishPayload(BaseModel):
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = []
    cover_path: str | None = None
    topic: str | None = None
    schedule_at: datetime | None = None
```

不要直接把数据库模型传给平台层。

原因：

- 平台层不应该知道 `VideoTask`/`PlanItem` 的 ORM 细节
- DTO 更稳定，也更方便测试

---

## 浏览器层重整建议

这是当前最该先动刀的地方。

### 现状问题

当前 `plan run` 中：

- 一个浏览器上下文承载多个待发布项
- 每条创建一个 Tab
- 填充阶段和人工确认阶段共用同一批 page 引用
- 一旦 context 断开，整批任务都被连带打挂

### 新建议

引入 `BrowserSessionManager`，统一管理三件事：

1. 打开和关闭 BitBrowser
2. 创建和恢复 Playwright context
3. 为单个发布任务提供隔离 page

推荐模式：

#### 模式 1：单任务单页面

- 每个 `PlanItem` 获取自己的 page
- 填充完成后立即进入确认
- 完成后立刻释放 page

优点：

- 最稳
- 最容易恢复
- 最适合当前人工确认场景

缺点：

- 吞吐量低

#### 模式 2：单账号单会话，单任务顺序执行

- 一个账号对应一个 BitBrowser 会话
- 但同一时刻只处理一个发布条目
- 不再提前批量填充多个 Tab

这比你当前“先填充一批，再逐条确认”更稳很多，是最推荐的过渡方案。

### 不建议继续保留的模式

- 同一 context 长时间挂多个待确认标签页
- 把 `Page` 对象存活跨越多轮人工操作
- 在命令层直接控制 `new_page()/bring_to_front()/goto()`

---

## 发布流程的推荐拆法

建议把一个发布动作拆成下面几个标准步骤：

```text
select item
-> lock item
-> build payload
-> open browser session
-> fill platform form
-> wait/submit
-> fetch published url
-> persist status
-> create comment task
-> release resources
```

落地到代码，可以是：

```text
PublishWorkflow
  -> PublishService
    -> BrowserSessionService
    -> PlatformRegistry
    -> PlanRepository / VideoTaskRepository / CommentTaskRepository
```

这会比当前 `cmd/plan.py` 一把梭可维护得多。

---

## 适合未来扩展哔哩哔哩的结构

你项目里其实已经有一个初版 B 站发布器，但它现在还比较薄，更多像样例实现。

后续扩展哔哩哔哩，建议按下面能力拆：

### 平台目录结构建议

```text
src/platforms/bilibili/
├── publisher.py        # 发布器主入口
├── selectors.py        # 页面选择器
├── validators.py       # 页面状态检查、登录检查
├── mapper.py           # 平台字段映射
└── models.py           # 平台特有返回值/参数
```

百家号、小红书也同样处理。

### 为什么这样拆

因为页面自动化的变化最频繁的是：

- selector
- 页面就绪判断
- 提交后的回链逻辑

把这些和“发布流程主逻辑”拆开，页面改版时只需要改平台内部。

### 哔哩哔哩未来通常要支持的能力

- 视频上传
- 标题填写
- 简介填写
- 标签填写
- 封面上传
- 分区/话题选择
- 定时发布
- 发布成功后的稿件链接回填

这些能力不需要一开始全部做完，但接口最好先留出来。

---

## 数据模型建议

当前 `videos / video_tasks / plan_items / comment_tasks` 这套思路是对的，不用推翻。

建议增强而不是重建。

### 1. `video_tasks`

保留为“素材处理任务”。

建议职责：

- 记录合成前后的文件信息
- 记录处理状态
- 保留平台无关的发布输入快照

建议新增或强化字段：

- `input_path`
- `output_path`
- `payload_snapshot`
- `last_error_code`
- `retry_count`

### 2. `plan_items`

保留为“账号 × 视频任务 × 平台发布动作”。

建议强化：

- `platform`
- `publish_mode`，如 `manual_confirm` / `auto_submit`
- `session_key`
- `attempt_no`
- `published_url`
- `platform_result`

这样以后同一个 `video_task` 发多个平台会更自然。

### 3. `publish_records`（建议新增）

如果你后面平台越来越多，建议新增独立发布记录表，保存每次尝试的细节。

作用：

- 一条计划项可以有多次尝试
- 便于追踪失败原因
- 不污染主状态表

---

## 推荐的状态机

### PlanItem 发布状态

```text
PENDING
-> PREPARING
-> FILLED
-> WAITING_CONFIRM
-> SUBMITTING
-> PUBLISHED
-> URL_FETCHED
-> DONE

异常分支：
PREPARING/FILLED/SUBMITTING -> FAILED
WAITING_CONFIRM -> CANCELLED / FAILED
```

你当前状态过于粗，只靠 `pending / publishing / published / failed` 很难准确恢复流程。

特别是人工确认场景，`WAITING_CONFIRM` 非常有必要。

---

## 迁移路线

建议分三期做，不要一次重构到底。

### 第一阶段：止血

目标：先让发布链路稳定下来。

建议动作：

1. `plan run` 改成“单账号单会话、单条顺序处理”，取消批量 Tab 预填充。
2. 抽出 `PublishWorkflow`，把 `cmd/plan.py` 里的发布主逻辑搬进去。
3. 抽出 `BrowserSessionManager`，统一管理 BitBrowser + Playwright。
4. 平台层统一成 `fill_form / submit / fetch_published_url` 三段式。
5. 移除配置里的硬编码 webhook，全部改读环境变量。

这一阶段不要求目录大改，但能显著提升稳定性。

### 第二阶段：收口职责

目标：让层级名副其实。

建议动作：

1. `cmd` 只保留参数解析和结果输出。
2. 让 `service` 真正承接业务动作，不再只是 repo 包装。
3. 让 `repository` 只做数据访问，不做业务语义判断。
4. 把平台页面逻辑从命令层彻底移除。
5. 把平台相关 DTO 抽出来。

### 第三阶段：多平台能力平台化

目标：让新平台接入成本明显下降。

建议动作：

1. 引入 `PlatformRegistry`
2. 每个平台实现统一接口
3. 平台能力配置化
4. 发布策略可配置：自动提交 / 人工确认 / 只填充
5. 同一 `video_task` 支持面向多个平台创建 `plan_item`

---

## 我建议你下一步优先做什么

如果你准备继续迭代，我建议优先级这样排：

1. 先改发布编排，不要再批量保活多个 Tab。
2. 再把平台抽象重做成三段式接口。
3. 然后把百家号和哔哩哔哩都接到统一发布器上。
4. 最后再处理更大的目录重整和状态模型细化。

原因很简单：

- 当前最痛的是稳定性，不是目录美观。
- 先把发布流程从“脚本堆砌”升级成“可恢复的工作流”，你后面扩平台才不会越扩越乱。

---

## 一个适合你当前项目的最小可行结构

如果只做最小重整，我建议先变成这样：

```text
src/
├── app/
│   └── cli/
├── workflows/
│   ├── publish_workflow.py
│   ├── plan_workflow.py
│   └── composite_workflow.py
├── services/
│   ├── publish_service.py
│   ├── plan_service.py
│   ├── browser_session_service.py
│   └── video_service.py
├── platforms/
│   ├── base.py
│   ├── registry.py
│   ├── baijiahao/
│   ├── bilibili/
│   └── xiaohongshu/
├── infra/
│   ├── db/
│   ├── browser/
│   ├── media/
│   └── http/
├── db/
└── utils/
```

这是我认为对你现在最现实、最能落地的一版。

---

## 结论

这项目后续要扩到哔哩哔哩等更多平台，关键不在于“再写一个 upload.py”，而在于先把下面三件事做对：

1. 发布流程从命令脚本中抽出来。
2. 浏览器会话和平台页面操作从业务流程中解耦。
3. 平台能力用统一协议接入。

做完这三步之后：

- 百家号可以更稳
- 哔哩哔哩可以更自然地扩
- 小红书也不会再成为另一套平行宇宙代码

这才是适合继续长期迭代的架构基础。

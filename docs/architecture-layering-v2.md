# wt-media-flow 新架构分层方案（V2.1）

> 日期：2026-04-20  
> 适用场景：本地 CLI 自动化工具（非 WebServer）  
> 目标：让“采集→合成→发布→评论”链路更清晰、更稳、更好改。

---

## 1. 先明确边界

这个项目当前不是 Web 服务，而是“本地任务工具”：
- 输入：命令行参数 + YAML 配置
- 执行：本地下载、FFmpeg 合成、Playwright 自动化发布
- 输出：终端日志 + SQLite 状态 + 通知

所以分层的目的不是做 Controller/HTTP，而是：
- 把“命令行入口”和“业务流程”拆开
- 把“业务规则”和“技术实现”拆开
- 让流程可测试、可回归、可扩展

---

## 2. 分层模型（工具型架构）

采用四层，但按 CLI 工具语义定义：

1. `interfaces`：命令入口层（CLI）
2. `application`：流程编排层（UseCase）
3. `domain`：业务规则层（状态机/策略）
4. `infrastructure`：技术实现层（DB/API/浏览器/下载器）

依赖方向：

`interfaces -> application -> domain <- infrastructure`

规则：
- `interfaces` 不直接碰数据库和第三方 API
- `domain` 不 import SQLAlchemy/Playwright/requests
- `application` 负责“串流程”，不写平台细节

---

## 3. 每层具体做什么

### 3.1 interfaces（CLI 命令层）

建议目录：`src/interfaces/cli/commands/`

做：
- 参数解析与基础校验
- 调用一个 usecase
- 把结果打印成 CLI 文本

不做：
- 直接 `SessionLocal()`、直接改模型状态
- 直接写 Playwright 上传流程

当前迁移来源：
- `src/cmd/*.py`

### 3.2 application（流程编排层）

建议目录：`src/application/usecases/`

做：
- 编排完整业务步骤
- 控制事务边界和重试入口
- 统一返回结构（success/message/code/data）

建议用例：
- `ClawUseCase`
- `CompositeUseCase`
- `PlanCreateUseCase`
- `PlanRunUseCase`
- `PlanCheckUseCase`
- `CommentBatchUseCase`

### 3.3 domain（业务规则层）

建议目录：`src/domain/`

做：
- 状态迁移规则
- 任务分配策略
- 去重与约束判定

关键约束应下沉到这里：
- `VideoTask` 只管采集/合成生命周期
- `PlanItem` 只管发布生命周期
- `CommentTask` 只管评论生命周期
- 同一 `source_vid` 不能重复进入发布中计划

### 3.4 infrastructure（技术实现层）

建议目录：`src/infrastructure/`

做：
- SQLAlchemy repo 实现
- BitBrowser / Douyin / WeCom 客户端
- 平台发布适配器（百家号/B站/小红书）
- 下载器与 FFmpeg 封装

当前迁移来源：
- `src/db/*`
- `src/library/*`
- `src/downloader/*`
- `src/plat/*`

---

## 4. 用“真实命令”看分层落点

### 4.1 `claw --fetch`

- `interfaces`：解析参数（keyword/category/count）
- `application`：执行“搜索->标准化->入库”
- `domain`：判定是否重复、状态初值规则
- `infrastructure`：调 Douyin API、写 SQLite

### 4.2 `composite --vids ...`

- `interfaces`：读取命令参数与配置
- `application`：按任务列表编排下载与合成
- `domain`：插入点、重合成策略、状态流转校验
- `infrastructure`：requests 下载、ffmpeg 处理、repo 落库

### 4.3 `plan run --plan-id --account-id`

- `interfaces`：入参校验与进度打印
- `application`：串行“填充->人工确认->回填 URL->建评论任务”
- `domain`：`PlanItem` 状态机（pending/publishing/published/failed）
- `infrastructure`：BitBrowser + Playwright + repository

---

## 5. 目标目录结构（工具导向）

```text
src/
  main.py
  interfaces/
    cli/
      commands/
        claw_command.py
        composite_command.py
        plan_command.py
        comment_command.py
  application/
    dto/
    usecases/
      claw_usecase.py
      composite_usecase.py
      plan_create_usecase.py
      plan_run_usecase.py
      plan_check_usecase.py
      comment_batch_usecase.py
  domain/
    models/
    policies/
    services/
    ports/
  infrastructure/
    db/
      models/
      repositories/
    clients/
      bit_browser_client.py
      douyin_client.py
      wecom_client.py
    platforms/
      baijiahao_platform.py
      bilibili_platform.py
      xiaohongshu_platform.py
    media/
      ffmpeg_compositor.py
    downloaders/
      douyin_downloader.py
      bilibili_downloader.py
  shared/
    config/
    logging/
    errors/
```

---

## 6. 当前代码映射（可执行改造）

- `src/cmd/*` -> `interfaces/cli/commands/*`
- `src/processor/claw_processor.py` -> `application/usecases/claw_usecase.py`
- `src/cmd/composite.py + src/processor/compositor.py`
  - 编排部分 -> `application/usecases/composite_usecase.py`
  - ffmpeg 执行部分 -> `infrastructure/media/ffmpeg_compositor.py`
- `src/cmd/plan.py`
  - create/run/check 编排 -> `application/usecases/plan_*`
- `src/db/repositories.py` -> `infrastructure/db/repositories/*`
- `src/library/*` -> `infrastructure/clients/*`
- `src/downloader/*` -> `infrastructure/downloaders/*`
- `src/plat/*` -> `infrastructure/platforms/*`

---

## 7. 低风险迁移计划（按周）

### Week 1：命令层瘦身

- 先改 `plan`，拆出 `plan_create/run/check` usecase
- `cmd/plan.py` 只保留参数与输出

验收标准：
- 命令行为不变
- 代码行数明显下降

### Week 2：合成链路拆分

- `composite` 编排下沉到 usecase
- ffmpeg 细节收敛到 `infrastructure/media`

验收标准：
- `_composite_by_vid/_recomposite` 不再散落在命令层

### Week 3：采集链路拆分

- `claw` 命令改为 usecase 驱动
- 两阶段状态变更规则集中到 domain policy

验收标准：
- 不再在多个模块直接写 `claw_status`

### Week 4：端口与测试补齐

- 为 repo/platform/downloader 定义 ports
- 补充 usecase 单测和关键集成测试

验收标准：
- 核心用例可 mock 测试，不依赖真实浏览器

---

## 8. Review 清单（你重点看这几条）

1. 分层是否足够贴近“本地 CLI 工具”而非 WebServer  
2. 是否接受 `plan -> composite -> claw` 的改造顺序  
3. 是否同意状态权威收敛：
   - 合成前后看 `VideoTask`
   - 发布看 `PlanItem`
   - 评论看 `CommentTask`

---

## 9. 非目标（避免误解）

本次分层方案不包含：
- 不引入 HTTP API 服务
- 不要求把项目改造成微服务
- 不强制替换 SQLite

这次只做“结构清晰化 + 风险降低 + 便于持续迭代”。

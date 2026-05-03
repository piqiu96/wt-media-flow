# wt-media-flow 轻量级架构方案（Review Draft）

> 日期：2026-04-20  
> 适用：小规模、本地 CLI 自动化工具  
> 目标：减少复杂度，同时把代码边界理顺。

---

## 1. 结论先行

采用轻量三层，不引入复杂 DDD 拆分：

1. `interface/`：入口层（`command` + `web`）
2. `flows/`：流程编排层（核心业务）
3. `infra/`：技术实现层（DB/API/浏览器/下载/合成）

依赖关系固定为：

`interface -> flows -> infra`

---

## 2. 每层职责（简化版）

## 2.1 `interface/`

做：
- `command`：参数解析、配置合并、命令行输出
- `web`：请求参数映射、响应格式化（仅做轻联动）
- 调用 flow

不做：
- 不直接访问数据库
- 不直接写 Playwright / FFmpeg 逻辑

## 2.2 `flows/`

做：
- 业务流程编排
- 状态流转（集中在 flow 内，避免四处分散）
- 失败重试入口和结果聚合

建议 flow：
- `claw_flow.py`
- `composite_flow.py`
- `plan_flow.py`
- `comment_flow.py`

## 2.3 `infra/`

做：
- 仓储（SQLite/SQLAlchemy）
- 外部客户端（BitBrowser、Douyin、WeCom）
- 平台适配器（百家号/B站/小红书）
- 下载器（yt-dlp）
- 合成器（ffmpeg）

---

## 3. 目标目录（轻量）

```text
src/
  main.py
  interface/
    command/
      claw.py
      composite.py
      plan.py
      comment.py
      download.py
      setup.py
    web/
      app.py
      routes/
        claw.py
        composite.py
        plan.py
        comment.py
  flows/
    claw_flow.py
    composite_flow.py
    plan_flow.py
    comment_flow.py
  infra/
    db/
      models.py
      repositories.py
      database.py
    clients/
      bit_api.py
      douyin_api.py
      wecom.py
    platforms/
      baijiahao.py
      bilibili.py
      xiaohongshu.py
    media/
      compositor.py
    downloaders/
      douyin.py
      bilibili.py
  shared/
    settings.py
    log.py
    utils.py
```

---

## 4. 当前代码映射（怎么落地）

- `src/cmd/*` -> `src/interface/command/*`
- `src/cmd/plan.py` 的核心逻辑 -> `src/flows/plan_flow.py`
- `src/cmd/composite.py` 业务编排 -> `src/flows/composite_flow.py`
- `src/processor/claw_processor.py` -> `src/flows/claw_flow.py`
- `src/processor/compositor.py` -> `src/infra/media/compositor.py`
- `src/db/*` -> `src/infra/db/*`
- `src/library/*` -> `src/infra/clients/*`
- `src/plat/*` -> `src/infra/platforms/*`
- `src/downloader/*` -> `src/infra/downloaders/*`

---

## 5. 实施步骤（2-3 周）

## Phase 1（先做，低风险）

- 新建 `flows/plan_flow.py`
- `cmd/plan.py` 改成“只解析参数 + 调 flow”
- 行为保持一致（不改命令参数）

验收：
- `plan create/list/run/check` 命令结果不变
- `cmd/plan.py` 文件大幅变短

## Phase 2

- 拆 `composite`：命令层与流程层分离
- 保留现有 `VideoCompositor`，只移动目录和调用边界

验收：
- `composite` 命令功能不回归
- 合成相关异常只在 flow 汇总输出

## Phase 3

- 拆 `claw` 与 `comment`
- 统一 flow 返回结构：`{"success": bool, "message": str, "data": ...}`

验收：
- 四条主链路都走 flow
- interface 层（command/web）不再直接操作 repo/client

---

## 6. 轻量原则（防止过度设计）

- 不引入 `ports` 接口层（现阶段没必要）
- 不拆 `domain/policies/services` 多层
- 不为“未来可能”预留太多抽象
- 先保证“读得懂 + 改得动 + 不回归”

当且仅当以下情况出现，再升级架构：
- 需要新增 Web/API 入口
- 需要多数据源切换
- 需要大规模团队并行开发

补充：
- 允许新增 `interface/web`，但必须保持“薄入口”：
- Web 层只做参数与返回映射，不新增业务分支。
- 业务逻辑仍然统一在 `flows`，确保 command/web 行为一致。

---

## 7. 你需要 review 的点

1. 三层方案是否符合你对“小工具”的预期  
2. 目录命名是否接受：`interface/flows/infra`（interface 下分 `command` 与 `web`）  
3. 是否同意按 `plan -> composite -> claw/comment` 顺序改造

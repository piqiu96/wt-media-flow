# wt-media-flow 轻量 API 化落地方案（可执行版）

> 日期：2026-04-20  
> 目标：在不引入重架构的前提下，启动端口承接简单数据业务接口。  
> 原则：`interface/web` 只做薄入口，业务仍在 `flows`。

---

## 1. 方案结论

在现有 CLI 工具基础上，新增一个轻量 Web 入口层：

- `interface/command`：保留现有命令行能力
- `interface/web`：新增 HTTP API（FastAPI）
- `flows`：作为唯一业务流程层，CLI/Web 共用
- `infra`：数据库与第三方能力实现

依赖关系：

`interface(command|web) -> flows -> infra`

---

## 2. 范围控制（V1）

V1 只做“简单数据业务 + 少量流程触发”，不做复杂异步系统。

包含：
- 列表查询接口（videos/accounts/plans）
- 详情查询接口（plan detail）
- 轻量触发接口（create plan / run plan by account）
- 健康检查接口

不包含：
- 完整任务队列系统
- WebSocket 推送
- 权限系统（先走内网/白名单）

---

## 3. 目标目录（与轻量分层一致）

```text
src/
  interface/
    web/
      app.py
      deps.py
      schemas/
        common.py
        plan.py
        video.py
      routes/
        health.py
        videos.py
        accounts.py
        plans.py
  flows/
    video_flow.py
    account_flow.py
    plan_flow.py
  infra/
    db/
      database.py
      repositories.py
```

说明：
- `routes` 仅参数映射和调用 flow。
- `schemas` 只定义请求/响应模型，避免散落。
- `flows/*_flow.py` 按资源拆分，不按框架拆分。

---

## 4. 接口清单（V1）

## 4.1 基础

- `GET /api/healthz`
  - 用途：存活检查
  - 返回：`{"success": true, "message": "ok"}`

## 4.2 视频

- `GET /api/videos?limit=20`
  - 用途：分页/限量列表
  - flow：`list_videos_flow(limit)`

## 4.3 账号

- `GET /api/accounts`
  - 用途：活跃账号列表
  - flow：`list_accounts_flow()`

## 4.4 计划

- `GET /api/plans?date=YYYY-MM-DD`
  - 用途：按日期查询计划
  - flow：`list_plans_flow(date)`

- `GET /api/plans/{plan_id}`
  - 用途：查看计划详情（items + 状态汇总）
  - flow：`get_plan_detail_flow(plan_id)`

- `POST /api/plans/create`
  - 入参：`{"date":"today|YYYY-MM-DD","dry_run":false}`
  - flow：`create_plan_flow(date, dry_run)`

- `POST /api/plans/{plan_id}/run`
  - 入参：`{"account_id":123}`
  - flow：`run_plan_flow(plan_id, account_id)`
  - 备注：V1 先同步执行（与 CLI 行为一致）

---

## 5. 统一返回结构（必须统一）

所有接口返回统一结构：

```json
{
  "success": true,
  "message": "ok",
  "data": {},
  "error_code": ""
}
```

规则：
- 成功：`success=true`，`error_code=""`
- 失败：`success=false`，`message` 可读，`error_code` 稳定
- HTTP 状态码可先统一 `200`，后续再细化为 `4xx/5xx`

---

## 6. Flow 改造最小策略

目标：CLI 和 Web 都调同一个 flow。

步骤：
1. 先把现有 `cmd/plan.py` 中业务逻辑抽到 `flows/plan_flow.py`
2. `cmd/plan.py` 仅保留参数解析和 print
3. `routes/plans.py` 直接复用 `plan_flow.py`

同样策略应用到 videos/accounts 查询 flow。

---

## 7. 启动方式

依赖：

```bash
pip install fastapi uvicorn
```

本地启动：

```bash
uvicorn src.interface.web.app:app --host 0.0.0.0 --port 8000 --reload
```

生产建议（轻量）：
- 先单进程部署
- 仅内网访问或反向代理白名单

---

## 8. 分阶段执行计划（可直接排期）

## Phase 1（0.5-1 天）：脚手架

- 建立 `interface/web/app.py`
- 增加 `health` 路由
- 接口统一响应模型

验收：
- `GET /api/healthz` 可用

## Phase 2（1-2 天）：只读接口

- `GET /api/videos`
- `GET /api/accounts`
- `GET /api/plans`
- `GET /api/plans/{id}`

验收：
- 与 CLI 查询结果一致

## Phase 3（1-2 天）：流程触发接口

- `POST /api/plans/create`
- `POST /api/plans/{id}/run`

验收：
- 能通过 API 触发并看到数据库状态变化
- 失败信息可追踪

## Phase 4（0.5 天）：稳定化

- 基础异常处理中间件
- 请求日志（path, cost, success）
- README 增加 API 启动说明

---

## 9. 风险与规避

- 风险：Web 路由里再次写业务逻辑，造成 CLI/Web 分叉
  - 规避：所有路由仅调用 flow，禁止直接 repo 调用

- 风险：`run plan` 为长流程，HTTP 超时
  - 规避：V1 限内网人工调用；后续可升级异步 job（V2）

- 风险：接口返回格式不一致
  - 规避：统一 `success/message/data/error_code`

---

## 10. Review 决策点

请确认以下 4 点：

1. 是否同意 V1 接口范围（先读多写少）  
2. 是否同意 `run plan` 先同步执行（后续再异步）  
3. 是否同意统一响应结构（便于前端联调）  
4. 是否同意先改 `plan` flow，再扩到其他模块


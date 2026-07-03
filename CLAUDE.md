# CLAUDE.md

## 项目

wt-media-flow — 视频素材采集 + 合成 + 多平台发布系统。

## 环境

- Python 3.14，虚拟环境在 `.venv/`
- **必须使用 `.venv/bin/python3` 执行命令**，系统没有 `python` 命令
- 执行格式：`.venv/bin/python3 src/main.py <command> [args]`

## 常用命令

```bash
# 采集素材（按品类 + 配置文件，推荐）
.venv/bin/python3 src/main.py claw --category 三角洲 --config conf/claw.yaml
.venv/bin/python3 src/main.py claw --category 暗区突围 --config conf/claw.yaml

# 采集（单关键词，不加 --config）
.venv/bin/python3 src/main.py claw --keyword "关键词" --count 10

# 两阶段采集：只入库 / 只下载
.venv/bin/python3 src/main.py claw --category 三角洲 --fetch --config conf/claw.yaml
.venv/bin/python3 src/main.py claw --download --category 三角洲

# 合成视频（通过素材库 vid）
.venv/bin/python3 src/main.py composite --vid <source_vid> --config conf/composite.yaml --category 三角洲 --platform bilibili --pool pool-hz

# 批量合成
.venv/bin/python3 src/main.py composite --vids <vid1> <vid2> --config conf/composite.yaml --category 三角洲 --platform baijiahao --pool pool-hz
.venv/bin/python3 src/main.py composite --batch --category 三角洲 --platform bilibili --pool pool-hz --config conf/composite.yaml --limit 20

# 发布计划
.venv/bin/python3 src/main.py plan create --user-id <USER_ID> --dry-run
.venv/bin/python3 src/main.py plan create --user-id <USER_ID>
.venv/bin/python3 src/main.py plan run --plan-id <N> --account-id <M>
.venv/bin/python3 src/main.py plan check --plan-id <N>

# 评论
.venv/bin/python3 src/main.py comment batch --account-id 1

# 清理 / 工具
.venv/bin/python3 src/main.py cleanup
.venv/bin/python3 src/main.py setup --check
.venv/bin/python3 src/main.py serve --port 8000

# 下载视频
.venv/bin/python3 src/main.py download --source douyin --url "https://v.douyin.com/xxx"

# 初始化/迁移数据库
.venv/bin/python3 src/main.py init

# 安装依赖
.venv/bin/python3 -m pip install -r requirements.txt
```

## 架构

```
app/cli    → workflows → services → infra/db (repositories + models)
app/web                           → infra/browser (bit_api)
                                  → infra/http (douyin_api)
                                  → infra/media (compositor, video_util)
                                  → infra/downloader (yt-dlp)
           → platforms (baijiahao, bilibili — PublisherProtocol)
```

**分层原则**：
- 复杂跨层交互（跨多个 service/infra 编排）→ `workflows/`
- 简单操作（单一 infra/service 调用）→ CLI 直调 infra 或 service
- 上层调下层，下层不依赖上层

## 核心文件

| 文件 | 说明 |
|------|------|
| `src/main.py` | 入口，argparse 分发 |
| `src/conf/settings.py` | 所有配置（pydantic-settings） |
| `src/app/cli/__init__.py` | 命令框架 + 注册表（ABC + @register_command） |
| `src/app/web/api.py` | FastAPI Web API |
| `src/workflows/claw_workflow.py` | 采集工作流（DouyinApi + 入库 + 下载）|
| `src/workflows/plan_workflow.py` | 计划工作流（创建/运行/检查）|
| `src/workflows/publish_workflow.py` | 发布工作流（BitBrowser + Playwright）|
| `src/workflows/composite_workflow.py` | 合成工作流 |
| `src/workflows/comment_workflow.py` | 评论工作流 |
| `src/services/` | 业务服务（publish, plan, browser_session, video）|
| `src/platforms/` | 平台适配（base 协议, registry, baijiahao/, bilibili/）|
| `src/infra/media/compositor.py` | FFmpeg 合成器（截尾/贴纸/时长控制）|
| `src/infra/http/douyin_api.py` | 抖音 API 客户端（itfaba.com）|
| `src/infra/media/video_util/` | 视频去重/场景检测/尾部动画 |
| `src/infra/db/models.py` | SQLAlchemy 模型 |
| `src/infra/db/repositories.py` | Repository 层 |

## 数据目录

| 目录 | 说明 |
|------|------|
| `store/publisher.db` | SQLite 数据库 |
| `data/downloads/` | 下载的视频文件（按 date/category 分目录）|
| `data/guides/{category}/` | 引导视频（按品类分目录，平台路径在 `conf/pools/*.json` 或 `conf/composite.yaml` 配置）|
| `data/output/` | 合成输出 |
| `data/stickers/` | PNG 贴纸素材 |
| `data/overlays/` | 尾部动画素材 |
| `conf/` | YAML 配置文件 |

## 数据流

```
采集: claw → DouyinApi.search() → ClawWorkflow.ingest() → VideoRepository.create_from_claw()
下载: ClawWorkflow.download_pending() → requests → data/downloads/{date}/{category}/
合成: composite --vid → CompositeWorkflow → VideoCompositor(FFmpeg) → data/output/
发布: plan create → PlanWorkflow → plan run → PublishWorkflow → BitBrowser+Playwright → 平台上传
过审: plan check → PlanWorkflow.check() → HTTP 验证 → 企微通知
```

## 约定

- 所有 command.execute() 返回 `{"success": bool, "message": str, ...}`
- 配置优先级：CLI 参数 > pool 品类配置 > YAML 配置 > settings.py 默认值
- 注册模式：`@register_command`（cmd）、`@register_downloader`（downloader）、手动注册（plat）
- 数据库：Repository 模式，Session 注入
- 采集去重：`source_platform + source_vid`
- 合成默认：insert_at 随机 10-20s，截尾 3-5s，时长 ≤ 180s

## 搜索参数默认值

- `publish_time=1`（最近一天）
- `filter_duration="1-5"`（1-5 分钟视频）
- `count` 最低 10 条（API 限制）
- ⚠️ `claw.yaml` 里 `sort_type=2`，带 `--config` 时 CLI 参数无法覆盖，单关键词采集用裸命令不加 `--config`

## 已知未完成项

| 项目 | 状态 |
|------|------|
| B站分区自动选择 | `bilibili/publisher.py` 中已跳过，需手动确认 |
| 小红书平台 | `platforms/xiaohongshu/` 枚举已定义，发布逻辑未实现 |
| `publish` 命令 | `app/cli/publish.py` 是调试用直接发布命令，日常走 `plan run` |
| print → logger 迁移 | workflows/ 和 infra/ 层大量使用 print，待统一 |

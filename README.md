# wt-media-flow — 视频素材采集 + 合成 + 多平台发布系统

集成素材采集、视频合成加工、多平台自动发布的全流程工具。
支持从抖音采集素材入库，自动下载合成带引导视频的去重内容，通过比特浏览器实现多账号矩阵发布。

**技术栈**：Python 3.14 · SQLite(SQLAlchemy) · FFmpeg · Playwright · FastAPI · 比特浏览器 CDP

## 核心工作流

```
采集(claw) → 素材库(videos) → 合成(composite) → 计划(plan create) → 发布(plan run)
```

1. **采集**：从抖音 API 批量抓取素材元数据入库，支持关键词搜索 / 链接 / 两阶段下载
2. **合成**：传入 vid 自动下载 → 插入引导视频 → 截尾去重 → 贴纸叠加 → 时长控制
3. **计划**：按账号日限自动分配已合成视频，高热度优先
4. **发布**：比特浏览器 + Playwright 自动化发布，支持百家号 / B站

---

## 快速开始

### 环境要求

- Python 3.14，虚拟环境在 `.venv/`
- 比特浏览器（多账号发布功能需要）

### 安装

```bash
python3.14 -m venv .venv
source .venv/bin/activate
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 src/main.py setup    # 安装 yt-dlp/ffmpeg 到 bin/
.venv/bin/python3 src/main.py init     # 初始化数据库
```

> **注意**：必须使用 `.venv/bin/python3`，系统没有全局 `python` 命令。

---

## 命令参考

### 素材采集（claw）

```bash
# 按关键词采集（最低 10 条，API 限制）
.venv/bin/python3 src/main.py claw --keyword "三角洲 活动" --count 20

# 按品类 + 配置文件采集（推荐）
.venv/bin/python3 src/main.py claw --category 三角洲 --config conf/claw.yaml

# 按品类采集暗区突围
.venv/bin/python3 src/main.py claw --category 暗区突围 --config conf/claw.yaml

# 单链接采集
.venv/bin/python3 src/main.py claw --url "https://v.douyin.com/xxx"

# dry-run：只展示结果不入库
.venv/bin/python3 src/main.py claw --keyword "三角洲" --dry-run

# 两阶段模式：先只入库，稍后再下载
.venv/bin/python3 src/main.py claw --category 三角洲 --fetch --config conf/claw.yaml
.venv/bin/python3 src/main.py claw --download --category 三角洲

# 重试下载失败的视频（有人工确认）
.venv/bin/python3 src/main.py claw --download --category 三角洲 --retry-failed
```

**搜索参数默认值**（可通过 conf/claw.yaml 覆盖）：
- `publish_time=1`（最近一天）
- `filter_duration="1-5"`（1-5 分钟视频）
- `sort_type=2`（最新排序）

### 视频合成（composite）

```bash
# 通过素材库 vid 合成（推荐，自动下载 + 合成）
.venv/bin/python3 src/main.py composite --vid 7627089837556988532 --config conf/composite.yaml --category 三角洲

# 批量 vid 合成
.venv/bin/python3 src/main.py composite --vids <vid1> <vid2> --config conf/composite.yaml --category 三角洲

# 按配置批量重合成
.venv/bin/python3 src/main.py composite --recomposite --config conf/composite.yaml --category 三角洲

# 本地文件直接合成（调试用）
.venv/bin/python3 src/main.py composite --input video.mp4 --guide data/guides/三角洲/guide.mp4
```

**合成流程**：`原视频前段 + 引导视频 + 原视频后段 + 尾部动画`

| 特性 | 默认值 |
|------|--------|
| 截尾去重 | 随机剪去末尾 3-5s |
| 引导插入点 | 随机 10-20s 范围 |
| 时长控制 | ≤ 150s |
| 贴纸叠加 | 2-5 张半透明 PNG |
| 视频去重 | 亮度/对比度/裁切/速度微调 + 尾部动画 |

### 发布计划（plan）

```bash
# 创建计划（dry-run 预览）
.venv/bin/python3 src/main.py plan create --dry-run

# 正式创建
.venv/bin/python3 src/main.py plan create

# 执行计划（逐账号发布）
.venv/bin/python3 src/main.py plan run --plan-id 1 --account-id 1

# 查看计划列表
.venv/bin/python3 src/main.py plan list

# 检查过审状态（次日执行）
.venv/bin/python3 src/main.py plan check --plan-id 1

# 重置失败任务
.venv/bin/python3 src/main.py plan reset-failed --plan-id 1
```

### 评论管理（comment）

```bash
.venv/bin/python3 src/main.py comment single --account-id 1 --url "https://..."
.venv/bin/python3 src/main.py comment batch --account-id 1
```

### 账号管理（account）

```bash
# 添加账号
.venv/bin/python3 src/main.py account add \
  --browser-id 1 --platform baijiahao --name "账号名" \
  --tag "三角洲,蛋仔派对" --daily-limit 5

# 列出所有账号
.venv/bin/python3 src/main.py account list
```

### 视频管理（video）

```bash
.venv/bin/python3 src/main.py video add --path /path/to/video.mp4 --title "标题"
.venv/bin/python3 src/main.py video list
```

### 下载（download）

```bash
.venv/bin/python3 src/main.py download --source douyin --url "https://v.douyin.com/xxx"
.venv/bin/python3 src/main.py download --source bilibili --url "https://www.bilibili.com/video/BVxxx"
```

### 清理 & 工具

```bash
.venv/bin/python3 src/main.py cleanup                 # 清理过期/失败的合成任务
.venv/bin/python3 src/main.py setup --check           # 检查工具（ffmpeg/yt-dlp）状态
.venv/bin/python3 src/main.py init                    # 初始化/迁移数据库
.venv/bin/python3 src/main.py serve --port 8000       # 启动 Web API（FastAPI，文档 /docs）
```

### 直接发布（publish，调试用）

```bash
# 对指定账号直接发布 video_tasks 中的合成任务（调试用，日常走 plan run）
.venv/bin/python3 src/main.py publish --account-id 1 --limit 3
```

---

## 每日运行流程

使用 `/daily-run` skill 自动编排四阶段（采集 → 合成 → 计划 → 发布），也可手动执行：

```bash
# 阶段一：采集（三角洲 + 暗区突围）
.venv/bin/python3 src/main.py claw --category 三角洲 --config conf/claw.yaml
.venv/bin/python3 src/main.py claw --category 暗区突围 --config conf/claw.yaml

# 阶段二：合成
.venv/bin/python3 src/main.py composite --recomposite --config conf/composite.yaml --category 三角洲
.venv/bin/python3 src/main.py composite --recomposite --config conf/composite.yaml --category 暗区突围

# 阶段三：创建发布计划
.venv/bin/python3 src/main.py plan create --dry-run   # 预览
.venv/bin/python3 src/main.py plan create             # 正式创建

# 阶段四：逐账号发布（account-id 1-10）
.venv/bin/python3 src/main.py plan run --plan-id <N> --account-id 1
# ...
```

---

## 架构

```
src/
├── main.py                  # 入口，argparse 分发
├── conf/settings.py         # 全局配置（pydantic-settings）
├── app/
│   ├── cli/                 # CLI 命令层（13 个命令，ABC + @register_command）
│   └── web/api.py           # FastAPI Web API
├── workflows/               # 流程编排（跨 service/infra 的业务流程）
│   ├── plan_workflow.py
│   ├── publish_workflow.py
│   ├── composite_workflow.py
│   ├── comment_workflow.py
│   └── claw_workflow.py
├── services/                # 业务服务（单一 infra/Repository 组合）
│   ├── publish_service.py
│   ├── plan_service.py
│   ├── browser_session_service.py
│   └── video_service.py
├── platforms/               # 平台适配（PublisherProtocol）
│   ├── base.py              # 协议定义（fill_form / submit / fetch_published_url）
│   ├── registry.py
│   ├── baijiahao/           # 完整实现
│   └── bilibili/            # 基本实现（分区需手动确认）
└── infra/                   # 基础设施（外部依赖封装）
    ├── db/                  # SQLAlchemy（models + repositories + database）
    ├── browser/bit_api.py   # 比特浏览器 API
    ├── http/douyin_api.py   # 抖音 API 客户端
    ├── media/               # FFmpeg 合成器 + 视频去重工具
    └── downloader/          # yt-dlp 下载封装（抖音/B站）
```

**分层原则**：
- 复杂跨层交互（跨多个 service/infra 编排）→ `workflows/`
- 简单操作（单一 infra/service 调用）→ CLI 直调 infra/service
- 上层调下层，下层不依赖上层

---

## 数据目录

| 目录/文件 | 说明 |
|-----------|------|
| `data/publisher.db` | SQLite 数据库 |
| `data/downloads/` | 下载的原始视频（按日期/品类分目录）|
| `data/guides/{category}/guide.mp4` | 引导视频（按品类分目录）|
| `data/output/` | 合成输出视频 |
| `data/stickers/` | PNG 贴纸素材 |
| `data/overlays/` | 尾部动画素材 |

### 数据库表

| 表 | 说明 |
|----|------|
| `videos` | 素材表（标题/标签/来源/URL/热度/发布时间/品类）|
| `video_tasks` | 合成任务（输出路径/状态）|
| `browsers` | 比特浏览器容器 |
| `accounts` | 发布账号（平台/browser_id/日限额）|
| `publish_plans` | 发布计划 |
| `plan_items` | 计划条目（账号/视频/状态/通知）|
| `comment_tasks` | 评论任务 |

---

## 配置文件

| 文件 | 说明 |
|------|------|
| `conf/claw.yaml` | 采集配置（品类关键词/搜索参数）|
| `conf/composite.yaml` | 合成配置（引导视频路径/插入位置/去重）|
| `conf/categories.yaml` | 品类列表（三角洲/暗区突围/蛋仔派对）|
| `conf/comment_templates.yaml` | 评论模板 |
| `src/conf/settings.py` | 全局默认配置（路径/超时/编码参数）|

**配置优先级**：CLI 参数 > YAML 配置 > settings.py 默认值

---

## 平台支持状态

| 平台 | 状态 | 备注 |
|------|------|------|
| 百家号（baijiahao）| 完整 | 三段式发布 + 过审检查 + 企微通知 |
| B站（bilibili）| 基本可用 | 分区选择需手动确认 |
| 小红书（xiaohongshu）| 待实现 | 枚举已定义，发布逻辑未完成 |

---

## 数据流

```
采集: claw → DouyinApi.search() → ClawWorkflow.ingest() → VideoRepository.create_from_claw()
下载: ClawWorkflow.download_pending() → requests → data/downloads/{date}/{category}/
合成: composite --vid → CompositeWorkflow → VideoCompositor(FFmpeg) → data/output/
发布: plan create → PlanWorkflow → plan run → PublishWorkflow → BitBrowser+Playwright → 平台上传
过审: plan check → PlanWorkflow.check() → HTTP 请求验证 → 企微通知
```

---

## 已知限制

### Playwright 文件上传 50MB 限制

通过 CDP 连接比特浏览器时，Playwright 默认限制上传文件大小为 **50MB**：

```
FileChooser.set_files: Cannot transfer files larger than 50Mb to a browser not co-located with the server
```

**修改方法**：

```bash
# 找到文件
.venv/lib/python3.14/site-packages/playwright/driver/package/lib/server/fileUploadUtils.js
```

找到 `fileUploadSizeLimit` 常量，改为 200MB：

```js
const fileUploadSizeLimit = 200 * 1024 * 1024;
```

> ⚠️ 重新安装/升级 playwright 后需重新修改。

### github限制
```bash
打开vpn

ping
140.82.113.3 github.com
151.101.1.194 github.global.ssl.fastly.net

sudo vim /etc/hosts，将上述的内容粘贴进去
```
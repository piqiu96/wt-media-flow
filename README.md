# wt-media-flow — 视频素材采集 + 合成 + 多平台发布系统

集成素材采集、视频下载、视频合成加工、多平台自动发布的全流程工具。
支持从抖音采集素材入库，自动下载合成带引导视频的去重内容，通过比特浏览器实现多账号矩阵发布。

## 核心工作流

```
采集(claw) → 素材库(videos) → 合成(composite) → 发布(publish)
```

1. **采集**：通过关键词搜索或链接从抖音 API 批量抓取素材元数据入库（不下载文件）
2. **素材库**：运营查看素材信息（标题、标签、统计数据），选择要合成的内容
3. **合成**：传入 vid 自动下载远程视频 → 插入引导视频 → 截尾去重 → 贴纸叠加 → 时长控制
4. **发布**：通过比特浏览器 + Playwright 自动化发布到 B站/百家号/小红书

## 功能

- **素材采集**：抖音关键词搜索 + 链接批量采集，元数据入库（标签/统计/原视频发布时间）
- **视频下载**：抖音（去水印）、B站（yt-dlp）
- **视频合成**：
  - FFmpeg 引导片段插入，分辨率/帧率/采样率自动对齐
  - 截尾去重：默认剪去原视频末尾 3-5s
  - 插入点随机化：默认 10-20s 范围内随机
  - 贴纸叠加：2-5 张半透明 PNG 贴纸分散在视频边缘
  - 时长控制：默认 ≤ 150s（2 分半），超出自动截短
  - 视频去重：亮度/对比度/裁切/速度/色调微调 + 尾部动画
- **多平台发布**：Bilibili、百家号、小红书（Playwright 自动化）
- **账号矩阵管理**：比特浏览器多开 + 分组管理
- **任务调度**：定时发布/评论/点赞，线程池并发执行

## 环境要求

- Python 3.12+
- 比特浏览器（多账号浏览器管理，发布功能需要）

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py setup            # 安装 yt-dlp/ffmpeg 到 bin/
python src/main.py init             # 初始化数据库
```

## 配置

```bash
cp conf/.env.example conf/.env      # 可选，填入比特浏览器 API 地址等
```

YAML 配置文件位于 `conf/` 目录：

| 配置文件 | 说明 |
|---------|------|
| `conf/claw.yaml` | 采集配置（关键词/链接/搜索参数） |
| `conf/composite.yaml` | 合成配置（引导视频/插入位置/去重） |
| `conf/download.yaml` | 下载配置（来源/画质/cookies） |
| `conf/pipeline.yaml` | 全流程配置（下载→合成→发布） |

## 命令

所有命令通过 `.venv/bin/python3 src/main.py <command>` 执行。

### 素材采集

```bash
# 关键词搜索采集（最低 10 条）
python src/main.py claw --keyword "三角洲行动 活动" --count 10

# 单链接采集
python src/main.py claw --url "https://v.douyin.com/xxx"

# 批量链接文件
python src/main.py claw --urls-file data/douyin_urls.txt

# dry-run 只看不入库
python src/main.py claw --keyword "美食" --dry-run

# YAML 配置文件
python src/main.py claw --config conf/claw.yaml
```

### 视频合成

```bash
# 通过素材库 vid 自动下载合成（推荐）
python src/main.py composite --vid 7627089837556988532 --guide data/guides/guide.mp4

# 批量 vid 合成
python src/main.py composite --vids 762xxx 762xxx 762xxx --guide data/guides/guide.mp4

# 指定最大时长（秒）
python src/main.py composite --vid 762xxx --guide data/guides/guide.mp4 --max-duration 120

# 本地文件合成
python src/main.py composite --input video.mp4 --guide data/guides/guide.mp4

# 批量目录合成
python src/main.py composite --input data/downloads/ --guide data/guides/guide.mp4
```

### 视频下载

```bash
python src/main.py download --source douyin --url "https://v.douyin.com/xxx"
python src/main.py download --source bilibili --url "https://www.bilibili.com/video/BVxxx" --cookies-from-browser chrome
```

### 账号 & 任务管理

```bash
python src/main.py account add --platform bilibili --username x --profile-id xxx
python src/main.py account list
python src/main.py video add --path /path/to/video.mp4 --title "标题"
python src/main.py video list
python src/main.py task list
python src/main.py plan --group g1 --count 100 --comment --like
python src/main.py run                    # 启动调度器
```

### 其他

```bash
python src/main.py setup --check          # 检查工具状态
python src/main.py init                   # 初始化/迁移数据库
python src/main.py pipeline --config conf/pipeline.yaml  # 全流程
```

## 命令速查

| 命令 | 说明 |
|------|------|
| `claw` | 从抖音采集素材到素材库（搜索关键词或链接） |
| `download` | 从抖音/B站下载视频 |
| `composite` | 视频合成（插入引导 + 去重 + 贴纸 + 时长控制） |
| `pipeline` | 全流程（下载→合成→发布） |
| `setup` | 环境初始化（安装 ffmpeg/yt-dlp） |
| `init` | 初始化数据库 |
| `account` | 账号管理（add/list） |
| `video` | 视频管理（add/list） |
| `task` | 任务管理（list） |
| `plan` | 生成发布计划 |
| `run` | 启动任务调度器 |

## 架构

```
src/
├── main.py           # 入口
├── conf/             # 静态配置（pydantic-settings + .env）
├── cmd/              # 命令层（参数解析 + 输出）
├── processor/        # 业务处理核心（合成器/采集器/流水线）
├── service/          # 数据业务 + 浏览器池
├── library/          # 外部 API 封装（抖音API/BitBrowser）
├── downloader/       # 视频下载（抖音/B站，基于 yt-dlp）
├── planner/          # 发布计划生成
├── scheduler/        # 任务调度（线程池轮询）
├── worker/           # 任务执行（浏览器自动化）
├── plat/             # 平台发布（Playwright: B站/百家号/小红书）
├── db/               # 数据模型 + Repository
└── utils/            # 工具函数（日志/随机/反风控）
```

### 分层原则

```
cmd → processor → service → db
                → scheduler / worker / planner
                → downloader / plat
                → library
```

上层调下层，下层不依赖上层。

## 合成特性详解

合成流程：`原视频前段(front) + 引导视频(guide) + 原视频后段(back) + 尾部动画(tail)`

| 特性 | 说明 | 默认值 |
|------|------|--------|
| 截尾去重 | 原视频末尾随机剪去 N 秒 | 3-5s |
| 插入点随机 | 引导视频插入位置在范围内随机 | 10-20s |
| 时长控制 | 超出目标时长则截短 back 段 | ≤ 150s |
| 贴纸叠加 | 随机 PNG 贴纸在 back 段边缘位置分时出现 | 2-5 张 |
| 引导去重 | 引导视频亮度/对比度/裁切/速度微调 | 自动 |
| 整体去重 | 合并后色调/亮度/锐化微调 | 自动 |
| 尾部动画 | 从 overlays 目录选取或自动生成 | 1-3s |

## 数据库

SQLite，位于 `data/publisher.db`。

| 表 | 说明 |
|---|------|
| `accounts` | 发布账号（平台/用户名/profile_id/分组/日限额） |
| `videos` | 素材表（标题/标签/来源追踪/远程URL/原视频发布时间/原始API数据） |
| `publish_tasks` | 发布任务（账号/视频/类型/状态/调度时间/重试） |
| `task_logs` | 任务日志 |

## 注意事项

1. **执行命令**：始终使用 `.venv/bin/python3 src/main.py` 或激活虚拟环境后执行
2. **比特浏览器**：发布功能需确保比特浏览器服务已启动
3. **登录状态**：首次使用各平台前需在比特浏览器中手动登录账号
4. **发布限制**：新账号建议减少发布频率，避免触发风控
5. **采集去重**：按 `source_platform + source_vid` 自动去重，重复素材不会入库

## 已知限制与解决方案

### Playwright 文件上传 50MB 限制

通过 CDP（`connect_over_cdp`）连接比特浏览器时，Playwright 的 `FileChooser.set_files` /
`set_input_files` 默认限制传输文件大小为 **50MB**，超出会报错：

```
FileChooser.set_files: Cannot transfer files larger than 50Mb to a browser not co-located with the server
```

**修改方法**：编辑 Playwright 驱动源码中的 `fileUploadSizeLimit` 常量：

```
.venv/lib/python3.14/site-packages/playwright/driver/package/lib/server/fileUploadUtils.js
```

找到 `fileUploadSizeLimit` 并调大（单位：字节，默认 `50 * 1024 * 1024`），例如改为 200MB：

```js
const fileUploadSizeLimit = 200 * 1024 * 1024;
```

> ⚠️ 该文件随 pip 安装，**重新安装/升级 playwright 后会被覆盖**，需重新修改。

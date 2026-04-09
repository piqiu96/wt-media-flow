# wt-media-pub — 矩阵视频自动发布系统

集成视频下载、视频合成加工、多平台自动发布的全流程工具。
通过比特浏览器实现多账号矩阵管理，支持 B站/百家号/小红书。

## 功能

- **视频下载**：抖音（去水印）、B站（yt-dlp）
- **视频合成**：FFmpeg 引导片段插入，分辨率/帧率/采样率自动对齐
- **多平台发布**：Bilibili、百家号、小红书（Playwright 自动化）
- **账号矩阵管理**：比特浏览器多开 + 分组管理
- **任务调度**：定时发布/评论/点赞，线程池并发执行

## 环境要求

- Python 3.12+
- 比特浏览器（多账号浏览器管理）

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py setup            # 安装 yt-dlp/ffmpeg 到 bin/
```

## 配置

```bash
cp conf/.env.example conf/.env      # 填入比特浏览器 API 地址等
```

配置示例：

```env
# 比特浏览器配置
BIT_API_URL=http://127.0.0.1:54345

# 调度配置
SCHEDULER_INTERVAL=30
MAX_CONCURRENT_TASKS=3
TASK_RETRY_LIMIT=3

# 发布时间配置
PUBLISH_START_HOUR=8
PUBLISH_END_HOUR=23

# 浏览器池配置
BROWSER_POOL_SIZE=5
BROWSER_IDLE_TIMEOUT=600
```

## 命令

| 命令 | 说明 |
|------|------|
| `setup [--check]` | 环境初始化 / 检查工具 |
| `init` | 初始化数据库 |
| `download --source douyin\|bilibili --url URL` | 下载视频 |
| `composite --input a.mp4 --guide g.mp4 --insert-at 10` | 合成视频 |
| `pipeline --config conf/pipeline.yaml` | 全流程（下载→合成→发布） |
| `account add --platform bilibili --username x --profile-id xxx` | 添加账号 |
| `account list` | 列出账号 |
| `video add --path /path/to/video.mp4 --title "标题"` | 添加视频 |
| `video list` | 列出视频 |
| `task list` | 列出任务 |
| `plan --group g1 --count 100 [--comment] [--like]` | 生成发布计划 |
| `run` | 启动调度器 |

所有命令通过 `python src/main.py <command>` 执行。

## 架构

```
src/
├── main.py           # 入口
├── conf/             # 静态配置（pydantic-settings + .env）
├── cmd/              # 命令层（参数解析 + 输出）
├── processor/        # 业务处理核心
├── service/          # 数据业务 + 浏览器池
├── library/          # 外部 API 封装（BitBrowser SDK）
├── downloader/       # 视频下载（抖音/B站）
├── planner/          # 发布计划
├── scheduler/        # 任务调度（线程池轮询）
├── worker/           # 任务执行（浏览器自动化）
├── plat/             # 平台发布（Playwright）
├── db/               # 数据模型 + Repository
└── utils/            # 工具函数
```

### 分层原则

```
cmd → processor → service → db
                → scheduler / worker / planner
                → downloader / plat
                → library
```

上层调下层，下层不依赖上层。

## 平台扩展

如需添加新平台，在 `src/plat/` 下创建新目录并实现 `BasePlatform` 接口，然后在 `src/plat/__init__.py` 中注册。

## 数据库

系统使用 SQLite 存储数据，数据库文件位于 `data/publisher.db`。

主要表：`accounts`（账号）、`videos`（视频）、`publish_tasks`（发布任务）、`task_logs`（日志）

## 注意事项

1. **比特浏览器**：确保比特浏览器服务已启动，API 地址配置正确
2. **Profile ID**：在比特浏览器中创建窗口后，复制对应的 Profile ID
3. **登录状态**：首次使用各平台前需手动登录账号
4. **发布限制**：新账号建议减少发布频率，避免触发风控

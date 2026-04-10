# CLAUDE.md

## 项目

wt-media-flow — 视频素材采集 + 合成 + 多平台发布系统。

## 环境

- Python 3.14，虚拟环境在 `.venv/`
- **必须使用 `.venv/bin/python3` 执行命令**，系统没有 `python` 命令
- 执行格式：`.venv/bin/python3 src/main.py <command> [args]`

## 常用命令

```bash
# 采集素材
.venv/bin/python3 src/main.py claw --keyword "关键词" --count 10
.venv/bin/python3 src/main.py claw --url "https://v.douyin.com/xxx"

# 合成视频（通过素材库 vid）
.venv/bin/python3 src/main.py composite --vid <source_vid> --guide data/guides/guide.mp4

# 批量合成
.venv/bin/python3 src/main.py composite --vids <vid1> <vid2> --guide data/guides/guide.mp4

# 下载视频
.venv/bin/python3 src/main.py download --source douyin --url "https://v.douyin.com/xxx"

# 初始化/迁移数据库
.venv/bin/python3 src/main.py init

# 安装/检查工具
.venv/bin/python3 src/main.py setup --check

# 安装依赖
.venv/bin/python3 -m pip install -r requirements.txt
```

## 架构

```
cmd → processor → service → db (repositories + models)
               → library (douyin_api, bit_api, video_util)
               → downloader (yt-dlp)
               → plat (playwright 发布)
```

上层调下层，下层不依赖上层。

## 核心文件

| 文件 | 说明 |
|------|------|
| `src/main.py` | 入口，argparse 分发 |
| `src/conf/settings.py` | 所有配置（pydantic-settings） |
| `src/cmd/__init__.py` | 命令框架 + 注册表（ABC + @register_command） |
| `src/cmd/claw.py` | 采集命令 |
| `src/cmd/composite.py` | 合成命令（支持 --vid/--vids） |
| `src/cmd/download.py` | 下载命令 |
| `src/processor/compositor.py` | FFmpeg 合成器（截尾/贴纸/时长控制） |
| `src/processor/claw_processor.py` | 采集入库处理器 |
| `src/library/douyin_api.py` | 抖音 API 客户端（itfaba.com） |
| `src/library/video_util/` | 视频去重/场景检测/尾部动画 |
| `src/db/models.py` | SQLAlchemy 模型（Account, Video, PublishTask, TaskLog） |
| `src/db/repositories.py` | Repository 层 |

## 数据目录

| 目录 | 说明 |
|------|------|
| `data/publisher.db` | SQLite 数据库 |
| `data/downloads/` | 下载的视频文件 |
| `data/guides/` | 引导视频（合成用） |
| `data/output/` | 合成输出 |
| `data/stickers/` | PNG 贴纸素材 |
| `data/overlays/` | 尾部动画素材 |
| `conf/` | YAML 配置文件 |

## 数据流

```
采集: claw → DouyinApi.search() → ClawProcessor → VideoRepository.create_from_claw()
合成: composite --vid → DB查询 → requests下载 → FFmpeg合成(front+guide+back+tail) → 输出
发布: plan → PublishTask → Scheduler → Worker → BitBrowser+Playwright → 平台上传
```

## 约定

- 所有 command.execute() 返回 `{"success": bool, "message": str, ...}`
- 配置优先级：CLI 参数 > YAML 配置 > settings.py 默认值
- 注册模式：`@register_command`（cmd）、`@register_downloader`（downloader）、手动注册（plat）
- 数据库：Repository 模式，Session 注入
- 采集去重：`source_platform + source_vid`
- 合成默认：insert_at 随机 10-20s，截尾 3-5s，时长 ≤ 150s

## 搜索参数默认值

- `publish_time=1`（最近一天）
- `filter_duration="1-5"`（1-5 分钟视频）
- `count` 最低 10 条（API 限制）

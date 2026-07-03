# wt-media-flow 历史包袱清理审计

> 审计日期：2026-07-03  
> 范围：无用代码、运行数据、配置和使用说明。  
> 原则：不调整现有架构；本文仅供 review，不执行删除或数据修复。

## 1. Review 结论

建议将清理分为三批：

1. **可直接清理**：缓存、空文件、测试产物、错误说明和已经确认下线的功能文件。
2. **确认后清理**：未被数据库引用的媒体、旧引导视频、数据库历史任务和仓库内二进制。
3. **只修正不删除**：仍在使用但内容过期、重复或存在风险的配置与文档。

当前工作区已有未提交修改。特别是 `conf/pipeline.yaml` 和
`src/app/cli/blend.py` 已在工作区删除，是否正式删除应纳入本次 review。

## 2. 可直接清理

### 2.1 运行缓存与空文件

- [x] 删除所有 `__pycache__/` 和 `*.pyc`。
- [x] 删除仓库及 `data/` 内所有 `.DS_Store`。
- [x] 删除空数据库 `data/publisher.db`，正式数据库位于
  `store/publisher.db`。
- [x] 删除空目录：
  - `data/videos/`
  - `data/overlay_sources/`
  - `data/overlays/`
  - `data/guides/视频0703/`
  - `data/downloads/2026-06-10/`
- [x] 删除 0 字节损坏视频：
  `data/output/2026-06-19/三角洲/7652619310606683407_三角洲S10新赛季内容全爆料新地图新武器新干员.mp4`。

### 2.2 已下线代码和配置

- [x] 确认删除 `src/app/cli/blend.py`。当前工作区已删除，命令注册和
  `main.py` 也已移除相关入口。
- [x] 确认删除 `conf/pipeline.yaml`。当前工作区已删除，项目已无
  `pipeline` 命令。
- [x] 删除源码注释中的历史迁移描述，例如“从 `cmd/` 迁移”和旧文件行号。
- [x] 删除 `src/services/video_service.py` 中“pipeline 用”的过期注释。

### 2.3 明确未使用的代码

- [x] 删除 `utils.random_utils.random_publish_time()`，仓库内没有调用方。
- [x] 删除 `utils.anti_risk.AntiRiskStrategy` 及 `utils/__init__.py` 中对应导出，
  仓库内没有业务调用方。
- [x] 删除 `utils/__init__.py` 中未被使用的聚合导出；当前代码均直接从具体模块导入。

以上仅依据仓库静态引用判断。如果这些 API 被仓库外脚本调用，需要保留。

## 3. 数据清理候选

### 3.1 明确测试产物

以下文件均未被数据库引用，可在确认测试不再需要后删除，合计约 320MiB：

- [x] `data/output/blend_test_luoke.mp4`
- [x] `data/output/blend_test_luoke_balanced_random.mp4`
- [x] `data/output/blend_test_luoke_subtitle_suppressed.mp4`
- [x] `data/output/blend_test_luoke_continuous.mp4`
- [x] `data/output/blend_test_luoke_variant_2.mp4`
- [x] `data/output/blend_landscape_75_review_test.mp4`
- [x] `data/output/composite_blend_test/`

### 3.2 未被数据库引用的媒体

扫描 `data/downloads/` 和 `data/output/` 得到：

| 指标 | 数量/体积 |
|---|---:|
| 磁盘媒体文件 | 1,367 个 / 44.83GiB |
| 初次审计未被数据库路径引用 | 122 个 / 3.99GiB |
| 数据库引用但文件不存在 | 11,637 条路径 |

优先 review：

- [x] `data/output/2026-06-19/0619暗区突围.zip`，约 1.60GiB。
- [x] 上述 blend 测试视频。
- [x] 删除 8 个没有任何数据库记录的下载文件，约 151MiB。
- [x] 复核并删除 105 个路径未引用但可按 `source_vid` 关联任务的输出文件；
  12 条活动任务同步标记为 `FAILED`，其余任务原本已失败。

注意：不能只按“数据库未引用”直接删除。ZIP 打包结果本来就不会写入
`videos` 或 `video_tasks`；部分媒体也可能是人工交付文件。删除前必须同时
按精确路径和 `source_vid` 复核；存在精确数据库记录时先更新逻辑状态再删除。

### 3.3 引导视频回收站

- [x] review `data/guides/回收站/`，约 848MiB。决定：保留。

当前 `conf/composite.yaml` 和 `conf/pools/*.json` 均未引用回收站文件。
如果不再需要回滚旧引导视频，可整体归档到仓库外或删除。

### 3.4 日志、锁和备份

- [x] 删除轮转日志和自动任务历史日志，释放约 17MiB；保留当前
  `log/publisher.log`。
- [x] `store/locks/auto_claw.lock`、`auto_composite.lock` 是运行态文件，
  不应由 Git 跟踪；确认没有任务运行后删除并从索引移除。
- [x] `store/backups/deleted_unreferenced_media_20260512_195641.json`
  属于一次性清理报告，确认无审计价值后移出 Git。
- [x] `store/publisher.sql` 约 11MiB。确认是否仍是恢复基线；若不是，
  移到外部备份并从 Git 移除。
- [x] `store/backups/publisher.before_cleanup_20260512_195641.db`
  约 34MiB，确认恢复窗口结束后删除。

## 4. 数据库历史状态

当前正式数据库约 112MiB：

| 表/状态 | 数量 | 时间范围 |
|---|---:|---|
| `video_tasks.COMPOSITING` | 86 | 2026-05-05 至 2026-06-20 |
| `video_tasks.FAILED` | 1,980 | 2026-05-02 至 2026-06-21 |
| `video_tasks.PENDING` | 2 | 2026-06-11 |
| `plan_items.PENDING` | 4,328 | 2026-05-13 至 2026-06-20 |
| `plan_items.FAILED` | 1,854 | 2026-05-03 至 2026-05-11 |
| `videos` 已删除标记 | 973 | - |

建议 review：

- [x] 将 88 条长期或关联孤立输出的活动任务标记为 `FAILED`。
- [x] 将 4,328 条历史 `PENDING` 计划项标记为 `FAILED`，40 个计划收束为 `done`。
- [x] 保留失败任务及错误信息，不删除数据库记录。
- [x] 将 5,980 条缺失源文件标记为 `deleted=1`，5,679 条缺失合成产物
  标记为 `EXPIRED`，并同步失效关联计划项。
- [x] 清理前已创建数据库备份，并在单一事务中完成状态更新。

目前 `comment_tasks` 为 0，且所有 `plan_items` 都没有 `PUBLISHED` 状态。
需要确认这是业务尚未使用、发布回链未写入，还是历史数据已被重置。

## 5. 配置清理

### 5.1 必须修正

- [x] 已 review `src/conf/settings.py` 中提交过的企微 webhook 和 AI key；
  决定：保留现状，暂不轮换。
- [x] 已 review 将敏感配置移至 `conf/.env` 的建议；决定：暂不执行。
- [x] 更新 `conf/.env.example`。其中 `SCHEDULER_INTERVAL`、
  `MAX_CONCURRENT_TASKS`、`TASK_RETRY_LIMIT`、`BROWSER_POOL_SIZE`、
  `BROWSER_IDLE_TIMEOUT` 均不在当前 `Settings` 中。
- [x] 修正 `conf/.env.example` 的 `DATABASE_URL`，当前示例会指向仓库根目录，
  而默认数据库位于 `store/publisher.db`。
- [x] 修正 `conf/download.yaml` 的旧命令：
  `python main.py cmd download` 已不存在。
- [x] 所有配置示例统一使用 `.venv/bin/python3 src/main.py ...`。

### 5.2 需要业务确认

- [x] `categories.yaml` 包含“绝区零”，但 `claw.yaml` 没有对应关键词。
  决定：保留品类，后续补关键词。
- [x] `overlay.yaml` 使用 dance/live/anime 分类，与游戏主流程完全独立。
  决定：保留 `overlay` 功能及配置。
- [x] 删除 `comment_templates.yaml` 中的推广链接、引导搜索、时效文案和重复
  品类模板，仅保留 `default` 通用评论。
- [x] 已 review `claw.yaml` 中具有时效性的关键词。决定：本轮保留现状。

### 5.3 重复但暂不改结构

87 条引导配置引用实际指向 19 个文件。重复来自：

- `composite.yaml.guide_by_platform`
- `composite.yaml.guide_by_category`
- `pool-hz.json`
- `pool-yy.json`

本轮不调整配置结构。清理时只需：

- [x] 未发现需要删除的已停用品类配置；“绝区零”已确认保留。
- [x] pool 与全局 fallback 路径均有效，保留现有差异。
- [x] 配置修改后运行路径存在性检查。

## 6. 使用说明清理

### README.md

- [x] 已 review 末尾“github限制”和修改 `/etc/hosts` 的机器故障记录。
  决定：保留。
- [x] 主标题和简介不要宣称“小红书自动发布”；该适配器会直接抛出
  `NotImplementedError`。
- [x] 命令参考以 `src/main.py --help` 为准，删除已下线命令。
- [x] 配置表不要把品类示例写成只有三项，实际注册了 15 项。
- [x] 明确 `pack`、`overlay`、`diagnose` 和 Web API 是辅助能力还是日常流程。

### AGENTS.md / CLAUDE.md

- [x] 删除历史迁移说明和过期产品介绍。
- [x] 保留真实执行约束、关键命令、配置优先级和禁止事项。
- [x] 两份文件保留完整内容，并以 `AGENTS.md` 为基准保持字节级一致。

### docs/prd/product-spec.md

- [x] 将“现有能力”和“规划能力”分开。
- [x] 评论任务当前数据库为空，标记为实验性能力。
- [x] Web API 缺少完整运行验证，标记为实验性接口。
- [x] 小红书保持“未实现”，不再出现在已支持平台表述中。

## 7. 仓库内容 review

- [x] `bin/ffmpeg`、`bin/ffprobe`、`bin/yt-dlp` 共约 121MiB，且为 macOS
  平台二进制。决定：保留二进制及 Git 跟踪状态。
- [x] `create_user_example.py` 是一次性初始化脚本。确认是否仍用于部署；
  不再使用则删除，仍使用则在 README 中明确入口。
- [x] `.agents/`、`.claude/`、`.codex/` 存在重复 skill。决定：保留现状，
  但需确认哪一份是源文件，避免三份同时人工编辑。
- [x] 删除已失效的 `build.sh`；其引用的根目录文件和 `conf_online/` 已不存在。

## 8. 建议执行顺序

1. 轮换泄露凭据，修正 `.env.example`。
2. 提交已经确认的 `blend`、`pipeline` 下线变更。
3. 清理缓存、空文件、损坏文件和测试产物。
4. 导出 122 个孤立媒体的完整清单，人工确认后删除。
5. 处理 11,637 条失效数据库路径和历史任务状态。
6. 清理回收站、日志、锁、备份和旧 SQL。
7. 修正配置示例、README、AGENTS.md、CLAUDE.md 和产品说明。
8. 最后运行单元测试、CLI help、配置路径检查和数据库诊断。

## 9. 本轮未执行

- 未修改项目架构或目录分层。
- 未删除数据库业务记录，仅更新历史失效记录的逻辑状态。
- 保留 `data/guides/回收站/`、仓库二进制、时效关键词、GitHub 排障说明、
  敏感配置现状和三套 Agent Skill。

## 10. 执行结果

- 删除 105 个未绑定输出、8 个未入库下载、blend 测试产物和历史 ZIP。
- 删除缓存、空文件、损坏视频、历史日志、运行锁、旧备份和 SQL 快照。
- 删除已下线或未使用的 `blend`、`pipeline`、`build.sh`、用户示例和随机行为工具。
- 数据库清理：
  - 5,980 条缺失源文件记录标记 `deleted=1`。
  - 5,679 条缺失合成产物标记 `EXPIRED`。
  - 88 条长期或孤立输出关联活动任务标记 `FAILED`。
  - 4,328 条历史待发布项标记 `FAILED`。
  - 40 个历史计划收束为 `done`。
- 清理前备份：
  `store/backups/publisher.before_history_cleanup_20260703_155732.db`。
- 验证：8 个单元测试通过，CLI 加载正常，87 个引导配置引用均存在。

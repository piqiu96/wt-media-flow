---
description: 对本项目的运营日常视频流程进行自动化。用户输入目标视频数量和游戏品类时使用：筛选或维护指定游戏的热门关键词，调用项目现有命令抓取抖音素材，按热门活动、游戏攻略、活动攻略、装备攻略筛选，下载视频，批量合成，创建发布计划，并最终打包视频。必须严格遵循本仓库
  src/main.py 已实现的 CLI 命令和 conf 配置。
name: video-claw
---

触发方式：按指定游戏和视频数量执行运营视频采集、筛选、下载、合成、计划创建和打包流程。

# Video Claw

用于执行本项目的游戏运营视频流水线。核心目标是：根据运营输入的游戏和目标视频数量，产出可发布/可打包的视频素材包。

## 输入信息

开始前先确认这些信息：

- `游戏品类`：必须存在于 `conf/categories.yaml`，当前支持 `三角洲`、`暗区突围`、`蛋仔派对`、`火影忍者`、`洛克王国`、`王者荣耀`、`星穹铁道`、`荒野乱斗`、`光遇`、`第五人格`。
- `目标视频数量`：运营希望最终生成/打包的视频数。
- `user_id`：创建计划时必填，命令是 `plan create --user-id <user_id>`。
- `pool`：视频池配置，对应 `conf/pools/<pool>.json`，常见为 `pool-hz`、`pool-yy`。
- `是否需要 dry-run`：当关键词刚调整、用户要求先筛选、或结果质量不确定时，先 dry-run。

如果缺少 `游戏品类`、`目标视频数量`、`pool` 或 `user_id`，且无法从上下文安全推断，只问一个简短问题补齐。

## 硬性规则

- 所有项目命令都必须从仓库根目录执行。
- 所有 Python 项目命令都必须使用 `.venv/bin/python3 src/main.py ...`。
- 不要编造命令，只能使用本项目已有 CLI：`claw`、`composite`、`plan`、`pack`、`account`、`video`、`setup`、`init`、`cleanup`。
- `claw --category` 的合法值以 `conf/categories.yaml` 为准。
- 关键词以 `conf/claw.yaml` 为准；只有用户要求调整关键词或当前热点明显需要更新时，才修改该文件。
- 合成时优先使用 `--pool` 读取 `conf/pools/<pool>.json` 中的引导视频路径，因为这些路径与当前 `data/guides/` 文件更匹配。
- 除非用户明确要求自动发布，否则不要执行 `plan run`。本 skill 的默认终点是 `pack` 打包。

## 内容筛选标准

保留标题、标签、描述中明确符合以下方向的视频：

- 热门活动
- 游戏攻略
- 活动攻略
- 装备攻略
- 福利、白嫖、免费领取、限时领取
- 赛季任务、新赛季、新版本热点

排除以下内容：

- 与指定游戏无关
- 纯娱乐、纯剪辑、无攻略信息的普通对局
- 无活动/攻略/装备/福利意图的直播切片
- 标题党、低信息量反应视频、无明确运营价值内容
- 与当前运营目标无关的泛内容

热度优先级遵循项目已有数据：抓取后会记录 `like_count`、`collect_count`、`comment_count`，计划和重合成相关逻辑会优先使用 `(like_count + collect_count)` 排序。

## 标准流程

### 1. 检查环境

环境不确定时先执行：

```bash
.venv/bin/python3 --version
.venv/bin/python3 src/main.py setup --check
```

本项目预期 Python 为 `3.14.x`。

### 2. 检查品类和关键词

执行前查看配置：

```bash
sed -n '1,160p' conf/categories.yaml
sed -n '1,180p' conf/claw.yaml
```

关键词应围绕运营需要组织。常用意图词：

- 活动、活动攻略、限时活动
- 福利、白嫖、免费领取、礼包
- 攻略、新手攻略、赛季攻略、速通
- 装备推荐、新武器、新版本
- 当前活动名、节日名、赛季名

如果要更新热门关键词，只调整 `conf/claw.yaml` 里对应 `keywords_by_category.<游戏品类>` 的列表，不改无关品类。

### 3. 先抓取结果

关键词生成后直接执行fetch，等fetch入库以后不需要的直接该数据库状态就可以，这样避免浪费资源重复抓取。 执行后根据标题、标签、作者、点赞、评论、收藏等信息判断是否需要调整关键词，直到结果基本符合预期的热门活动/游戏攻略/活动攻略/装备攻略为止。

游戏个数比较多的时候，需要控制好并发，避免出现过多的失败。通常抓取过程中最多1-2个游戏同时进行，其他的派对后面再抓取即可

```bash
.venv/bin/python3 src/main.py claw --category <游戏品类> --config conf/claw.yaml --fetch
```

如果无关内容太多，改窄关键词，或临时用单关键词验证：

```bash
.venv/bin/python3 src/main.py claw --category <游戏品类> --keyword "<游戏品类> 活动攻略" --count <数量> --dry-run
```

dry-run 结果重点看标题、标签、作者、点赞、评论、收藏。只要结果明显偏离“热门活动/游戏攻略/活动攻略/装备攻略”，就先调整关键词再正式抓取。

### 4. 抓取并下载

常规一段式抓取入库并下载：注意控制并发，一次下载命令不超过2个

```bash
.venv/bin/python3 src/main.py claw --category <游戏品类> --config conf/claw.yaml
```


如果需要先入库审核，再下载，使用两阶段：

```bash
.venv/bin/python3 src/main.py claw --category <游戏品类> --fetch --config conf/claw.yaml
.venv/bin/python3 src/main.py claw --download --category <游戏品类>
```

下载失败重试：

```bash
.venv/bin/python3 src/main.py claw --download --category <游戏品类> --retry-failed
```

注意：`--retry-failed` 会有人工确认提示，不要绕过确认。

### 5. 批量合成视频

按目标视频数量合成。若有 `pool`，优先使用：

```bash
.venv/bin/python3 src/main.py composite --batch --category <游戏品类> --pool <pool> --config conf/composite.yaml --limit <目标视频数量>
```

没有 `pool` 时：

```bash
.venv/bin/python3 src/main.py composite --batch --category <游戏品类> --config conf/composite.yaml --limit <目标视频数量>
```

如果提示找不到引导视频，检查：

```bash
find data/guides -type f -iname '*.mp4'
sed -n '1,220p' conf/pools/pool-hz.json
sed -n '1,220p' conf/pools/pool-yy.json
```

然后选择正确的 `--pool`，或在用户确认后显式传入 `--guide <路径>`。

### 6. 创建发布计划

先 dry-run 预览：

```bash
.venv/bin/python3 src/main.py plan create --user-id <user_id> --dry-run
```

确认后正式创建：

```bash
.venv/bin/python3 src/main.py plan create --user-id <user_id>
```

查看计划并记录 `plan_id`：

```bash
.venv/bin/python3 src/main.py plan list
```

### 7. 打包视频

默认打包整个计划：

```bash
.venv/bin/python3 src/main.py pack --plan-id <plan_id>
```

只打包某个账号：

```bash
.venv/bin/python3 src/main.py pack --plan-id <plan_id> --account-id <account_id>
```

只有用户明确要求 AI 标题时才加：

```bash
.venv/bin/python3 src/main.py pack --plan-id <plan_id> --ai-titles
```

## 常见问题处理

- `--category` 无效：查看并按需更新 `conf/categories.yaml`，不要直接运行无效品类。
- 抓不到素材：放宽 `conf/claw.yaml` 的关键词，或临时使用更通用的 `--keyword` dry-run。
- 无关素材太多：加入活动、攻略、福利、装备等意图词，减少泛词。
- 没有待合成素材：先确认是否已下载，执行 `claw --download --category <游戏品类>`。
- 合成找不到 guide：优先改用 `--pool pool-hz` 或 `--pool pool-yy`。
- `plan create` 失败：确认传入了 `--user-id`，并检查该用户下是否有可用账号、浏览器容器和已合成任务。
- 不要因为计划不足就直接发布；先补抓、补合成，再重新创建计划。

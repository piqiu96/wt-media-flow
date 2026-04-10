---
name: xhs
description: guide auto publish video to xhs.
license: Complete terms in LICENSE.txt
---

# 小红书发布视频

自动化发布视频到小红书平台，支持填写标题、描述、封面、标签等信息。

## 使用方式

```
/xiaohongshu-publish --video <视频路径> --title <标题> --desc <描述> --cover <封面路径> --tags <标签1,标签2>
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--video` | 是 | 本地视频文件路径 |
| `--title` | 是 | 视频标题 |
| `--desc` | 否 | 视频描述内容 |
| `--cover` | 否 | 封面图片路径，不填则自动截取 |
| `--tags` | 否 | 标签列表，逗号分隔 |

## 执行流程

当用户调用此 skill 时，按以下步骤执行：

### 1. 参数解析

解析用户传入的参数：
- `video`: 视频文件绝对路径
- `title`: 视频标题（必填，限制字数）
- `desc`: 视频描述（可选）
- `cover`: 封面图片路径（可选）
- `tags`: 标签列表（可选，格式：标签1,标签2,标签3）

### 2. 环境检查

- 检查视频文件是否存在
- 检查封面文件是否存在（如果提供）
- 确认比特浏览器 API 是否可用（默认 `http://127.0.0.1:54345`）

### 3. 启动浏览器

通过比特浏览器 API 启动浏览器环境：
```python
BIT_API = "http://127.0.0.1:54345"
PROFILE_ID = "<用户配置的浏览器指纹ID>"
```

### 4. 执行发布流程

使用 Playwright 执行以下自动化步骤：

1. **打开小红书创作者中心**
   - 访问 `https://creator.xiaohongshu.com/publish/publish`
   - 等待页面加载完成

2. **检查登录状态**
   - 如果未登录，提示用户扫码登录
   - 等待登录成功

3. **上传视频**
   - 点击上传区域或使用文件选择器
   - 选择本地视频文件
   - 等待视频上传完成

4. **填写标题**
   - 在标题输入框输入视频标题
   - 使用拟人化输入（随机延迟）

5. **填写描述**
   - 在描述区域输入视频描述内容
   - 支持多行文本

6. **上传封面**
   - 如果提供了封面图片，点击上传封面
   - 选择封面文件
   - 等待上传完成

7. **添加标签**
   - 逐个添加标签
   - 每个标签添加后等待短暂延迟

8. **发布**
   - 点击发布按钮
   - 等待发布完成

### 5. 结果反馈

- 发布成功：返回发布链接或成功提示
- 发布失败：返回错误信息和可能的原因

## 配置项

在项目的 `library/xiaohongshu_config.py` 中配置：

```python
# 比特浏览器配置
BIT_API = "http://127.0.0.1:54345"
PROFILE_ID = "your_profile_id"

# 发布配置
DEFAULT_VISIBILITY = "public"  # public/private
AUTO_PUBLISH = True  # 是否自动点击发布，False 则停留在预览页面
```

## 注意事项

1. 首次使用需要扫码登录小红书账号
2. 视频上传时间取决于视频大小和网络状况
3. 建议在发布前检查内容是否符合平台规范
4. 标签数量建议控制在 5 个以内

## 示例

```bash
# 发布视频
/xiaohongshu-publish --video /Users/pika/Desktop/my_video.mp4 --title "今日穿搭分享" --desc "春季新款穿搭推荐" --cover /Users/pika/Desktop/cover.jpg --tags "穿搭,春季,时尚"

# 仅上传视频不发布
/xiaohongshu-publish --video /Users/pika/Desktop/test.mp4 --title "测试视频" --no-publish
```
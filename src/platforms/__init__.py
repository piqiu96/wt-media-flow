"""
平台适配层 — 自动注册所有已实现的平台

import 各平台子包即触发注册。
"""
# 已实现平台
import platforms.baijiahao  # noqa: F401
import platforms.bilibili   # noqa: F401

# 枚举已定义、发布逻辑待实现（注册后可查询 capabilities，调用发布会抛 NotImplementedError）
import platforms.xiaohongshu  # noqa: F401

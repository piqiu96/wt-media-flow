"""
pool_config — 视频池配置加载工具

视频池通过 JSON 文件管理（conf/pools/{pool_id}.json），不在数据库存储。
每个池子定义各品类的引导视频路径和合成参数，多个用户可共享同一个池子。
"""
import json
from pathlib import Path
from typing import Optional


def load_pool(pool_id: str) -> dict:
    """加载指定 pool_id 对应的 JSON 配置文件。

    文件路径：{BASE_DIR}/conf/pools/{pool_id}.json

    返回 pool 配置字典，格式：
    {
      "id": "pool-a",
      "name": "A组",
      "categories": {
        "三角洲": {
          "guide": "data/guides/三角洲/guide.mp4",
          "guides": {
            "baijiahao": "data/guides/三角洲/guide-bjh.mp4",
            "bilibili": "data/guides/三角洲/guide-bili.mp4"
          },
          "insert_at": 12
        },
        ...
      }
    }

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: pool_id 为空
    """
    if not pool_id:
        raise ValueError("pool_id 不能为空")

    from conf.settings import settings
    path = Path(settings.BASE_DIR) / "conf" / "pools" / f"{pool_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"视频池配置不存在: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def get_pool_guide(pool_id: str, category: str,
                   platform: str | None = None) -> Optional[str]:
    """获取指定池子中某品类的引导视频路径，不存在返回 None。

    优先级：categories.{category}.guides.{platform} > categories.{category}.guide
    """
    if not pool_id or not category:
        return None
    try:
        pool = load_pool(pool_id)
        cat_cfg = pool.get("categories", {}).get(category, {})
        if platform:
            guide = cat_cfg.get("guides", {}).get(platform)
            if guide:
                return guide
        return cat_cfg.get("guide")
    except (FileNotFoundError, ValueError):
        return None


def get_pool_category_config(pool_id: str, category: str) -> dict:
    """获取指定池子中某品类的完整合成配置（guide/insert_at/max_duration 等）。

    返回空字典表示未配置，调用方需自行 fallback 到全局 composite.yaml。
    """
    if not pool_id or not category:
        return {}
    try:
        pool = load_pool(pool_id)
        return pool.get("categories", {}).get(category, {})
    except (FileNotFoundError, ValueError):
        return {}

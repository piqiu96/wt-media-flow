"""
评论话术库工具：从 YAML 配置文件按品类随机取评论内容
"""
import random
from pathlib import Path

_DEFAULT_PATH = "conf/comment_templates.yaml"


def get_random_comment(category: str,
                       templates_path: str = _DEFAULT_PATH) -> str:
    """
    按 category 从话术库随机取一条评论。
    找不到对应品类时使用 default。
    """
    path = Path(templates_path)
    if not path.exists():
        return "内容不错，收藏了！"
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            tpl = yaml.safe_load(f) or {}
    except Exception:
        return "内容不错，收藏了！"

    pool = tpl.get(category) or tpl.get("default") or ["内容不错，收藏了！"]
    return random.choice(pool)

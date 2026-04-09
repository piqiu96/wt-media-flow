import random
import time
from datetime import datetime, timedelta
from conf.settings import settings

def random_publish_time(start_hour: int = None, end_hour: int = None) -> datetime:
    """生成随机发布时间"""
    start_hour = start_hour or settings.PUBLISH_START_HOUR
    end_hour = end_hour or settings.PUBLISH_END_HOUR

    now = datetime.utcnow()
    start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=59, second=59, microsecond=0)

    # 如果已过当天发布时段，则安排到明天
    if now >= end:
        start += timedelta(days=1)
        end += timedelta(days=1)

    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))

    return start + timedelta(seconds=random_seconds)

def random_delay(min_ms: int = 500, max_ms: int = 2000) -> float:
    """随机延迟（毫秒）"""
    return random.uniform(min_ms / 1000, max_ms / 1000)

def random_mouse_move(page, width: int = 1920, height: int = 1080):
    """随机鼠标移动"""
    x = random.randint(100, width - 100)
    y = random.randint(100, height - 100)
    page.mouse.move(x, y)

def random_scroll(page, min_y: int = 200, max_y: int = 800):
    """随机滚动"""
    y = random.randint(min_y, max_y)
    page.mouse.wheel(0, y)

def random_sleep(min_sec: float = 1.0, max_sec: float = 3.0):
    """随机等待"""
    time_to_wait = random.uniform(min_sec, max_sec)
    time.sleep(time_to_wait)

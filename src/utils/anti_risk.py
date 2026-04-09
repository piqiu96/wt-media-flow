import time
import random
from playwright.sync_api import Page
from .random_utils import random_delay, random_mouse_move, random_scroll

class AntiRiskStrategy:
    """反风控策略"""

    @staticmethod
    def human_type(page: Page, selector: str, text: str):
        """拟人化输入"""
        page.click(selector)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")

        for char in text:
            page.keyboard.type(char, delay=random.randint(30, 120))

        time.sleep(random_delay(500, 1500))

    @staticmethod
    def human_browse(page: Page, duration: int = 30):
        """模拟浏览行为"""
        start = time.time()
        while time.time() - start < duration:
            # 随机滚动
            random_scroll(page)
            time.sleep(random.uniform(1, 3))

            # 随机移动鼠标
            random_mouse_move(page)
            time.sleep(random.uniform(0.5, 1.5))

    @staticmethod
    def simulate_behavior(page: Page):
        """模拟人类行为"""
        # 1. 随机移动鼠标
        for _ in range(2):
            random_mouse_move(page)
            time.sleep(random.uniform(0.5, 1))

        # 2. 随机滚动
        random_scroll(page)
        time.sleep(random.uniform(1, 2))

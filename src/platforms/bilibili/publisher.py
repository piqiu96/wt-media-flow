"""
哔哩哔哩发布器 — 实现 PublisherProtocol

三段式：fill_form → submit（自动提交） → fetch_published_url
"""
import os
import re
import time
import random

from playwright.sync_api import Page

from platforms.base import (
    PlatformCapabilities, PublishPayload, FillResult, SubmitResult,
)
from utils.log import get_logger

logger = get_logger(__name__)

# 超时常量
_TIMEOUT = 300000           # 5 分钟
_EL_TIMEOUT = 60000         # 1 分钟
_IDLE_TIMEOUT = 5000        # 5 秒

# B站视频分区映射（常用游戏分区）
_GAME_ZONES = {
    "三角洲": "单机游戏",
    "暗区突围": "单机游戏",
    "蛋仔派对": "单机游戏",
    "游戏": "单机游戏",
    "火影忍者": "单机游戏",
}


class BilibiliPublisher:
    """哔哩哔哩视频发布器"""

    platform_name = "bilibili"
    capabilities = PlatformCapabilities(
        supports_video=True,
        supports_cover_upload=True,
        supports_comment=False,          # 暂不支持评论
        supports_scheduled_publish=True,
        requires_manual_confirm=False,   # B站支持自动提交
        allows_same_source_reuse=True,   # 同素材可多次分配（不同去重种子）
    )

    # ── 阶段 1：fill_form ─────────────────────────────────────

    def fill_form(self, page: Page, payload: PublishPayload) -> FillResult:
        """填充B站视频投稿表单"""
        try:
            # 1. 进入投稿页
            page.goto(
                "https://member.bilibili.com/platform/upload/video/frame",
                wait_until="domcontentloaded", timeout=_TIMEOUT,
            )
            try:
                page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            time.sleep(random.uniform(3, 5))
            logger.info(f"页面标题: {page.title()}")
            logger.info(f"页面URL:  {page.url}")

            # 2. 上传视频文件
            upload_selectors = [
                'input[type="file"][accept*="video"]',
                'input[type="file"]',
                '.bcc-upload input[type="file"]',
            ]
            upload_el = None
            for sel in upload_selectors:
                try:
                    page.wait_for_selector(sel, state="attached", timeout=_EL_TIMEOUT)
                    upload_el = sel
                    break
                except Exception:
                    pass
            if not upload_el:
                raise RuntimeError("未找到视频上传区域")

            logger.info(f"找到上传元素: {upload_el}")
            page.locator(upload_el).first.set_input_files(
                payload.video_path, timeout=_TIMEOUT)
            logger.info(f"视频文件已选择: {payload.video_path}")

            # 3. 等待上传+转码完成
            if not self._wait_for_upload(page, timeout=600):
                raise RuntimeError("视频上传/转码超时（600s）")
            time.sleep(random.uniform(2, 3))

            # 4. 填写标题
            title_selectors = [
                '.video-title .input-val',
                'input[maxlength="80"]',
                '.title-input input',
            ]
            for sel in title_selectors:
                try:
                    page.wait_for_selector(sel, timeout=10000)
                    page.click(sel)
                    page.keyboard.press("Control+a")
                    page.keyboard.type(payload.title[:80])
                    logger.info(f"标题已填写: {payload.title[:50]}")
                    break
                except Exception:
                    continue

            # 5. 填写标签
            if payload.tags:
                try:
                    tag_input_sels = [
                        '.tag-input-wrp input',
                        'input[placeholder*="标签"]',
                        'input[placeholder*="tag"]',
                    ]
                    for sel in tag_input_sels:
                        try:
                            page.wait_for_selector(sel, timeout=5000)
                            for tag in payload.tags[:5]:
                                tag = tag.strip()
                                if not tag:
                                    continue
                                page.click(sel)
                                page.keyboard.type(tag)
                                page.keyboard.press("Enter")
                                time.sleep(random.uniform(0.3, 0.5))
                            logger.info(f"标签已填写: {payload.tags[:5]}")
                            break
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning(f"标签填写失败（跳过）: {e}")

            # 6. 上传封面
            if payload.cover_path and os.path.isfile(payload.cover_path):
                self._upload_cover(page, payload.cover_path)

            # 7. 选择分区（基于 category 映射）
            category = payload.category or ""
            self._select_zone(page, category)

            return FillResult(success=True, message="B站投稿表单填充完成")

        except Exception as e:
            return FillResult(success=False, error=str(e))

    def _upload_cover(self, page: Page, cover_path: str) -> None:
        """直接给封面 file input 赋值，无需点击触发"""
        cover_sels = [
            'input[type="file"][accept*="image"]',
            '.cover-upload input[type="file"]',
            '.upload-cover input[type="file"]',
        ]
        for sel in cover_sels:
            try:
                el = page.locator(sel).first
                el.set_input_files(cover_path, timeout=10000)
                time.sleep(random.uniform(1.0, 1.5))
                logger.info(f"封面已上传: {cover_path}")
                return
            except Exception:
                continue
        logger.warning("未找到封面上传 input，跳过封面上传")

    def _select_zone(self, page: Page, category: str = "") -> None:
        """选择投稿分区。
        流程：点击分区输入框 → 选一级分区"游戏" → 选二级分区（单机游戏/网络游戏）
        category 为空或未匹配时默认选"单机游戏"。
        """
        zone_name = _GAME_ZONES.get(category, "单机游戏")
        logger.info(f"尝试选择分区: category={category!r} → {zone_name}")

        try:
            # 点击分区选择触发器（多种可能的选择器）
            zone_trigger_sels = [
                '#video-up-app > div.video-basic-wrp > div.video-basic > div.form > div:nth-child(5) > div > div.selector-container > div > div',
                '.zone-select',
                '[class*="zone-select"]',
                'input[placeholder*="分区"]',
                '.select-wrap:has-text("分区")',
                '.type-select',
                '[class*="type-select"]',
                '[class*="channel"]',
                '.bcc-select',
                '[placeholder*="选择分区"]',
                '[placeholder*="请选择分区"]',
                ':text("请选择分区")',
                ':text("选择分区")',
            ]
            triggered = False
            for sel in zone_trigger_sels:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        el.click()
                        triggered = True
                        logger.info(f"分区触发器已点击: {sel}")
                        time.sleep(random.uniform(0.5, 1.0))
                        break
                except Exception:
                    continue

            # JS 兜底：扫描 DOM 找含「分区」文字的可点击元素
            if not triggered:
                try:
                    clicked = page.evaluate("""() => {
                        const keywords = ['分区', '类型'];
                        const tags = ['input', 'button', 'div', 'span', 'label', 'li'];
                        for (const kw of keywords) {
                            for (const tag of tags) {
                                const els = Array.from(document.querySelectorAll(tag));
                                for (const el of els) {
                                    const txt = (el.innerText || el.placeholder || el.value || '').trim();
                                    const r = el.getBoundingClientRect();
                                    if (txt.includes(kw) && r.width > 0 && r.height > 0) {
                                        el.click();
                                        return txt;
                                    }
                                }
                            }
                        }
                        return null;
                    }""")
                    if clicked:
                        triggered = True
                        logger.info(f"分区触发器 JS 兜底点击成功: '{clicked}'")
                        time.sleep(random.uniform(0.5, 1.0))
                except Exception as e:
                    logger.debug(f"JS 兜底失败: {e}")

            if not triggered:
                logger.warning("未找到分区触发器，跳过分区选择")
                return

            # 一级分区：游戏
            try:
                game_sel = ':text-is("游戏")'
                page.locator(game_sel).first.click(timeout=5000)
                logger.info("已选一级分区: 游戏")
                time.sleep(random.uniform(1.0, 1.5))  # 等子菜单渲染
            except Exception as e:
                logger.warning(f"一级分区「游戏」点击失败: {e}")
                return

            # 二级分区：精确匹配 → 部分匹配 → 搜索框
            try:
                sub_sel = f':text("{zone_name}")'
                page.locator(sub_sel).first.click(timeout=5000)
                logger.info(f"已选二级分区: {zone_name}")
                time.sleep(random.uniform(0.3, 0.6))
            except Exception as e:
                # 降级：尝试直接搜索输入框
                logger.warning(f"二级分区「{zone_name}」点击失败: {e}，尝试搜索输入")
                try:
                    search_sel = 'input[placeholder*="搜索分区"]'
                    page.locator(search_sel).first.type(zone_name, timeout=3000)
                    time.sleep(0.5)
                    page.locator(f':text-is("{zone_name}")').first.click(timeout=3000)
                    logger.info(f"搜索选择分区成功: {zone_name}")
                except Exception as e2:
                    logger.warning(f"分区搜索也失败，跳过: {e2}")

        except Exception as e:
            logger.warning(f"分区选择整体失败（不影响投稿，需手动确认）: {e}")

    # ── 阶段 2：submit ────────────────────────────────────────

    def submit(self, page: Page) -> SubmitResult:
        """点击投稿按钮"""
        try:
            submit_selectors = [
                '#video-up-app > div.video-basic-wrp > div.video-basic > div.form > div:nth-child(17) > div > div > span',
                '.submit-add:has-text("投稿")',
                'button:has-text("投稿")',
                '.submit-btn:has-text("投稿")',
                'button:has-text("立即投稿")',
                '[class*="submit"]:has-text("投稿")',
                ':text-is("立即投稿")',
                ':text-is("提交")',
            ]
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible() and btn.is_enabled():
                        btn.click()
                        logger.info(f"已点击投稿: {sel}")
                        time.sleep(random.uniform(2, 3))
                        return SubmitResult(success=True)
                except Exception:
                    continue

            raise RuntimeError("未找到可点击的投稿按钮")

        except Exception as e:
            return SubmitResult(success=False, error=str(e))

    # ── 阶段 3：fetch_published_url ───────────────────────────

    def fetch_published_url(self, page: Page,
                            known_urls: set[str] | None = None,
                            poll_timeout: int = 120) -> str:
        """从投稿管理页获取最新视频链接"""
        if known_urls is None:
            known_urls = set()

        content_list_url = "https://member.bilibili.com/platform/upload-manager/article"

        deadline = time.time() + poll_timeout
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            page.goto(content_list_url, wait_until="domcontentloaded",
                      timeout=_TIMEOUT)
            try:
                page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            time.sleep(2)

            try:
                # B站稿件管理页链接格式
                link_sel = 'a[href*="/video/BV"]'
                page.wait_for_selector(link_sel, timeout=_EL_TIMEOUT)
                links = page.locator(link_sel).all()
                for link in links[:10]:
                    href = (link.get_attribute("href") or "").strip()
                    if not href:
                        continue
                    # 提取 BV 号
                    m = re.search(r'(BV[\w]+)', href)
                    if m:
                        public_url = f"https://www.bilibili.com/video/{m.group(1)}"
                    else:
                        public_url = href if href.startswith("http") else f"https:{href}"
                    if public_url not in known_urls:
                        logger.info(f"[URL抓取] 第{attempt}次 → {public_url}")
                        return public_url
            except Exception:
                pass

            remaining = int(deadline - time.time())
            logger.info(f"[URL轮询] 未发现新链接，{remaining}s后重试...")
            time.sleep(10)

        logger.warning(f"[URL超时] 轮询{poll_timeout}s未找到新链接")
        return ""

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _wait_for_upload(page: Page, timeout: int = 600) -> bool:
        """等待视频上传+转码完成"""
        deadline = time.time() + timeout
        logger.info("等待视频上传/转码...")
        while time.time() < deadline:
            try:
                # B站上传完成信号：进度 100% 或 "上传完成" 文字
                success_sels = [
                    ':text("上传完成")',
                    '.upload-progress:has-text("100%")',
                    '.file-item-status:has-text("完成")',
                ]
                for sel in success_sels:
                    try:
                        if page.locator(sel).first.is_visible():
                            logger.info("上传/转码完成")
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
            elapsed = int(time.time() - (deadline - timeout))
            if elapsed % 30 == 0:
                logger.info(f"上传中... {elapsed}s")
            time.sleep(5)
        return False

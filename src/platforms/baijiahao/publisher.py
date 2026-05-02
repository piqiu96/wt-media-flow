"""
百家号发布器 — 实现 PublisherProtocol

三段式：fill_form → submit（人工确认，空操作） → fetch_published_url
"""
import re
import time
import random

from playwright.sync_api import Page

from platforms.base import (
    PlatformCapabilities, PublishPayload, FillResult, SubmitResult,
)
from utils.log import get_logger

logger = get_logger(__name__)

# 统一超时（毫秒）
_TIMEOUT = 300000           # 5 分钟：页面加载 / 文件上传等
_EL_TIMEOUT = 60000         # 1 分钟：元素查找
_IDLE_TIMEOUT = 5000        # 5 秒：networkidle
_IDLE_TIMEOUT_PUBLISH = 10000  # 10 秒：发布页 networkidle


class BaijiahaoPublisher:
    """百家号视频发布器"""

    platform_name = "baijiahao"
    capabilities = PlatformCapabilities(
        supports_video=True,
        supports_cover_upload=False,      # 封面上传暂跳过（会触发 session 检测）
        supports_comment=True,
        supports_scheduled_publish=False,
        requires_manual_confirm=True,     # 百家号需人工点发布
        allows_same_source_reuse=False,   # 同源视频不复用
    )

    # ── 阶段 1：fill_form ─────────────────────────────────────

    def fill_form(self, page: Page, payload: PublishPayload) -> FillResult:
        """填充百家号视频发布表单（不提交）"""
        try:
            # 1. 进入视频发布页
            page.goto(
                "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                wait_until="domcontentloaded", timeout=_TIMEOUT,
            )
            try:
                page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT_PUBLISH)
            except Exception:
                pass
            time.sleep(random.uniform(3, 5))
            logger.info(f"页面标题: {page.title()}")
            logger.info(f"页面URL:  {page.url}")

            # 1.5 关闭新手引导遮罩
            try:
                page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                pass
            for tour_sel in [
                'button:has-text("我知道了")',
                'button:has-text("跳过")',
                'button:has-text("关闭")',
                '[class*="tour"] button',
                '[class*="guide"] button',
            ]:
                try:
                    btn = page.locator(tour_sel).first
                    if btn.is_visible():
                        btn.click()
                        logger.info(f"已关闭引导弹窗: {tour_sel}")
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # 2. 找上传按钮并选择视频文件
            upload_selectors = [
                'input[type="file"][accept*=".mp4"]',
                'input[type="file"]',
                '[data-testid="video-upload-btn"]',
            ]
            upload_el = None
            for sel in upload_selectors:
                try:
                    state = "attached" if "input" in sel and "file" in sel else "visible"
                    page.wait_for_selector(sel, state=state, timeout=_EL_TIMEOUT)
                    upload_el = sel
                    break
                except Exception:
                    pass
            if not upload_el:
                raise RuntimeError("未找到视频上传区域")

            logger.info(f"找到上传元素: {upload_el}")
            if "input" in upload_el and "file" in upload_el:
                page.locator(upload_el).first.set_input_files(
                    payload.video_path, timeout=_TIMEOUT)
            else:
                with page.expect_file_chooser(timeout=_TIMEOUT) as fc_info:
                    page.locator(upload_el).first.click(force=True)
                fc_info.value.set_files(payload.video_path, timeout=_TIMEOUT)
            logger.info(f"视频文件已选择: {payload.video_path}")

            # 3. 等待上传完成（coverWrap 出现）
            if not self._wait_for_upload(page, timeout=900):
                raise RuntimeError("视频上传超时（900s）")
            time.sleep(random.uniform(1, 2))

            # 4. 填写标题
            title_sel = '[class*="editorArea"]'
            try:
                page.wait_for_selector(title_sel, timeout=_EL_TIMEOUT)
                page.click(title_sel)
                page.keyboard.press("Control+a")
                page.keyboard.type(payload.title[:100])
                time.sleep(random.uniform(0.5, 1))
                logger.info(f"标题已填写: {payload.title[:50]}")
            except Exception as e:
                logger.warning(f"标题填写失败: {e}")

            # 5. 封面上传暂跳过
            logger.info("封面上传已跳过")

            return FillResult(success=True, message="内容填充完成")

        except Exception as e:
            return FillResult(success=False, error=str(e))

    # ── 阶段 2：submit ────────────────────────────────────────

    def submit(self, page: Page) -> SubmitResult:
        """百家号为人工确认模式，submit 为空操作"""
        return SubmitResult(success=True)

    # ── 阶段 3：fetch_published_url ───────────────────────────

    def fetch_published_url(self, page: Page,
                            known_urls: set[str] | None = None,
                            poll_timeout: int = 300) -> str:
        """从内容列表页抓取最新发布的文章链接"""
        if known_urls is None:
            known_urls = set()

        content_list_url = (
            "https://baijiahao.baidu.com/builder/rc/content"
            "?currentPage=1&pageSize=10&search=&type=&collection="
            "&startDate=&endDate="
        )
        sel = 'a[href*="builder/preview/s?id="]'

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
                page.wait_for_selector(sel, timeout=_EL_TIMEOUT)
                links = page.locator(sel).all()
                for link in links[:10]:
                    href = (link.get_attribute("href") or "").strip()
                    if not href:
                        continue
                    m = re.search(r'[?&]id=(\d+)', href)
                    if m:
                        public_url = f"https://baijiahao.baidu.com/s?id={m.group(1)}"
                    else:
                        public_url = href
                    if public_url not in known_urls:
                        logger.info(f"[URL抓取] 第{attempt}次 → {public_url}")
                        return public_url
            except Exception:
                pass

            remaining = int(deadline - time.time())
            logger.info(
                f"[URL轮询] 未发现新链接（已知{len(known_urls)}条），"
                f"{remaining}s后重试..."
            )
            time.sleep(15)

        logger.warning(f"[URL超时] 轮询{poll_timeout}s未找到新链接")
        return ""

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _wait_for_upload(page: Page, timeout: int = 900) -> bool:
        """等待视频上传完成：以封面区出现（coverWrap）为信号"""
        deadline = time.time() + timeout
        logger.info("等待视频上传完成...")
        while time.time() < deadline:
            try:
                closed = page.is_closed()
                logger.debug(f"[DIAG] page closed={closed}, url={page.url}")
                if closed:
                    logger.warning("[DIAG] page 已关闭，退出上传等待")
                    return False
            except Exception as diag_e:
                logger.debug(f"[DIAG] page 状态检查失败: {diag_e}")
            try:
                el = page.wait_for_selector(
                    '[class*="coverWrap"]', timeout=_EL_TIMEOUT)
                if el and el.is_visible():
                    logger.info("上传完成，封面区已出现")
                    return True
            except Exception:
                pass
            elapsed = int(time.time() - (deadline - timeout))
            logger.info(f"上传中... {elapsed}s")
        return False

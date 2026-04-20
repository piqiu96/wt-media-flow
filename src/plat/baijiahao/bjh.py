import time
import random
from ..base import BasePlatform
from typing import Optional, Dict, Any

# 统一超时（毫秒）：页面加载 / 文件上传等耗时操作
_TIMEOUT = 300000  # 5 分钟
# 元素查找超时
_EL_TIMEOUT = 60000  # 1 分钟
# 评论框选择器逐个尝试超时（短，快速轮换）
_CMT_SEL_TIMEOUT = 5000  # 5 秒
# networkidle 等待超时（SPA 页面很难真正 idle，快速放弃）
_IDLE_TIMEOUT = 5000          # 评论/列表页 5 秒
_IDLE_TIMEOUT_PUBLISH = 10000  # 发布页稍长 10 秒


class BaijiahaoPlatform(BasePlatform):
    platform_name = "baijiahao"

    def wait_for_upload(self, timeout: int = 900) -> bool:
        """等待视频上传完成：以封面区出现（coverWrap）为信号"""
        deadline = time.time() + timeout
        print("  等待视频上传完成...", flush=True)
        while time.time() < deadline:
            try:
                el = self.page.wait_for_selector('[class*="coverWrap"]', timeout=_EL_TIMEOUT)
                if el and el.is_visible():
                    print("  上传完成，封面区已出现")
                    return True
            except Exception:
                pass
            elapsed = int(time.time() - (deadline - timeout))
            print(f"  上传中... {elapsed}s", flush=True)
        return False

    def fill_only(self, video_path: str, title: str,
                  description: str = "", tags: str = "",
                  cover_path: Optional[str] = None) -> Dict[str, Any]:
        """阶段1：填充内容（goto→上传视频→填标题→上传封面），不等待人工确认"""
        try:
            # 1. 进入百家号视频发布页
            self.page.goto("https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                           wait_until="domcontentloaded", timeout=_TIMEOUT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT_PUBLISH)
            except Exception:
                pass
            time.sleep(random.uniform(3, 5))
            print(f"  页面标题: {self.page.title()}")
            print(f"  页面URL:  {self.page.url}")

            # 1.5 关闭新手引导遮罩（cheetah-tour 蒙层）
            try:
                self.page.keyboard.press("Escape")
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
                    btn = self.page.locator(tour_sel).first
                    if btn.is_visible():
                        btn.click()
                        print(f"  已关闭引导弹窗: {tour_sel}")
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # 2. 找上传按钮并选择视频文件
            upload_selectors = [
                'input[type="file"][accept*="video"]',
                'input[type="file"]',
                '[data-testid="video-upload-btn"]',
            ]
            upload_el = None
            for sel in upload_selectors:
                try:
                    # file input 通常隐藏，用 attached 忽略可见性
                    state = "attached" if 'input' in sel and 'file' in sel else "visible"
                    self.page.wait_for_selector(sel, state=state, timeout=_EL_TIMEOUT)
                    upload_el = sel
                    break
                except Exception:
                    pass
            if not upload_el:
                raise RuntimeError("未找到视频上传区域")

            print(f"  找到上传元素: {upload_el}")
            if 'input' in upload_el and 'file' in upload_el:
                self.page.locator(upload_el).first.set_input_files(video_path, timeout=_TIMEOUT)
            else:
                with self.page.expect_file_chooser(timeout=_TIMEOUT) as fc_info:
                    self.page.locator(upload_el).first.click(force=True)
                fc_info.value.set_files(video_path, timeout=_TIMEOUT)
            print(f"  视频文件已选择: {video_path}")

            # 3. 等待上传完成（coverWrap 出现）
            if not self.wait_for_upload(timeout=900):
                raise RuntimeError("视频上传超时（900s）")
            time.sleep(random.uniform(1, 2))

            # 4. 填写标题（editorArea 是 contenteditable 编辑器）
            title_sel = '[class*="editorArea"]'
            try:
                self.page.wait_for_selector(title_sel, timeout=_EL_TIMEOUT)
                self.page.click(title_sel)
                self.page.keyboard.press("Control+a")
                self.page.keyboard.type(title[:100])
                time.sleep(random.uniform(0.5, 1))
                print(f"  标题已填写: {title[:50]}")
            except Exception as e:
                print(f"  警告: 标题填写失败 - {e}")

            # 5. 封面处理：横版 + 竖版各上传一张
            if cover_path:
                for idx, label in [(1, "横版"), (2, "竖版")]:
                    try:
                        slot_sel = f'[class*="coverWrap"] > div:nth-child({idx})'
                        self.page.wait_for_selector(slot_sel, timeout=_EL_TIMEOUT)
                        file_input = self.page.locator(
                            f'{slot_sel} input[type="file"]'
                        )
                        file_input.wait_for(state="attached", timeout=_EL_TIMEOUT)
                        file_input.set_input_files(cover_path)
                        print(f"  {label}封面已上传: {cover_path}")
                        time.sleep(random.uniform(1, 1.5))
                    except Exception as e:
                        print(f"  {label}封面上传失败（跳过）: {e}")
            else:
                print("  无封面图，跳过封面上传")

            return {"success": True, "message": "内容填充完成"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def upload_video(self, video_path: str, title: str,
                     description: str = "", tags: str = "",
                     cover_path: Optional[str] = None) -> Dict[str, Any]:
        """填充 + 等待人工确认（向后兼容旧流程）"""
        from utils.confirm import wait_confirm
        result = self.fill_only(video_path, title, description, tags, cover_path)
        if not result.get("success"):
            return result
        success = wait_confirm("内容已填充完毕，请在浏览器中检查标题/封面后手动点击发布")
        if not success:
            return {"success": False, "error": "人工标记失败"}
        return {"success": True, "message": "人工确认发布完成", "url": self.page.url}

    def fetch_latest_published_url(self, known_urls: set = None, poll_timeout: int = 300) -> str:
        """从内容列表页抓取最新发布的文章链接。
        known_urls: 之前已发布的 URL 集合，用于去重
        poll_timeout: 最长轮询秒数（默认 300s）
        """
        import re
        import time as _time
        if known_urls is None:
            known_urls = set()

        content_list_url = (
            "https://baijiahao.baidu.com/builder/rc/content"
            "?currentPage=1&pageSize=10&search=&type=&collection=&startDate=&endDate="
        )
        # 预览链接格式：http://baijiahao.baidu.com/builder/preview/s?id=XXXXX
        sel = 'a[href*="builder/preview/s?id="]'

        deadline = _time.time() + poll_timeout
        attempt = 0
        while _time.time() < deadline:
            attempt += 1
            self.page.goto(content_list_url, wait_until="domcontentloaded", timeout=_TIMEOUT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            _time.sleep(2)

            try:
                self.page.wait_for_selector(sel, timeout=_EL_TIMEOUT)
                links = self.page.locator(sel).all()
                for link in links[:10]:
                    href = (link.get_attribute("href") or "").strip()
                    if not href:
                        continue
                    # 提取 id，转为公开链接
                    m = re.search(r'[?&]id=(\d+)', href)
                    if m:
                        public_url = f"https://baijiahao.baidu.com/s?id={m.group(1)}"
                    else:
                        public_url = href
                    if public_url not in known_urls:
                        print(f"  [URL抓取] 第{attempt}次 → {public_url}")
                        return public_url
            except Exception:
                pass

            remaining = int(deadline - _time.time())
            print(f"  [URL轮询] 未发现新链接（已知{len(known_urls)}条），{remaining}s后重试...", flush=True)
            _time.sleep(15)

        # 超时兜底
        print(f"  [URL超时] 轮询{poll_timeout}s未找到新链接")
        return ""

    def auto_comment(self, url: str, content: str) -> Dict[str, Any]:
        """全自动评论：导航→填入→停顿→点提交，无需人工干预"""
        try:
            # 1. 打开页面
            self.page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            time.sleep(random.uniform(2, 3))

            page_title = self.page.title()
            page_url   = self.page.url
            print(f"  页面标题: {page_title}")
            print(f"  页面URL:  {page_url}")

            error_signals = ["错误", "not found", "404", "无法访问",
                             "该内容暂时无法查看", "内容不存在", "已删除", "违规"]
            if any(s.lower() in page_title.lower() for s in error_signals):
                raise RuntimeError(f"页面不可评论（标题: {page_title}）")
            from urllib.parse import urlparse
            host = urlparse(page_url).hostname or ""
            if not any(host.endswith(h) for h in ("baijiahao.baidu.com", "haokan.baidu.com", "baidu.com")):
                raise RuntimeError(f"页面跳转到未知域名: {host}")

            # 2. 找评论输入框
            comment_selectors = [
                'textarea[placeholder*="发表神评妙论"]',
                'textarea[placeholder*="评论"]',
                'textarea[placeholder*="说点什么"]',
                'div[contenteditable="true"][placeholder*="评论"]',
                '[class*="comment"] textarea',
                '[class*="commentInput"] textarea',
            ]
            input_el = None
            for sel in comment_selectors:
                try:
                    self.page.wait_for_selector(sel, timeout=_CMT_SEL_TIMEOUT)
                    input_el = sel
                    print(f"  找到评论框: {sel}")
                    break
                except Exception:
                    pass
            if not input_el:
                els = self.page.query_selector_all('input, textarea, div[contenteditable="true"]')
                print(f"  [调试] 未找到评论框，页面共 {len(els)} 个可输入元素：")
                for el in els[:8]:
                    ph  = el.get_attribute('placeholder') or el.get_attribute('data-placeholder') or ''
                    cls = (el.get_attribute('class') or '')[:80]
                    tag = el.evaluate('e => e.tagName')
                    print(f"    <{tag}> placeholder='{ph}' class='{cls}'")
                raise RuntimeError("未找到评论输入框")

            # 3. 填入内容
            self.page.click(input_el)
            time.sleep(random.uniform(0.5, 1))
            self.page.keyboard.type(content)
            print(f"  已填入: {content[:60]}")

            # 4. 停顿（等按钮从 disabled 变为可点击）
            time.sleep(random.uniform(1.5, 2.5))

            # 5. 找提交按钮并点击
            submit_selectors = [
                'button:has-text("发布")',
                'button:has-text("评论")',
                '[class*="comment"] button[class*="submit"]',
                '[class*="commentInput"] button',
                '[class*="comment"] button:not([disabled])',
            ]
            submit_el = None
            for sel in submit_selectors:
                try:
                    btn = self.page.locator(sel).first
                    if btn.is_visible() and btn.is_enabled():
                        submit_el = sel
                        break
                except Exception:
                    pass
            if not submit_el:
                raise RuntimeError("未找到可点击的提交按钮")

            self.page.locator(submit_el).first.click()
            print(f"  已点击提交: {submit_el}")

            # 6. 短暂等待确认提交生效
            time.sleep(random.uniform(1, 2))
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def fill_comment(self, url: str, content: str) -> Dict[str, Any]:
        """打开帖子页面，填入评论内容，不等待确认（供 fire 模式使用）"""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            time.sleep(random.uniform(2, 4))

            page_title = self.page.title()
            page_url   = self.page.url
            print(f"  页面标题: {page_title}")
            print(f"  页面URL:  {page_url}")

            error_signals = ["错误", "not found", "404", "无法访问",
                             "该内容暂时无法查看", "内容不存在", "已删除", "违规"]
            if any(s.lower() in page_title.lower() for s in error_signals):
                raise RuntimeError(f"页面不可评论（标题: {page_title}）")

            from urllib.parse import urlparse
            host = urlparse(page_url).hostname or ""
            if not any(host.endswith(h) for h in ("baijiahao.baidu.com", "haokan.baidu.com", "baidu.com")):
                raise RuntimeError(f"页面跳转到未知域名: {host}")

            comment_selectors = [
                'textarea[placeholder*="发表神评妙论"]',
                'textarea[placeholder*="评论"]',
                'textarea[placeholder*="说点什么"]',
                'div[contenteditable="true"][placeholder*="评论"]',
                '[class*="comment"] textarea',
                '[class*="commentInput"] textarea',
            ]
            input_el = None
            for sel in comment_selectors:
                try:
                    self.page.wait_for_selector(sel, timeout=_CMT_SEL_TIMEOUT)
                    input_el = sel
                    break
                except Exception:
                    pass

            if not input_el:
                els = self.page.query_selector_all('input, textarea, div[contenteditable="true"]')
                print(f"  [调试] 未找到评论框，页面共 {len(els)} 个可输入元素")
                raise RuntimeError("未找到评论输入框")

            self.page.click(input_el)
            time.sleep(random.uniform(0.3, 0.8))
            self.page.keyboard.type(content)
            time.sleep(random.uniform(0.5, 1))
            print(f"  评论内容已填入: {content[:60]}")
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def comment_on(self, url: str, content: str, wait_seconds: int = 120) -> Dict[str, Any]:
        """打开帖子页面，找到评论框填入内容，等待人工点击提交"""
        try:
            # 1. 打开帖子页面
            self.page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT)
            try:
                self.page.wait_for_load_state("networkidle", timeout=_IDLE_TIMEOUT)
            except Exception:
                pass
            time.sleep(random.uniform(2, 4))
            page_title = self.page.title()
            page_url = self.page.url
            print(f"  页面标题: {page_title}")
            print(f"  页面URL:  {page_url}")

            # 1.5 页面有效性检查：错误页 / 审核中 / 不可访问
            error_signals = ["错误", "not found", "404", "无法访问",
                             "该内容暂时无法查看", "内容不存在", "已删除", "违规"]
            if any(s.lower() in page_title.lower() for s in error_signals):
                raise RuntimeError(f"页面不可评论（标题: {page_title}）")
            from urllib.parse import urlparse
            host = urlparse(page_url).hostname or ""
            valid_hosts = ("baijiahao.baidu.com", "haokan.baidu.com", "baidu.com")
            if not any(host.endswith(h) for h in valid_hosts):
                raise RuntimeError(f"页面跳转到未知域名: {host}")

            # 2. 找评论输入框
            comment_selectors = [
                'textarea[placeholder*="发表神评妙论"]',
                'textarea[placeholder*="评论"]',
                'textarea[placeholder*="说点什么"]',
                'div[contenteditable="true"][placeholder*="评论"]',
                '[class*="comment"] textarea',
                '[class*="commentInput"] textarea',
            ]
            input_el = None
            for sel in comment_selectors:
                try:
                    self.page.wait_for_selector(sel, timeout=_CMT_SEL_TIMEOUT)
                    input_el = sel
                    print(f"  找到评论框: {sel}")
                    break
                except Exception:
                    pass

            if not input_el:
                # 输出调试信息帮助确认选择器
                els = self.page.query_selector_all(
                    'input, textarea, div[contenteditable="true"]')
                print(f"  [调试] 未找到评论框，页面共 {len(els)} 个可输入元素：")
                for el in els[:10]:
                    ph = (el.get_attribute('placeholder') or
                          el.get_attribute('data-placeholder') or '')
                    cls = (el.get_attribute('class') or '')[:80]
                    tag = el.evaluate('e => e.tagName')
                    print(f"    <{tag}> placeholder='{ph}' class='{cls}'")
                raise RuntimeError("未找到评论输入框，请检查选择器")

            # 3. 点击激活并填入内容
            self.page.click(input_el)
            time.sleep(random.uniform(0.3, 0.8))
            self.page.keyboard.type(content)
            time.sleep(random.uniform(0.5, 1))
            print(f"  评论内容已填入: {content[:60]}")

            # 4. 等待人工确认提交
            from utils.confirm import wait_confirm
            success = wait_confirm("评论内容已填入，请在浏览器中手动点击提交")
            if not success:
                return {"success": False, "error": "人工标记失败"}
            return {"success": True, "message": "评论完成"}

        except Exception as e:
            return {"success": False, "error": str(e)}

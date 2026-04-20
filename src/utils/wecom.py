"""
企微机器人通知工具

send_text            — 发送 markdown 消息
send_publish_report  — plan run 完成后的发布汇报
send_check_report    — plan check 过审通知
check_url_accessible — 检测百家号链接是否已过审
"""
import requests


def send_text(webhook_url: str, content: str) -> bool:
    """发送 markdown 格式消息到企微机器人，返回是否成功"""
    if not webhook_url:
        return False
    try:
        resp = requests.post(
            webhook_url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=10,
        )
        data = resp.json()
        return data.get("errcode", -1) == 0
    except Exception:
        return False


def send_publish_report(
    webhook_url: str,
    plan_id: int,
    plan_date: str,
    account_name: str,
    items_info: list,
) -> bool:
    """
    发布汇报消息（plan run 完成后调用）。

    items_info: [{"title": str, "url": str, "success": bool, "error": str}, ...]
    """
    if not webhook_url:
        return False

    success_count = sum(1 for i in items_info if i.get("success"))
    fail_count = len(items_info) - success_count

    lines = [
        f"**📢 发布汇报 | plan_id={plan_id} | {plan_date}**",
        f"账号：{account_name}",
        f"成功 {success_count} / 失败 {fail_count} / 共 {len(items_info)} 条",
        "",
    ]

    for item in items_info:
        title = (item.get("title") or "")[:20]
        url = item.get("url") or ""
        if item.get("success"):
            if url:
                lines.append(f"✅ [{title}]({url})")
            else:
                lines.append(f"✅ {title}（链接获取中，可稍后 plan check 查看）")
        else:
            err = (item.get("error") or "")[:40]
            lines.append(f"❌ {title or '未知'}" + (f"  — {err}" if err else ""))
        lines.append("")

    content = "\n".join(lines).rstrip()
    return send_text(webhook_url, content)


def send_check_report(
    webhook_url: str,
    plan_id: int,
    account_name: str,
    passed_items: list,
) -> bool:
    """
    过审通知消息（plan check 发现新过审时调用）。

    passed_items: [{"title": str, "url": str}, ...]
    """
    if not webhook_url or not passed_items:
        return False

    lines = [
        f"**✅ 过审通知 | plan_id={plan_id}**",
        f"账号：{account_name}",
        f"以下内容已可访问：",
        "",
    ]
    for item in passed_items:
        title = (item.get("title") or "")[:20]
        url = item.get("url") or ""
        if url:
            lines.append(f"🔗 [{title}]({url})")
        else:
            lines.append(f"🔗 {title}")
        lines.append("")

    content = "\n".join(lines).rstrip()
    return send_text(webhook_url, content)


def check_url_accessible(url: str, timeout: int = 15, page=None) -> bool:
    """
    检测百家号视频文章链接是否已过审可访问。

    百家号视频公开链接：https://baijiahao.baidu.com/s?id=xxx
    无论过审与否均 302 跳到 haokan.baidu.com/v?vid=xxx，需通过页面内容区分。

    好看视频页面特征：
      过审  → 页面 title 标签内含视频标题（非"好看视频"通用标题）
      未过审 → title 为通用标题，或页面含"您访问的视频不存在"

    page: Playwright Page 对象。传入时用浏览器检查（绕过风控），否则降级用 requests。
    """
    if not url:
        return False

    if page is not None:
        return _check_via_browser(url, page, timeout)
    return _check_via_requests(url, timeout)


def _check_via_browser(url: str, page, timeout: int) -> bool:
    """用 Playwright page 访问链接，通过页面 title 判断过审。"""
    try:
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        title = page.title()
        # 通用兜底标题 → 未过审
        if not title or title in ("好看视频", "百度好看", "百家号"):
            return False
        # 含"视频不存在"等错误关键词 → 未过审
        if "不存在" in title or "错误" in title or "出错" in title:
            return False
        return True
    except Exception:
        return False


def _check_via_requests(url: str, timeout: int) -> bool:
    """降级：用 requests 检查（无 Cookie，易触发风控）。"""
    _NOT_EXIST = "您访问的视频不存在".encode("unicode_escape").decode()

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/120.0.0.0 Safari/537.36"},
        )

        if resp.status_code >= 400:
            return False

        if "mbd.baidu.com/newspage/data/error" in resp.url:
            return False

        text = resp.text
        if _NOT_EXIST in text:
            return False
        if 'name="title" content=' in text:
            return True

        return False

    except Exception:
        return False

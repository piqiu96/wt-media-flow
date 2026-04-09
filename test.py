#!/usr/bin/env python3
"""
矩阵视频自动发布系统 - 测试程序

用于测试比特浏览器连接、元素定位、视频上传等功能
"""
import argparse
import sys
import os
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from settings import settings
from src.browser.bit_api import BitBrowserAPI
from src.browser.browser_manager import BrowserManager
from playwright.sync_api import sync_playwright


def test_bit_browser_api(profile_id: str):
    """测试比特浏览器 API"""
    print(f"=== 测试比特浏览器 API ===")
    print(f"Profile ID: {profile_id}")

    api = BitBrowserAPI()

    # 测试打开浏览器
    print("\n1. 测试打开浏览器...")
    result = api.open_browser(profile_id)
    if result.get("success"):
        print(f"   ✓ 打开成功")
        print(f"   WS: {result['data']['ws'][:50]}...")
        print(f"   HTTP: {result['data']['http']}")
    else:
        print(f"   ✗ 打开失败: {result}")
        return False

    # 等待一下
    time.sleep(2)

    # 测试关闭浏览器
    print("\n2. 测试关闭浏览器...")
    result = api.close_browser(profile_id)
    print(f"   关闭浏览器完成")

    # 测试列出浏览器
    print("\n3. 测试列出浏览器...")
    result = api.list_browsers()
    if result.get("success"):
        print(f"   ✓ 列出成功，共有 {len(result['data'].get('list', []))} 个浏览器")
    else:
        print(f"   ✗ 列出失败: {result}")

    return True


def test_browser_manager(profile_id: str):
    """测试浏览器管理器"""
    print(f"=== 测试浏览器管理器 ===")
    print(f"Profile ID: {profile_id}")

    manager = BrowserManager()

    with sync_playwright() as p:
        print("\n1. 打开浏览器...")
        session = manager.open_browser(profile_id, p)
        print(f"   ✓ 浏览器已打开")

        print("\n2. 创建页面...")
        page = manager.get_page(profile_id, session)
        print(f"   ✓ 页面已创建")

        print("\n3. 访问测试页面...")
        page.goto("https://www.baidu.com")
        print(f"   ✓ 页面已加载: {page.title()}")

        print("\n4. 测试元素定位...")
        try:
            search_input = page.locator("#kw")
            if search_input.count() > 0:
                print(f"   ✓ 找到搜索框")
            else:
                print(f"   ✗ 未找到搜索框")
        except Exception as e:
            print(f"   ✗ 元素定位失败: {e}")

        print("\n5. 测试模拟输入...")
        try:
            search_input.fill("测试搜索")
            print(f"   ✓ 输入成功")
        except Exception as e:
            print(f"   ✗ 输入失败: {e}")

        time.sleep(1)

        print("\n6. 清理浏览器...")
        manager.close_browser(profile_id)
        print(f"   ✓ 浏览器已保留在池中")

    # 清理
    manager.cleanup_expired()
    print(f"\n✓ 浏览器池状态: {manager.get_pool_status()}")

    return True


def test_platform_upload(platform: str, profile_id: str, video_path: str):
    """测试平台上传功能"""
    print(f"=== 测试平台上传 ===")
    print(f"平台: {platform}")
    print(f"Profile ID: {profile_id}")
    print(f"视频路径: {video_path}")

    # 检查视频文件
    if not os.path.exists(video_path):
        print(f"   ✗ 视频文件不存在: {video_path}")
        return False

    from src.plat import get_platform
    from src.browser.browser_manager import BrowserManager

    manager = BrowserManager()

    with sync_playwright() as p:
        print("\n1. 打开浏览器...")
        session = manager.open_browser(profile_id, p)
        page = manager.get_page(profile_id, session)
        print(f"   ✓ 浏览器已打开")

        print("\n2. 加载平台页面...")
        platform_class = get_platform(platform)
        plat = platform_class(page)

        url_map = {
            "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
            "baijiahao": "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
            "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish"
        }

        page.goto(url_map.get(platform))
        page.wait_for_load_state("networkidle")
        print(f"   ✓ 页面已加载: {page.title()}")

        print("\n3. 测试元素定位...")
        selectors = {
            "bilibili": {
                "upload": "text=上传视频",
                "title": "#title",
                "desc": "#desc"
            },
            "baijiahao": {
                "upload": ".upload-area",
                "title": 'input[placeholder*="标题"]',
                "desc": 'div[contenteditable="true"]'
            },
            "xiaohongshu": {
                "upload": "text=上传视频",
                "title": 'input[placeholder*="标题"]',
                "desc": 'div[contenteditable="true"]'
            }
        }

        test_selectors = selectors.get(platform, {})
        for name, selector in test_selectors.items():
            try:
                element = page.locator(selector)
                if element.count() > 0:
                    print(f"   ✓ 找到 {name}")
                else:
                    print(f"   ✗ 未找到 {name}")
            except Exception as e:
                print(f"   ✗ {name} 定位失败: {e}")

        print("\n4. 测试文件选择器...")
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                # 点击上传区域（可能需要根据实际情况调整）
                upload_area = page.locator(test_selectors.get("upload", ""))
                if upload_area.count() > 0:
                    upload_area.click()
                else:
                    print(f"   ✗ 未找到上传区域")
                    return False

            file_chooser = fc_info.value
            print(f"   ✓ 文件选择器已触发")
        except Exception as e:
            print(f"   ✗ 文件选择器失败: {e}")
            return False

        print("\n5. 注意：未实际上传视频，仅测试元素定位")
        print(f"   实际上传时取消注释以下代码:")
        print(f"   file_chooser.set_files('{video_path}')")

        time.sleep(2)

        print("\n6. 清理...")
        manager.close_browser(profile_id)

    return True


def test_random_behavior(profile_id: str):
    """测试随机行为模拟"""
    print(f"=== 测试随机行为模拟 ===")
    print(f"Profile ID: {profile_id}")

    from src.browser.browser_manager import BrowserManager
    from src.utils.anti_risk import AntiRiskStrategy

    manager = BrowserManager()
    anti_risk = AntiRiskStrategy()

    with sync_playwright() as p:
        print("\n1. 打开浏览器...")
        session = manager.open_browser(profile_id, p)
        page = manager.get_page(profile_id, session)
        print(f"   ✓ 浏览器已打开")

        print("\n2. 访问测试页面...")
        page.goto("https://www.baidu.com")
        print(f"   ✓ 页面已加载")

        print("\n3. 测试模拟人类行为...")
        anti_risk.simulate_behavior(page)
        print(f"   ✓ 行为模拟完成")

        time.sleep(1)

        print("\n4. 清理...")
        manager.close_browser(profile_id)

    return True


def test_all(profile_id: str, video_path: str):
    """运行所有测试"""
    print("=" * 50)
    print("运行所有测试")
    print("=" * 50)

    tests = [
        ("比特浏览器 API", lambda: test_bit_browser_api(profile_id)),
        ("浏览器管理器", lambda: test_browser_manager(profile_id)),
        ("随机行为模拟", lambda: test_random_behavior(profile_id)),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n")
        try:
            result = test_func()
            results.append((name, "✓ 通过" if result else "✗ 失败"))
        except Exception as e:
            print(f"   ✗ 测试异常: {e}")
            results.append((name, f"✗ 异常: {str(e)[:50]}"))

    # 如果有视频文件，测试上传功能
    if video_path and os.path.exists(video_path):
        print(f"\n")
        for platform in ["bilibili", "baijiahao", "xiaohongshu"]:
            try:
                result = test_platform_upload(platform, profile_id, video_path)
                results.append((f"{platform} 上传", "✓ 通过" if result else "✗ 失败"))
                time.sleep(2)
            except Exception as e:
                print(f"   ✗ {platform} 测试异常: {e}")
                results.append((f"{platform} 上传", f"✗ 异常: {str(e)[:50]}"))

    # 显示测试结果
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    for name, status in results:
        print(f"{name:<20} {status}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="矩阵视频自动发布系统 - 测试程序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 测试比特浏览器 API
  python test.py --api --profile-id xxx

  # 测试浏览器管理器
  python test.py --manager --profile-id xxx

  # 测试平台上传
  python test.py --upload --platform bilibili --profile-id xxx --video /path/to/video.mp4

  # 测试随机行为
  python test.py --behavior --profile-id xxx

  # 运行所有测试
  python test.py --all --profile-id xxx --video /path/to/video.mp4
        """
    )

    parser.add_argument("--profile-id", required=True, help="比特浏览器 Profile ID")
    parser.add_argument("--video", help="测试视频文件路径")

    subparsers = parser.add_subparsers(dest="command", help="测试类型")

    subparsers.add_parser("api", help="测试比特浏览器 API")
    subparsers.add_parser("manager", help="测试浏览器管理器")
    subparsers.add_parser("behavior", help="测试随机行为模拟")

    upload_parser = subparsers.add_parser("upload", help="测试平台上传")
    upload_parser.add_argument("--platform", required=True,
                             choices=["bilibili", "baijiahao", "xiaohongshu"])

    subparsers.add_parser("all", help="运行所有测试")

    args = parser.parse_args()

    if args.command == "api":
        test_bit_browser_api(args.profile_id)
    elif args.command == "manager":
        test_browser_manager(args.profile_id)
    elif args.command == "behavior":
        test_random_behavior(args.profile_id)
    elif args.command == "upload":
        if not args.video:
            print("错误: --video 参数是必需的")
            return
        test_platform_upload(args.platform, args.profile_id, args.video)
    elif args.command == "all":
        test_all(args.profile_id, args.video)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

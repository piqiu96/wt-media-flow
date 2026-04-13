"""
ClawCommand - 素材采集命令
"""
from cmd import BaseCommand, register_command


@register_command
class ClawCommand(BaseCommand):
    command_name = "claw"
    command_help = "从抖音采集素材到素材库（搜索关键词或链接）"

    def setup_parser(self, parser) -> None:
        parser.add_argument("--keyword", "-k", help="搜索关键词")
        parser.add_argument("--url", help="单个视频链接或 vid")
        parser.add_argument("--urls-file", help="批量链接文件（每行一个 URL）")
        parser.add_argument("--count", type=int, default=10,
                            help="每个关键词采集数量（最低 10 条，API 限制）")
        parser.add_argument("--sort-type", type=int, default=0,
                            choices=[0, 1, 2],
                            help="排序（0 综合 / 1 点赞 / 2 最新，默认 0）")
        parser.add_argument("--publish-time", type=int, default=1,
                            choices=[0, 1, 7, 182],
                            help="发布时间筛选（0 不限 / 1 一天 / 7 七天 / 182 半年，默认 1）")
        parser.add_argument("--filter-duration", type=str, default="1-5",
                            help="视频时长筛选（'0-1' 1分钟以下 / '1-5' 1-5分钟 / '5-10000' 5分钟以上，默认 '1-5'）")
        parser.add_argument("--dry-run", action="store_true",
                            help="只展示搜索结果不入库")
        parser.add_argument("--category", "-c", default="",
                            help="分类标签（如 '游戏'），用于目录分类存储")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def execute(self, args) -> dict:
        from library.douyin_api import DouyinApi
        from processor.claw_processor import ClawProcessor

        config = self.load_config(args)

        # 合并参数
        keyword = self.merge_args(args, config, "keyword")
        url = self.merge_args(args, config, "url")
        urls_file = self.merge_args(args, config, "urls_file")
        count = self.merge_args(args, config, "count", 10)
        sort_type = self.merge_args(args, config, "sort_type", 0)
        publish_time = self.merge_args(args, config, "publish_time", 1)
        filter_duration = self.merge_args(args, config, "filter_duration", "1-5")
        content_type = config.get("content_type", 1)
        dry_run = getattr(args, "dry_run", False)
        category = self.merge_args(args, config, "category", "")

        # 从配置文件读取关键词和链接列表
        keywords = config.get("keywords", [])
        if keyword:
            keywords.append(keyword)
        urls = config.get("urls") or []
        if url:
            urls.append(url)
        if urls_file:
            urls.extend(self._read_urls_file(urls_file))

        if not keywords and not urls:
            return {"success": False,
                    "message": "请指定 --keyword 或 --url/--urls-file，或在配置文件中提供"}

        # 初始化 API 客户端
        try:
            api = DouyinApi()
        except Exception as e:
            return {"success": False, "message": str(e)}

        # 采集素材
        all_items = []

        # 搜索关键词
        for kw in keywords:
            print(f"搜索关键词: {kw} (数量: {count}, 排序: {sort_type})")
            try:
                items = api.search(kw, count=count, sort_type=sort_type,
                                   content_type=content_type,
                                   publish_time=publish_time,
                                   filter_duration=filter_duration)
                print(f"  找到 {len(items)} 条结果")
                all_items.extend(items)
            except Exception as e:
                print(f"  搜索失败: {e}")

        # 链接获取
        for u in urls:
            print(f"获取链接: {u}")
            try:
                item = api.fetch_by_url(u)
                if item:
                    print(f"  获取成功: {item['vid']} - {item['title'][:40]}")
                    all_items.append(item)
                else:
                    print(f"  未获取到数据")
            except Exception as e:
                print(f"  获取失败: {e}")

        if not all_items:
            return {"success": False, "message": "未采集到任何素材"}

        print(f"\n共采集到 {len(all_items)} 条素材")

        # dry-run 模式：展示结果
        if dry_run:
            print("\n[dry-run] 素材列表:")
            for i, item in enumerate(all_items, 1):
                stats = item.get("statistics", {})
                print(f"  {i}. [{item['vid']}] {item['title'][:50]}")
                print(f"     作者: {item['author']}  "
                      f"点赞: {stats.get('digg_count', 0)}  "
                      f"评论: {stats.get('comment_count', 0)}  "
                      f"收藏: {stats.get('collect_count', 0)}")
                if item.get("tags"):
                    print(f"     标签: {item['tags']}")
            return {"success": True, "message": f"[dry-run] 共 {len(all_items)} 条素材"}

        # 入库
        print()
        processor = ClawProcessor()
        stats = processor.run(all_items, category=category)

        print(f"\n采集完成:")
        print(f"  总计: {stats['total']}")
        print(f"  新增: {stats['added']}")
        print(f"  跳过(重复): {stats['skipped']}")
        print(f"  失败: {stats['failed']}")

        return {
            "success": stats["added"] > 0 or stats["skipped"] > 0,
            "message": f"新增 {stats['added']}，跳过 {stats['skipped']}，失败 {stats['failed']}",
            "stats": stats,
        }

    def _read_urls_file(self, file_path: str) -> list[str]:
        """从文件读取 URL 列表"""
        urls = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        except FileNotFoundError:
            print(f"  URL 文件不存在: {file_path}")
        return urls

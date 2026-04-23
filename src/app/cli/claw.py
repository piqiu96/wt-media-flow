"""
ClawCommand - 素材采集命令
"""
from app.cli import BaseCommand, register_command


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
        parser.add_argument("--fetch", action="store_true",
                            help="只入库元数据，不下载视频文件（两阶段第一步）")
        parser.add_argument("--download", action="store_true",
                            help="只下载库中 pending 视频，不做搜索（两阶段第二步）")
        parser.add_argument("--retry-failed", action="store_true",
                            help="配合 --download：将 failed 视频重置为 pending 后重试（需人工确认）")
        parser.add_argument("--category", "-c", required=False,
                            help="游戏品类，--download 时可只传此参数")
        parser.add_argument("--config", help="YAML 配置文件路径")

    def execute(self, args) -> dict:
        from infra.http.douyin_api import DouyinApi
        from workflows.claw_workflow import ClawWorkflow

        config = self.load_config(args)

        download_only = getattr(args, "download", False)
        fetch_only    = getattr(args, "fetch", False)
        retry_failed  = getattr(args, "retry_failed", False)
        category      = self.merge_args(args, config, "category", "")

        # ── 模式一：--download  只下载 pending 视频 ──────────────────────────
        if download_only:
            if retry_failed:
                from infra.db.database import SessionLocal
                from infra.db.repositories import VideoRepository
                db = SessionLocal()
                try:
                    repo = VideoRepository(db)
                    failed = repo.get_failed_claw(category=category)
                    if not failed:
                        print("没有下载失败的视频")
                        return {"success": True, "message": "没有失败视频"}
                    print(f"\n以下 {len(failed)} 条视频下载失败，将重置后重试：")
                    for v in failed:
                        print(f"  [{v.id}] {(v.title or v.source_vid or '')[:50]}  错误: {v.claw_error or '未知'}")
                    confirm = input("\n是否全部重置并重新下载？(y/N): ").strip().lower()
                    if confirm != "y":
                        print("已取消")
                        return {"success": True, "message": "已取消重试"}
                finally:
                    db.close()

            workflow = ClawWorkflow()
            result = workflow.download_pending(
                category=category or None,
                retry_failed=retry_failed,
            )
            print(f"\n下载完成: 成功 {result['done']}，失败 {result['failed']}")
            return {
                "success": result["done"] > 0 or result["total"] == 0,
                "message": f"下载成功 {result['done']}，失败 {result['failed']}",
                **result,
            }

        # ── 公共：category 校验（非 --download 模式才强制校验）──────────────
        from pathlib import Path
        import yaml as _yaml
        _cat_path = Path("conf/categories.yaml")
        if _cat_path.exists():
            with open(_cat_path, encoding="utf-8") as _f:
                valid_keys = (_yaml.safe_load(_f) or {}).get("categories", [])
            if not category:
                return {"success": False, "message": f"--category 必填，有效值: {valid_keys}"}
            if category not in valid_keys:
                return {"success": False,
                        "message": f"--category '{category}' 无效，有效值: {valid_keys}"}

        # 合并其余参数
        keyword = self.merge_args(args, config, "keyword")
        url = self.merge_args(args, config, "url")
        urls_file = self.merge_args(args, config, "urls_file")
        if config:
            count = config.get("count", 10)
            sort_type = config.get("sort_type", 0)
            publish_time = config.get("publish_time", 1)
            filter_duration = config.get("filter_duration", "1-5")
        else:
            count = getattr(args, "count", 10)
            sort_type = getattr(args, "sort_type", 0)
            publish_time = getattr(args, "publish_time", 1)
            filter_duration = getattr(args, "filter_duration", "1-5")
        content_type = config.get("content_type", 1)
        dry_run = getattr(args, "dry_run", False)

        # 关键词
        kw_by_cat = config.get("keywords_by_category", {})
        if kw_by_cat and category and category in kw_by_cat:
            keywords = list(kw_by_cat[category])
        else:
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

        # 搜索
        all_items = []
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

        # dry-run
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
        workflow = ClawWorkflow()

        # ── 模式二：--fetch  只入库，不下载 ─────────────────────────────────
        if fetch_only:
            stats = workflow.ingest(all_items, category=category)
            print(f"\n入库完成（未下载）:")
            print(f"  总计: {stats['total']}")
            print(f"  新增: {stats['added']}")
            print(f"  跳过(重复): {stats['skipped']}")
            print(f"  失败: {stats['failed']}")
            return {
                "success": stats["added"] > 0 or stats["skipped"] > 0,
                "message": f"入库 {stats['added']}，跳过 {stats['skipped']}，失败 {stats['failed']}（未下载）",
                "stats": stats,
            }

        # ── 模式三（默认）：入库 + 下载 ──────────────────────────────────────
        stats = workflow.run(all_items, category=category)
        print(f"\n采集完成:")
        print(f"  总计: {stats['total']}")
        print(f"  新增: {stats['added']}")
        print(f"  跳过(重复): {stats['skipped']}")
        print(f"  失败: {stats['failed']}")
        print(f"  已下载: {stats['downloaded']}")
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

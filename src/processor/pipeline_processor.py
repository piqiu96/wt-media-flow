"""全流程编排处理器（下载 → 合成 → 入库）"""
import os

from downloader import get_downloader
from processor.compositor import VideoCompositor
from db.database import SessionLocal
from service.video_service import VideoService
from conf.settings import settings


class PipelineProcessor:
    def run(self, config: dict, load_config_fn=None) -> dict:
        """
        执行全流程 pipeline

        Args:
            config: 已解析的 YAML 配置
        """
        steps = config.get("steps", ["download", "composite"])
        print(f"Pipeline 步骤: {' → '.join(steps)}")
        print()

        pipeline_results = {}

        # === Step 1: 下载 ===
        downloaded_files = []
        if "download" in steps:
            print("=" * 50)
            print("步骤 1: 下载视频")
            print("=" * 50)

            dl_config = config.get("download", {})
            source = dl_config.get("source")
            if not source:
                return {"success": False, "message": "download 配置中缺少 source"}

            urls = dl_config.get("urls", [])
            urls_file = dl_config.get("urls_file")
            if urls_file:
                urls.extend(self._read_urls_file(urls_file))

            if not urls:
                return {"success": False, "message": "download 配置中缺少 urls"}

            output_dir = dl_config.get("output_dir", settings.DOWNLOAD_DIR)
            cookies = dl_config.get("cookies", "")
            quality = dl_config.get("quality", "best")

            downloader = get_downloader(source)
            dl_results = downloader.batch_download(
                urls, output_dir, cookies=cookies, quality=quality
            )

            downloaded_files = [
                r["file_path"] for r in dl_results
                if r.get("success") and r.get("file_path")
            ]

            success_count = len(downloaded_files)
            print(f"\n下载完成: {success_count}/{len(urls)} 成功")
            pipeline_results["download"] = dl_results

            if success_count == 0:
                return {"success": False, "message": "所有视频下载失败", "results": pipeline_results}

        # === Step 2: 合成 ===
        composited_files = []
        if "composite" in steps:
            print("\n" + "=" * 50)
            print("步骤 2: 视频合成")
            print("=" * 50)

            comp_config = config.get("composite", {})
            guide_video = comp_config.get("guide_video")
            if not guide_video:
                return {"success": False, "message": "composite 配置中缺少 guide_video"}

            insert_at = float(comp_config.get("insert_at", settings.DEFAULT_INSERT_AT))
            guide_duration = float(comp_config.get("guide_duration", 0))
            output_dir = comp_config.get("output_dir", settings.OUTPUT_DIR)

            compositor = VideoCompositor()

            if downloaded_files:
                input_files = downloaded_files
            else:
                input_dir = comp_config.get("input_dir", settings.DOWNLOAD_DIR)
                input_files = sorted([
                    os.path.join(input_dir, f)
                    for f in os.listdir(input_dir)
                    if f.lower().endswith(tuple(VideoCompositor.VIDEO_EXTENSIONS))
                ])

            comp_results = []
            for i, input_file in enumerate(input_files, 1):
                filename = os.path.basename(input_file)
                output_path = os.path.join(output_dir, filename)
                print(f"\n--- [{i}/{len(input_files)}] {filename} ---")

                result = compositor.composite(
                    input_file, guide_video, insert_at, output_path, guide_duration
                )
                comp_results.append({**result, "input": filename})

                if result.get("success"):
                    composited_files.append(result["output_path"])

            success_count = len(composited_files)
            print(f"\n合成完成: {success_count}/{len(input_files)} 成功")
            pipeline_results["composite"] = comp_results

            if success_count == 0:
                return {"success": False, "message": "所有视频合成失败", "results": pipeline_results}

        # === Step 3: 入库 ===
        if "publish" in steps:
            print("\n" + "=" * 50)
            print("步骤 3: 入库发布")
            print("=" * 50)

            pub_config = config.get("publish", {})
            title_prefix = pub_config.get("title_prefix", "")
            tags = pub_config.get("tags", "")
            description = pub_config.get("description", "")

            db = SessionLocal()
            publish_results = []
            try:
                video_svc = VideoService(db)
                files_to_publish = composited_files or downloaded_files
                for file_path in files_to_publish:
                    filename = os.path.splitext(os.path.basename(file_path))[0]
                    title = f"{title_prefix}{filename}" if title_prefix else filename

                    result = video_svc.add_from_file(
                        path=file_path, title=title,
                        description=description, tags=tags
                    )
                    print(f"  入库: {title}")
                    publish_results.append({"success": True, "title": title, "path": file_path})
            except Exception as e:
                print(f"  入库失败: {e}")
                publish_results.append({"success": False, "error": str(e)})
            finally:
                db.close()

            pipeline_results["publish"] = publish_results
            print(f"\n入库完成: {len([r for r in publish_results if r.get('success')])} 个视频")

        # 汇总
        print("\n" + "=" * 50)
        print("Pipeline 完成")
        print("=" * 50)
        return {"success": True, "message": "Pipeline 执行完成", "results": pipeline_results}

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

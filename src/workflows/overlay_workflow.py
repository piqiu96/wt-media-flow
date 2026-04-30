"""
OverlayWorkflow — 尾部动画素材采集 + 切片流程

fetch: 从抖音搜索并下载源视频 → data/overlay_sources/{category}/
clip:  扫描源视频目录，切片 → data/overlays/{category}/
run:   fetch + clip 一步完成
"""
import os
import re

import requests

from conf.settings import settings
from utils.log import get_logger

logger = get_logger(__name__)


class OverlayWorkflow:

    def fetch(self, keywords: list[str], count: int, category: str) -> dict:
        """从抖音搜索并下载源视频到 data/overlay_sources/{category}/"""
        from infra.http.douyin_api import DouyinApi

        output_dir = os.path.join(settings.OVERLAY_SOURCE_DIR, category)
        os.makedirs(output_dir, exist_ok=True)

        api = DouyinApi()

        total_fetched = 0
        total_downloaded = 0
        total_failed = 0

        for keyword in keywords:
            logger.info(f"搜索: {keyword!r}，count={count}")
            try:
                items = api.search(
                    keyword=keyword,
                    count=count,
                    sort_type=1,          # 按热度
                    publish_time=7,       # 最近7天
                    filter_duration="0",  # 不限时长（舞蹈视频可能超5分钟）
                )
            except Exception as e:
                logger.error(f"搜索失败 {keyword!r}: {e}")
                continue

            logger.info(f"  搜到 {len(items)} 条")
            total_fetched += len(items)

            for item in items:
                vid = item.get("vid") or item.get("aweme_id") or ""
                video_url = item.get("video_url") or ""
                title = item.get("title") or vid
                if not video_url:
                    logger.warning(f"  vid={vid} 无 URL，跳过")
                    total_failed += 1
                    continue

                safe_title = re.sub(r'[^\w\u4e00-\u9fff]+', '_', title)[:40].strip('_')
                filename = f"{vid}_{safe_title}.mp4"
                local_path = os.path.join(output_dir, filename)

                if os.path.isfile(local_path):
                    logger.info(f"  已存在: {filename}")
                    total_downloaded += 1
                    continue

                try:
                    resp = requests.get(video_url, stream=True, timeout=settings.DOWNLOAD_TIMEOUT)
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    size_mb = os.path.getsize(local_path) / 1024 / 1024
                    logger.info(f"  下载完成: {filename} ({size_mb:.1f}MB)")
                    total_downloaded += 1
                except Exception as e:
                    logger.error(f"  下载失败 vid={vid}: {e}")
                    if os.path.isfile(local_path):
                        os.unlink(local_path)
                    total_failed += 1

        msg = f"fetch 完成: 搜到 {total_fetched} 条，下载 {total_downloaded} 成功，{total_failed} 失败"
        logger.info(msg)
        return {
            "success": total_downloaded > 0,
            "message": msg,
            "fetched": total_fetched,
            "downloaded": total_downloaded,
            "failed": total_failed,
            "output_dir": output_dir,
        }

    def clip(self, category: str,
             clip_duration: float = 5.0,
             max_clips: int = 5,
             min_source_duration: float = 10.0) -> dict:
        """将 overlay_sources/{category}/ 下的视频切片到 overlays/{category}/"""
        from infra.media.video_util.clipper import OverlayClipper
        from utils.tool_finder import find_tool

        src_dir = os.path.join(settings.OVERLAY_SOURCE_DIR, category)
        out_dir = os.path.join(settings.OVERLAY_DIR, category)

        if not os.path.isdir(src_dir):
            return {"success": False, "message": f"源目录不存在: {src_dir}，请先运行 overlay fetch"}

        ffmpeg_path = find_tool("ffmpeg", settings.FFMPEG_PATH)
        ffmpeg_dir = os.path.dirname(ffmpeg_path) if ffmpeg_path else ""
        ffprobe_path = os.path.join(ffmpeg_dir, "ffprobe") if ffmpeg_dir else "ffprobe"

        clipper = OverlayClipper(
            ffmpeg_path=ffmpeg_path or "ffmpeg",
            ffprobe_path=ffprobe_path,
        )

        logger.info(f"切片: {src_dir} → {out_dir}")
        logger.info(f"  参数: clip_duration={clip_duration}s, max_clips={max_clips}, min_source={min_source_duration}s")

        result = clipper.clip_dir(
            src_dir=src_dir,
            output_dir=out_dir,
            clip_duration=clip_duration,
            max_clips=max_clips,
            min_source_duration=min_source_duration,
        )

        msg = (f"clip 完成: 处理 {result['total']} 个源文件，"
               f"生成 {result['clipped']} 个切片，"
               f"跳过 {result['skipped']} 个")
        logger.info(msg)
        return {
            "success": result["clipped"] > 0,
            "message": msg,
            "output_dir": out_dir,
            **result,
        }

    def run(self, keywords: list[str], count: int, category: str,
            clip_duration: float = 5.0,
            max_clips: int = 5,
            min_source_duration: float = 10.0) -> dict:
        """fetch + clip 一步完成"""
        fetch_result = self.fetch(keywords=keywords, count=count, category=category)

        if not fetch_result.get("success") and fetch_result.get("downloaded", 0) == 0:
            return fetch_result

        clip_result = self.clip(
            category=category,
            clip_duration=clip_duration,
            max_clips=max_clips,
            min_source_duration=min_source_duration,
        )

        return {
            "success": clip_result.get("success", False),
            "message": f"{fetch_result['message']} | {clip_result['message']}",
            "fetch": fetch_result,
            "clip": clip_result,
        }

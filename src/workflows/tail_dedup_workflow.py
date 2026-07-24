"""
TailDedupWorkflow — 为成品视频拼接尾部动画去重素材

流程：扫描输入目录 → 对每个视频随机选尾部动画 + 贴纸 + 去重滤镜 → 输出
"""
import os
import random
import subprocess
from pathlib import Path

from conf.settings import settings
from utils.log import get_logger
from utils.tool_finder import find_tool

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
OVERLAY_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}


class TailDedupWorkflow:
    """为成品视频拼接尾部动画 + 去重处理"""

    def __init__(self):
        self.ffmpeg_path = find_tool("ffmpeg", settings.FFMPEG_PATH)
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg 未找到，请先运行: python main.py setup")

        ffmpeg_dir = os.path.dirname(self.ffmpeg_path)
        self.ffprobe_path = os.path.join(ffmpeg_dir, "ffprobe") if ffmpeg_dir else "ffprobe"

    def get_video_info(self, video_path: str) -> dict:
        """ffprobe 获取视频信息"""
        import json

        cmd = [
            self.ffprobe_path, "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe 失败: {result.stderr}")

        data = json.loads(result.stdout)
        info = {"width": 0, "height": 0, "fps": 30.0, "duration": 0.0,
                "sample_rate": 44100, "audio_channels": 2}

        for stream in data.get("streams", []):
            if stream["codec_type"] == "video":
                info["width"] = int(stream.get("width", 0))
                info["height"] = int(stream.get("height", 0))
                fps_str = stream.get("r_frame_rate", "30/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    info["fps"] = float(num) / float(den) if float(den) > 0 else 30.0
                else:
                    info["fps"] = float(fps_str)
            elif stream["codec_type"] == "audio":
                info["sample_rate"] = int(stream.get("sample_rate", 44100))
                info["audio_channels"] = int(stream.get("channels", 2))

        fmt = data.get("format", {})
        info["duration"] = float(fmt.get("duration", 0))
        return info

    def _load_overlays(self, overlay_dir: str) -> list[str]:
        """加载所有可用尾部动画文件"""
        if not os.path.isdir(overlay_dir):
            logger.warning(f"尾部动画目录不存在: {overlay_dir}，尝试父目录")
            # 尝试递归查找
            all_files = []
            for root, _dirs, files in os.walk(overlay_dir):
                for f in files:
                    if Path(f).suffix.lower() in OVERLAY_EXTENSIONS:
                        all_files.append(os.path.join(root, f))
            return all_files

        return [
            os.path.join(overlay_dir, f)
            for f in os.listdir(overlay_dir)
            if Path(f).suffix.lower() in OVERLAY_EXTENSIONS
        ]

    def _build_dedup_filters(self) -> list[str]:
        """构建去重滤镜（与 VideoDedup.final_dedup_filters 一致）"""
        filters = []
        # 色调偏移 ±3°
        h = random.uniform(-3, 3)
        filters.append(f"hue=h={h:.2f}")
        # 亮度微调
        b = random.uniform(-0.02, 0.02)
        filters.append(f"eq=brightness={b:.4f}")
        # 轻微锐化/模糊
        sharp = random.uniform(-0.3, 0.3)
        filters.append(f"unsharp=3:3:{sharp:.2f}:3:3:0")
        return filters

    def _build_sticker_overlay_filters(self, sticker_dir: str,
                                        w: int, h: int,
                                        tail_duration: float,
                                        inputs: list[str],
                                        in_label: str) -> tuple[list[str], str]:
        """在尾部动画段叠加随机贴纸（复用 compositor.StickerOverlay 逻辑）"""
        from infra.media.compositor import StickerOverlay
        sticker = StickerOverlay(sticker_dir)
        if not sticker.available() or tail_duration <= 0:
            return [], in_label
        return sticker.build_overlay_filters(tail_duration, w, h, in_label, inputs)

    def _dedup_single(self, input_path: str, overlay_path: str,
                       output_path: str,
                       enable_dedup: bool = True,
                       enable_stickers: bool = True,
                       max_duration: float = 0) -> dict:
        """对单个视频做尾部拼接 + 去重"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            # 获取视频参数
            src_info = self.get_video_info(input_path)
            w, h = src_info["width"], src_info["height"]
            fps = src_info["fps"]
            sr = src_info["sample_rate"]
            duration = src_info["duration"]

            logger.info(f"原视频: {w}x{h}, {fps:.2f}fps, {duration:.1f}s")

            overlay_info = self.get_video_info(overlay_path)
            overlay_duration = overlay_info["duration"]
            logger.info(f"尾部动画: {os.path.basename(overlay_path)}, {overlay_duration:.1f}s")

            # 时长控制
            final_duration = duration + overlay_duration
            if max_duration > 0 and final_duration > max_duration:
                # 如果超出最大时长，只截取源视频的前面部分
                src_keep = max(max_duration - overlay_duration, 5)
                if src_keep < duration:
                    logger.info(f"时长控制: 源视频从 {duration:.1f}s 截取到 {src_keep:.1f}s")
                    duration = src_keep

            # 构建 inputs
            inputs = ["-i", input_path, "-i", overlay_path]

            # 素材缩放对齐
            overlay_v_filters = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps:.6f},setsar=1"
            )
            overlay_a_filters = f"aresample={sr}"

            # 构建 filter_complex
            filter_parts = []

            # 源视频（可能截取）
            if max_duration > 0 and duration < src_info["duration"]:
                filter_parts.append(
                    f"[0:v]trim=0:{duration:.3f},setpts=PTS-STARTPTS[v1]"
                )
                filter_parts.append(
                    f"[0:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[a1]"
                )
            else:
                filter_parts.append("[0:v]setpts=PTS-STARTPTS[v1]")
                filter_parts.append("[0:a]asetpts=PTS-STARTPTS[a1]")

            # 尾部动画
            filter_parts.append(f"[1:v]{overlay_v_filters},setpts=PTS-STARTPTS[v2]")
            filter_parts.append(f"[1:a]{overlay_a_filters},asetpts=PTS-STARTPTS[a2]")

            # 贴纸叠加（在尾部动画段）
            if enable_stickers:
                tail_label = "[v2raw]"
                filter_parts[-2] = filter_parts[-2].replace("[v2]", tail_label)
                sticker_filters, v2_label = self._build_sticker_overlay_filters(
                    settings.STICKER_DIR, w, h, overlay_duration, inputs, tail_label
                )
                filter_parts.extend(sticker_filters)
                # 重映射到 [v2]
                if v2_label != "[v2]":
                    filter_parts.append(f"{v2_label}null[v2]")

            # concat
            concat_n = 2
            concat_labels = "[v1][a1][v2][a2]"

            if enable_dedup:
                dedup_filters = self._build_dedup_filters()
                dedup_chain = ",".join(dedup_filters)
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[concatv][outa]"
                )
                filter_parts.append(f"[concatv]{dedup_chain}[outv]")
                logger.info(f"去重滤镜: {len(dedup_filters)} 个")
            else:
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[outv][outa]"
                )

            filter_complex = ";\n".join(filter_parts)

            cmd = [
                self.ffmpeg_path, "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", settings.VIDEO_CODEC,
                "-c:a", settings.AUDIO_CODEC,
                "-movflags", "+faststart",
                output_path,
            ]

            logger.info(f"合成: {os.path.basename(input_path)} + {os.path.basename(overlay_path)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error(f"FFmpeg 失败: {result.stderr[-500:]}")
                return {"success": False, "error": f"FFmpeg 失败:\n{result.stderr[-500:]}"}

            out_size_mb = os.path.getsize(output_path) / 1024 / 1024
            logger.info(f"完成: {os.path.basename(output_path)} ({out_size_mb:.1f}MB)")
            return {"success": True, "output_path": output_path}

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 执行超时（600s）")
            return {"success": False, "error": "FFmpeg 执行超时"}
        except Exception as e:
            logger.error(f"处理异常: {e}")
            return {"success": False, "error": str(e)}

    def batch_dedup(self, input_dir: str, output_dir: str,
                     overlay_dir: str = "",
                     enable_dedup: bool = True,
                     enable_stickers: bool = True,
                     max_duration: float = 0) -> dict:
        """批量处理目录下所有视频"""
        overlay_dir = overlay_dir or settings.OVERLAY_DIR
        os.makedirs(output_dir, exist_ok=True)

        # 加载视频文件列表
        video_files = sorted([
            f for f in os.listdir(input_dir)
            if Path(f).suffix.lower() in VIDEO_EXTENSIONS
        ])

        if not video_files:
            logger.warning(f"输入目录中没有视频文件: {input_dir}")
            return {"success": False, "message": "输入目录中无视频文件"}

        # 加载尾部动画
        overlays = self._load_overlays(overlay_dir)
        if not overlays:
            logger.warning(f"尾部动画目录为空: {overlay_dir}")
            return {"success": False, "message": "尾部动画目录为空"}

        logger.info(f"处理 {len(video_files)} 个视频, 尾部动画 {len(overlays)} 个")
        logger.info(f"去重: {'开启' if enable_dedup else '关闭'}, 贴纸: {'开启' if enable_stickers else '关闭'}")

        results = []
        success_count = 0

        for i, filename in enumerate(video_files, 1):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)

            # 随机选尾部动画
            overlay_path = random.choice(overlays)

            logger.info(f"[{i}/{len(video_files)}] {filename}")
            result = self._dedup_single(
                input_path, overlay_path, output_path,
                enable_dedup=enable_dedup,
                enable_stickers=enable_stickers,
                max_duration=max_duration,
            )
            result["input"] = filename
            results.append(result)

            if result.get("success"):
                success_count += 1
                logger.info(f"  ✅ 成功")
            else:
                logger.error(f"  ❌ 失败: {result.get('error', '')}")

        logger.info(f"批量处理完成: {success_count}/{len(video_files)} 成功")
        return {
            "success": success_count > 0,
            "message": f"处理 {len(video_files)} 个视频: {success_count} 成功, {len(video_files) - success_count} 失败",
            "results": results,
        }

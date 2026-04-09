"""
FFmpeg 视频合成器 - 在原视频指定位置插入引导视频，支持去重处理
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from conf.settings import settings
from utils.log import get_logger
from library.video_util import VideoDedup, SceneDetector, TailAnimation

logger = get_logger(__name__)


class VideoCompositor:
    """视频合成器：在原视频指定位置插入引导视频片段，支持去重增强"""

    VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}

    def __init__(self, ffmpeg_path: str = ""):
        from utils.tool_finder import find_tool
        self.ffmpeg_path = ffmpeg_path or find_tool("ffmpeg", settings.FFMPEG_PATH)
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg 未找到，请先运行: python main.py setup")

        ffmpeg_dir = os.path.dirname(self.ffmpeg_path)
        self.ffprobe_path = os.path.join(ffmpeg_dir, "ffprobe") if ffmpeg_dir else "ffprobe"

    def get_video_info(self, video_path: str) -> dict:
        """用 ffprobe 获取视频信息"""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
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

    def composite(self, input_video: str, guide_video: str,
                  insert_at: float, output_path: str,
                  guide_duration: float = 0,
                  dedup: bool = True,
                  insert_range: Optional[tuple[float, float]] = None) -> dict:
        """在原视频 insert_at 秒处插入引导视频

        参数:
            input_video: 原视频路径
            guide_video: 引导视频路径
            insert_at: 插入位置（秒）
            output_path: 输出路径
            guide_duration: 截取引导视频前 N 秒（0=完整）
            dedup: 是否启用去重处理
            insert_range: 自适应插入范围 (min_t, max_t)，优先于 insert_at
        """
        if not os.path.isfile(input_video):
            return {"success": False, "error": f"输入视频不存在: {input_video}"}
        if not os.path.isfile(guide_video):
            return {"success": False, "error": f"引导视频不存在: {guide_video}"}

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # 去重工具
        dedup_proc = VideoDedup() if dedup else None
        scene_detector = SceneDetector(self.ffprobe_path) if dedup and insert_range else None
        tail_anim = TailAnimation(self.ffmpeg_path) if dedup else None

        try:
            logger.info(f"探测视频参数: {input_video}")
            src_info = self.get_video_info(input_video)
            w, h = src_info["width"], src_info["height"]
            fps = src_info["fps"]
            sr = src_info["sample_rate"]
            duration = src_info["duration"]

            logger.info(f"原视频: {w}x{h}, {fps:.2f}fps, {duration:.1f}s, {sr}Hz")

            # 1. 自适应插入点
            if scene_detector and insert_range:
                min_t, max_t = insert_range
                insert_at = scene_detector.find_insert_point(
                    input_video, min_t, max_t, duration
                )
                logger.info(f"自适应插入点: {insert_at:.2f}s（范围 {min_t}-{max_t}s）")

            # 如果原视频时长不足 insert_at，在末尾拼接
            if duration <= insert_at:
                logger.info(f"原视频时长 ({duration:.1f}s) <= 插入点 ({insert_at}s)，将在末尾拼接")
                return self._concat_at_end(input_video, guide_video, output_path,
                                           w, h, fps, sr, guide_duration,
                                           dedup_proc, tail_anim)

            # 2. 构建 filter_complex
            filter_parts = []
            inputs = ["-i", input_video, "-i", guide_video]

            # --- 引导视频 filter ---
            guide_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"

            guide_v_filters = []
            guide_a_filters = []

            if guide_duration > 0:
                guide_v_filters.append(f"trim=0:{guide_duration}")
                guide_v_filters.append("setpts=PTS-STARTPTS")
                guide_a_filters.append(f"atrim=0:{guide_duration}")
                guide_a_filters.append("asetpts=PTS-STARTPTS")

            guide_v_filters.append(guide_scale)
            guide_v_filters.append(f"fps={fps:.6f}")

            if not guide_a_filters:
                guide_a_filters.append("asetpts=PTS-STARTPTS")
            guide_a_filters.append(f"aresample={sr}")

            # 去重 filter（追加到引导视频 filter 链）
            speed_ratio = 1.0
            if dedup_proc:
                extra_v_filters, speed_ratio = dedup_proc.guide_dedup_filters()
                guide_v_filters.extend(extra_v_filters)
                # crop 会改变尺寸/SAR，需要 scale+pad+setsar 恢复
                guide_v_filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
                guide_a_filters.append(dedup_proc.guide_audio_dedup_filter(speed_ratio))
                logger.info(f"引导去重: eq/crop/speed 微调, 速度 {speed_ratio:.4f}x")

            guide_v_filters.append("setpts=PTS-STARTPTS")

            filter_parts.extend([
                # 原视频前半段
                f"[0:v]trim=0:{insert_at},setpts=PTS-STARTPTS[v1]",
                f"[0:a]atrim=0:{insert_at},asetpts=PTS-STARTPTS[a1]",
                # 引导视频（对齐+去重）
                f"[1:v]{','.join(guide_v_filters)}[v2]",
                f"[1:a]{','.join(guide_a_filters)}[a2]",
                # 原视频后半段
                f"[0:v]trim={insert_at},setpts=PTS-STARTPTS[v3]",
                f"[0:a]atrim={insert_at},asetpts=PTS-STARTPTS[a3]",
            ])

            # 3. 尾部动画
            tail_path = None
            concat_n = 3
            concat_labels = "[v1][a1][v2][a2][v3][a3]"

            if tail_anim:
                tail_path = tail_anim.get_tail_source(w, h, sr, fps, settings.OVERLAY_DIR)
                if tail_path:
                    tail_idx = len(inputs) // 2  # input index (0-based)
                    inputs.extend(["-i", tail_path])
                    tail_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
                    filter_parts.extend([
                        f"[{tail_idx}:v]{tail_scale},fps={fps:.6f},setpts=PTS-STARTPTS[v4]",
                        f"[{tail_idx}:a]aresample={sr},asetpts=PTS-STARTPTS[a4]",
                    ])
                    concat_n = 4
                    concat_labels = "[v1][a1][v2][a2][v3][a3][v4][a4]"
                    logger.info(f"尾部动画: {tail_path}")

            # 4. concat
            if dedup_proc:
                # concat → 整体去重 filter → 输出
                final_filters = dedup_proc.final_dedup_filters()
                final_v_chain = ",".join(final_filters)
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[concatv][outa]"
                )
                filter_parts.append(f"[concatv]{final_v_chain}[outv]")
                logger.info(f"整体去重: {len(final_filters)} 个 filter")
            else:
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[outv][outa]"
                )

            filter_complex = ";\n".join(filter_parts)

            cmd = [
                self.ffmpeg_path, "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", settings.VIDEO_CODEC,
                "-c:a", settings.AUDIO_CODEC,
                "-movflags", "+faststart",
                output_path,
            ]

            logger.info("合成中...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            # 清理临时尾部动画文件
            self._cleanup_tail(tail_path)

            if result.returncode != 0:
                logger.error(f"FFmpeg 失败: {result.stderr[-500:]}")
                return {"success": False, "error": f"FFmpeg 失败:\n{result.stderr[-500:]}"}

            output_size = os.path.getsize(output_path)
            logger.info(f"合成完成: {output_path} ({output_size / 1024 / 1024:.1f}MB)")

            return {"success": True, "output_path": output_path}

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 执行超时（600s）")
            return {"success": False, "error": "FFmpeg 执行超时（600s）"}
        except Exception as e:
            logger.error(f"合成异常: {e}")
            return {"success": False, "error": str(e)}

    def _concat_at_end(self, input_video: str, guide_video: str, output_path: str,
                       w: int, h: int, fps: float, sr: int,
                       guide_duration: float = 0,
                       dedup_proc=None, tail_anim=None) -> dict:
        """原视频时长不足时，在末尾拼接引导视频"""
        guide_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        inputs = ["-i", input_video, "-i", guide_video]
        filter_parts = []

        # 原视频
        filter_parts.append("[0:v]setpts=PTS-STARTPTS[v1]")
        filter_parts.append("[0:a]asetpts=PTS-STARTPTS[a1]")

        # 引导视频
        guide_v_filters = []
        guide_a_filters = []

        if guide_duration > 0:
            guide_v_filters.append(f"trim=0:{guide_duration}")
            guide_v_filters.append("setpts=PTS-STARTPTS")
            guide_a_filters.append(f"atrim=0:{guide_duration}")
            guide_a_filters.append("asetpts=PTS-STARTPTS")

        guide_v_filters.append(guide_scale)
        guide_v_filters.append(f"fps={fps:.6f}")

        if not guide_a_filters:
            guide_a_filters.append("asetpts=PTS-STARTPTS")
        guide_a_filters.append(f"aresample={sr}")

        if dedup_proc:
            extra_v, speed_ratio = dedup_proc.guide_dedup_filters()
            guide_v_filters.extend(extra_v)
            # crop 会改变尺寸/SAR，需要 scale+pad+setsar 恢复
            guide_v_filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
            guide_a_filters.append(dedup_proc.guide_audio_dedup_filter(speed_ratio))

        guide_v_filters.append("setpts=PTS-STARTPTS")

        filter_parts.append(f"[1:v]{','.join(guide_v_filters)}[v2]")
        filter_parts.append(f"[1:a]{','.join(guide_a_filters)}[a2]")

        # 尾部动画
        tail_path = None
        concat_n = 2
        concat_labels = "[v1][a1][v2][a2]"

        if tail_anim:
            tail_path = tail_anim.get_tail_source(w, h, sr, fps, settings.OVERLAY_DIR)
            if tail_path:
                tail_idx = len(inputs) // 2
                inputs.extend(["-i", tail_path])
                tail_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
                filter_parts.extend([
                    f"[{tail_idx}:v]{tail_scale},fps={fps:.6f},setpts=PTS-STARTPTS[v3]",
                    f"[{tail_idx}:a]aresample={sr},asetpts=PTS-STARTPTS[a3]",
                ])
                concat_n = 3
                concat_labels = "[v1][a1][v2][a2][v3][a3]"
                logger.info(f"尾部动画: {tail_path}")

        # concat + 整体去重
        if dedup_proc:
            final_filters = dedup_proc.final_dedup_filters()
            final_v_chain = ",".join(final_filters)
            filter_parts.append(
                f"{concat_labels}concat=n={concat_n}:v=1:a=1[concatv][outa]"
            )
            filter_parts.append(f"[concatv]{final_v_chain}[outv]")
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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        self._cleanup_tail(tail_path)

        if result.returncode != 0:
            logger.error(f"FFmpeg 失败: {result.stderr[-500:]}")
            return {"success": False, "error": f"FFmpeg 失败:\n{result.stderr[-500:]}"}

        return {"success": True, "output_path": output_path}

    def _cleanup_tail(self, tail_path: Optional[str]):
        """清理自动生成的临时尾部动画文件"""
        if tail_path and "/tmp/" in tail_path:
            try:
                os.unlink(tail_path)
            except OSError:
                pass

    def batch_composite(self, input_dir: str, guide_video: str,
                        insert_at: float, output_dir: str,
                        guide_duration: float = 0,
                        dedup: bool = True,
                        insert_range: Optional[tuple[float, float]] = None) -> list[dict]:
        """批量处理目录下所有视频"""
        os.makedirs(output_dir, exist_ok=True)

        video_files = sorted([
            f for f in os.listdir(input_dir)
            if Path(f).suffix.lower() in self.VIDEO_EXTENSIONS
        ])

        if not video_files:
            logger.warning(f"目录中没有视频文件: {input_dir}")
            return []

        logger.info(f"批量合成: {len(video_files)} 个视频, 去重={'开启' if dedup else '关闭'}")
        results = []

        for i, filename in enumerate(video_files, 1):
            logger.info(f"--- [{i}/{len(video_files)}] {filename} ---")
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)

            result = self.composite(
                input_path, guide_video, insert_at, output_path,
                guide_duration, dedup=dedup, insert_range=insert_range
            )
            results.append({**result, "input": filename})

            status = "成功" if result.get("success") else "失败"
            logger.info(f"  {status}")

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"批量合成完成: {success_count}/{len(results)} 成功")
        return results

"""
FFmpeg 视频合成器 - 在原视频指定位置插入引导视频，支持去重处理
"""
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Optional

from conf.settings import settings
from utils.log import get_logger
from infra.media.video_util import VideoDedup, SceneDetector, TailAnimation

logger = get_logger(__name__)

# 常量
TAIL_RESERVE = 3.0      # 尾部动画预留秒数
BACK_TAIL_CUT = (3.0, 5.0)  # back 段默认截尾范围（秒）


class StickerOverlay:
    """在视频段上叠加随机贴纸"""

    STICKER_EXTENSIONS = {".png", ".jpg", ".jpeg"}

    # 8 个边缘区域（相对于视频宽高的比例）
    POSITIONS = [
        (0.02, 0.02),   # 左上
        (0.85, 0.02),   # 右上
        (0.02, 0.85),   # 左下
        (0.85, 0.85),   # 右下
        (0.40, 0.02),   # 上中
        (0.40, 0.85),   # 下中
        (0.02, 0.40),   # 左中
        (0.85, 0.40),   # 右中
    ]

    def __init__(self, sticker_dir: str = ""):
        self.sticker_dir = sticker_dir or settings.STICKER_DIR
        self._stickers = self._load_stickers()

    def _load_stickers(self) -> list[str]:
        if not os.path.isdir(self.sticker_dir):
            return []
        return [
            os.path.join(self.sticker_dir, f)
            for f in os.listdir(self.sticker_dir)
            if Path(f).suffix.lower() in self.STICKER_EXTENSIONS
        ]

    def available(self) -> bool:
        return len(self._stickers) >= 2

    def build_overlay_filters(self, back_duration: float, w: int, h: int,
                              back_label: str, inputs: list[str]) -> tuple[list[str], str]:
        """构建贴纸 overlay filter 链

        返回: (filter_parts, final_label)
        """
        if not self.available() or back_duration <= 0:
            return [], back_label

        # 随机选 2-5 张贴纸
        count = min(random.randint(2, 5), len(self._stickers))
        chosen = random.sample(self._stickers, count)

        # 贴纸尺寸：短边的 5-8%
        short_side = min(w, h)
        sticker_size = int(short_side * random.uniform(0.05, 0.08))
        sticker_size = max(sticker_size, 30)

        # 随机分配位置（不重复）
        positions = random.sample(self.POSITIONS, min(count, len(self.POSITIONS)))

        # 将 back 段时间均匀分成 count 个时间窗口
        window = back_duration / count

        filter_parts = []
        current_label = back_label

        for i, (sticker_path, pos) in enumerate(zip(chosen, positions)):
            # 计算输入索引
            stk_idx = len(inputs) // 2
            inputs.extend(["-i", sticker_path])

            # 时间窗口
            t_start = i * window
            t_end = min(t_start + window - 0.5, back_duration)
            if t_end <= t_start:
                t_end = t_start + window

            # 位置（像素）
            x = int(w * pos[0])
            y = int(h * pos[1])

            # 透明度 50-80%
            opacity = round(random.uniform(0.5, 0.8), 2)

            next_label = f"[v3s{i}]"
            # scale 贴纸 + 设置透明度 + overlay
            filter_parts.append(
                f"[{stk_idx}:v]scale={sticker_size}:{sticker_size},format=rgba,"
                f"colorchannelmixer=aa={opacity}[stk{i}]"
            )
            filter_parts.append(
                f"{current_label}[stk{i}]overlay=x={x}:y={y}:"
                f"enable='between(t,{t_start:.1f},{t_end:.1f})'{next_label}"
            )
            current_label = next_label

        logger.info(f"贴纸叠加: {count} 张, 尺寸 {sticker_size}px")
        return filter_parts, current_label


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

    def _calc_back_end(self, duration: float, insert_at: float,
                       effective_guide: float, max_duration: float) -> float:
        """计算 back 段结束时间（两步截取）"""
        # Step 1: 默认截尾 3-5s
        tail_cut = random.uniform(*BACK_TAIL_CUT)
        back_end = duration - tail_cut
        # 确保 back 段至少有 5s
        if back_end <= insert_at + 5:
            back_end = duration  # 视频太短就不截尾了

        logger.info(f"截尾: 剪去末尾 {tail_cut:.1f}s → back 结束于 {back_end:.1f}s")

        # Step 2: 时长控制
        if max_duration and max_duration > 0:
            total = insert_at + effective_guide + (back_end - insert_at) + TAIL_RESERVE
            if total > max_duration:
                back_max = max_duration - insert_at - effective_guide - TAIL_RESERVE
                if back_max > 5:  # 至少保留 5s
                    back_end = insert_at + back_max
                    logger.info(f"时长控制: back 段截取到 {back_max:.1f}s（目标 ≤ {max_duration}s）")

        return back_end

    @staticmethod
    def _build_watermark_filter(text: str, style: dict,
                                in_label: str, out_label: str) -> str:
        """构建水印 drawtext filter

        drift=lissajous: Lissajous 曲线漂移
        drift=static:    固定居中
        """
        safe = text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        fontsize = style.get("fontsize", 22)
        opacity = style.get("opacity", 0.25)
        drift = style.get("drift", "lissajous")

        if drift == "static":
            x, y = "(W-tw)/2", "(H-th)/2"
        else:  # lissajous
            x = "W/2+W*0.35*sin(t*0.4)"
            y = "H/2+H*0.35*cos(t*0.7)"

        return (
            f"{in_label}setsar=1,"
            f"drawtext="
            f"text='{safe}':"
            f"fontsize={fontsize}:"
            f"fontcolor=white@{opacity}:"
            f"x='{x}':"
            f"y='{y}'"
            f"{out_label}"
        )

    def composite(self, input_video: str, guide_video: str,
                  insert_at: float, output_path: str,
                  guide_duration: float = 0,
                  dedup: bool = True,
                  insert_range: Optional[tuple[float, float]] = None,
                  max_duration: float = 0,
                  category: str = "",
                  watermark_text: str = "",
                  watermark_style: Optional[dict] = None) -> dict:
        """在原视频 insert_at 秒处插入引导视频

        参数:
            input_video: 原视频路径
            guide_video: 引导视频路径
            insert_at: 插入位置（秒）
            output_path: 输出路径
            guide_duration: 截取引导视频前 N 秒（0=完整）
            dedup: 是否启用去重处理
            insert_range: 自适应插入范围 (min_t, max_t)，优先于 insert_at
            max_duration: 最终视频最大时长（秒），0=不限制
            watermark_text: 水印文字，空字符串=不加水印
            watermark_style: 水印样式 dict（fontsize/opacity/drift）
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
        sticker = StickerOverlay()

        try:
            logger.info(f"探测视频参数: {input_video}")
            src_info = self.get_video_info(input_video)
            w, h = src_info["width"], src_info["height"]
            fps = src_info["fps"]
            sr = src_info["sample_rate"]
            duration = src_info["duration"]

            logger.info(f"原视频: {w}x{h}, {fps:.2f}fps, {duration:.1f}s, {sr}Hz")

            # 获取引导视频时长
            guide_info = self.get_video_info(guide_video)
            effective_guide = guide_duration if guide_duration > 0 else guide_info["duration"]

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
                                           dedup_proc, tail_anim, max_duration, category,
                                           watermark_text, watermark_style)

            # 计算 back 段结束时间（截尾 + 时长控制）
            back_end = self._calc_back_end(duration, insert_at, effective_guide, max_duration)
            back_duration = back_end - insert_at

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
                guide_v_filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
                guide_a_filters.append(dedup_proc.guide_audio_dedup_filter(speed_ratio))
                logger.info(f"引导去重: eq/crop/speed 微调, 速度 {speed_ratio:.4f}x")

            guide_v_filters.append("setpts=PTS-STARTPTS")

            # --- back 段 filter（截尾后） ---
            back_v_label = "[v3]"
            back_trim_v = f"[0:v]trim={insert_at}:{back_end},setpts=PTS-STARTPTS"
            back_trim_a = f"[0:a]atrim={insert_at}:{back_end},asetpts=PTS-STARTPTS[a3]"

            # 贴纸叠加：先输出到临时 label，再叠加贴纸
            if sticker.available():
                back_trim_v += "[v3raw]"
                sticker_filters, back_v_label = sticker.build_overlay_filters(
                    back_duration, w, h, "[v3raw]", inputs
                )
            else:
                back_trim_v += "[v3]"
                sticker_filters = []

            filter_parts.extend([
                # 原视频前半段
                f"[0:v]trim=0:{insert_at},setpts=PTS-STARTPTS[v1]",
                f"[0:a]atrim=0:{insert_at},asetpts=PTS-STARTPTS[a1]",
                # 引导视频（对齐+去重）
                f"[1:v]{','.join(guide_v_filters)}[v2]",
                f"[1:a]{','.join(guide_a_filters)}[a2]",
                # 原视频后半段（截尾后）
                back_trim_v,
                back_trim_a,
            ])

            # 追加贴纸 filter
            filter_parts.extend(sticker_filters)

            # 如果贴纸改变了 v3 的 label，需要映射回 [v3]
            if back_v_label != "[v3]":
                # 重命名 label: 直接在最后一个 sticker filter 里已经输出了 back_v_label
                # 需要用 null filter 映射
                filter_parts.append(f"{back_v_label}null[v3]")

            # 3. 尾部动画
            tail_path = None
            concat_n = 3
            concat_labels = "[v1][a1][v2][a2][v3][a3]"

            if tail_anim:
                tail_path = tail_anim.get_tail_source(w, h, sr, fps, settings.OVERLAY_DIR)
                if tail_path:
                    tail_idx = len(inputs) // 2
                    inputs.extend(["-i", tail_path])
                    tail_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
                    filter_parts.extend([
                        f"[{tail_idx}:v]{tail_scale},fps={fps:.6f},setpts=PTS-STARTPTS[v4]",
                        f"[{tail_idx}:a]aresample={sr},asetpts=PTS-STARTPTS[a4]",
                    ])
                    concat_n = 4
                    concat_labels = "[v1][a1][v2][a2][v3][a3][v4][a4]"
                    logger.info(f"尾部动画: {tail_path}")

            # 4. concat + 水印
            if dedup_proc:
                final_filters = dedup_proc.final_dedup_filters()
                final_v_chain = ",".join(final_filters)
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[concatv][outa]"
                )
                if watermark_text:
                    filter_parts.append(f"[concatv]{final_v_chain}[wm_in]")
                    filter_parts.append(
                        self._build_watermark_filter(
                            watermark_text, watermark_style or {}, "[wm_in]", "[outv]"
                        )
                    )
                else:
                    filter_parts.append(f"[concatv]{final_v_chain}[outv]")
                logger.info(f"整体去重: {len(final_filters)} 个 filter")
            else:
                if watermark_text:
                    filter_parts.append(
                        f"{concat_labels}concat=n={concat_n}:v=1:a=1[wm_in][outa]"
                    )
                    filter_parts.append(
                        self._build_watermark_filter(
                            watermark_text, watermark_style or {}, "[wm_in]", "[outv]"
                        )
                    )
                else:
                    filter_parts.append(
                        f"{concat_labels}concat=n={concat_n}:v=1:a=1[outv][outa]"
                    )

            if watermark_text:
                logger.info(f"水印: '{watermark_text}' drift={( watermark_style or {}).get('drift','lissajous')}")

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
                       dedup_proc=None, tail_anim=None,
                       max_duration: float = 0,
                       category: str = "",
                       watermark_text: str = "",
                       watermark_style: Optional[dict] = None) -> dict:
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
                tail_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
                filter_parts.extend([
                    f"[{tail_idx}:v]{tail_scale},fps={fps:.6f},setpts=PTS-STARTPTS[v3]",
                    f"[{tail_idx}:a]aresample={sr},asetpts=PTS-STARTPTS[a3]",
                ])
                concat_n = 3
                concat_labels = "[v1][a1][v2][a2][v3][a3]"
                logger.info(f"尾部动画: {tail_path}")

        # concat + 整体去重 + 水印
        if dedup_proc:
            final_filters = dedup_proc.final_dedup_filters()
            final_v_chain = ",".join(final_filters)
            filter_parts.append(
                f"{concat_labels}concat=n={concat_n}:v=1:a=1[concatv][outa]"
            )
            if watermark_text:
                filter_parts.append(f"[concatv]{final_v_chain}[wm_in]")
                filter_parts.append(
                    self._build_watermark_filter(
                        watermark_text, watermark_style or {}, "[wm_in]", "[outv]"
                    )
                )
            else:
                filter_parts.append(f"[concatv]{final_v_chain}[outv]")
        else:
            if watermark_text:
                filter_parts.append(
                    f"{concat_labels}concat=n={concat_n}:v=1:a=1[wm_in][outa]"
                )
                filter_parts.append(
                    self._build_watermark_filter(
                        watermark_text, watermark_style or {}, "[wm_in]", "[outv]"
                    )
                )
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
                        insert_range: Optional[tuple[float, float]] = None,
                        max_duration: float = 0) -> list[dict]:
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
                guide_duration, dedup=dedup, insert_range=insert_range,
                max_duration=max_duration
            )
            results.append({**result, "input": filename})

            status = "成功" if result.get("success") else "失败"
            logger.info(f"  {status}")

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"批量合成完成: {success_count}/{len(results)} 成功")
        return results

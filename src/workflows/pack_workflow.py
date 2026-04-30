"""
PackWorkflow — 视频打包工作流

根据 plan_id 将合成视频 + 封面打包成 zip，生成 AI 优化标题（三平台风格），
输出到 data/output/pack_plan_{plan_id}.zip，方便运营人员手动发布。
"""
import csv
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import requests as _req
from PIL import Image

from utils.log import get_logger

logger = get_logger(__name__)

_MIN_COVER_W = 720
_MIN_COVER_H = 405


class PackWorkflow:

    def pack(self, plan_id: int, account_id: int | None = None,
             ai_titles: bool = False) -> dict:
        from infra.db.database import SessionLocal
        from infra.db.repositories import (
            PlanItemRepository, VideoTaskRepository, AccountRepository,
        )
        from conf.settings import settings

        db = SessionLocal()
        try:
            item_repo = PlanItemRepository(db)
            vt_repo   = VideoTaskRepository(db)
            acc_repo  = AccountRepository(db)

            items = item_repo.list_by_plan(plan_id)
            if not items:
                return {"success": False, "message": f"plan_id={plan_id} 无任务"}

            if account_id:
                items = [i for i in items if i.account_id == account_id]
                if not items:
                    return {"success": False,
                            "message": f"plan_id={plan_id} 账号 {account_id} 无任务"}

            logger.info(f"plan_id={plan_id} 共 {len(items)} 条，开始打包")

            # 初始化 AI 客户端（仅 --ai-titles 时启用）
            ai_client = None
            if ai_titles:
                try:
                    import anthropic
                    # ANTHROPIC_BASE_URL/ANTHROPIC_AUTH_TOKEN 由 IDE 注入，优先级高于构造参数
                    # 暂时替换为 DeepSeek 值，构造完成后立即还原
                    _saved = {k: os.environ.get(k) for k in
                              ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
                    os.environ["ANTHROPIC_BASE_URL"] = settings.AI_BASE_URL
                    os.environ["ANTHROPIC_API_KEY"]  = settings.AI_API_KEY
                    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
                    try:
                        ai_client = anthropic.Anthropic()
                    finally:
                        for k, v in _saved.items():
                            if v is None:
                                os.environ.pop(k, None)
                            else:
                                os.environ[k] = v
                    logger.info("AI 标题生成已启用")
                except Exception as e:
                    logger.warning(f"AI 客户端初始化失败，跳过 AI 标题: {e}")

            # 按账号分组
            acc_groups: dict[int, list] = {}
            for item in items:
                acc_groups.setdefault(item.account_id, []).append(item)

            # 用 tmpdir 暂存，最后打包成 zip
            with tempfile.TemporaryDirectory() as tmpdir:
                manifest_rows = []

                for acc_order, (aid, acc_items) in enumerate(
                        sorted(acc_groups.items()), start=1):
                    acc = acc_repo.get_by_id(aid)
                    acc_name = (acc.name or str(aid)) if acc else str(aid)
                    platform  = (acc.platform or "baijiahao") if acc else "baijiahao"

                    # 账号目录名：01_区颖颖E5_baijiahao
                    safe_name = re.sub(r'[\\/:*?"<>|]', "_", acc_name)
                    dir_name  = f"{acc_order:02d}_{safe_name}_{platform}"
                    acc_dir   = Path(tmpdir) / dir_name
                    acc_dir.mkdir(parents=True, exist_ok=True)

                    acc_meta = []

                    for idx, item in enumerate(
                            sorted(acc_items, key=lambda x: x.order_idx), start=1):
                        vt = vt_repo.get_by_id(item.video_task_id)
                        if not vt:
                            continue

                        orig_title = vt.title or ""
                        category   = vt.category or item.category or ""

                        # 1. 复制视频文件
                        src_path = vt.output_path or ""
                        video_filename = None
                        if src_path and os.path.exists(src_path):
                            video_filename = f"{idx:02d}_{_safe_title(orig_title)}.mp4"
                            shutil.copy2(src_path, acc_dir / video_filename)
                        else:
                            logger.warning(f"  视频文件不存在: {src_path}")

                        # 2. 下载封面
                        cover_filename = None
                        cover_url = vt.cover_url or ""
                        if cover_url:
                            local = _download_cover(cover_url)
                            if local:
                                cover_filename = f"{idx:02d}_cover.jpg"
                                shutil.move(local, str(acc_dir / cover_filename))

                        # 3. AI 生成三平台标题
                        titles = _generate_titles(ai_client, orig_title, category)

                        acc_meta.append({
                            "序号": idx,
                            "视频文件": video_filename or "",
                            "封面文件": cover_filename or "",
                            "原标题":   orig_title,
                            "标题_百家号":    titles["baijiahao"],
                            "标题_哔哩哔哩":  titles["bilibili"],
                            "标题_小红书":    titles["xiaohongshu"],
                            "标签": vt.tags or "",
                            "品类": category,
                        })
                        manifest_rows.append({
                            "序号":     f"{acc_order:02d}-{idx:02d}",
                            "账号ID":   aid,
                            "账号名":   acc_name,
                            "平台":     platform,
                            "品类":     category,
                            "目录":     dir_name,
                            "视频文件": video_filename or "",
                            "封面文件": cover_filename or "",
                            "原标题":   orig_title,
                            "标题_百家号":    titles["baijiahao"],
                            "标题_哔哩哔哩":  titles["bilibili"],
                            "标题_小红书":    titles["xiaohongshu"],
                            "标签":     vt.tags or "",
                        })
                        logger.info(f"  [{dir_name}] {idx:02d} {orig_title[:30]}")

                    # 写账号 manifest.json
                    with open(acc_dir / "manifest.json", "w", encoding="utf-8") as f:
                        json.dump(acc_meta, f, ensure_ascii=False, indent=2)

                # 写汇总 manifest.csv
                csv_path = Path(tmpdir) / "manifest.csv"
                if manifest_rows:
                    fields = list(manifest_rows[0].keys())
                    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                        w = csv.DictWriter(f, fieldnames=fields)
                        w.writeheader()
                        w.writerows(manifest_rows)

                # 打包成 zip，输出到项目根目录 output/
                output_dir = Path(settings.BASE_DIR) / "output"
                output_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                suffix = datetime.now().strftime("%Y%m%d_%H%M")
                zip_path = output_dir / f"pack_plan_{plan_id}_{suffix}.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in Path(tmpdir).rglob("*"):
                        if file.is_file():
                            zf.write(file, file.relative_to(tmpdir))

            size_mb = zip_path.stat().st_size / 1024 / 1024
            msg = (f"打包完成: {zip_path}（{len(manifest_rows)} 条，"
                   f"{size_mb:.1f} MB）")
            logger.info(msg)
            return {"success": True, "message": msg,
                    "zip_path": str(zip_path), "count": len(manifest_rows)}

        finally:
            db.close()


# ── 内部工具函数 ────────────────────────────────────────────────

def _safe_title(title: str, max_len: int = 40) -> str:
    """清洗标题：去掉 #话题、特殊字符，用于文件名"""
    t = re.sub(r'#\S+', '', title).strip()
    t = re.sub(r'[\\/:*?"<>|\s]+', '_', t)
    return t[:max_len] or "video"


def _download_cover(cover_url: str) -> str | None:
    """下载封面并放大到 ≥ 720×405，返回临时文件路径"""
    try:
        resp = _req.get(cover_url, timeout=30)
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(resp.content)
        tmp.close()
        try:
            img = Image.open(tmp.name)
            w, h = img.size
            scale = max(_MIN_COVER_W / w, _MIN_COVER_H / h)
            if scale > 1:
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                img.save(tmp.name, "JPEG", quality=92)
        except Exception:
            pass
        return tmp.name
    except Exception as e:
        logger.warning(f"封面下载失败: {e}")
        return None


def _generate_titles(ai_client, orig_title: str, category: str) -> dict:
    """调用 Claude API 生成三平台标题；失败则返回清洗后的原标题"""
    fallback = _safe_title(orig_title).replace("_", " ").strip() or orig_title
    result = {"baijiahao": fallback, "bilibili": fallback, "xiaohongshu": fallback}

    if not ai_client or not orig_title:
        return result

    prompt = f"""原标题：{orig_title}
游戏品类：{category}

请生成3种平台风格的标题，只返回 JSON，不要任何解释：
{{
  "baijiahao": "百家号风格（简洁权威，15-25字，无#话题）",
  "bilibili": "B站风格（可带【】标记或梗，20-30字）",
  "xiaohongshu": "小红书风格（emoji开头，种草感，20-35字）"
}}"""

    try:
        msg = ai_client.messages.create(
            model="deepseek-v4-flash",
            max_tokens=300,
            system="你是游戏短视频标题优化专家，擅长为不同平台生成吸引点击的标题。",
            messages=[{
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }],
        )
        text_block = next((b for b in msg.content if hasattr(b, "text")), None)
        if not text_block:
            return result
        text = text_block.text.strip()
        # 提取 JSON
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            result.update({k: v for k, v in data.items() if k in result and v})
    except Exception as e:
        logger.warning(f"AI 标题生成失败（使用原标题）: {e}")

    return result

#!/usr/bin/env python3
"""
将 .codex/skills/ 同步到 .claude/skills/

功能：
- 扫描 .codex/skills/ 下所有 skill 目录
- 将 SKILL.md 转换为 Claude 格式写入 .claude/skills/<name>/
- 合并 agents/openai.yaml 中的 display_name / short_description 到 frontmatter
- 支持 --dry-run 预览、--force 覆盖已有、--reverse 反向同步（claude → codex）
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CODEX_SKILLS = ROOT / ".codex" / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"

# 不需要同步的辅助文件
SKIP_FILES = {"openai.yaml", "agents"}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter，返回 (metadata, body)"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    body = text[end + 3 :].lstrip("\n")
    return meta, body


def build_frontmatter(meta: dict) -> str:
    """将 dict 序列化为 YAML frontmatter"""
    dumped = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{dumped}\n---\n"


def read_codex_skill(skill_dir: Path) -> dict:
    """读取一个 codex skill 的完整信息"""
    info = {"dir": skill_dir, "name": skill_dir.name, "files": []}

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        text = skill_md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        info["meta"] = meta
        info["body"] = body
    else:
        info["meta"] = {}
        info["body"] = ""

    # 读取 openai.yaml 合并额外信息
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if openai_yaml.exists():
        with open(openai_yaml, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        iface = data.get("interface", {})
        info["openai"] = iface
    else:
        info["openai"] = {}

    # 收集需要同步的额外文件（SKILL.md 和 agents/ 之外的）
    for f in skill_dir.iterdir():
        if f.name == "SKILL.md":
            continue
        if f.name in SKIP_FILES or f.name == "agents":
            continue
        info["files"].append(f)

    return info


def read_claude_skill(skill_dir: Path) -> dict:
    """读取一个 claude skill 的完整信息"""
    info = {"dir": skill_dir, "name": skill_dir.name, "files": []}

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        text = skill_md.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        info["meta"] = meta
        info["body"] = body
    else:
        info["meta"] = {}
        info["body"] = ""

    for f in skill_dir.iterdir():
        if f.name == "SKILL.md":
            continue
        info["files"].append(f)

    return info


def merge_meta_to_claude(codex_info: dict) -> tuple[dict, str]:
    """将 codex skill 信息合并为 claude 格式的 frontmatter + body"""
    meta = dict(codex_info["meta"])  # 保留原始 meta

    # openai.yaml 的 display_name 覆盖 name（如有）
    openai = codex_info["openai"]
    if openai.get("display_name") and not meta.get("name"):
        meta["name"] = openai["display_name"]

    # openai.yaml 的 short_description 补充 description（如有）
    if openai.get("short_description") and not meta.get("description"):
        meta["description"] = openai["short_description"]

    # default_prompt 写入 body 头部作为触发说明
    body = codex_info["body"]
    if openai.get("default_prompt") and "触发方式" not in body:
        trigger = f"触发方式：{openai['default_prompt']}\n\n"
        body = trigger + body

    return meta, body


def merge_meta_to_codex(claude_info: dict) -> tuple[dict, str, dict]:
    """将 claude skill 信息合并为 codex 格式：frontmatter + body + openai.yaml"""
    meta = dict(claude_info["meta"])
    body = claude_info["body"]

    openai = {}
    if meta.get("name"):
        openai["display_name"] = meta["name"]
    if meta.get("description"):
        openai["short_description"] = meta["description"]

    return meta, body, openai


def sync_codex_to_claude(dry_run: bool = False, force: bool = False):
    """从 .codex/skills/ 同步到 .claude/skills/"""
    if not CODEX_SKILLS.exists():
        print(f"目录不存在: {CODEX_SKILLS}")
        return

    synced, skipped, errors = [], [], []

    for skill_dir in sorted(CODEX_SKILLS.iterdir()):
        if not skill_dir.is_dir():
            continue

        codex_info = read_codex_skill(skill_dir)
        name = codex_info["name"]
        target_dir = CLAUDE_SKILLS / name

        # 检查目标是否已存在
        if target_dir.exists() and not force:
            existing_md = target_dir / "SKILL.md"
            if existing_md.exists():
                skipped.append(name)
                print(f"  跳过 {name}（已存在，用 --force 覆盖）")
                continue

        meta, body = merge_meta_to_claude(codex_info)
        content = build_frontmatter(meta) + "\n" + body

        if dry_run:
            print(f"  [dry-run] 将写入: {target_dir}/SKILL.md")
            print(f"    name: {meta.get('name')}")
            print(f"    description: {meta.get('description', '')[:60]}...")
            synced.append(name)
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # 同步额外文件（LICENSE.txt 等）
        for f in codex_info["files"]:
            dest = target_dir / f.name
            if f.is_file():
                shutil.copy2(f, dest)
            elif f.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(f, dest)

        synced.append(name)
        print(f"  同步 {name} → .claude/skills/{name}/")

    print(f"\n完成：{len(synced)} 同步, {len(skipped)} 跳过, {len(errors)} 错误")


def sync_claude_to_codex(dry_run: bool = False, force: bool = False):
    """从 .claude/skills/ 同步到 .codex/skills/"""
    if not CLAUDE_SKILLS.exists():
        print(f"目录不存在: {CLAUDE_SKILLS}")
        return

    synced, skipped, errors = [], [], []

    for skill_dir in sorted(CLAUDE_SKILLS.iterdir()):
        if not skill_dir.is_dir():
            continue

        claude_info = read_claude_skill(skill_dir)
        name = claude_info["name"]
        target_dir = CODEX_SKILLS / name

        if target_dir.exists() and not force:
            existing_md = target_dir / "SKILL.md"
            if existing_md.exists():
                skipped.append(name)
                print(f"  跳过 {name}（已存在，用 --force 覆盖）")
                continue

        meta, body, openai = merge_meta_to_codex(claude_info)
        content = build_frontmatter(meta) + "\n" + body

        if dry_run:
            print(f"  [dry-run] 将写入: {target_dir}/SKILL.md")
            print(f"    name: {meta.get('name')}")
            if openai:
                print(f"    openai.yaml: display_name={openai.get('display_name')}")
            synced.append(name)
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(content, encoding="utf-8")

        # 写入 openai.yaml
        if openai:
            agents_dir = target_dir / "agents"
            agents_dir.mkdir(exist_ok=True)
            yaml_content = yaml.dump(
                {"interface": openai},
                allow_unicode=True,
                default_flow_style=False,
            )
            (agents_dir / "openai.yaml").write_text(yaml_content, encoding="utf-8")

        # 同步额外文件
        for f in claude_info["files"]:
            dest = target_dir / f.name
            if f.is_file():
                shutil.copy2(f, dest)
            elif f.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(f, dest)

        synced.append(name)
        print(f"  同步 {name} → .codex/skills/{name}/")

    print(f"\n完成：{len(synced)} 同步, {len(skipped)} 跳过, {len(errors)} 错误")


def main():
    parser = argparse.ArgumentParser(
        description="同步 Codex skills ↔ Claude skills"
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="反向同步：从 .claude/skills/ → .codex/skills/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不写入文件",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有 skill",
    )
    args = parser.parse_args()

    if args.reverse:
        print("反向同步：.claude/skills/ → .codex/skills/\n")
        sync_claude_to_codex(dry_run=args.dry_run, force=args.force)
    else:
        print("同步：.codex/skills/ → .claude/skills/\n")
        sync_codex_to_claude(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()

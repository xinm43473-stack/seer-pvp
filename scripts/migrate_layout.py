#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把数据目录按「来源」和「业务口径」拆开（2026-11-19 用户要求）。

用户口径：从外部爬下来的文件放一处；程序读取的列表/推荐技能/体系等业务文件放另一处。

    data/
      bwiki/       BWIKI 抓取（精灵索引、魂印、属性克制表、池数据）
      seerapi/     SeerAPI 抓取（技能、魂印全文、精灵资料、媒体、抓取缓存）
      derived/     由上面两层生成的派生物（属性表、全量库、名词词表、缺图日志）
    references/
      catalog/     人维护、程序读取的业务口径（列表、强度、定位词表、审计、人工覆盖、体系聚合）
      systems/     单个体系文件（本来就是业务区，保持不动）

脚本里统一用 `DATA / "子目录/文件名"` 形式，所以本脚本只需做两类替换：
    1. `DATA / "x.json"`、`os.path.join(DATA, "x.json")`、`_load("x.json")`
    2. `REF / "data" / ...`、`"references" / "data" / ...`

用法:
    python scripts/migrate_layout.py --dry-run
    python scripts/migrate_layout.py
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REF = ROOT / "references"
CATALOG = REF / "catalog"

# 旧位置 -> 新位置（相对项目根）
MOVES = {
    # ---- BWIKI 抓取 ----
    "data/bwiki/elves.json": "data/bwiki/elves.json",
    "data/bwiki/souls.json": "data/bwiki/souls.json",
    "data/bwiki/typeChart.lua": "data/bwiki/typeChart.lua",
    "data/pool.json": "data/bwiki/pool.json",
    # ---- SeerAPI 抓取 ----
    "data/seerapi.json": "data/seerapi/seerapi.json",
    "data/skills.json": "data/seerapi/skills.json",
    "data/skills_full.json": "data/seerapi/skills_full.json",
    "data/elf_skills.json": "data/seerapi/elf_skills.json",
    "data/soul_full.json": "data/seerapi/soul_full.json",
    "data/spirit_info.json": "data/seerapi/spirit_info.json",
    "data/spirit_media.json": "data/seerapi/spirit_media.json",
    "data/seerapi_skills_cache.json": "data/seerapi/seerapi_skills_cache.json",
    # ---- 派生物 ----
    "data/typechart.json": "data/derived/typechart.json",
    "data/spirit_library.json": "data/derived/spirit_library.json",
    "data/soul_terms.json": "data/derived/soul_terms.json",
    "data/library_images_failures.json": "data/derived/library_images_failures.json",
    # ---- 人工维护的业务文件 ----
    "data/manual_overrides.json": "references/catalog/manual_overrides.json",
    "data/pull_selection.json": "references/catalog/pull_selection.json",
}

# 只改「代码 + 文档」：数据文件（json/csv）里的路径说明不参与重写，
# 前端产物（spirit_synergy_view.html）由 rebuild 重新生成，也不在这里改。
TEXT_SUFFIX = {".py", ".md", ".html", ".txt", ".yml", ".yaml"}
SKIP_DIRS = {"__pycache__", ".git", "assets", "dist", "_backup"}
SKIP_FILES = {"scripts/migrate_layout.py", "references/spirit_synergy_view.html"}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def move_files(dry: bool) -> None:
    for old, new in MOVES.items():
        src, dst = ROOT / old, ROOT / new
        if not src.exists():
            if dst.exists():
                print(f"  已迁移 {old} -> {new}")
            else:
                print(f"  缺失 {old}（跳过）")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dry:
            print(f"  {old} -> {new}")
            continue
        shutil.move(str(src), str(dst))
        print(f"  {old} -> {new}")


def rewrite_text(text: str) -> str:
    """按 MOVES 重写路径字面量；返回新文本。"""
    # 长的先替换，避免 data/raw/elves.json 被 data/elves.json 规则误伤
    for old, new in sorted(MOVES.items(), key=lambda kv: len(kv[0]), reverse=True):
        old_name = Path(old).name
        new_rel = Path(new)
        # 人工维护的文件从 data/ 挪进 references/catalog，单独处理（其余 data/ 文件走下面的子目录规则）
        if old.startswith("data/manual_overrides") or old.startswith("data/pull_selection"):
            text = text.replace(f'DATA / "{old_name}"', f'REF / "catalog" / "{old_name}"')
            text = text.replace(f"DATA / '{old_name}'", f"REF / 'catalog' / '{old_name}'")
            text = text.replace(f'os.path.join(DATA, "{old_name}")',
                                f'os.path.join(REF, "catalog", "{old_name}")')
            text = text.replace(f"os.path.join(DATA, '{old_name}')",
                                f"os.path.join(REF, 'catalog', '{old_name}')")
            text = text.replace(f'_load("{old_name}")', f'_load("references/catalog/{old_name}")')
            text = text.replace(f"_load('{old_name}')", f"_load('references/catalog/{old_name}')")
            text = text.replace(f'"data/{old_name}"', f'"references/catalog/{old_name}"')
            text = text.replace(f"'data/{old_name}'", f"'references/catalog/{old_name}'")
            continue
        # data/ 下的抓取文件：脚本里写的是 DATA / "名字"，把文件名换成「子目录/名字」
        if old.startswith("data/"):
            sub = new_rel.relative_to("data").as_posix()   # 例如 seerapi/skills.json
            if old.startswith("data/raw/"):
                sub = sub  # raw 层去掉，已在 MOVES 里体现
            text = text.replace(f'DATA / "{old_name}"', f'DATA / "{sub}"')
            text = text.replace(f"DATA / '{old_name}'", f"DATA / '{sub}'")
            text = text.replace(f'os.path.join(DATA, "{old_name}")', f'os.path.join(DATA, "{sub}")')
            text = text.replace(f"os.path.join(DATA, '{old_name}')", f"os.path.join(DATA, '{sub}')")
            text = text.replace(f'_load("{old_name}")', f'_load("{sub}")')
            text = text.replace(f"_load('{old_name}')", f"_load('{sub}')")
            # 直接写整段路径的
            text = text.replace(f'"data/{old_name}"', f'"data/{sub}"')
            text = text.replace(f"'data/{old_name}'", f"'data/{sub}'")
            text = text.replace(f'"data\\\\{old_name}"', f'"data\\\\{sub}"')
    # references/data -> references/catalog
    text = text.replace('REF / "data" / ', 'REF / "catalog" / ')
    text = text.replace("REF / 'data' / ", "REF / 'catalog' / ")
    text = text.replace('"references" / "data" / ', '"references" / "catalog" / ')
    text = text.replace('"references/data', '"references/catalog')
    text = text.replace('"references\\\\data', '"references\\\\catalog')
    text = text.replace("references/data/", "references/catalog/")
    return text


def rewrite_sources(dry: bool) -> list[tuple[str, int]]:
    changed = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIX:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel(path) in SKIP_FILES:
            continue
        if path.stat().st_size > 30_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = rewrite_text(text)
        if new == text:
            continue
        changed.append((rel(path), text.count("\n")))
        if not dry:
            path.write_text(new, encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for d in ("data/bwiki", "data/seerapi", "data/derived", "references/catalog"):
        if not args.dry_run:
            (ROOT / d).mkdir(parents=True, exist_ok=True)

    print("移动文件：")
    move_files(args.dry_run)
    if not args.dry_run:
        # 清掉搬空的旧目录（data/raw、references/data）
        for d in (ROOT / "data" / "raw", REF / "data"):
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
                print(f"  删除空目录 {rel(d)}")
    print("重写引用：")
    changed = rewrite_sources(args.dry_run)
    for name, _ in changed:
        print("  ", name)
    print(f"共 {len(changed)} 个文件被改写")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

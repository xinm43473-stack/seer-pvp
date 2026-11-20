# -*- coding: utf-8 -*-
"""打包 dist/seer-peak-pvp.zip，并打印交付校验用的关键文件 md5。

口径与手工交付一致：整包 = 项目根（排除 .workbuddy / dist / __pycache__ / .git），
包内根目录名固定 seer-peak-pvp/。测试副本（_*.html）、临时文件与 .pyc 一律不进包。

用法：
  python scripts/pack_skill.py                # 打包 + testzip + 关键文件 md5
  python scripts/pack_skill.py --dry-run      # 只统计会打进去的文件
"""
from __future__ import annotations

import argparse
import hashlib
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "seer-peak-pvp.zip"
ARC_ROOT = "seer-peak-pvp"
SKIP_DIRS = {".workbuddy", "dist", "__pycache__", ".git", "node_modules", ".cache"}
SKIP_SUFFIX = (".pyc", ".tmp", ".bak")
SKIP_PREFIX = ("_", "~$")      # 测试副本 / Office 临时文件
KEY_FILES = ("references/spirit_synergy_view.html", "scripts/synergy_view_template.html")


def collect() -> list[Path]:
    files: list[Path] = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name.endswith(SKIP_SUFFIX) or name.startswith(SKIP_PREFIX):
                continue
            files.append(Path(base) / name)
    return files


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 Skill 分发包并打印校验信息")
    ap.add_argument("--dry-run", action="store_true", help="只统计文件，不写 zip")
    args = ap.parse_args()

    files = collect()
    print("files", len(files))
    if args.dry_run:
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for i, path in enumerate(files, 1):
            rel = path.relative_to(ROOT).as_posix()
            z.write(path, ARC_ROOT + "/" + rel)
            if i % 5000 == 0:
                print("  %d/%d" % (i, len(files)), flush=True)
    os.replace(tmp, OUT)

    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        print("written", OUT, OUT.stat().st_size)
        print("testzip", bad, "items", len(z.namelist()))
        for rel in KEY_FILES:
            inner = ARC_ROOT + "/" + rel
            same = hashlib.md5(z.read(inner)).hexdigest() == md5(ROOT / rel)
            print("  %-42s %s" % (rel, "md5 OK" if same else "md5 MISMATCH"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

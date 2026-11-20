#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从浏览器 leveldb 里捞回本机改动，注入到前端内联层。

背景（2026-11-19 用户反馈「之前做好的都没了」）：
    页面把编辑存在 localStorage（`seer_peak_view_edits_v3_r2` 等），而 localStorage
    按 origin 隔离。之前用户是双击 HTML（`file://`）打开的，后来改用预览服务
    （`http://127.0.0.1:端口`），于是新页面读不到旧数据——数据没丢，只是换了域。

做法：
    1. 从 Edge / Chrome 的 Local Storage leveldb 里扫描 `seer_peak_view_*` 键；
       leveldb 的 value 可能是 UTF-16LE 或 Latin1，也可能被 snappy 压缩（压缩块跳过）。
    2. 能解析的键导出到 `references/catalog/recovered_local_state.json`。
    3. `--apply` 时把 `edits`（精灵补丁）写进内联 `DATA.editor.persisted`，
       把库添加列表并进 `DATA.library.adds`，这样任何 origin 打开都能看到。

用法:
    python scripts/recover_local_storage.py                 # 只扫描并导出
    python scripts/recover_local_storage.py --apply         # 扫描 + 注入前端
"""

from __future__ import annotations

import argparse
import json
import io
import os
import shutil
from pathlib import Path

import viewdata

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "references" / "spirit_synergy_view.html"
OUT = ROOT / "references" / "catalog" / "recovered_local_state.json"
PREFIX = "seer_peak_view_"

BROWSER_DIRS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data/Default/Local Storage/leveldb",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Local Storage/leveldb",
]


def json_at(buf: bytes, start: int):
    """在 start 附近按 UTF-16LE / Latin1 切出 JSON 对象或数组。"""
    for width in (2, 1):
        for skip in range(0, 40):
            i = start + skip
            if width == 2:
                if i + 1 >= len(buf) or buf[i] not in (0x7b, 0x5b) or buf[i + 1] != 0:
                    continue
            elif buf[i] not in (0x7b, 0x5b):
                continue
            out, depth, instr, esc, j = [], 0, False, False, i
            while j + width <= len(buf):
                ch = chr(buf[j] | (buf[j + 1] << 8)) if width == 2 else chr(buf[j])
                j += width
                out.append(ch)
                if instr:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        instr = False
                else:
                    if ch == '"':
                        instr = True
                    elif ch in "{[":
                        depth += 1
                    elif ch in "}]":
                        depth -= 1
                        if depth == 0:
                            break
            try:
                return json.loads("".join(out))
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def scan(leveldb: Path) -> dict[str, tuple[int, object]]:
    """扫一个 leveldb 目录，返回 {key: (文件时间戳, 值)}（后者覆盖前者）。"""
    found: dict[str, tuple[int, object]] = {}
    if not leveldb.exists():
        return found
    for path in sorted(leveldb.glob("*")):
        if path.suffix not in (".log", ".ldb"):
            continue
        try:
            buf = path.read_bytes()
        except OSError:
            continue
        mtime = int(path.stat().st_mtime)
        pos = 0
        while True:
            i = buf.find(PREFIX.encode(), pos)
            if i < 0:
                break
            pos = i + 1
            end = i
            while end < len(buf) and 32 <= buf[end] < 127:
                end += 1
            key = buf[i:end].decode("ascii", "ignore")
            val = json_at(buf, end)
            if val is None:
                continue
            # 同一个键会在 log / ldb 里出现多份（历史值），取序列化后最长的那个：
            # 编辑补丁是「整份覆盖」，最长即最全；按时间戳取容易拿到压缩块残片。
            prev = found.get(key)
            if prev is None or len(json.dumps(val, ensure_ascii=False)) > \
                    len(json.dumps(prev[1], ensure_ascii=False)):
                found[key] = (mtime, val)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leveldb", default=None, help="指定 leveldb 目录（默认扫 Edge/Chrome）")
    ap.add_argument("--apply", action="store_true", help="注入前端内联层")
    args = ap.parse_args()

    dirs = [Path(args.leveldb)] if args.leveldb else [d for d in BROWSER_DIRS if d.exists()]
    state: dict[str, object] = {}
    for d in dirs:
        got = scan(d)
        if got:
            print(f"{d}\n  解析到 {len(got)} 个键")
            for k in sorted(got):
                v = got[k][1]
                print(f"    {k:44} {type(v).__name__:5} {len(v) if hasattr(v, '__len__') else ''}")
            state.update({k: v for k, (_, v) in got.items()})

    if not state:
        print("没有扫到可解析的键（可能 leveldb 里是压缩块，或浏览器不是 Edge/Chrome）")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("导出 ->", OUT, os.path.getsize(OUT), "bytes")

    if not args.apply:
        return 0

    # edits：取最全的那份（键名以 edits_v3 结尾且不是子键）
    edits = None
    for k, v in state.items():
        if isinstance(v, dict) and k in ("seer_peak_view_edits_v3_r2", "seer_peak_view_edits_v3"):
            if edits is None or len(v) > len(edits):
                edits = v
    adds: list[int] = []
    for k, v in state.items():
        if isinstance(v, list) and k.endswith("library"):
            adds += [int(x) for x in v if isinstance(x, (int, float)) or str(x).isdigit()]
    adds = list(dict.fromkeys(int(x) for x in adds))

    if not edits and not adds:
        print("没有可注入的 edits / library，跳过")
        return 1

    shutil.copyfile(HTML, HTML.with_suffix(".html.bak"))
    payload = viewdata.read(HTML)

    editor = payload.setdefault("editor", {})
    persisted = editor.setdefault("persisted", {})
    added = 0
    for sid, patch in (edits or {}).items():
        if not isinstance(patch, dict):
            continue
        persisted[str(sid)] = patch
        added += 1
    lib = payload.setdefault("library", {})
    before = len(lib.get("adds") or [])
    lib["adds"] = list(dict.fromkeys([*(lib.get("adds") or []), *adds]))

    viewdata.save_payload(HTML, payload)
    print(f"注入完成：persisted +{added} 只，library.adds {before} -> {len(lib['adds'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

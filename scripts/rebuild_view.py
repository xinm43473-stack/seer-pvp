# -*- coding: utf-8 -*-
"""用最新模板 + 现有内联 DATA 重建单文件前端，并把 soul_tags 扩到全库。

这是「只改样式/逻辑」时的唯一正确入口：
- 现有 HTML 的 DATA 里是用户定制过的 218 只 / 21 体系 / 10 档评级，不能走 build_synergy_view.py。
- 模板与 HTML 同源（只差 DATA 行与行尾），所以「新模板 + 旧 DATA」可安全产出新 HTML。
- soul_tags：保留 nodes 的 media 主魂印标签，其余库精灵用 spirit_library 的魂印 id 反查补齐。

用法：python scripts/rebuild_view.py [--backup-dir DIR]
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import systems_store
import viewdata

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "references" / "spirit_synergy_view.html"
TPL = ROOT / "scripts" / "synergy_view_template.html"
LIB = ROOT / "data" / "derived" / "spirit_library.json"
SCHEMA = ROOT / "references" / "catalog" / "editor_schema.json"
TAG_RAW = ROOT / "data" / "seerapi_media" / "raw" / "soulmark_tag"
MARK_RAW = ROOT / "data" / "seerapi_media" / "raw" / "soulmark"
COMBO_RAW = ROOT / "data" / "seerapi_media" / "raw" / "element_type_combination"
SYSDIR = ROOT / "references" / "systems"
ROSTER = ROOT / "references" / "catalog" / "roster.json"


def attr_type_map() -> dict:
    """属性名（去掉分隔符）→ element_type_combination id。

    单属性与双属性都在同一张表里，前端据此用「一枚组合图标」表示双属性，
    不必在两枚小图标之间留缝。
    """
    out: dict[str, int] = {}
    for path in sorted(glob.glob(str(COMBO_RAW / "*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        name, tid = d.get("name"), d.get("id")
        if not name or not isinstance(tid, int):
            continue
        out[re.sub(r"[\s·・/、,，+]+", "", str(name))] = tid
    return out


def sync_editor_schema(payload: dict) -> str:
    """把 editor_schema.json 同步进内联 DATA。

    内联 schema 由历史构建脚本拼装，本脚本只换模板不动 DATA，于是改完
    editor_schema.json 会出现「inlined editor schema differs」。这里同步编辑器真正
    依赖的几块：fields（字段定义）、limits、schema_version、system_edit；
    terms/registries/scope/media_import 由别的来源拼装，保持原样。
    editable 跟着 fields 走，避免再出现「schema 里有字段、editable 里没有」的漂移。
    """
    editor = payload.get("editor")
    if editor is None:
        return "missing"
    inline = editor.get("schema") or {}
    disk = json.loads(SCHEMA.read_text(encoding="utf-8"))
    changed = []
    for key in ("schema_version", "fields", "limits", "system_edit"):
        if key in disk and inline.get(key) != disk[key]:
            inline[key] = disk[key]
            changed.append(key)
    editor["schema"] = inline
    extra = [k for k in (editor.get("editable") or []) if k in ("edge_state", "deletions")]
    editable = [f["key"] for f in (disk.get("fields") or [])] + extra
    dedup = []
    for k in editable:
        if k not in dedup:
            dedup.append(k)
    if editor.get("editable") != dedup:
        editor["editable"] = dedup
        changed.append("editable")
    return "updated(%s)" % ",".join(changed) if changed else "same"


def sync_spirit_profile(payload: dict) -> dict:
    """把 roster.json 的定位与备注注入 nodes。

    nodes 原先只有展示字段，classes/roles/note 从未注入，所以编辑器里定位是空的、
    图鉴也没有定位与备注可显示（2026-11-18 用户反馈）。这里按 id 对齐写入，
    浏览器里的 editors（localStorage 补丁）仍然优先于这里的基线值。
    """
    if not ROSTER.exists():
        return {"filled": 0}
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    by_id = {}
    for row in roster.get("spirits") or []:
        try:
            by_id[int(row["id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    filled = 0
    for node in payload.get("nodes") or []:
        try:
            sid = int(node.get("id"))
        except (TypeError, ValueError):
            continue
        row = by_id.get(sid)
        if not row:
            continue
        classes = [str(x).strip() for x in (row.get("classes") or []) if str(x).strip()]
        roles = [str(x).strip() for x in (row.get("roles") or []) if str(x).strip()]
        note = str(row.get("note") or "").strip()
        if (node.get("classes") or []) != classes or (node.get("roles") or []) != roles \
                or (node.get("note") or "") != note:
            node["classes"] = classes
            node["roles"] = roles
            node["note"] = note
            filled += 1
    return {"filled": filled, "roster": len(by_id)}


SOUL_MARK_RE = re.compile(r"[ \t]*\[sprite[^\]]*\]", re.I)
SOUL_COLOR_RE = re.compile(r"[ \t]*\[/?color[^\]]*\]", re.I)


def strip_soul_versions(payload: dict) -> dict:
    """清掉节点上的魂印版本字段（前端只显示最新一版，2026-11-20 用户口径）。

    曾经这里会补 `soul_prev`／`soul_prev_id`／`advance`，让图鉴出「强化前／强化后」
    开关；开关已删，这三个字段只剩包袱：留着会被误读成「还有一版没显示」。
    `advance_forms.json` 保留在 catalog 里作口径记录（哪 22 只用强化后的魂印／种族值）。
    """
    removed = 0
    for node in payload.get("nodes") or []:
        for key in ("soul_prev", "soul_prev_id", "advance"):
            if key in node:
                node.pop(key, None)
                removed += 1
    return {"stripped": removed}


def clean_soul(text: str) -> str:
    """去掉魂印里的 BWIKI 图标标记（[sprite name=dot1] 之类）。

    这些是分条图标，页面上会原样显示成一段乱码，所以换成换行保留分条结构；
    顺手去掉 [color] 标签、折叠多余空行。幂等，可反复跑。
    """
    s = SOUL_MARK_RE.sub("\n", str(text or ""))
    s = SOUL_COLOR_RE.sub("", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s


def sanitize_soul_markup(payload: dict) -> dict:
    """清洗显示层与资料层的魂印标记，并把结果写回 spirit_library.json。

    nodes（218 只主列表）与 library（1977 只隐藏源）都要清：
    魂印原文来自 BWIKI，带 [sprite name=dotN] 分条图标，前端 pre-wrap 会直接显示。
    """
    def scrub(row: dict) -> int:
        """nodes 里魂印有两套字段：soul（BWIKI 全文）与 soul_mark（SeerAPI 结算文本），都要清。"""
        n = 0
        for key in ("soul", "soul_mark"):
            val = row.get(key)
            if isinstance(val, str) and SOUL_MARK_RE.search(val):
                row[key] = clean_soul(val)
                n += 1
        for mk in row.get("soulmarks") or []:
            if isinstance(mk, dict):
                text = mk.get("text")
                if isinstance(text, str) and SOUL_MARK_RE.search(text):
                    mk["text"] = clean_soul(text)
                    n += 1
        return n

    touched_nodes = 0
    for row in payload.get("nodes") or []:
        touched_nodes += 1 if scrub(row) else 0

    touched_lib = 0
    lib_rows = (payload.get("library") or {}).get("spirits") or []
    for row in lib_rows:
        touched_lib += 1 if scrub(row) else 0

    # 落回数据层，避免下次从 spirit_library.json 重建时又带回来
    if LIB.exists():
        doc = json.loads(LIB.read_text(encoding="utf-8"))
        changed = 0
        for row in (doc.get("spirits") or {}).values():
            soul = row.get("soul")
            if isinstance(soul, str) and SOUL_MARK_RE.search(soul):
                row["soul"] = clean_soul(soul)
                changed += 1
        if changed:
            LIB.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("soul markup: nodes", touched_nodes, "| library", touched_lib,
              "| spirit_library.json", changed)
    return {"nodes": touched_nodes, "library": touched_lib}


def sync_library_skills(payload: dict) -> dict:
    """把 data/derived/spirit_library.json 的技能行同步进内联库。

    build_synergy_view.py 负责整体注入 library 层，但它依赖已删除的 raw 抓取层；
    补抓脚本（fetch_missing_skills.py）改的是 spirit_library.json，若不同步，
    页面里这些精灵的技能表仍是空的（2026-11-18 「无限自由没有技能」即此）。
    只覆盖「库里有非空技能」的条目，空值一律保留内联原样。
    """
    rows = (payload.get("library") or {}).get("spirits") or []
    if not isinstance(rows, list) or not LIB.exists():
        return {"filled": 0, "skipped": 0}
    src = json.loads(LIB.read_text(encoding="utf-8")).get("spirits") or {}
    filled = 0
    for row in rows:
        key = str(row.get("id"))
        fresh = (src.get(key) or {}).get("skills") or []
        if fresh and row.get("skills") != fresh:
            row["skills"] = fresh
            filled += 1
    return {"filled": filled, "skipped": len(rows) - filled}


def soul_tags_by_library(payload: dict) -> dict:
    """全库魂印标签：先按魂印 id → 标签名建表，再用 spirit_library 的魂印反查。"""
    names: dict[int, str] = {}
    for path in sorted(glob.glob(str(TAG_RAW / "*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        if isinstance(d.get("id"), int) and d.get("name"):
            names[d["id"]] = d["name"]

    mark_tags: dict[str, list[str]] = {}
    for path in glob.glob(str(MARK_RAW / "*.json")):
        d = json.load(open(path, encoding="utf-8"))
        ids = sorted({int(x["id"]) for x in (d.get("tag") or [])
                      if isinstance(x, dict) and isinstance(x.get("id"), int)})
        tags = [names[x] for x in ids if x in names]
        if tags:
            mark_tags[str(d.get("id"))] = tags

    lib = json.load(open(LIB, encoding="utf-8"))["spirits"]
    tags = dict(payload.get("soul_tags") or {})
    for sid, row in lib.items():
        if str(sid) in tags:
            continue
        marks = row.get("soulmarks") or []
        for pick in [x for x in marks if x.get("primary")] + marks:
            hit = mark_tags.get(str(pick.get("id")))
            if hit:
                tags[str(sid)] = hit[:8]
                break
    return tags


def sync_systems(payload: dict, only_existing: bool = False) -> dict:
    """把 references/systems/ 的单体系文件同步进内联 DATA。

    全量模式（默认）：DATA.systems 与 references/systems/ 目录严格对齐（项数以目录为准），
    并重算 edges 与统计，否则「体系管理」只看到前端内联的旧快照，比文件夹少。
    只覆盖模式（--only-existing-systems）：保留内联现有条目，仅替换同名内容。
    """
    if not SYSDIR.is_dir():
        return {"systems": 0, "edges": 0, "added": 0, "updated": 0}
    _, systems = systems_store.load_dir(SYSDIR)
    if not systems:
        return {"systems": 0, "edges": 0, "added": 0, "updated": 0}
    by_key = {str(s.get("key")): s for s in systems}
    current = payload.get("systems") or []

    if only_existing:
        updated = 0
        for i, s in enumerate(current):
            hit = by_key.get(str(s.get("key")))
            if hit is not None and hit != s:
                current[i] = hit
                updated += 1
        return {"systems": len(current), "edges": len(payload.get("edges") or []),
                "added": 0, "updated": updated}

    # 前端原有顺序在前（用户口径），其余按 index.json 顺序补在后面
    ordered, seen = [], set()
    for s in current:
        key = str(s.get("key"))
        if key in by_key and key not in seen:
            ordered.append(by_key[key])
            seen.add(key)
    added = 0
    for s in systems:
        key = str(s.get("key"))
        if key not in seen:
            ordered.append(s)
            seen.add(key)
            added += 1
    updated = sum(1 for s in current if str(s.get("key")) in by_key and by_key[str(s.get("key"))] != s)
    payload["systems"] = ordered

    # 显式边清单跟着体系走（前端「关系联动编辑」以它为基线）
    edges = []
    for s in ordered:
        meta_map = s.get("edge_meta") or {}
        for pair in (s.get("chain_edges") or []):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            a, b = pair
            meta = meta_map.get("%s-%s" % (a, b)) or {}
            edges.append({
                "system_key": str(s.get("key")),
                "system_name": str(s.get("name") or s.get("key")),
                "a": int(a), "b": int(b),
                "type": meta.get("type") or "resource",
                "note": str(meta.get("note") or "").strip(),
                "chain_status": str(s.get("chain_status") or ""),
            })
    payload["edges"] = edges

    stats = payload.setdefault("stats", {})
    stats["systems"] = len(ordered)
    stats["explicit_edges"] = len(edges)
    kinds = {}
    for s in ordered:
        kinds[str(s.get("kind") or "未分类")] = kinds.get(str(s.get("kind") or "未分类"), 0) + 1
    stats["kinds"] = kinds
    # 资料层与归档计数跟着内联数据走：media 只在删精灵/改体系时变，别让它留在旧值上误导接手人。
    media = payload.get("media") or {}
    mstats = media.get("stats") or {}
    stats["media_spirits"] = len(media.get("spirits") or {})
    if mstats.get("images") is not None:
        stats["media_images"] = mstats["images"]
    if mstats.get("skills") is not None:
        stats["media_skills"] = mstats["skills"]
    leads_path = ROOT / "references" / "catalog" / "historical_leads.json"
    if leads_path.exists():
        try:
            leads = json.loads(leads_path.read_text(encoding="utf-8"))
            stats["archived_leads"] = len(leads.get("items") or [])
        except (OSError, json.JSONDecodeError):
            pass
    chain_path = ROOT / "references" / "catalog" / "chain_audit.json"
    if chain_path.exists():
        try:
            chain = json.loads(chain_path.read_text(encoding="utf-8"))
            stats["verified_pairs"] = len(chain.get("verified_pairs") or [])
            stats["verified_synergies"] = len(chain.get("items") or [])
        except (OSError, json.JSONDecodeError):
            pass
    return {"systems": len(ordered), "edges": len(edges), "added": added, "updated": updated}


def main() -> int:
    ap = argparse.ArgumentParser(description="用模板重建单文件前端（保留内联 DATA）")
    ap.add_argument("--backup-dir", default=None,
                    help="备份目录，默认 dist/backups（带时间戳，保留最近 20 份）")
    ap.add_argument("--no-sync-systems", action="store_true",
                    help="不从 references/systems/ 同步体系（默认会全量同步）")
    ap.add_argument("--only-existing-systems", action="store_true",
                    help="只替换同名体系，不把单文件里多出来的体系补进前端（旧口径）")
    args = ap.parse_args()

    # 2026-11-20：备份改到 dist/backups 并按时间戳命名。
    # 原来写系统临时目录 + 固定文件名：①每次覆盖成「上一次的产物」，回滚根本拿不到旧版；
    # ②temp 会被系统清理（当晚就没了，想要 11-19 的版本已经找不到）。现在每次重建都留一份。
    backup_dir = Path(args.backup_dir or (ROOT / "dist" / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    bak = backup_dir / time.strftime("backup-%Y%m%d-%H%M%S.html")
    shutil.copyfile(HTML, bak)
    keep = sorted(backup_dir.glob("backup-*.html"))[-20:]
    for old_bak in sorted(backup_dir.glob("backup-*.html"))[:-20]:
        old_bak.unlink(missing_ok=True)
    print("backup ->", bak, "| 保留", len(keep), "份")

    payload = viewdata.read(HTML)
    print("nodes", len(payload.get("nodes", [])), "systems", len(payload.get("systems", [])))
    if args.no_sync_systems:
        print("systems sync: skipped")
    else:
        info = sync_systems(payload, only_existing=args.only_existing_systems)
        print("systems sync:", info["systems"], "systems /", info["edges"], "edges",
              "| 新增", info["added"], "更新", info["updated"], "| from", SYSDIR.name + "/")

    # 2026-11-18：顶部「精选拉取」改为「备注」开关，前端不再读这个字段；
    # 数据层 references/catalog/pull_selection.json 保留，将来要恢复功能再挂回按钮。
    payload.pop("pull_selection", None)
    print("editor schema sync:", sync_editor_schema(payload))
    print("spirit profile sync:", sync_spirit_profile(payload))
    print("library skills sync:", sync_library_skills(payload))
    sanitize_soul_markup(payload)
    print("soul versions:", strip_soul_versions(payload))
    payload["build"] = time.strftime("%Y-%m-%d %H:%M")   # 页头显示，便于确认看到的是哪一版

    before = len(payload.get("soul_tags") or {})
    payload["soul_tags"] = soul_tags_by_library(payload)
    # 2026-11-15：data/seerapi_media/raw（160MB 原始抓取层）已按用户要求删除。
    # attr_types / soul_tags 本来就是内联进前端的成品层，缺 raw 时必须以 payload 为准，
    # 否则重建一次页面会把 139 个属性图标映射清空。raw 存在时仍可增量补全。
    fresh = attr_type_map()
    merged = dict(payload.get("attr_types") or {})
    merged.update(fresh)
    payload["attr_types"] = merged
    print("soul_tags", before, "->", len(payload["soul_tags"]),
          "| attr_types", len(payload["attr_types"]), "(raw 补全", len(fresh), ")")

    tpl = io.open(TPL, encoding="utf-8", newline="").read()
    try:
        out = viewdata.build(tpl, payload)
    except viewdata.ViewDataError as exc:
        raise SystemExit(f"{exc}；拒绝重建")
    viewdata.write(HTML, out)
    print("written", HTML, os.path.getsize(HTML), "chars", len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

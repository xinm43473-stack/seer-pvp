#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild references/catalog/depth_audit.json from the current roster.

A one-line ``play`` is a mechanism index, not a completed tactical chain. This
script audits which deep-dive spirits carry the six required elements in
``spirits[].deep_dive`` and ranks the rest by how often they are referenced by
named systems, so the next research pass starts with the most load-bearing
spirits.

Usage:
  python scripts/build_depth_audit.py
"""
from __future__ import annotations

import collections
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "references" / "catalog" / "depth_audit.json"
FIELDS = ["conditions", "sequence", "resources", "bp_cost",
          "failure_points", "replacement_check"]
PLACEHOLDERS = ["待核", "需读取", "待补", "尚未", "暂无", "待确认",
                "按当季", "补写", "确定与", "不从名称推断", "须读取"]


def load(path: str, fallback):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else fallback


def main() -> int:
    roster = load("references/catalog/roster.json", {"spirits": []})
    systems = load("references/catalog/systems.json", {"systems": []})
    souls = load("data/seerapi/soul_full.json", {"souls": {}}).get("souls", {})
    expansions = load("references/catalog/soul_expansions.json", {"entries": []}).get("entries", [])
    spirits = roster.get("spirits", [])

    refs: collections.Counter = collections.Counter()
    for system in systems.get("systems", []):
        for field in ("core", "support", "counter"):
            for sid in system.get(field, []):
                refs[sid] += 1

    full = [e for e in spirits
            if e.get("deep_dive") and all(e["deep_dive"].get(k) for k in FIELDS)]
    full_ids = {e["id"] for e in full}

    queue = []
    for e in spirits:
        if e["id"] in full_ids:
            continue
        play = e.get("play", "")
        n = refs[e["id"]]
        queue.append({
            "id": e["id"],
            "name": e["name"],
            "system_refs": n,
            "play_len": len(play),
            "placeholder": any(k in play for k in PLACEHOLDERS),
            "soul_full_len": len(souls.get(str(e["id"]), {}).get("text", "")),
            "priority": "high" if n >= 3 else ("medium" if n >= 1 else "normal"),
        })
    queue.sort(key=lambda x: (-x["system_refs"], -x["play_len"], x["id"]))

    expanded_ids = {x["id"] for x in expansions}
    short = [{"id": e["id"], "name": e["name"],
              "len": len(souls.get(str(e["id"]), {}).get("text", "")),
              "expanded": e["id"] in expanded_ids}
             for e in spirits
             if len(souls.get(str(e["id"]), {}).get("text", "")) < 180]

    doc = {
        "generated_at": date.today().isoformat(),
        "purpose": "审计 roster.json 深研层逐只战术链的研究深度；一句话 play 只作机制索引，不算完整操作链。",
        "required_fields": FIELDS,
        "field_meanings": {
            "conditions": "成立条件", "sequence": "逐回合顺序",
            "resources": "PP／血线／背包位／阵亡顺序等资源",
            "bp_cost": "BP 成本", "failure_points": "失效点",
            "replacement_check": "上位替代结论（无上位／有上位但独立价值／有上位则排除）",
        },
        "total_spirits": len(spirits),
        "full_chain_count": len(full),
        "full_chain_ids": sorted(full_ids),
        "full_chain_names": [e["name"] for e in full],
        "pending_count": len(queue),
        "priority_counts": dict(collections.Counter(x["priority"] for x in queue)),
        "queue": queue,
        "short_soul_text": {
            "count": len(short),
            "note": "短文本不等于抓取截断：如 3033 帝天战佛 52 字已是完整魂印；只有引用了未展开状态名的条目才按 soul_expansions.json 方法追技能页。",
            "ids": short,
        },
        "soul_expansion_ids": sorted(expanded_ids),
        "policy": "按 system_refs 降序逐只补写；改动 roster.json 的 spirits 或 deep_dive 后必须重跑本脚本，再跑 check_roster.py。不得为了凑数量把机制推演写成当月强度。",
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"depth audit: {len(full)}/{len(spirits)} full chains, {len(queue)} queued "
          f"(high={doc['priority_counts'].get('high', 0)}), {len(short)} short soul texts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

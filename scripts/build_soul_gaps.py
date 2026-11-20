#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit auto-dropped spirits against complete BWIKI soul text.

The auto catalog was built from a truncated soul-text dump. This script finds
dropped spirits whose complete soul text contradicts the recorded drop reason
(no soul / single clause / low stats) and writes a review queue. Items in the
queue are NOT promoted automatically: they still need per-spirit research.

Usage: python scripts/build_soul_gaps.py
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = ROOT / "references" / "catalog" / "soul_text_gaps.json"

spec = importlib.util.spec_from_file_location("bd", HERE / "build_dataset.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)


def main() -> int:
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    souls = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))["souls"]
    roster = json.loads((ROOT / "references" / "catalog" / "roster.json").read_text(encoding="utf-8"))
    active = {x["id"] for x in roster["spirits"]}
    pending = {x["id"] for x in roster["pending_research"] if x.get("id")}
    overrides = {x["id"] for x in json.loads((REF / "catalog" / "manual_overrides.json").read_text(encoding="utf-8"))["spirits"]}

    items = []
    for row in pool["dropped"]:
        eid, name, reason = row.get("id"), row.get("name", ""), row.get("reason", "")
        entry = souls.get(str(eid), {})
        text = entry.get("text", "")
        full_len, raw_len = len(text), entry.get("raw_len", 0)
        clauses = bd.clauses(text)
        tags = bd.tag_effect(text)
        core = sorted(set(tags) & bd.CORE_TAGS)
        category = ""
        if reason == "无魂印" and text:
            category = "无魂印判定存疑（BWIKI 检出魂印）"
        elif "单条魂印" in reason and (len(clauses) >= 2 or core or full_len >= 150):
            category = "旧自动理由作废：魂印全文多段/含核心机制"
        elif "种族值过低" in reason and full_len >= 300 and len(core) >= 2:
            category = "旧自动理由作废：低种族但魂印机制丰富"
        elif text:
            category = "形态规则剔除（魂印全文已备查）"
        if not category:
            continue
        items.append({
            "id": eid, "name": name, "drop_reason": reason, "category": category,
            "soul_full_len": full_len, "soul_raw_len": raw_len,
            "clauses": len(clauses), "core_tags": core,
            "soul_head": text[:120].replace("\n", " "),
            "status": "已人工回捞" if eid in overrides or eid in active else
                      ("候选池" if eid in pending else "待深研"),
            "review": "需核月榜、上位替代与实战价值后才可晋升 spirits；不得直接推荐",
        })

    suspect = [x for x in items if x["category"] != "形态规则剔除（魂印全文已备查）"]
    suspect.sort(key=lambda x: (-x["soul_full_len"], x["id"]))
    items.sort(key=lambda x: (x["category"], -x["soul_full_len"]))
    with_soul = sum(1 for row in pool["dropped"] if souls.get(str(row.get("id")), {}).get("text"))
    no_soul_mismatch = sum(1 for x in suspect if x["category"].startswith("无魂印"))
    doc = {
        "generated_at": date.today().isoformat(),
        "source": "data/bwiki/pool.json dropped + data/seerapi/soul_full.json（BWIKI 魂印全文）",
        "criteria": "F20261104：旧「单条魂印／种族值过低」自动剔除理由已作废，不再作为判断条件；本队列按 BWIKI 魂印全文与两位 UP 主作品覆盖重新排序复核。一代精灵王/上位合并属形态规则，只备查不自动翻案",
        "dropped_total": len(pool["dropped"]),
        "dropped_with_soul_text": with_soul,
        "queue_total": len(items),
        "suspect_total": len(suspect),
        "no_soul_mismatch": no_soul_mismatch,
        "policy": "此队列是重新评估优先级，不是新推荐名单；是否重点深研以两位 UP 主是否出过配置/攻略作品为准，逐只深研后通过者才写入 spirits",
        "suspects": suspect,
        "all_items": items,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"dropped={len(pool['dropped'])}, with BWIKI soul={with_soul}, "
          f"queue={len(items)}, suspect={len(suspect)}, no-soul mismatch={no_soul_mismatch}")
    for x in suspect[:12]:
        print(f"  {x['id']} {x['name']} | {x['category']} | 魂印 {x['soul_full_len']} 字 "
              f"| 原因 {x['drop_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

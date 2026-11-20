#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh every derived layer after spirits are promoted or soul text changes.

Typical order after editing ``references/catalog/roster.json``:
  python scripts/sync_derived.py
  python scripts/build_overrides.py
  python scripts/check_roster.py

It rebuilds the false-drop review queue, the T0-T2 deep-dive gap queue,
creator coverage, catalog statistics, and the manual-override ID list. Newly
found false-drop suspects are enqueued in ``pending_research`` (never directly
into ``spirits``).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
REF = ROOT / "references"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_roster(roster):
    # 2026-11-08 全量审计：统一为标准 json.dumps(indent=2)，与 apply_core_roles.py /
    # apply_link_cleanup.py 一致。旧版自定义紧凑格式会让 roster.json 在两种格式间
    # 来回抖动（每次重跑产生 5000+ 行无意义 diff）。
    (REF / "catalog" / "roster.json").write_text(
        json.dumps(roster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    gaps = load_module("bsg", "build_soul_gaps.py")
    gaps.main()  # rebuild false-drop review queue from complete soul text
    gap_doc = json.loads((REF / "catalog" / "soul_text_gaps.json").read_text(encoding="utf-8"))
    soul_doc = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    roster = json.loads((REF / "catalog" / "roster.json").read_text(encoding="utf-8"))

    active = {x["id"] for x in roster["spirits"]}
    pending = {x["id"] for x in roster["pending_research"] if x.get("id")}
    excluded_ids = {x["id"] for x in roster["excluded_examples"]}
    elf_ids = {x["id"] for x in pool["elves"]}
    dropped_ids = {x["id"] for x in pool["dropped"]
                   if isinstance(x, dict) and isinstance(x.get("id"), int)}
    all_catalog_ids = elf_ids | dropped_ids
    id_range = roster["catalog"].get("id_range", [2987, 4950])
    # Keep catalog counts in sync if build_dataset.py rebuilt the pool under
    # the F20261104 rules (no stat-total / soul-clause drops).
    roster["catalog"]["available_count"] = len(pool["elves"])
    roster["catalog"]["dropped_count"] = len(pool["dropped"])
    roster["catalog"]["covered_ids"] = len(all_catalog_ids)
    roster["catalog"]["jump_ids"] = sorted(set(range(id_range[0], id_range[1] + 1)) - all_catalog_ids)

    # 1. Manual overrides = every deep-dive spirit the auto filter had dropped.
    manual_only = sorted(active - elf_ids)
    roster["catalog"]["manual_only_ids"] = manual_only
    roster["catalog"]["manual_override_count"] = len(manual_only)

    # 2. T0-T2 spirits that still lack a hand-written tactic chain.
    high = [e for e in pool["elves"] if e.get("tier") in ("T0", "T1", "T2")]
    missing = [e for e in high if e["id"] not in active and e["id"] not in excluded_ids]
    missing.sort(key=lambda e: ("T0T1T2T3T4".index(e["tier"][1]), -e.get("score", 0)))
    tier_doc = {
        "generated_at": gap_doc.get("generated_at", ""),
        "source": "data/bwiki/pool.json 自动评分（本地机制完整度，非社区月榜）",
        "criteria": "pool.tier 属 T0/T1/T2 且未写入 roster.json 的 spirits（未写逐回合战术链）",
        "t0_t2_total": len(high),
        "missing_deep_dive": len(missing),
        "policy": "此队列用于排深研优先级，不表示这些精灵强度不足，也不表示可直接推荐；结论仍以当月竞技图鉴与魂印原文为准。",
        "items": [{"id": e["id"], "name": e["name"], "attr": e["attr"], "tier": e["tier"],
                   "score": e.get("score"), "tags": e.get("tags", [])[:6],
                   "in_pending_research": e["id"] in pending,
                   "soul_clauses": len(e.get("clauses", []))} for e in missing],
    }
    (REF / "catalog" / "tier_gaps.json").write_text(json.dumps(tier_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    roster["catalog"]["high_tier_total"] = len(high)
    roster["catalog"]["high_tier_missing_deep_dive"] = len(missing)

    # 3. Creator coverage after promotions.
    themed = roster.get("creator_coverage", {}).get("themed_spirit_ids", [])
    roster.setdefault("creator_coverage", {})["in_spirits"] = sorted(set(themed) & active)
    roster["creator_coverage"]["in_pending_research"] = sorted(set(themed) & pending)

    # 4. Newly found false-drop suspects must enter the candidate pool first.
    added = []
    first_kings = set(roster.get("review_rules", {}).get("first_gen_kings_excluded_names", []))
    creator_idx = json.loads((REF / "catalog" / "creator_index.json").read_text(encoding="utf-8"))
    themed_ids = {x["id"] for x in creator_idx["themed_spirits"]}
    for item in gap_doc["suspects"]:
        if item["id"] in active or item["id"] in pending:
            continue
        if item["id"] in excluded_ids:  # 用户人工审核删除的过弱精灵不回灌
            continue
        if item.get("name") in first_kings:  # 除自然王外不录入一代王基础形态
            continue
        if item["id"] not in themed_ids:  # 标题提及不作依据，只认配置/攻略专题
            continue
        roster["pending_research"].append({
            "id": item["id"], "name": item["name"], "attr": "待核",
            "priority": "normal", "source": "C20261104",
            "note": f"BWIKI 魂印全文 {item['soul_full_len']} 字/{item['clauses']} 段，与自动剔除原因"
                    f"「{item['drop_reason']}」冲突；按「先入列表、后深研」重新评估，需核月榜、"
                    "上位替代与实战价值，不直接推荐",
        })
        pending.add(item["id"])
        added.append(item["id"])

    # 5. Soul-text statistics.
    souls = soul_doc["souls"]
    with_text = sum(1 for v in souls.values() if v.get("text"))
    expanded = sum(1 for v in souls.values()
                   if v.get("text") and v.get("full_len", 0) > v.get("raw_len", 0) * 1.3 + 30)
    roster["catalog"]["soul_full"] = {
        "file": "data/seerapi/soul_full.json", "id_count": len(souls), "with_text": with_text,
        "expanded_vs_raw": expanded, "suspect_review": gap_doc["suspect_total"],
        "dropped_with_soul_text": gap_doc["dropped_with_soul_text"],
    }
    write_roster(roster)

    gaps.main()  # refresh status labels now that new candidates are recorded
    print(f"sync: spirits={len(active)}, pending={len(roster['pending_research'])}, "
          f"manual_overrides={len(manual_only)}, T0-T2 gap={len(missing)}/{len(high)}, "
          f"ids={len(souls)}, with_text={with_text}, expanded={expanded}, "
          f"suspects={gap_doc['suspect_total']}, new_pending={len(added)}")
    if added:
        print("new ids:", added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild ``references/catalog/manual_overrides.json``.

The auto-built ``data/bwiki/pool.json`` drops some spirits whose value only becomes
clear after manual research (low stat total, single-clause soul, special ID).
This script restores those spirits from the raw BWIKI dumps and attaches the
hand-written tactic from ``references/catalog/roster.json`` so ``query.py`` can find
them. Re-run it after ``build_dataset.py`` refreshes the auto catalog.

Usage: python scripts/build_overrides.py
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"

spec = importlib.util.spec_from_file_location("bd", HERE / "build_dataset.py")
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)  # build_dataset has a __main__ guard, so this is safe


def main():
    guard_legacy(__file__)
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    roster = json.loads((ROOT / "references" / "catalog" / "roster.json").read_text(encoding="utf-8"))
    raw_elves = {x["id"]: x for x in json.loads((DATA / "bwiki" / "elves.json").read_text(encoding="utf-8"))}
    raw_souls = json.loads((DATA / "bwiki" / "souls.json").read_text(encoding="utf-8"))
    soul_full_path = DATA / "seerapi/soul_full.json"
    soul_full = json.loads(soul_full_path.read_text(encoding="utf-8")).get("souls", {}) if soul_full_path.exists() else {}
    dropped = {x["id"]: x for x in pool["dropped"] if isinstance(x, dict) and isinstance(x.get("id"), int)}
    deep = {x["id"]: x for x in roster["spirits"]}
    elf_ids = {x["id"] for x in pool["elves"]}

    manual_ids = sorted(set(roster["catalog"]["manual_only_ids"]) | (set(deep) - elf_ids))
    out = []
    for sid in manual_ids:
        spirit = deep.get(sid, {})
        base = raw_elves.get(sid, {})
        souls = [s for s in raw_souls if sid in s.get("elves", [])]
        soul = max(souls, key=lambda s: s.get("sid", 0)) if souls else {}
        full_entry = soul_full.get(str(sid), {})
        effect = str(full_entry.get("text") or soul.get("effect", "")).strip()
        soul_source = "BWIKI 魂印全文" if full_entry.get("text") else "raw/souls.json（可能截断，待 fetch_souls_full.py 补齐）"
        stats = base.get("stats") or {k: 0 for k in ("体力", "攻击", "防御", "特攻", "特防", "速度")}
        tags = bd.tag_effect(effect) + ["人工深研回捞"]
        out.append({
            "id": sid,
            "name": spirit.get("name") or base.get("name") or dropped.get(sid, {}).get("name") or f"#{sid}",
            "attr": spirit.get("attr") or base.get("attr") or "未核",
            "total": base.get("total", 0),
            "stats": stats,
            "intro": base.get("intro", ""),
            "series": base.get("series", ""),
            "skill_ids": base.get("skills", ""),
            "soul": effect,
            "soul_source": soul_source,
            "soul_id": soul.get("sid") or full_entry.get("sid"),
            "clauses": bd.clauses(effect),
            "tags": tags,
            "score": 0.0,
            "auto_tier": "不适用",
            "tier": "T3",  # sort-compatible placeholder; never shown as a rating
            "tier_display": "人工深研层（自动评分不适用）",
            "meta": False,
            "beats": [],
            "weak_to": [],
            "manual_override": True,
            "override_reason": dropped.get(sid, {}).get("reason", "超出 2987–4950 自动快照或原始数据缺失"),
            "deep_dive": {
                "status": spirit.get("status"),
                "roles": spirit.get("roles", []),
                "mechanics": spirit.get("mechanics", []),
                "play": spirit.get("play", ""),
                "synergies": spirit.get("synergies", []),
                "sources": spirit.get("sources", []),
            },
        })

    doc = {
        "generated_at": "2026-11-04",
        "policy": "人工深研结论优先于自动筛选；这些精灵虽在 pool.dropped，仍必须能被 query.py 查到魂印与战术",
        "source": "data/bwiki/elves.json + data/bwiki/souls.json + references/catalog/roster.json",
        "rebuild": "python scripts/build_overrides.py（在 build_dataset.py 刷新全量图鉴后重跑）",
        "count": len(out),
        "spirits": out,
    }
    (REF / "catalog" / "manual_overrides.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manual overrides: {len(out)} spirits; soul text present: "
          f"{sum(1 for x in out if x['soul'])}/{len(out)}")
    for x in out:
        print(f"  {x['id']} {x['name']} | clauses={len(x['clauses'])} | {x['override_reason']}")


if __name__ == "__main__":
    main()

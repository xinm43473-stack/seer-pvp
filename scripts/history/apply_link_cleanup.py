#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keep only explicit, mutually declared chain edges as relationship claims.

2026-11-05 user correction: "不能关联别瞎关联，没关联就没关联直接说就行".
Previously this script moved unverified declarations into ``leads`` and the
front end still rendered those 349 declarations as "关联线索" cards. That is
still a made-up relationship. Now:

  * every declaration must be mutual AND sit on an explicit chain edge;
  * all other declarations are archived to references/catalog/historical_leads.json
    as pure history (never queried, never rendered, never recommended);
  * ``roster.spirits[].leads`` becomes empty everywhere.

The rewrite preserves roster.json's one-object-per-line layout and is
idempotent. Run after build_chain_audit.py, then re-run the chain audit.

Usage: python scripts/apply_link_cleanup.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "references"
ROSTER = REF / "catalog" / "roster.json"
CHAIN = REF / "catalog" / "chain_audit.json"
ARCHIVE = REF / "catalog" / "historical_leads.json"


def main() -> int:
    chain = json.loads(CHAIN.read_text(encoding="utf-8"))
    verified = {tuple(x) for x in chain.get("verified_pairs", [])}
    # 2026-11-06: roster.json is now a normal indented JSON document (the old
    # one-object-per-line layout broke as soon as a nested field was edited).
    doc = json.loads(ROSTER.read_text(encoding="utf-8"))
    objects = {obj["id"]: obj for obj in doc["spirits"]}

    claims = {sid: set(obj.get("synergies", [])) | set(obj.get("leads", []))
              for sid, obj in objects.items()}
    # Explicit chain edges are authoritative: write them back reciprocally so
    # the deep-dive layer matches systems.json exactly.
    keep = set(verified)
    for sid in claims:
        claims[sid] |= {b for (a, b) in keep if a == sid}
    names = {sid: obj["name"] for sid, obj in objects.items()}

    archived = []
    before_syn = sum(len(o.get("synergies", [])) for o in objects.values())
    before_leads = sum(len(o.get("leads", [])) for o in objects.values())
    for sid, obj in objects.items():
        old_leads = set(obj.get("leads", []))
        for other in sorted(claims[sid] - {b for b in claims[sid] if (sid, b) in keep}):
            archived.append({
                "a": sid,
                "b": other,
                "a_name": names.get(sid, str(sid)),
                "b_name": names.get(other, str(other)),
                "origin": "leads" if other in old_leads else "synergies",
                "reason": ("历史声明未落在 systems.json 的显式 chain_edges 上，或缺少双向互证；"
                           "不是同队配合，只是同一骨架／备选位或旧版单向声明"),
            })
        obj["synergies"] = sorted(b for b in claims[sid] if (sid, b) in keep)
        obj["leads"] = []

    # Merge with the existing archive so repeated runs stay idempotent and
    # never erase the history that was moved out on the first run.
    existing = []
    if ARCHIVE.exists():
        try:
            existing = json.loads(ARCHIVE.read_text(encoding="utf-8")).get("items", [])
        except json.JSONDecodeError:
            existing = []
    merged = {(x["a"], x["b"], x.get("origin")): x for x in existing}
    for x in archived:
        merged[(x["a"], x["b"], x.get("origin"))] = x
    archived_all = sorted(merged.values(), key=lambda x: (x["a"], x["b"]))
    archive_doc = {
        "schema_version": "1.0",
        "generated_at": date.today().isoformat(),
        "purpose": "2026-11-05 起移出关联层的历史声明留痕。只说明「以前写过什么」，不构成任何关联、线索或推荐依据。",
        "policy": "查询、配合前端、体系注册表与推荐一律不读取本文件。没有显式 chain_edges 的精灵对直接写「暂无已核实关联」。",
        "stats": {
            "archived_claims": len(archived_all),
            "archived_pairs": len({(x["a"], x["b"]) for x in archived_all}),
            "verified_claims_kept": sum(len(o["synergies"]) for o in objects.values()),
        },
        "items": archived_all,
    }
    ARCHIVE.write_text(json.dumps(archive_doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")

    doc["spirits"] = [objects[x["id"]] for x in doc["spirits"]]
    ROSTER.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    after = sum(len(o["synergies"]) for o in objects.values())
    print("strict link cleanup: %d synergies + %d leads -> %d verified claims" %
          (before_syn, before_leads, after))
    print("  archived %d history declarations to %s" % (len(archived), ARCHIVE.name))
    print("  explicit chain edges used:", len(verified) // 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

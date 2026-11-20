#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply the creator-work based inclusion standard.

The old auto filter dropped spirits for "single-clause soul" or "low stat
total". Both reasons are void: the raw soul dump truncated multi-clause effects,
and stat totals do not decide PvP value. Inclusion is now decided by whether
蝶夏Channel / 不要脸的狗子 published a configuration or guide work for the
spirit (see ``references/catalog/creator_index.json``).

This script:
  1. writes ``references/catalog/voided_drops.json`` as a queryable audit queue;
  2. enqueues previously unlisted spirits that have creator work leads;
  3. records the new standard in roster.json and creator_index.json.

Usage: python scripts/apply_creator_filter.py
"""
from __future__ import annotations
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402

import json
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
REF = ROOT / "references"

VOID_PREFIXES = ("单条魂印", "种族值过低")
SOURCE = "F20261104"


def write_roster(roster):
    # 2026-11-08 全量审计：统一为标准 json.dumps(indent=2)，与 apply_core_roles.py /
    # apply_link_cleanup.py 一致。旧版自定义紧凑格式会让 roster.json 在两种格式间
    # 来回抖动（每次重跑产生 5000+ 行无意义 diff）。
    (REF / "catalog" / "roster.json").write_text(
        json.dumps(roster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    guard_legacy(__file__)
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    roster = json.loads((REF / "catalog" / "roster.json").read_text(encoding="utf-8"))
    idx = json.loads((REF / "catalog" / "creator_index.json").read_text(encoding="utf-8"))

    active = {x["id"] for x in roster["spirits"]}
    pending = {x["id"] for x in roster["pending_research"] if x.get("id")}
    excluded = {x["id"] for x in roster["excluded_examples"]}
    themed = {x["id"]: x for x in idx["themed_spirits"]}

    voided = [x for x in pool["dropped"] if str(x.get("reason", "")).startswith(VOID_PREFIXES)]
    items = []
    for row in voided:
        sid = row["id"]
        if sid in active:
            state = "spirits"
        elif sid in pending:
            state = "pending_research"
        elif sid in excluded:
            state = "excluded_examples"
        else:
            state = "unlisted"
        if sid in themed:
            coverage, work = "配置/攻略专题", themed[sid].get("example_work", "")
        else:
            coverage, work = "未查到配置/攻略作品覆盖", ""
        items.append({"id": sid, "name": row["name"], "void_reason": row["reason"],
                      "state": state, "creator_coverage": coverage, "example_work": work})

    doc = {
        "generated_at": date.today().isoformat(),
        "policy": "「单条魂印」与「种族值过低」两类自动剔除理由作废；是否录入以两位 UP 主是否出过配置/攻略作品为准。此队列保证旧理由不再把精灵挡在可查列表之外，不等于推荐。",
        "standard_source": "references/catalog/creator_index.json",
        "total": len(items),
        "by_reason": dict(Counter("单条魂印且无核心机制" if x["void_reason"].startswith("单条魂印")
                                  else "种族值过低" for x in items)),
        "by_state": dict(Counter(x["state"] for x in items)),
        "by_coverage": dict(Counter(x["creator_coverage"] for x in items)),
        "next_action": "配置/攻略专题覆盖者必须落在 spirits 或 pending_research；作品提及者按新标准入候选池待核；未查到覆盖者保留可查记录，发现作品后立即入池。",
        "items": items,
    }
    (REF / "catalog" / "voided_drops.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # New standard brings creator-covered spirits into the candidate pool first.
    added = []
    for item in items:
        if item["state"] != "unlisted" or item["creator_coverage"] != "配置/攻略专题":
            continue
        roster["pending_research"].append({
            "id": item["id"], "name": item["name"], "attr": "待核",
            "priority": "high" if item["creator_coverage"] == "配置/攻略专题" else "normal",
            "source": SOURCE,
            "note": "旧自动剔除理由「%s」已作废；按新口径「两位 UP 主是否出过配置/攻略作品」重新入列表，线索《%s》。需确认是否为配置/攻略视频并核魂印全文、月榜与上位替代，不直接推荐" %
                    (item["void_reason"], item["example_work"][:40]),
        })
        item["state"] = "pending_research"
        added.append(item["id"])
    doc["by_state"] = dict(Counter(x["state"] for x in items))
    doc["newly_enqueued"] = added
    (REF / "catalog" / "voided_drops.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    roster["filter_policy"] = {
        "effective": date.today().isoformat(),
        "standard": "两位 UP 主（蝶夏Channel UID 59224295、不要脸的狗子 UID 287935100）是否出过配置/攻略视频或专题作品，是精灵是否录入与是否进入深研队列的唯一标准",
        "voided_rules": ["单条魂印且无核心机制", "种族值过低"],
        "voided_reason": "早期 raw/souls.json 把多段魂印截成一句，单条/多条不可判定；种族值也不等于 PvP 价值",
        "still_checked_at_deep_dive": ["无魂印须按 BWIKI 魂印全文复核，不沿用自动结论", "一代精灵王与明显上位替代只在深研层判断形态，不作为录入阶段删除依据"],
        "coverage_source": "references/catalog/creator_index.json 的 themed_spirits（配置/攻略专题）为唯一依据；标题提及层已删除，狗子视频清单缺口见 gaps",
        "history": "data/bwiki/pool.json 的 dropped 仅作历史留痕；两类作废理由对应精灵见 references/catalog/voided_drops.json",
        "entry_rule": "先入 pending_research 与 references/docs/candidates.md，逐只深研后才晋升 spirits；录入 ≠ 推荐",
    }

    idx["policy"] = ("两位 UP 主是否出过配置/攻略视频或专题作品，是精灵录入与进入深研队列的唯一标准；"
                     "不以魂印条数（抓取会截断）、种族值或自动评分作为判断条件。录入仅代表进入可查列表，不等于可直接推荐。")
    idx["filter_standard"] = {
        "effective": date.today().isoformat(),
        "primary": "蝶夏Channel 97 篇精灵专题专栏（培养方案／配置分享／解析／觉醒契约特训篇等）",
        "secondary": "标题提及层（周测评／返场／皮肤／剧情／同人向）2026-11-04 已整体删除，不作录入依据",
        "gou": "不要脸的狗子 UID 287935100 的解析／实战／配置视频；711 个视频标题被 B 站风控拦截，当前仅 6 条可核验线索，缺口见 gaps",
        "voided_auto_rules": ["单条魂印且无核心机制", "种族值过低"],
        "audit_queue": "references/catalog/voided_drops.json",
    }
    (REF / "catalog" / "creator_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_roster(roster)
    print(f"voided drops: {len(items)}; by_state={doc['by_state']}; "
          f"by_coverage={doc['by_coverage']}; newly_enqueued={len(added)}; "
          f"pending_total={len(roster['pending_research'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full re-audit of every active spirit's strength evidence and every link.

This is the 2026-11-05 second pass requested after the 3056 (机盖) correction:
not one spirit, but all 227 selectable spirits, all 40 named systems and all
declared relationships are checked and written to references/catalog/full_audit.json.

Nothing here invents a strength tier. A spirit without a dated, citable
seasonal source stays 未评级; the audit records *which* evidence is missing and
how urgent the re-check is.

Outputs: references/catalog/full_audit.json
Run after build_strength.py / build_chain_audit.py, before build_synergy_view.py.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REF = ROOT / "references"
DATA = ROOT / "data"
sys.path.insert(0, str(HERE))

from build_spirit_index import collect  # noqa: E402

OUT = REF / "catalog" / "full_audit.json"
RETIRED = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")

BODY_ELEMENTS = {
    "成立条件": r"成立|条件|前提|需要",
    "逐回合顺序": r"顺序|→|依次|先.{0,60}再|第[一二三1-9]回合|回合结束|登场后|下1只|下 1 只",
    "资源": r"PP|背包|阵亡|血线|体力|名额|宝石|配置",
    "失效点": r"失效|风险|反制|注意|不要|禁止|互斥|怕|被控",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tactic_bodies(text: str) -> dict[str, str]:
    heads = list(re.finditer(r"^(#{2,4})\s+(.+?)\s*$", text, re.M))
    out = {}
    for i, m in enumerate(heads):
        level = len(m.group(1))
        end = len(text)
        for nxt in heads[i + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        out[m.group(2).strip()] = text[m.end():end].strip()
    return out


def main() -> int:
    rows, roster, idx = collect()
    pool = load(DATA / "bwiki/pool.json")
    overrides = load(REF / "catalog" / "manual_overrides.json")
    systems_doc = load(REF / "catalog" / "systems.json")
    systems = systems_doc["systems"]
    strength = load(REF / "catalog" / "strength.json")
    chain = load(REF / "catalog" / "chain_audit.json")
    matchups = load(REF / "catalog" / "matchups.json") if (REF / "catalog" / "matchups.json").exists() else {"items": []}
    bodies = tactic_bodies((REF / "docs" / "tactics.md").read_text(encoding="utf-8"))

    elves = {x["id"]: x for x in pool["elves"]}
    deep = {x["id"]: x for x in roster["spirits"]}
    names = {x["id"]: x["name"] for x in pool["elves"]}
    names.update({x["id"]: x["name"] for x in roster["spirits"]})
    names.update({x.get("id"): x.get("name", "") for x in roster["pending_research"]
                  if x.get("id") is not None})
    names.update({x["id"]: x["name"] for x in idx["themed_spirits"]})
    names.update({x["id"]: x["name"] for x in overrides["spirits"]})

    active_ids = {x["id"] for x in rows if x["id"] is not None}
    excluded_ids = {x.get("id") for x in roster["excluded_examples"] if x.get("id")}
    all_known = set(elves) | {x["id"] for x in overrides["spirits"]}
    themed_ids = {x["id"] for x in idx["themed_spirits"]}

    # ---- evidence indexes -------------------------------------------------
    pool_members: dict[int, str] = {}
    for entry in strength.get("official_pools", []):
        for level in ("banned", "limited", "semi_limited"):
            for sid in entry.get(level, []):
                pool_members[sid] = "%s %s" % (entry["code"], level)
    ratings = {x["id"]: x for x in strength.get("ratings", [])}
    # Watchlist now also contains official-pool members, so month-chart naming
    # must be derived from system evidence rather than from that mixed list.
    chart_ids = set()
    for item in systems:
        if "月榜" in item.get("evidence", ""):
            chart_ids.update(item.get("core", []))
            chart_ids.update(item.get("support", []))
    core_ids: set[int] = set()
    support_ids: set[int] = set()
    counter_ids: set[int] = set()
    for item in systems:
        core_ids.update(item.get("core", []))
        support_ids.update(item.get("support", []))
        counter_ids.update(item.get("counter", []))
    verified_pairs = {tuple(x) for x in chain.get("verified_pairs", [])}
    chain_members = {i for pair in verified_pairs for i in pair}
    link_grade = {(x["a"], x["b"]): x for x in chain.get("items", [])}

    # ---- 1) every selectable spirit --------------------------------------
    spirit_items = []
    conflict_counts: collections.Counter = collections.Counter()
    priority_counts: collections.Counter = collections.Counter()
    for row in sorted(rows, key=lambda x: (x["id"] is None, x["id"] or 0)):
        sid = row["id"]
        if sid is None:
            # Four candidate-pool rows have no verified ID yet; they still
            # belong to the selectable 227 and must appear in the audit.
            spirit_items.append({
                "id": None,
                "name": row["name"],
                "main_layer": row["main"],
                "layers": row["layers"],
                "complexity_tier": "—",
                "complexity_score": None,
                "deep_status": None,
                "roles": [],
                "play_chars": 0,
                "has_full_chain": False,
                "evidence_flags": ["候选池：序号待核，不得进入推荐或体系成员"],
                "human_strength": row.get("strength", "未评级"),
                "rating_basis": "",
                "conflicts": ["序号未核，无法核对魂印、上位替代与当季证据"],
                "review_priority": "P0 序号待核，先完成精灵身份核验",
            })
            conflict_counts["序号未核，无法核对魂印、上位替代与当季证据"] += 1
            priority_counts["P0 序号待核，先完成精灵身份核验"] += 1
            continue
        e = elves.get(sid, {})
        d = deep.get(sid)
        tier = e.get("tier", "—")
        score = e.get("score")
        status = d.get("status") if d else None
        play = d.get("play", "") if d else ""
        evidence = []
        if sid in pool_members:
            evidence.append("官方限制池 " + pool_members[sid])
        if sid in chart_ids:
            evidence.append("具体月份竞技图鉴／月榜点名")
        if sid in themed_ids:
            evidence.append("配置／攻略专题作品")
        if sid in core_ids:
            evidence.append("体系核心位")
        if sid in support_ids:
            evidence.append("体系补位")
        if sid in chain_members:
            evidence.append("已核顺序链成员")
        if d and d.get("deep_dive"):
            evidence.append("已写完整六要素战术链")

        conflicts = []
        if status in ("core", "meta") and tier in ("T3", "T4", "—"):
            conflicts.append("深研定位为环境／核心位，但机制复杂度分偏低或无分档")
        if tier == "—":
            conflicts.append("无机制复杂度分档（人工回捞或资料层精灵），复杂度分不可用")
        if sid in pool_members and sid not in ratings:
            conflicts.append("有官方限制池地位证据，但人工强度仍未评级")
        if d and len(play) < 80 and not d.get("deep_dive"):
            conflicts.append("深研说明为占位短句，不足以支撑强度结论")
        if sid in chain_members and not (d and d.get("deep_dive")):
            conflicts.append("参与已核顺序链，但本只尚未写完整逐回合链")
        for c in conflicts:
            conflict_counts[c] += 1

        if sid in ratings:
            priority = "已评级"
        elif sid in pool_members and status in ("core", "meta"):
            priority = "P0 官方池核心，优先补当季证据"
        elif status in ("core", "meta") and tier in ("T3", "T4", "—"):
            priority = "P1 复杂度分与实战定位冲突"
        elif d and len(play) < 80:
            priority = "P2 深研说明不足"
        elif sid in chart_ids or sid in core_ids:
            priority = "P2 月榜／体系点名，待当季证据"
        else:
            priority = "P3 无当季证据"
        priority_counts[priority] += 1

        spirit_items.append({
            "id": sid,
            "name": row["name"],
            "main_layer": row["main"],
            "layers": row["layers"],
            "complexity_tier": tier,
            "complexity_score": score,
            "deep_status": status,
            "roles": d.get("roles", []) if d else [],
            "play_chars": len(play),
            "has_full_chain": bool(d and d.get("deep_dive")),
            "evidence_flags": evidence,
            "human_strength": row.get("strength", "未评级"),
            "rating_basis": ratings[sid]["basis"] if sid in ratings else "",
            "conflicts": conflicts,
            "review_priority": priority,
        })

    # ---- 2) every named system -------------------------------------------
    system_items = []
    for item in systems:
        body = bodies.get(item.get("section", ""), "")
        elements = [k for k, pattern in BODY_ELEMENTS.items() if re.search(pattern, body)]
        members = (set(item.get("core", [])) | set(item.get("support", [])) |
                   set(item.get("counter", [])))
        ref_only = sorted(m for m in members if m not in active_ids and m in all_known)
        unknown = sorted(m for m in members if m not in all_known)
        core = [int(x) for x in item.get("core", [])]
        system_items.append({
            "key": item["key"],
            "name": item["name"],
            "kind": item["kind"],
            "evidence_grade": item.get("evidence_grade"),
            "chain_status": item.get("chain_status"),
            "evidence_raw": item.get("evidence", ""),
            "section": item.get("section"),
            "body_chars": len(body),
            "body_elements": elements,
            "body_short": len(body) < 250,
            "core_count": len(core),
            "single_core": len(core) < 2,
            "core": core,
            "support": item.get("support", []),
            "counter": item.get("counter", []),
            "reference_only_members": ref_only,
            "unknown_members": unknown,
            "flags": (["体系成员含资料层精灵，仅作正文参照，不进可选列表"] if ref_only else [])
                     + (["体系成员 ID 未在任何资料层找到"] if unknown else [])
                     + (["正文较短，操作链信息密度低，须复核"] if len(body) < 250 else [])
                     + (["单核体系，顺序链只来自补位指向主核"] if len(core) < 2 else []),
        })

    # ---- 3) every declared link ------------------------------------------
    link_items = []
    for rec in chain.get("items", []):
        a, b = rec["a"], rec["b"]
        link_items.append({
            "a": a, "b": b,
            "a_name": rec.get("a_name", names.get(a, str(a))),
            "b_name": rec.get("b_name", names.get(b, str(b))),
            "grade": rec["grade"],
            "group": rec["group"],
            "mutual": rec.get("mutual", False),
            "source_field": rec.get("source_field", "leads"),
            "systems": rec.get("systems", []),
            "also_systems": rec.get("also_systems", []),
        })

    findings = [
        {"key": "strength_coverage",
         "finding": "只有带日期与可核来源的强度才能写评级；其余一律未评级，不按机制复杂度推算 T 级。",
         "action": "已生成 227 只逐只评级依据审计与复核优先级；官方限制池成员逐只登记在 official_pool_members。",
         "status": "已处理"},
        {"key": "auto_score_conflict",
         "finding": "深研定位 core/meta 但复杂度分 T3/T4/无分档者，属于自动评分系统性低估的功能位。",
         "action": "逐只写入 conflicts 与 P1 复核队列；bias_review 已扩大到全部低分档功能位。",
         "status": "已处理"},
        {"key": "unsupported_synergy_declarations",
         "finding": "无正文依据的单向声明与同体系备选位声明不应留在 synergies 字段里当作联动。",
         "action": "已从 synergies 迁到 leads（线索字段），chain_audit 继续逐条留痕并标 source_field。",
         "status": "已处理"},
        {"key": "unverified_system_in_verified_link",
         "finding": "已核顺序链声明的 systems/note 会混入未核体系名，容易被读成该体系也已核。",
         "action": "systems 只列已核体系，未核体系移入 also_systems。",
         "status": "已处理"},
        {"key": "one_way_verified_link",
         "finding": "verified_pairs 双向展开，使单向 synergies 声明也被判为已核同队顺序链。",
         "action": "单向声明改判「顺序链支持（单向，待互证）」并归入关联线索。",
         "status": "已处理"},
        {"key": "reference_only_members",
         "finding": "少数体系成员只存在于资料层，不进总表与可选列表。",
         "action": "逐项登记 reference_only_members，前端继续只作正文参照。",
         "status": "已处理"},
    ]

    doc = {
        "schema_version": "1.0",
        "generated_at": date.today().isoformat(),
        "purpose": "全量复查：%d 只活跃精灵的强度依据、%d 项体系正文、%d 条已核联动声明逐条留痕。" %
                   (len(spirit_items), len(systems), len(chain.get("items", []))),
        "policy": {
            "strength": "强度只认 references/catalog/strength.json 的带日期人工评级；未评级不推断，机制复杂度分只是文本复杂度。",
            "links": "同队配合只认 systems.json 的显式 chain_edges；历史声明已移出关联层，没关联就是没关联，不列骨架线索。",
            "no_invention": "不编造胜率、使用率、月榜名次或 T 级；复核队列不等于强度榜。",
        },
        "stats": {
            "spirits": len(spirit_items),
            "systems": len(system_items),
            "links": len(link_items),
            "rated": len(ratings),
            "official_pool_members": len(pool_members),
            "conflicts": sum(len(x["conflicts"]) for x in spirit_items),
            "conflict_counts": dict(conflict_counts.most_common()),
            "priority_counts": dict(priority_counts.most_common()),
            "systems_with_reference_only": sum(1 for x in system_items if x["reference_only_members"]),
            "systems_short_body": sum(1 for x in system_items if x["body_short"]),
            "systems_single_core": sum(1 for x in system_items if x["single_core"]),
        },
        "spirits": spirit_items,
        "systems": system_items,
        "links": link_items,
        "findings": findings,
        "related": ["references/catalog/strength.json", "references/catalog/chain_audit.json",
                    "references/catalog/systems.json", "references/catalog/roster.json",
                    "references/spirit_synergy_view.html"],
    }

    raw = json.dumps(doc, ensure_ascii=False, indent=2)
    for word in RETIRED:
        if word in raw:
            raise RuntimeError("full_audit.json must not contain retired wording: " + word)
    OUT.write_text(raw + "\n", encoding="utf-8")
    s = doc["stats"]
    print("full audit: %d spirits (%d conflicts, %d rated), %d systems, %d links" %
          (s["spirits"], s["conflicts"], s["rated"], s["systems"], s["links"]))
    print("  priorities:", dict(priority_counts.most_common()))
    print("  findings:", len(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

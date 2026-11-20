#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-audit every relationship claim and rebuild the ordered-chain registry.

Two defects are fixed here (2026-11-05):

1. The old front end expanded each system's ``core + support`` into a full
   Cartesian product, so "both can fill the same defensive slot" became
   "these two directly combo". The new rule is: adjacent ``core`` members form
   an ordered chain, ``support`` points at the first ``core`` (the anchor),
   and ``counter`` stays an opposing-side relation.
2. ``roster.spirits[].synergies`` was treated as a partner list. Each declared
   link is now graded against tactic bodies, named systems and matchups.json;
   anything without direct evidence becomes a lead, not a recommendation.

Outputs:
  references/catalog/systems.json     - adds evidence_grade / chain_status per system
  references/catalog/chain_audit.json - per-link grades, ordered pairs, statistics

Usage: python scripts/build_chain_audit.py
"""
from __future__ import annotations

import collections
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"
SYSTEMS = REF / "catalog" / "systems.json"
OUT = REF / "catalog" / "chain_audit.json"

GRADE_DEFS = {
    "实战／月榜": "具体月份竞技图鉴或可核实战复盘；可作同队顺序链依据，仍须写明赛季",
    "混合证据（部分待核）": "有月榜／实战成分，但部分分支只是推演或年份未定；顺序链标待核",
    "社区／攻略": "社区阵容口径或攻略机制核验；仅作组件线索，不作当月强度",
    "机制推演／待核": "只有魂印机制推演，须标「当月梯度待月榜复核」，不写操作结论",
    "待核线索": "只有标题／简介／环境术语，禁止直接推荐",
}
CHAIN_DEFS = {
    "顺序链已核": "正文写出成立条件／逐回合顺序，且证据为实战或月榜；可进「同队可配合」",
    "顺序链待核（证据不足）": "正文有顺序描述但证据为社区／推演／混合；只作体系信息，不进关系前端",
    "仅成员清单（无顺序正文）": "只列出骨架备选位，不表示两两直接联动；只作体系信息，不进关系前端",
    "待核线索（禁止直接推荐）": "体系本身待核，成员关系不进同队组",
    "BP 对策（不是同队）": "放对手限二／谱尼的对策位，属于对手侧",
    "组件互斥（警示）": "同时上场会对冲，属于警示",
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


def evidence_grade(item: dict) -> str:
    kind = item.get("kind", "")
    ev = item.get("evidence", "")
    if kind == "待核" or "待核线索（" in ev:
        return "待核线索"
    top = ("月榜" in ev) or ("实战复盘" in ev)
    soft = any(w in ev for w in ("推演", "待核", "设计复盘", "社区口径", "发布日待核", "仅 B 站"))
    if top and soft:
        return "混合证据（部分待核）"
    if top:
        return "实战／月榜"
    if any(w in ev for w in ("社区", "攻略", "专栏", "核验")):
        return "社区／攻略"
    return "机制推演／待核"


def chain_status(item: dict, grade: str, body: str) -> str:
    override = item.get("chain_status_override")
    if override:
        return override
    kind = item.get("kind", "")
    if kind == "待核":
        return "待核线索（禁止直接推荐）"
    if kind == "放谱对策":
        return "BP 对策（不是同队）"
    if kind == "组件互斥":
        return "组件互斥（警示）"
    has_seq = bool(re.search(r"顺序|→|依次|先.{0,40}再", body))
    if grade == "实战／月榜" and has_seq:
        return "顺序链已核"
    if has_seq:
        return "顺序链待核（证据不足）"
    return "仅成员清单（无顺序正文）"


BODY_ELEMENTS = {
    "成立条件": r"成立|条件|前提|需要",
    "逐回合顺序": r"顺序|→|依次|先.{0,60}再|第[一二三1-9]回合|回合结束|登场后|下1只|下 1 只",
    "资源": r"PP|背包|阵亡|血线|体力|名额|宝石|配置",
    "失效点": r"失效|风险|反制|注意|不要|禁止|互斥|怕|被控",
}


def body_review(item: dict, body: str) -> dict:
    """Record what the tactic section actually contains, not just its length."""
    core = item.get("core", [])
    return {
        "body_chars": len(body),
        "elements": [k for k, pattern in BODY_ELEMENTS.items() if re.search(pattern, body)],
        "short_body": len(body) < 250,
        "single_core": len(core) < 2,
    }


def chain_edges(item: dict) -> set[tuple[int, int]]:
    """Explicit directed edges registered in systems.json; never inferred."""
    out = set()
    for edge in item.get("chain_edges", []):
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            continue
        a, b = int(edge[0]), int(edge[1])
        if a != b:
            out.add((a, b))
    return out


def ordered_pairs(item: dict) -> set[tuple[int, int]]:
    """Both directions of each explicit edge (lookup only, not new links)."""
    pairs = set()
    for a, b in chain_edges(item):
        pairs.add((a, b))
        pairs.add((b, a))
    return pairs


def member_pairs(item: dict) -> set[tuple[int, int]]:
    ids = [int(x) for x in (set(item.get("core", [])) | set(item.get("support", [])))]
    return {(a, b) for a in ids for b in ids if a != b}


def main() -> int:
    doc = load(SYSTEMS)
    bodies = tactic_bodies((REF / "docs" / "tactics.md").read_text(encoding="utf-8"))
    roster = load(REF / "catalog" / "roster.json")
    matchups = load(REF / "catalog" / "matchups.json") if (REF / "catalog" / "matchups.json").exists() else {"items": []}
    strength = load(REF / "catalog" / "strength.json") if (REF / "catalog" / "strength.json").exists() else {"ratings": []}

    verified: set[tuple[int, int]] = set()
    directional: set[tuple[int, int]] = set()
    weak: set[tuple[int, int]] = set()
    grade_counts: collections.Counter = collections.Counter()
    status_counts: collections.Counter = collections.Counter()
    for item in doc["systems"]:
        body = bodies.get(item.get("section", ""), "")
        g = evidence_grade(item)
        c = chain_status(item, g, body)
        item["evidence_grade"] = g
        item["chain_status"] = c
        item["chain_review"] = body_review(item, body)
        grade_counts[g] += 1
        status_counts[c] += 1
        directional |= chain_edges(item)
        pairs = ordered_pairs(item)
        # 2026-11-15：41 个历史体系退役后，保留体系全部是用户口径录入（无逐回合正文），
        # 若仍以「顺序链已核」为唯一门槛，关系层会整体归零。edge_rule 本来就规定
        # 「同队联动只认 chain_edges 中逐条写明的有向边」，故把已登记的显式边作为可引用门槛；
        # chain_status=顺序链已核 只区分能否进「逐回合顺序链」推荐。
        verified |= pairs
        weak |= member_pairs(item) - pairs

    doc["evidence_grades"] = GRADE_DEFS
    doc["chain_statuses"] = CHAIN_DEFS
    doc["link_rule"] = (
        "同队可配合只认 systems.json 的 chain_edges 显式有向边（正文写出资源交接／先后顺序／机制互相放大）；"
        "chain_status=顺序链已核 只表示还能给出逐回合顺序，不影响显式边本身成立。"
        "core/support/counter 只是成员名单，禁止按位置或笛卡尔积推断。"
        "alternatives 中的并列／二选一／按对局补位只是同一骨架的择一组件，不是同队配合，也不等于 role_groups.json 的相似定位组（后者只由共享同一特色机制构成）；"
        "roster.synergies 只保留双向互证且落在显式边上的声明，历史无依据声明一律移出关联层并归档到 historical_leads.json。"
        "counter 与 matchups.json 只进反向对位。没有显式边就是没有关联，直接写「暂无已核实关联」。"
    )
    doc["version"] = "2026-11-05-explicit-edges"
    SYSTEMS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    matchup_lookup = {}
    matchup_pairs = []
    for m in matchups.get("items", []):
        a, b = int(m["a"]), int(m["b"])
        matchup_pairs.append([a, b])
        matchup_lookup[(a, b)] = m
        matchup_lookup[(b, a)] = m

    spirits = roster.get("spirits", [])
    spirit_ids = {int(x["id"]) for x in spirits}
    # synergies = the ONLY relationship claims. Historical one-way declarations
    # were archived to historical_leads.json on 2026-11-05; they are not links,
    # not clues shown to the user, and not graded here.
    syn_map = {int(x["id"]): {int(y) for y in x.get("synergies", [])} for x in spirits}
    archived_path = REF / "catalog" / "historical_leads.json"
    archived_count = 0
    if archived_path.exists():
        archived = json.loads(archived_path.read_text(encoding="utf-8"))
        archived_count = archived.get("stats", {}).get("archived_claims", 0)
    names = {int(x["id"]): x["name"] for x in spirits}
    verified_systems_by_pair = collections.defaultdict(list)
    other_systems_by_pair = collections.defaultdict(list)
    systems_by_pair = collections.defaultdict(list)
    for item in doc["systems"]:
        bucket = (verified_systems_by_pair if item["chain_status"] == "顺序链已核"
                  else other_systems_by_pair)
        for pair in member_pairs(item):
            systems_by_pair[pair].append(item["name"])
            bucket[pair].append(item["name"])

    all_claims = collections.defaultdict(set)
    for a, targets in syn_map.items():
        all_claims[a] |= targets

    items = []
    link_grades: collections.Counter = collections.Counter()
    mutual_count = 0
    source_counts: collections.Counter = collections.Counter()
    suppressed_one_way = 0
    for a in sorted(all_claims):
        for b in sorted(all_claims[a]):
            if a == b:
                continue
            pair = (a, b)
            field = "synergies" if b in syn_map.get(a, set()) else "leads"
            source_counts[field] += 1
            mutual = a in all_claims.get(b, set())
            if mutual:
                mutual_count += 1
            verified_names = sorted(set(verified_systems_by_pair.get(pair, [])))
            other_names = sorted(set(other_systems_by_pair.get(pair, [])))
            if pair in matchup_lookup:
                g = "反向对位（matchups.json）"
                note = matchup_lookup[pair].get("direction", "")
                systems = sorted(set(systems_by_pair.get(pair, [])))
                also = []
            elif pair in verified and mutual and field == "synergies":
                g = "显式边同队联动"
                note = "；".join(verified_names)[:120]
                systems = verified_names
                also = other_names
            elif pair in verified:
                g = "顺序链支持（单向／线索，待互证）"
                note = "落在已登记的显式边上，但本条是单向声明或历史线索，需双向互证后才能当同队推荐"
                systems = verified_names
                also = other_names
                suppressed_one_way += 1
            elif pair in weak:
                g = "同体系成员（无直接联动证据）"
                note = "同属一个骨架／备选位清单，不等于两两直接联动"
                systems = sorted(set(systems_by_pair.get(pair, [])))
                also = []
            elif b not in spirit_ids:
                g = "指向非深研层（单向线索）"
                note = "目标未在深研层，需先完成逐只核验"
                systems = []
                also = []
            else:
                g = "无正文依据（单向声明）"
                note = "历史声明未找到体系正文、月榜或实战对位依据，只作线索保留"
                systems = []
                also = []
            link_grades[g] += 1
            items.append({
                "a": a, "b": b, "a_name": names.get(a, str(a)),
                "b_name": names.get(b, str(b)),
                "grade": g, "mutual": mutual,
                "source_field": field,
                "systems": systems[:6],
                "also_systems": also[:6],
                "note": note,
                "group": ("同队" if g == "显式边同队联动" else
                          "对位" if g.startswith("反向对位") else "待核"),
            })

    out = {
        "schema_version": "1.0",
        "generated_at": date.today().isoformat(),
        "purpose": "逐条审计同队联动声明；只认 systems.json 的显式 chain_edges，杜绝把「同一骨架备选位」写成直接配合。无依据的历史声明已归档，不再进入关联层。",
        "rule": doc["link_rule"],
        "stats": {
            "systems": len(doc["systems"]),
            "systems_by_grade": dict(grade_counts),
            "systems_by_chain_status": dict(status_counts),
            "explicit_chain_edges": sum(len(x.get("chain_edges", [])) for x in doc["systems"]),
            "verified_chain_edges": len(directional),
            "pending_chain_edges": sum(len(x.get("chain_edges", [])) for x in doc["systems"]) - len(directional),
            "systems_without_edges": sum(1 for x in doc["systems"] if not x.get("chain_edges")),
            "verified_ordered_pairs": len(verified),
            "weak_member_pairs": len(weak),
            "archived_historical_leads": archived_count,
            "declared_links": len(items),
            "mutual_declarations": mutual_count,
            "one_way_declarations": len(items) - mutual_count,
            "by_grade": dict(link_grades),
            "by_source_field": dict(source_counts),
            "suppressed_one_way_verified": suppressed_one_way,
            "rated_by_humans": len(strength.get("ratings", [])),
        },
        "verified_pairs": sorted([list(x) for x in verified]),
        "verified_directional_pairs": sorted([list(x) for x in directional]),
        "matchup_pairs": matchup_pairs,
        "items": items,
        "policy": "改动 roster.json / systems.json / tactics.md / matchups.json 后必须重跑本脚本，再重建配合前端。没有显式 chain_edges 的精灵对就是没有关联，页面必须直接写「暂无已核实关联」，不得用骨架备选位或历史线索凑数。",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("chain audit: %d systems graded, %d verified ordered pairs, "
          "%d synergy declarations (%d mutual, %d one-way)" %
          (len(doc["systems"]), len(verified), len(items),
           mutual_count, len(items) - mutual_count))
    print("  grades:", dict(link_grades))
    print("  source fields:", dict(source_counts),
          "| one-way verified claims downgraded:", suppressed_one_way)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

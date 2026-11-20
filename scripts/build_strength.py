#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build references/catalog/strength.json, the human strength layer.

``data/bwiki/pool.json``'s ``tier``/``score`` are a *mechanism-text complexity*
percentile (base-stat normalisation + clause count + tag weights + recency).
They are NOT a PvP strength tier. This module separates the two:

  * explicit human ratings (dated, evidence-backed, never invented);
  * official restriction-pool evidence (BP cost, not a tier);
  * month-chart named cores (named, tier unrated);
  * a reproducible audit of functional slots whose mechanism value the
    complexity score systematically under-represents.

Usage: python scripts/build_strength.py
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

OUT = REF / "catalog" / "strength.json"

# Explicit human judgement. Never synthesise a tier without a dated decision.
MANUAL_RATINGS = [
    {
        "id": 3056,
        "name": "圣甲·盖亚",
        "grade": "T1（下限）",
        "basis": "用户 2026-11-05 判定「机盖应该是至少 T1 水平」",
        "evidence": [
            "当前期官方池（2026-10-16 起）准限制池仍在列；旧 O202608 池同样在准限制池",
            "SeerAPI soulmark:410（客户端版）：战斗阶段内死亡时附加等同该伤害数值的真实伤害＋造成致死伤害时恢复 1 点体力＋每回合回 1/3 最大体力；BWIKI 同号仍是旧版「扣除体力」，两源冲突已记录",
            "tactics.md 联防阵常见组件；实战记录可处理圣耀天马、拦住曝压制链",
        ],
        "sources": ["O20261016", "O202608", "W:3056", "T202407"],
        "season": "2026-10-16 官方竞技池（准限制池）",
        "status": "已核；当月梯度仍待具体月份竞技图鉴落文",
        "note": "本地旧自动评分 7.4 分 T4 是机制文本复杂度，不是强度；不得再用于梯度、BP 与推荐",
    },
]

# 历史池：2026-08-29 生效，保留用于对比期次变化。
LEGACY_POOLS = [
    {
        "code": "O202608",
        "effective": "2026-08-29",
        "banned": [4554, 3550, 4677],
        "limited": [5000, 3577, 4622, 4515, 4732, 4468, 3291, 4500, 3788, 3637],
        "semi_limited": [2987, 3056, 3613, 3986],
        "note": "只说明当时的 BP 成本与制度性地位；不等于胜率，也不直接换算成具体梯度",
    },
]


def load_official_pools():
    """当前期官方池优先从 references/catalog/official_pool.json 读取（SeerAPI 抓取）。

    2026-11-06 起不再把池成员硬编码在脚本里：SeerAPI 的 peak_pool 带
    start_time/end_time，期次一换就必须重抓，否则 P0 队列会按旧池排。
    """
    path = REF / "catalog" / "official_pool.json"
    if not path.exists():
        return list(LEGACY_POOLS)
    doc = json.loads(path.read_text(encoding="utf-8"))
    period = doc.get("period") or {}
    pools = doc.get("pools") or {}
    start = (period.get("start") or "")[:10]
    code = "O" + start.replace("-", "") if start else "O_CURRENT"
    current = {
        "code": code,
        "effective": start,
        "expires": (period.get("end") or "")[:10],
        "banned": (pools.get("ban") or {}).get("ids", []),
        "limited": (pools.get("limit") or {}).get("ids", []),
        "semi_limited": (pools.get("semi_limit") or {}).get("ids", []),
        "note": "当前期官方竞技池（SeerAPI peak_pool）；只说明 BP 成本与制度性地位，不等于胜率，也不直接换算成梯度",
    }
    return [current] + list(LEGACY_POOLS)

# Mechanism families the complexity score cannot see: their value comes from
# damage/interaction resolution, not from base stats or clause count.
BIAS_PATTERNS = {
    "拦截／兑子／反伤": r"致死|等额扣除|扣除对手|恢复1点|恢复 1 点|反弹|反伤|保留1点|抵挡下1次|抵挡下 1 次",
    "清 PP／技能资源": r"PP|pp|清零|归1|归 1|零 PP|零PP|损失PP|恢复.*PP",
    "复活／消逝／阵亡传承": r"复活|消逝|阵亡|传承|下1只出战|下 1 只出战",
    "免控／免秒杀／锁切": r"免控|免秒杀|免疫异常|锁切|锁先制|无法切换|封属",
    "护盾／庇护／减伤": r"护盾|护罩|庇护|减伤|抵挡|免伤",
    "断回合／双消／控场": r"断回合|消强|双消|清除.*强化|畏怯|疲惫|麻痹|烧伤|流血|诅咒",
}

# Words that must never reach the generated master list / front end.
RETIRED = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    rows, roster, idx = collect()
    pool = load(DATA / "bwiki/pool.json")
    souls = load(DATA / "seerapi/soul_full.json").get("souls", {})
    systems = load(REF / "catalog" / "systems.json")["systems"]
    overrides = load(REF / "catalog" / "manual_overrides.json")
    elves = {x["id"]: x for x in pool["elves"]}
    combined = dict(elves)
    combined.update({x["id"]: x for x in overrides.get("spirits", [])})
    names = {x["id"]: x["name"] for x in pool["elves"]}
    for x in roster["spirits"]:
        names.setdefault(x["id"], x["name"])
    for x in overrides.get("spirits", []):
        names.setdefault(x["id"], x["name"])

    active_ids = {x["id"] for x in rows if x["id"] is not None}
    system_ids = set()
    system_core = set()
    for item in systems:
        system_core.update(item.get("core", []))
        for field in ("core", "support", "counter"):
            system_ids.update(item.get(field, []))
    audit_ids = sorted(active_ids | system_ids)
    rated_ids = {x["id"] for x in MANUAL_RATINGS}
    deep_text = {}
    deep_status = {}
    for x in roster["spirits"]:
        deep_text[x["id"]] = " ".join(
            [str(x.get("play", ""))] +
            [str(v) for v in x.get("mechanics", [])] +
            [str(v) for v in x.get("roles", [])])
        deep_status[x["id"]] = x.get("status")

    official_pools = load_official_pools()
    current_pool = official_pools[0]
    # 当前期：用于「是否在池」判断与 P0 队列。
    pool_members = {}
    for level in ("banned", "limited", "semi_limited"):
        for sid in current_pool.get(level, []):
            pool_members[sid] = (current_pool["code"], level)
    # 全部期次：official_pool_members 要覆盖历史池，才能看出「从禁止池降到限制池」
    # 这种期次变化；只登记当前池会让 check_roster 的覆盖校验失败。
    history = {}
    for entry in official_pools:
        for level in ("banned", "limited", "semi_limited"):
            for sid in entry.get(level, []):
                history.setdefault(sid, []).append(
                    {"code": entry["code"], "level": level})
    official_pool_members = [{
        "id": sid,
        "name": names.get(sid, str(sid)),
        "code": pool_members[sid][0] if sid in pool_members else "历史",
        "level": pool_members[sid][1] if sid in pool_members else "history",
        "history": history.get(sid, []),
        "complexity_tier": combined.get(sid, {}).get("tier", "—"),
        "deep_status": deep_status.get(sid),
        "human_strength": next((x["grade"] for x in MANUAL_RATINGS if x["id"] == sid),
                               "未评级（限制池只证明 BP 成本与环境地位，不换算梯度）"),
        "note": "只说明当时的 BP 成本与制度性地位；不等于胜率，也不直接换算成具体梯度",
    } for sid in sorted(history)]

    # Second-pass scope (2026-11-05): every active spirit whose complexity
    # tier is low or missing, not just the ones whose soul text happens to hit
    # a keyword. Functional value, deep-dive status, official-pool presence and
    # system-core membership all count as reasons to re-check.
    bias = []
    for sid in audit_ids:
        if sid in rated_ids:
            continue
        e = combined.get(sid)
        if not e:
            continue
        tier = e.get("tier", "—")
        if tier not in ("T3", "T4", "—"):
            continue
        soul_text = souls.get(str(sid), {}).get("text", "") or e.get("soul", "")
        text = soul_text + " " + deep_text.get(sid, "")
        hits = [label for label, pattern in BIAS_PATTERNS.items()
                if re.search(pattern, text)]
        reasons = []
        if hits:
            reasons.append("魂印／深研文本命中结算型功能机制")
        if deep_status.get(sid) in ("core", "meta"):
            reasons.append("深研定位为环境／核心位")
        if sid in pool_members:
            reasons.append("官方限制池成员")
        if sid in system_core:
            reasons.append("体系核心位")
        if tier == "—":
            reasons.append("无机制复杂度分档，复杂度分不可用")
        if not reasons:
            continue
        evidence_from = []
        if soul_text:
            evidence_from.append("BWIKI 魂印全文／摘要")
        if sid in deep_text:
            evidence_from.append("深研条目机制／战术说明")
        if sid in pool_members:
            evidence_from.append("官方限制池 " + pool_members[sid][0])
        if sid in system_core:
            evidence_from.append("体系注册表 core")
        bias.append({
            "id": sid,
            "name": names.get(sid, e.get("name", "")),
            "complexity_tier": tier,
            "complexity_score": e.get("score"),
            "tags": e.get("tags", []),
            "mechanism_families": hits,
            "reasons": reasons,
            "evidence_from": evidence_from or ["资料层记录"],
            "action": "强度未评级；按当季竞技图鉴／官方限制池人工复核，不使用机制复杂度分作强度依据",
        })

    # Month-chart named cores are evidence of presence, not a tier.
    chart_marked = set()
    for item in systems:
        ev = item.get("evidence", "")
        if "月榜" not in ev:
            continue
        chart_marked.update(item.get("core", []))
        chart_marked.update(item.get("support", []))
    watchlist = [
        {"id": sid, "name": names.get(sid, str(sid)),
         "reason": ("官方限制池成员 " + pool_members[sid][0] + "（BP 成本证据，非梯度）"
                    if sid in pool_members else
                    "具体月份竞技图鉴／社区阵容点名的体系成员"),
         "status": "梯度未评级，禁止推算 T 级"}
        for sid in sorted((chart_marked | set(pool_members)) & (active_ids | system_ids))
    ]

    family_counts = collections.Counter(
        fam for x in bias for fam in x["mechanism_families"])
    low_complexity = sum(1 for sid in active_ids
                         if elves.get(sid, {}).get("tier") in ("T3", "T4"))

    doc = {
        "schema_version": "1.0",
        "generated_at": date.today().isoformat(),
        "purpose": "人工强度层：把「机制文本复杂度」与「PvP 强度」彻底分开，供总表、配合前端与查询使用。",
        "policy": {
            "authority_order": [
                "具体月份竞技图鉴（须带月份与作者口径）",
                "官方限制池／准限制池（只证明 BP 成本与环境地位）",
                "实战复盘与用户明确判定（须带日期）",
                "社区阵容口径（次级证据）",
                "魂印机制推演（只作线索，须标「当月梯度待月榜复核」）",
            ],
            "auto_score_definition": "data/bwiki/pool.json 的 tier/score = 种族值归一＋魂印分句数＋标签权重＋越新加权的百分位排名，衡量的是机制文本复杂度，不是强度。",
            "rule": "禁止用 tier/score 作梯度、BP、推荐或上位替代结论；门户 SEO 文的胜率／使用率一律不引用。",
            "unrated_default": "未评级（不推断）",
            "snapshot": "强度是带日期的快照；引用时写明赛季／月份，不写成永久排名。",
        },
        "grades": {
            "T0": "当季环境定义者（须有当月图鉴证据）",
            "T1": "当季一线可用（须有当月图鉴、官方池或明确实战证据）",
            "T2": "当季可用但有明确条件",
            "T3": "功能性／条件位",
            "T4": "娱乐或待核，不代表不可用",
            "未评级": "尚无当季证据，禁止推断",
        },
        "ratings": MANUAL_RATINGS,
        "official_pools": official_pools,
        "official_pool_members": official_pool_members,
        "watchlist": watchlist,
        "full_review": {
            "file": "references/catalog/full_audit.json",
            "scope": "227 只可选精灵逐只列出复杂度分档、深研状态、证据标记、冲突、当前人工强度与复核优先级",
            "rule": "复核队列与观察名单都不是强度榜；只有 ratings 里的带日期条目可作强度结论",
        },
        "bias_review": {
            "purpose": "自动评分系统性低估的功能位清单：这些精灵的强度靠结算规则与对位价值体现，复杂度分低或无分档不等于弱。",
            "method": "全量复查：取活跃层与体系成员中 tier=T3/T4/无分档者，命中结算型机制、深研定位 core/meta、官方限制池或体系核心任一即入队；列表只标「强度未评级／需人工复核」，不推算梯度。",
            "count": len(bias),
            "active_low_complexity": low_complexity,
            "family_counts": dict(family_counts.most_common()),
            "families": list(BIAS_PATTERNS),
            "items": bias,
        },
        "display": {
            "complexity_label": "机制复杂度（非强度）",
            "strength_label": "人工强度",
            "unrated_label": "未评级",
            "example": "3056 圣甲·盖亚：机制复杂度 T4，人工强度 T1（下限）——两者不矛盾，前者不是强度。",
        },
        "related": [
            "references/catalog/matchups.json", "references/catalog/chain_audit.json",
            "references/catalog/depth_audit.json", "references/docs/sources.md",
        ],
    }

    raw = json.dumps(doc, ensure_ascii=False, indent=2)
    for word in RETIRED:
        if word in raw:
            raise RuntimeError("strength.json must not contain retired wording: " + word)
    OUT.write_text(raw + "\n", encoding="utf-8")
    print("strength: %d rated, %d watchlist, %d bias-review slots "
          "(%d active spirits have low complexity tiers)" %
          (len(doc["ratings"]), len(watchlist), len(bias), low_complexity))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

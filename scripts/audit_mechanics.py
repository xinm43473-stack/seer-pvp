#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机制文本溯源审计（高风险锚词版）

2026-11-06 用户指出「摆渡者·费雷的魂印会附加己方已损失体力的 198% 的
百分比伤害」被写成「低血粉伤／后手降血／粉转真」——机制方向反了，还
出现原文没有的自造词。本脚本只查两类问题，避免把同义改写的短标签全部
报成错误：

1. 高风险机制断言（复活／秒杀／消逝／封属／清 PP／自损／已损失体力／
   低体／高体／无视／锁伤／必暴／吸血／双消／传承／体力上限）：mechanics
   里写了，但「魂印原文＋该精灵全部技能效果」里找不到对应锚词。
2. 自造词黑名单：原文从不出现的说法（粉转真、低血粉伤、先四低血、
   后手降血等），出现即标记。

用法:
  python scripts/audit_mechanics.py
  python scripts/audit_mechanics.py --json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
DATA = ROOT / "data"

RISKY = {
    "复活": ["复活"],
    "秒杀": ["秒杀"],
    "消逝": ["消逝"],
    "封属": ["属性技能无效", "属性技能失效"],
    "清PP": ["PP值归零", "PP值归0", "PP值-", "PP值 -", "降低对手所有技能",
             "所有技能PP值", "技能PP值", "PP值"],
    "自损": ["消耗自身", "损失自身", "消耗30%", "消耗 30%", "消耗当前最大体力"],
    "已损失体力": ["已损失体力", "损失体力"],
    "低体": ["低于30%", "低于 30%", "低于最大体力的1/2", "低于1/2", "低于 1/2", "体力低于"],
    "高体": ["高于对手", "体力高于", "满体力"],
    "无视": ["无视"],
    "锁伤": ["无法超过", "不超过", "不会超过"],
    "必暴": ["致命一击"],
    "吸血": ["吸取"],
    "双消": ["消除对手回合类", "消除能力提升", "反转对手能力提升", "消除双方"],
    "传承": ["传承", "下1只", "下 1 只", "下只精灵"],
    "体力上限": ["体力上限"],
    "免粉": ["百分比伤害", "固定伤害"],
    "封回血": ["无法通过自身技能恢复", "恢复效果减少", "无法恢复体力", "恢复体力效果"],
}

BAD_WORDS = [
    "粉转真", "低血粉伤", "先四低血", "后手降血", "六层强化魂印",
    "无限弹伤", "无条件秒杀",
]


def norm(text):
    return re.sub(r"\s+", "", text or "")


def main():
    roster = json.loads((REF / "catalog" / "roster.json").read_text(encoding="utf-8"))
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    souls = {x["id"]: x.get("soul") or "" for x in pool["elves"]}
    dropped = {x["id"]: x.get("soul") or "" for x in pool.get("dropped", [])
               if isinstance(x, dict) and isinstance(x.get("id"), int)}
    skills = json.loads((DATA / "seerapi/skills_full.json").read_text(encoding="utf-8"))
    soul_lib = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))["souls"]
    systems = json.loads((REF / "catalog" / "systems.json").read_text(encoding="utf-8"))["systems"]

    sys_of = {}
    for item in systems:
        for field in ("core", "support", "counter"):
            for sid in item.get(field) or []:
                sys_of.setdefault(sid, []).append(item["name"])

    def full_text(sid):
        soul = norm(souls.get(sid) or dropped.get(sid, "")
                    or (soul_lib.get(str(sid)) or {}).get("text", ""))
        sk = []
        for kid in skills.get("elves", {}).get(str(sid), []):
            item = skills.get("skills", {}).get(kid) or {}
            sk.append(norm(item.get("effect", "")))
        return soul + "".join(sk)

    rows = []
    for sp in roster["spirits"]:
        sid = sp["id"]
        full = full_text(sid)
        if len(full) < 20:
            rows.append({"id": sid, "name": sp["name"], "claim": "(原文缺失)",
                         "issue": "原文缺失", "systems": sys_of.get(sid, [])})
            continue

        # 2026-11-18：实战备注与核心机制已合并为 note（前端只有一个「备注」框），
        # 审计对象随之改为 note；旧数据没有 note 时回落到 mechanics。
        note_lines = [x.strip() for x in str(sp.get("note") or "").split("\n") if x.strip()]
        if not note_lines:
            note_lines = [str(x).strip() for x in (sp.get("mechanics") or []) if str(x).strip()]

        # 1) 黑名单自造词
        for kind in ("note", "play"):
            text = "\n".join(note_lines) if kind == "note" else sp.get("play", "")
            for bad in BAD_WORDS:
                if bad in text:
                    rows.append({"id": sid, "name": sp["name"], "claim": bad,
                                 "issue": "自造词/原文无此说法", "field": kind,
                                 "systems": sys_of.get(sid, [])})

        # 2) 高风险断言缺锚词
        for claim in note_lines:
            for label, anchors in RISKY.items():
                if label not in claim:
                    continue
                if any(a in full for a in anchors):
                    continue
                rows.append({"id": sid, "name": sp["name"], "claim": claim,
                             "issue": "机制「%s」在魂印与技能原文中找不到锚词" % label,
                             "anchors": anchors, "systems": sys_of.get(sid, [])})

    print("issues: %d / elves %d" % (len(rows), len(roster["spirits"])))
    for r in rows:
        print("  %-28s %s %s | %s | %s" % (
            r["issue"], r["id"], r["name"], r.get("field", "mechanics"),
            r["claim"][:70]))

    if "--json" in sys.argv:
        doc = {
            "generated_at": "2026-11-06",
            "purpose": "机制文本溯源审计：只列高风险机制断言（复活/秒杀/消逝/封属/清PP/自损/已损失体力/低体/高体/无视/锁伤/必暴/吸血/双消/传承/体力上限）在魂印与技能原文中找不到锚词，以及出现自造词的条目，供人工按原文重写。",
            "method": "锚词表 + 自造词黑名单；不做全量 2-gram 覆盖率，避免把同义改写的短标签误报。",
            "stats": {"spirits": len(roster["spirits"]), "issues": len(rows)},
            "items": rows,
        }
        (REF / "catalog" / "mechanics_audit.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written -> references/catalog/mechanics_audit.json")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-06 机制口径整改（历史脚本，已由核心定位口径取代；勿再运行）

用户指出两类系统性错误：
1. 把「机制等效／替代」写成「同队配合」——米罗博士第五技能是自损消逝换
   一只 1 血返场，与星域之魂「自身低于 30% 全技能秒杀」是同一目标的两种
   实现，不是互相放大的固定体系。
2. 把「同一辅助的受益者名单」当成「相似定位」——斯布林蒂未来链接的七条
   搭配各自功能位不同（零 PP 流血／PP 叠盾／奇点／已损失体力换伤／印记／
   异常反弹／形态标记），不构成同类功能位。

本脚本只做结构整改，不改写 roster 的逐只机制文本（那部分由人工按魂印＋
技能原文重写）。改完后重跑 build_chain_audit.py 起的重建链。
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "references"
DROP_SYSTEM = "米罗星域一血体系"
DROP_ROLE_GROUP = "sync_beneficiary"

LOW_HP_GROUP = {
    "key": "low_hp_execution",
    "name": "低体秒杀实现位",
    "aliases": ["一血秒杀位", "低血斩杀位"],
    "members": [3430, 4925],
    "shared": "都用「极低血量」换一次必杀窗口，但实现路径不同：一只靠自己进入低血线，一只靠消逝自己把队友拉成 1 血。二者是同一目标的两条路，不是机制互补。",
    "differences": [
        "3430 星域之魂：自身回合开始低于 30% 体力时全技能秒杀，随后清空全部 PP 并消除自身回合类效果；触发只依赖自身血线，不需要队友。",
        "4925 米罗博士：第五「太古的至宝」消耗全部体力、消逝自身，令己方场下首位已阵亡精灵以 1 点体力复活；复活目标由阵亡顺序决定、不能指定，被拉回者必须自带低体收益才兑现秒杀。",
    ],
    "relation": "同队只在「星域恰为场下首位阵亡」时成立，且米罗消逝后不能重复利用；这是高成本、可被阵亡顺序破坏的一次性衔接，不登记为稳定同队体系。通常按对局二选一。",
    "evidence_grade": "BWIKI 魂印全文＋技能页",
    "sources": ["W:3430", "W:4925", "SK:29409", "V2026STARS"],
    "verified_at": "2026-11-06",
}

POLICY_ADD = {
    "beneficiary_not_group": "同一辅助的多条受益路线（例如斯布林蒂「未来链接」的七种搭配）只是受益者名单，不是功能位，不得登记为相似定位。2026-11-06 已删除「PP 同步受益位」：库坦是零 PP 流血、铃熙是 PP 损失叠盾、逐界苍星是未来奇点、摆渡者·费雷是已损失体力换伤、缔笙是印记叠层、霍德尔是异常反弹、邪魇是形态标记，彼此不抢同一个位置。",
    "equivalent_not_combo": "「机制等效／替代」不得写成同队配合。米罗博士第五技能与星域之魂低体秒杀是两条等效路径（2026-11-06 由体系降为相似定位）；同队只在特定阵亡顺序下成立，不能当稳定体系推荐。",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, doc):
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main():
    # 2026-11-06 晚：相似定位层已按「共享同一特色机制」重构为 schema 2.0。
    # 本历史脚本会把按机制等效凑出的 low_hp_execution 组写回，禁止再跑。
    guard_legacy(__file__)
    role_file = REF / "catalog" / "role_groups.json"
    if role_file.exists() and load(role_file).get("schema_version", 1.0) >= 2.0:
        print("role_groups.json 已是 schema 2.0（核心定位口径）；本历史脚本不再适用，跳过。")
        print("重建定位层请跑 scripts/apply_core_roles.py 与 scripts/apply_core_role_groups.py。")
        return 0
    changed = []

    sys_path = REF / "catalog" / "systems.json"
    systems = load(sys_path)
    before = len(systems["systems"])
    systems["systems"] = [x for x in systems["systems"] if x["key"] != DROP_SYSTEM]
    if len(systems["systems"]) != before:
        changed.append("systems: -%s (%d -> %d)"
                       % (DROP_SYSTEM, before, len(systems["systems"])))
        systems["version"] = "2026-11-06-explicit-edges"
        # 记一条留痕，避免以后又被当成体系收回
        note = systems.setdefault("retired_systems", [])
        note.append({
            "key": DROP_SYSTEM,
            "retired_at": "2026-11-06",
            "reason": "米罗博士第五技能是自损消逝换一只 1 血返场，与星域之魂低于 30% 全技能秒杀是同一目标的两种实现，不是互相放大的同队体系；已改登记为 role_groups.low_hp_execution。",
            "replaced_by": "role_groups.json#low_hp_execution",
        })
        dump(sys_path, systems)

    role_path = REF / "catalog" / "role_groups.json"
    roles = load(role_path)
    groups = roles["groups"]
    before_groups = len(groups)
    groups = [g for g in groups if g["key"] != DROP_ROLE_GROUP]
    if len(groups) != before_groups:
        changed.append("role_groups: -%s (%d -> %d)"
                       % (DROP_ROLE_GROUP, before_groups, len(groups)))
    if not any(g["key"] == LOW_HP_GROUP["key"] for g in groups):
        groups.insert(1, dict(LOW_HP_GROUP))
        changed.append("role_groups: +%s" % LOW_HP_GROUP["key"])
    roles["groups"] = groups

    policy = roles.setdefault("policy", {})
    for k, v in POLICY_ADD.items():
        if policy.get(k) != v:
            policy[k] = v
            changed.append("role_groups.policy.%s" % k)
    roles["generated_at"] = "2026-11-06"
    roles["rule"] = (
        "相似定位＝抢同一个功能位的同类精灵。它说明「可以互相参照／通常只带一只」，"
        "不说明「这两只同队能互相放大」。同一辅助的多条受益路线不是功能位，不得登记为相似定位；"
        "机制等效／替代也不得写成同队配合。组内任意一对都不得出现在 chain_audit.json 的已核同队链上，"
        "否则说明分组写错了。没有写进任何组、也没有显式联动边或对位记录的精灵，直接写「暂无已核实关联」。"
    )
    dump(role_path, roles)

    if changed:
        print("applied mechanism fixes:")
        for line in changed:
            print("  -", line)
    else:
        print("no changes; already applied")
    print("systems now: %d | role groups now: %d"
          % (len(systems["systems"]), len(groups)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复并修正「伞邪双诛魔体系」（幂等）

2026-11-06 上午曾因只查尤莉米特当前魂印与本人技能表、没查到「诛魔」而误判
体系不存在并撤下。用户指出：体系确实存在，只是被策划针对、难以上场。

「诛魔」不是尤莉米特的魂印，而是技能「诛魔杀阵」（技能:17908，圣光灵神
3311 的远古圣灵物攻，先制 +3）：附加对手上次造成伤害数值的固定伤害。
双诛魔 = 该固定伤害 + 尤莉米特死亡时群辉加护给下只精灵首次技能的
「群芳加护消失时所受攻击伤害 20%×层数」百分比伤害；再由圣谕邪魇第五
（击败对手则令对手下一次攻击技能无效）收口。

同时修正尤莉米特魂印：本地 soul_full 存的是旧版（双方使用技能后受 1 点
固伤），BWIKI 网页已改为群芳／群辉加护的死亡传承版。
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "references"

SYSTEM = {
    "key": "伞邪双诛魔体系",
    "name": "伞邪双诛魔体系",
    "aliases": ["尤莉米特圣谕邪魇", "诛魔窗口", "双诛魔"],
    "core": [4364, 4554],
    "support": [3311],
    "kind": "同队联动",
    "evidence": "实战复盘",
    "sources": ["TIE8902900091", "W:4364", "SK:17908", "W:4554"],
    "section": "伞邪双诛魔：尤莉米特 × 圣谕邪魇（按当前魂印复核）",
    "carrier": "尤莉米特阵亡消耗群辉加护，给下只精灵首次技能附加 20%×层数 的百分比伤害；该技能再叠「诛魔杀阵」的对手上次伤害固伤，第五击败后封对手下次攻击",
    "status": "体系成立但当前环境难以上场",
    "evidence_grade": "实战／月榜",
    "chain_status": "顺序链已核",
    "chain_edges": [[4364, 4554]],
    "edge_meta": {
        "4364-4554": {
            "type": "resource",
            "note": "尤莉米特死亡时消耗所有群辉加护，每层让下只精灵登场后首次技能附加「群芳加护消失时所受攻击伤害 20%」的百分比伤害；邪魇承接这一段，再用诛魔杀阵叠对手上次伤害固伤",
        }
    },
    "alternatives": {"变体接棒位（二选一）": [4765, 3577]},
    "review_note": "「诛魔」来自技能:17908（圣光灵神 3311 的诛魔杀阵），不是尤莉米特魂印；3311 只作第三只挂件、不在 227 总表。体系怕封属、免粉、锁伤、不杀伞与先消传承，当前被策划针对难以上场。",
    "warning_edges": [],
}


def main():
    guard_legacy(__file__)
    path = REF / "catalog" / "systems.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    exists = any(x["key"] == SYSTEM["key"] for x in doc["systems"])
    if not exists:
        doc["systems"].append(dict(SYSTEM))
        print("restored system: %s" % SYSTEM["key"])
    else:
        for i, x in enumerate(doc["systems"]):
            if x["key"] == SYSTEM["key"]:
                doc["systems"][i] = dict(SYSTEM)
                print("updated system: %s" % SYSTEM["key"])
                break

    retired = doc.setdefault("retired_systems", [])
    kept = []
    for x in retired:
        if x.get("key") == SYSTEM["key"]:
            kept.append({
                "key": SYSTEM["key"],
                "retired_at": "2026-11-06",
                "restored_at": "2026-11-06",
                "reason": "曾因只查尤莉米特当前魂印与本人技能表、未查到「诛魔」而误删；用户指出诛魔来自技能:17908（圣光灵神诛魔杀阵），体系确实存在但难以上场，已恢复并按当前魂印重写。",
            })
        else:
            kept.append(x)
    doc["retired_systems"] = kept
    doc["version"] = "2026-11-06-explicit-edges"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print("systems now: %d | edges: %d"
          % (len(doc["systems"]),
             sum(len(x.get("chain_edges") or []) for x in doc["systems"])))


if __name__ == "__main__":
    main()

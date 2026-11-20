#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register explicit, evidence-backed chain edges for every named system.

2026-11-05 user correction: "部分关联不对，不能关联别瞎关联，没关联就没关联直接说就行".
The old builder derived teammate pairs from the *position* of ids inside
``core`` and from every ``support`` member. That invented links such as
"4333 哀·拉伯克 -> 3613 芳馨·茉蕊儿" (the tactic text says 哀拉 **or** 草王,
i.e. an either/or slot), "4875 炎兽 -> 3954 枫眠" (a support list of parallel
burn appliers), and "4125 古王 -> 4872 天女" (the chain actually runs the
other way round). It also turned the six alternative beneficiaries in the
斯布林蒂 table into six fixed teammates.

This script stores the edges that the tactic bodies actually describe. A pair
with no explicit edge is NOT a link, even when both ids sit in the same
system. Parallel slots are recorded in ``alternatives`` and belong to the
similar-role layer (references/catalog/role_groups.json), not to the teammate layer.

Idempotent: running it again does not change systems.json.

Usage: python scripts/apply_strict_links.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SYSTEMS = ROOT / "references" / "catalog" / "systems.json"

# key -> explicit directed edges (a creates the window / resource, b consumes it)
PATCH: dict[str, dict] = {
    "清PP体系": {
        "chain_edges": [[4333, 4620], [3613, 4620]],
        "alternatives": {
            "清 PP 前置位（二选一）": [4333, 3613],
            "按对局补位（不是固定队友）": [3954, 4676, 4541, 4553],
        },
        "review_note": "正文写「哀拉或草王先压低 PP」→ 4333/3613 是并列位，二者互不联动；162 行明写 support 是按对局选择的补位，不是必须同时上场的固定名单，故只保留两个前置位指向灯使的边。",
    },
    "空贝罗体系": {
        "chain_edges": [[4169, 4586], [4184, 4586]],
        "alternatives": {"按对局补位（不是固定队友）": [4808, 4605]},
        "review_note": "正文 259 行写 4169 裂痕与 4586 诗章共享同一颗人头，这才是联动；4184 是前台压斩杀线后交给空元收割。旧 core 顺序 [4586,4184,4169] 把后台双引擎写成先后接力，且 4184→4169 无正文依据，删。",
    },
    "多保一体系": {
        "chain_edges": [[4510, 4515]],
        "alternatives": {"按池选择的拦截位（并列备选）": [3033, 3788, 4364]},
        "review_note": "正文 270 行顺序为卫岳登场并阵亡解放 → 切霍光兑现，方向是 4510→4515；拦截位按池挑选，不是指向主核的辅助。",
    },
    "圣武星魂体系": {
        "chain_edges": [],  # 2026-11-07 审核撤销：双边砥砺是环境位，4677 无「叠层依赖砥砺」结算
        "support": [],
        "external_append": "4553 北鸟／4676 密王是正文 48 行写的「阻止叠层／逼切」反制位，登记为反向线索，不是己方辅助组件。",
        "review_note": "旧 support [4553,4676] 实为反制位，被当成辅助指向主核，属误关联，清空。",
    },
    "伞邪双诛魔体系": {
        "chain_edges": [[4364, 4554]],
        "alternatives": {"变体接棒位（二选一）": [4765, 3577]},
        "review_note": "正文 63 行「也可接 4765 或 3577」是替换位，不是同时上场的辅助；斩杀线与弹伤风险各不同。",
    },
    "斯布林蒂PP同步体系": {
        "chain_edges": [[4600, 4503]],
        "alternatives": {"表格中的并列受益位（按对局二选一，不默认同时可带）": [4517, 4450, 4594, 4386, 3941, 4554]},
        "review_note": "tactics.md 108–117 是「斯布林蒂体系的其他受益者」表格，每组都是 4600 的另一条路线；117 行明写「限池成本很高，先确认同池合法性，不默认同时可带」。旧 synergies 把六组全写成固定队友，属瞎关联。",
    },
    "无为龙塔体系": {
        "chain_edges": [[4288, 4661]],
        "review_note": "正文 131 行「龙塔承接高压回合 → 无为安全中切」，方向为 4288→4661。",
    },
    "蓓丽安特星执体系": {
        "chain_edges": [[4643, 4648]],
        "review_note": "正文 143 行「蓓阵亡转化支援 → 鲁斯王登场」，方向为 4643→4648。",
    },
    "猫阵体系": {
        "chain_edges": [[4541, 4808], [4169, 4808]],
        "alternatives": {"另一条发动机（不写成固定四件套）": [4126, 3986]},
        "review_note": "正文 347 行顺序为 4541 提供跳板、4169 挂裂痕、猫登场兑现；旧 core [4808,4541,4169] 生成 4808→4541→4169，把猫写成第一棒且 4541→4169 无正文依据。349 行明写 4126 是另一条发动机，不作辅助。",
    },
    "龟阵逼退体系": {
        "chain_edges": [[4676, 4762]],
        "alternatives": {"补位对策卡（不是增伤组件）": [4749, 4875, 4872]},
        "review_note": "正文 369 行明写 4749／4875 是补位而非增伤组件；363 行说明这是环境打法记录而非固定名单，support 不产生联动边。",
    },
    "烧伤流体系": {
        "core": [4622, 4875, 4219],
        "chain_edges": [[4622, 4875], [4875, 4219], [3954, 4875], [4622, 4219], [4622, 4517]],
        "alternatives": {
            "并列烧伤挂载位（二选一）": [3954, 4627, 3467, 4620],
            "并列烧伤受益位（二选一）": [4517],
        },
        "review_note": "正文 385 行顺序为「4622／3954 先挂烧伤 → 4875 转成神惧劫炎 → 4219／4517 承接先制增伤」，旧 core [4875,4622,4219] 顺序写反；挂载位与受益位都是并列的同类位，不两两联动。",
    },
    "天女传承体系": {
        "chain_edges": [[4872, 4125]],  # 2026-11-07 审核：三选一接棒位不拆成三条固定配合
        "alternatives": {"三选一接棒位（传承只给下 1 只）": [4125, 4800, 4288]},
        "review_note": "正文 415 行「天女下场或阵亡，不插第三只，让 4125／4800／4288 紧接登场吃砥砺」；旧 support→首核 逻辑把方向写成 4125→4872，且把三选一接棒位写成三个同时上场的辅助。",
    },
    "曝压制体系": {
        "chain_edges": [],
        "chain_status_override": "仅成员清单（无顺序正文）",
        "external_append": "4605 是视频里「拖到 50 回合用来破局」的替补位，与 4853 同队但不互相放大机制；不登记为顺序链，避免把「一起上场」写成联动。",
        "review_note": "正文 459 行只写「局面被拖到 50 回合时切 4605 破局」，两条机制各自独立；旧 core [4853,4605] 被自动判成已核顺序链，属误判，降级为仅成员清单。",
    },
    "薇尔诗位置体系": {
        "chain_edges": [],
        "review_note": "单核体系，位置资源是自身背包排布，不产生精灵两两联动边。",
    },
    # 2026-11-06 补全：这三项的边由 tactics.md 正文可核，必须一并登记，
    # 否则本脚本会把未在 PATCH 的体系 chain_edges 清空。
    "极渊PP清零体系": {
        "chain_edges": [[4797, 4468], [4797, 3711]],
    },
    "乌拉诺斯联攻体系": {
        "chain_edges": [[4126, 3516], [4126, 4219]],
    },
    "玛洛迪斯树海体系": {
        "chain_edges": [[3613, 3739], [4600, 3739], [4500, 3739]],
        "alternatives": {
            "场下体力保护位（二选一，不是配合）": [4500, 4814],
            "临时体力上限供给位（二选一，不是配合）": [3613, 4600],
        },
    },
    # 2026-11-06：咤克斯琉梦的共享事件边，避免本脚本清空。
    "咤克斯琉梦体系": {
        "chain_edges": [[4761, 4762]],
    },
    # 2026-11-07：第 41 项体系；本脚本会清空未声明的体系，必须同步登记。
    "多核接力体系": {
        "chain_edges": [[4766, 4599], [4599, 4387], [4387, 4808]],
        "alternatives": {"残局收割位（二选一）": [4765, 4808]},
        "core": [4766, 4599, 4387, 4808],
        "support": [4765],
    },
    "互斥与反向对位警示": {
        "warning_edges": [[4635, 4333], [4635, 3613], [4635, 4620]],
        "review_note": "正文 335 行只写「4635 登场给双方回满 PP 与 4333／3613／4620 的清 PP 路线直接对冲」，因此只登记这三条互斥警示边；core/support 里其余精灵是返场补位与放谱对策位，不两两生成警示卡。",
    },
}

DEFAULT_REVIEW = "正文未写出该精灵对之间的直接机制联动，不登记联动边；同体系成员只表示可选骨架位。"


def main() -> int:
    doc = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    changed = 0
    for item in doc["systems"]:
        # 2026-11-08：前端新建的体系（origin=view_edit）不参与 PATCH 重置，
        # 保留用户登记的成员与显式边；人工维护的体系仍按 PATCH 审核。
        if item.get("origin") == "view_edit":
            continue
        patch = PATCH.get(item["key"], {})
        target = {
            "chain_edges": patch.get("chain_edges", []),
            "alternatives": patch.get("alternatives", {}),
            "warning_edges": patch.get("warning_edges", []),
        }
        # 2026-11-06：未在 PATCH 声明 review_note 的体系保留现有说明，
        # 不再用 DEFAULT_REVIEW 覆盖（树海等体系的正文说明较长）。
        if "review_note" in patch:
            target["review_note"] = patch["review_note"]
        for key, value in target.items():
            if item.get(key) != value:
                item[key] = value
                changed += 1
        if "core" in patch and item.get("core") != patch["core"]:
            item["core"] = patch["core"]
            changed += 1
        if "support" in patch and item.get("support") != patch["support"]:
            item["support"] = patch["support"]
            changed += 1
        if "chain_status_override" in patch and item.get("chain_status_override") != patch["chain_status_override"]:
            item["chain_status_override"] = patch["chain_status_override"]
            changed += 1
        if "external_append" in patch:
            note = patch["external_append"]
            external = item.get("external", [])
            if note not in external:
                item["external"] = external + [note]
                changed += 1

    doc["edge_rule"] = (
        "同队联动只认 chain_edges 中逐条写明的有向边（正文写出资源交接／先后顺序／机制互相放大）；"
        "core/support/counter 是成员名单，禁止再按名单位置或笛卡尔积推断联动。"
        "alternatives 记录并列／二选一／按对局补位，只是同一骨架的择一组件，不是同队配合，也不等于 role_groups.json 的相似定位组（后者只由共享同一特色机制构成）。"
        "chain_edges 为空的体系即使标签是「顺序链已核」，也没有可推荐的精灵两两配合；查不到就是没有关联。"
    )
    doc["version"] = "2026-11-05-explicit-edges"
    # 2026-11-08：前端关系联动编辑优先级最高，避免 PATCH 把用户编辑回退。
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apply_edge_view_edits import apply_current_state as _apply_edge_state
    _apply_edge_state(doc)

    SYSTEMS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    edges = sum(len(x["chain_edges"]) for x in doc["systems"])
    print("strict links: %d systems, %d explicit chain edges, %d field updates" %
          (len(doc["systems"]), edges, changed))
    for item in doc["systems"]:
        if item["chain_edges"]:
            print("  %-16s %s" % (item["name"], item["chain_edges"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

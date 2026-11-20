"""按交接文档口径补齐可核验的配队顺序链（幂等）

2026-11-06 复核：tactics.md 已写出「首发压制 → 队友在资源空窗兑现」、
「乌拉增益 → 混地／安卡放大」这类资源交接与机制互相放大，但
systems.json 里「极渊 PP 清零体系」「乌拉诺斯联攻体系」仍标
「仅成员清单（无顺序正文）」、chain_edges 为空，前端因此查不到配合。

本脚本只补这两项 evidence_grade=实战／月榜、正文可核的有向边：
  * 4797→4468、4797→3711（pressure：先压 PP／抢人头差，后由队友兑现）
  * 4126→3516、4126→4219（resource：先建立乌拉增益／血契，后放大）
并在 tactics.md 对应章节补出明确「顺序」小节，供 build_chain_audit.py
把 chain_status 判为「顺序链已核」。

明确不补（HANDOVER.md 第 2 节口径）：
  * 受益者名单：奥菲利娅事件体系、斯布林蒂表格六条受益位；
  * 并列位：猫阵「另一条发动机」4126／3986、树海 alternatives；
  * 双向资源博弈：咤克斯琉梦体系（不是单向交接）；
  * 用户明令不登记的 4853／4605 曝压制体系；
  * evidence_grade 非「实战／月榜」的 16 项顺序链待核体系，补证据前不进同队组。

用法: python scripts/apply_relation_completion.py
"""

import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SYSTEMS = ROOT / "references" / "catalog" / "systems.json"
TACTICS = ROOT / "references" / "docs" / "tactics.md"

PATCH = [
    {
        "name": "极渊 PP 清零体系",
        "chain_edges": [[4797, 4468], [4797, 3711]],
        "edge_meta": {
            "4797-4468": {
                "type": "pressure",
                "note": "4797 首发双消、先三控制与第五让双方 PP 清零，压出对手技能资源空窗；4468 在该空窗叠层破局，顺序是先压资源后兑现",
            },
            "4797-3711": {
                "type": "pressure",
                "note": "4797 的 PP 压制与人头差为 3711 创造第五连压空间；3711 中切回 PP、叠层并用第五跳拦截，承接上一棒的回合差",
            },
        },
        "review_note": "正文写 4797 首发双消／第五双方 PP 清零制造资源空窗，4468 在该空窗叠层破局、3711 借人头差第五连压；2026-11-06 按正文补两条 pressure 显式边。support 的 4288 龙塔是限制组件，不是资源交付对象。",
        "anchor": "- **共同失败**：第五 PP 清零同样影响自己、极渊特性共振被针对、后续核心没有足够的免控/返场资源。",
        "marker": "- **顺序（2026-11-06 按正文补齐显式链）**：① 4797 首发",
        "addition": (
            "- **顺序（2026-11-06 按正文补齐显式链）**：① 4797 首发用先三控制、双消与第五让双方 PP 清零，"
            "压出对手技能资源空窗 → ② 4468 在该空窗叠层破局，或 3711 中切回 PP、叠层并用第五跳拦截连压。"
            "两条都是「先压资源、后由队友兑现」的 `pressure` 型顺序链，方向不可逆；4797 第五同时清空自身 PP，"
            "后续核心须自带免控／返场资源。support 的 4288 龙塔是稳定限制组件，不是资源交付对象，不登记为配合边。\n"
        ),
    },
    {
        "name": "乌拉诺斯联攻体系",
        "chain_edges": [[4126, 3516], [4126, 4219]],
        "edge_meta": {
            "4126-3516": {
                "type": "resource",
                "note": "4126 的乌拉增益先放大 3516 的护盾循环与混伤，3516 提供高容错站场；正文写明「增益放大」，属增益交接",
            },
            "4126-4219": {
                "type": "resource",
                "note": "4126 增益把 4219 对策拿到的回合差转化为真实突破，先建立增益后才有突破收益，方向不可逆",
            },
        },
        "review_note": "正文写 4126 增益放大 3516 护盾循环与混伤、把 4219 对策拿到的回合差转化为真实突破；2026-11-06 按正文补两条 resource 显式边。support 的 4797／4808／3986 是「受益者节奏不同」的并列发动机（猫阵体系把 4126／3986 记为另一条发动机），不登记为配合边。",
        "anchor": "- **共同风险**：乌拉被 Ban、增益被全场机制反用、受益者各自需要不同的首发/死切节奏。",
        "marker": "- **顺序（2026-11-06 按正文补齐显式链）**：① 4126",
        "addition": (
            "- **顺序（2026-11-06 按正文补齐显式链）**：① 4126 在出战背包或主动切换时先建立乌拉增益／神王血契 → "
            "② 3516 承接增益放大护盾循环与混伤，或 4219 把对策拿到的回合差转化为真实突破；两条都是 `resource` 型交接链。"
            "「4126 + 3516」正文里的「安卡中切是反向对位」指对手侧的反制，不写成队友；本节登记的 4126→4219 是另一条同队增益链。"
            "support 的 4797／4808／3986 是「受益者节奏不同」的并列发动机（猫阵体系把 4126／3986 记为「另一条发动机」），"
            "按口径不登记为配合边，本组不把受益者名单两两展开。\n"
        ),
    },
    {
        "name": "咤克斯琉梦体系",
        "chain_edges": [[4761, 4762]],
        "edge_meta": {
            "4761-4762": {
                "type": "shared_event",
                "note": "战斗开始按对手秒杀／瞬杀特性数量结算：4761 希望之花据此给己方危机感层数，4762 同时把对方的秒杀效果改为自身获得 1 层魔王咒怨，两者共享同一事件源而不是单向交付",
            },
        },
        "review_note": "2026-11-06 复核 W:4761／W:4762 魂印与 B 站配置记录第 49 期（点名咤克斯、琉梦处理瞬杀）后登记为 shared_event 共享事件边；不是「琉梦单向给咤克斯当补丁」。",
        "anchor": "- **关键**：不要把琉梦只当“咤克斯补丁”，双方资源交换会随希望之花是否被摧毁而反转。",
        "marker": "- **顺序（2026-11-06 按魂印共享事件补齐显式链）**",
        "addition": (
            "- **顺序（2026-11-06 按魂印共享事件补齐显式链）**：① 战斗开始时按对手「秒杀／瞬杀」特性数量结算，"
            "4761 希望之花据此累计己方危机感，4762 同时把对方的秒杀效果改为自身获得 1 层魔王咒怨（W:4761、W:4762；"
            "B 站配置记录第 49 期亦点名这两只处理瞬杀）→ ② 4761 提供团队减伤与免秒杀、登场弹控，4762 靠满体双消与"
            "非满体护盾护罩运营咒怨到斩杀线 → ③ 希望之花是否被摧毁决定双方资源交换的反转时点。"
            "登记为 `shared_event` 共享事件边，只表示同一事件源同时喂给两条机制，**不写成琉梦单向交付给咤克斯**，"
            "也不把「一起上场」当成顺序交接；当季梯度仍待具体月份竞技图鉴复核。\n"
        ),
    },
]


def main() -> None:
    guard_legacy(__file__)
    doc = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    by_name = {x["name"]: x for x in doc["systems"]}
    changed_systems = 0
    for patch in PATCH:
        item = by_name.get(patch["name"])
        if not item:
            raise SystemExit("missing system: " + patch["name"])
        if item.get("chain_edges") != patch["chain_edges"] or \
                item.get("edge_meta") != patch["edge_meta"] or \
                item.get("review_note") != patch["review_note"]:
            item["chain_edges"] = patch["chain_edges"]
            item["edge_meta"] = patch["edge_meta"]
            item["review_note"] = patch["review_note"]
            changed_systems += 1
    if changed_systems:
        SYSTEMS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    text = TACTICS.read_text(encoding="utf-8")
    changed_tactics = 0
    for patch in PATCH:
        anchor = patch["anchor"]
        if anchor not in text:
            raise SystemExit("tactics anchor missing for " + patch["name"])
        if patch["marker"] not in text:
            text = text.replace(anchor, anchor + "\n" + patch["addition"].rstrip("\n"), 1)
            changed_tactics += 1
    if changed_tactics:
        TACTICS.write_text(text, encoding="utf-8")

    print("relation completion: systems patched %d, tactics sections patched %d, "
          "explicit edges now %d" %
          (changed_systems, changed_tactics,
           sum(len(x.get("chain_edges", [])) for x in doc["systems"])))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登记「玛洛迪斯树海体系」并同步 3739 的客户端版魂印（幂等）。

2026-11-06 用户点名：玛洛迪斯（俗称「马」）有体系。本地 #3739 仍是旧魂印
（死亡 50% 重生／吸 300 体力），但 SeerAPI soulmark:1017 的客户端全文与
BWIKI 追加技能:29211「浩域森罗」已经改版为「苍茫树海」：

  * 树海生命力＝玛洛迪斯的临时体力上限，每 210 点替在场精灵触发 1 次
    苍茫之森（对方用技能后）／灵魂指引（回合结束时）；
  * 对方使用技能后，场下的玛洛迪斯受到等同威力值的真实伤害；
    回合结束后临时体力上限里没有体力值则树海消失；
  * 4500 武心婵（场下体力/PP 不会减少）与 4814 娜诺（用户口语「诺娜」）
    是场下保护位；3613 草王（芳馨祝福 500 点临时体力上限）与 4600 斯布林蒂
    （3 级链接同步体力上限给下只）是体力上限供给位。

4814 不在 227 只活跃总表、也没有深研定位，按项目口径只登记为资料层同位
参照，不写 chain_edges、不生成同队卡片（否则 roster.synergies 无法双向互证）。

用法：python scripts/apply_tree_sea_system.py
之后按重建链跑 build_chain_audit.py → apply_link_cleanup.py →
build_chain_audit.py → build_depth_audit.py → build_full_audit.py →
build_spirit_index.py → build_synergy_view.py → check_roster.py。
"""
from __future__ import annotations
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "references"
DATA = ROOT / "data"

SECTION = "玛洛迪斯树海体系：苍茫树海的层数、保位与体力上限交接（2026-11-06 用户点名复核）"

SYSTEM_KEY = "玛洛迪斯树海体系"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, doc) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def client_soul() -> tuple[str, str]:
    """从官方 seerapi-cli 落盘层取 soulmark:1017 的客户端全文与摘要。"""
    seerapi = load(DATA / "seerapi/seerapi.json")
    mark = seerapi["pets"]["3739"]["soulmarks"][0]
    assert mark["id"] == 1017, "3739 soulmark id changed, re-check seerapi.json"
    return mark["full"], mark["desc"]


def patch_soul_full(full_text: str, desc: str) -> None:
    path = DATA / "seerapi/soul_full.json"
    doc = load(path)
    entry = doc["souls"]["3739"]
    old = entry.get("text", "")
    if "苍茫树海" not in old:
        entry["bw_wiki_text"] = old
    entry["text"] = full_text
    entry["full_len"] = len(full_text)
    entry["raw_len"] = len(full_text)
    entry["desc"] = desc
    entry["soulmark_id"] = 1017
    entry["current_source"] = "SeerAPI soulmark:1017 客户端版全文（BWIKI 魂印:1017 仍显示旧摘要）"
    entry["note"] = (
        "2026-11-06 用户点名复核：BWIKI 魂印:1017 页面与本地旧快照只写「死亡 50% 重生／吸 300 体力」，"
        "SeerAPI 客户端版 soulmark:1017 的 full 文本已包含「苍茫树海」整段；BWIKI 追加技能:29211"
        "「浩域森罗」的携带效果写明登场创造树海与 21% 临时体力上限，两处互相印证，判为魂印改版而非另一只精灵。"
        "旧摘要存 bw_wiki_text，机制判断一律以本条客户端全文＋技能页为准。"
    )
    doc["count"] = len(doc["souls"])
    save(path, doc)


def patch_pool(desc: str) -> None:
    path = DATA / "bwiki/pool.json"
    doc = load(path)
    for elf in doc["elves"]:
        if elf["id"] != 3739:
            continue
        elf["soul"] = (
            "苍茫树海（客户端版 soulmark:1017）：树海生命力＝玛洛迪斯临时体力上限，"
            "每 210 点替在场精灵触发 1 次苍茫之森／灵魂指引；对方用技能后场下玛洛迪斯受等同威力真伤，"
            "临时上限打空则树海消失。旧版「死亡 50% 重生／吸 300 体力」效果仍保留，"
            "全文见 data/seerapi/soul_full.json 的 3739 条。"
        )
        elf["soul_client_desc"] = desc[:200]
        elf["soul_version_note"] = (
            "2026-11-06 按 SeerAPI soulmark:1017 客户端版与 BWIKI 技能:29211 更新；"
            "自动层 clauses/tier/score 仍是旧魂印时代的机制复杂度快照，不得当强度依据，"
            "全文以 data/seerapi/soul_full.json 的 3739 条为准。"
        )
        break
    save(path, doc)


DEEP_DIVE = {
    "conditions": (
        "玛洛迪斯携带追加技能「浩域森罗」(29211) 并在己方场上没有苍茫树海时登场；"
        "队友必须先把临时体力上限交到它手上，且出战背包里有场下体力保护位。"
    ),
    "sequence": (
        "①草王 3613 阵亡给下只 500 点临时体力上限，或大姐 4600 保持 3 级未来链接主动下场、"
        "把自身体力上限同步给下只；②玛洛迪斯作为「下只出战精灵」携浩域森罗登场，"
        "获得最大体力 21% 临时体力上限并恢复等量体力、创造苍茫树海；"
        "③武心婵 4500 位于出战背包常驻保护，双方场下精灵体力与 PP 不减少，"
        "挡掉「对方用技能→场下玛洛迪斯受等同威力真伤」；"
        "④对方每次用技能后，树海按生命力每 210 点替在场精灵触发 1 次苍茫之森，"
        "回合结束再按层数触发灵魂指引并给玛洛迪斯回 2 点 PP。"
    ),
    "resources": (
        "至少 3 个背包位（树海载体＋体力上限供给位＋场下保护位）；草王路线要牺牲一个阵亡位，"
        "大姐路线要一次主动下场且链接保持 3 级；玛洛迪斯的追加技能位与 PP；"
        "临时体力上限的持续时间（草王芳馨祝福免疫结束后失去）；每 210 点生命力＝1 次触发的分档。"
    ),
    "bp_cost": (
        "3739 当前期为准限制池位（见 references/catalog/official_pool.json），再叠加保护位与供给位的池成本；"
        "用三个位置换一个「树海不消失」的持续收益，前两回合几乎没有主动破局能力。"
    ),
    "failure_points": (
        "武心婵只锁「场下体力/PP 减少」，挡不住直接令不在场精灵死亡或交换体力类效果；"
        "娜诺保护要求自身存活且场下精灵体力已不满，首次真伤仍会扣；"
        "草王的 500 点临时体力上限在芳馨祝福免疫结束后失去，树海生命力随之下降甚至消失；"
        "大姐路线需要 3 级链接＋主动下场，链接被消耗或被击败即断供；"
        "对手高威力技能连发、断回合或清场效果会直接打空树海。"
        "无当季月榜／实战录像，当月梯度待月榜复核。"
    ),
    "replacement_check": (
        "无完全上位：3613 与 4600 都是「临时／同步体力上限交给下只」，但交付方式不同（阵亡祝福 vs 主动下场）；"
        "4500 与 4814 都是场下体力保护，但 4500 无条件锁体力与 PP、4814 只在体力不满时锁且需自身存活。"
        "4921 天堂极龙兽的临时体力上限来自自身恢复溢出、且给对手加上限，不能交给玛洛迪斯，不进本体系。"
        "这些是并列位，不是彼此的同队配合，也不构成相似定位组。"
    ),
    "verified_at": "2026-11-06",
    "soul_source": "SeerAPI soulmark:1017 客户端版全文 / BWIKI 技能:29211 浩域森罗 / 4500·4814·3613·4600 魂印全文",
}


def patch_roster() -> None:
    path = REF / "catalog" / "roster.json"
    doc = load(path)
    by_id = {x["id"]: x for x in doc["spirits"]}
    item = by_id[3739]
    old_roles = list(item.get("roles", []))
    item["roles"] = ["体系轴", "持续压制"]
    item["legacy_roles"] = sorted(set(item.get("legacy_roles", []) + old_roles))
    item["mechanics"] = [
        "苍茫树海：生命力＝玛洛迪斯临时体力上限，每 210 点替在场精灵触发 1 次苍茫之森／灵魂指引",
        "追加技能浩域森罗(29211)：登场时若无树海则获得最大体力 21% 临时体力上限并创造树海",
        "负面：对方用技能后场下玛洛迪斯受等同威力真伤，临时体力上限打空则树海消失",
        "旧版「死亡 50% 重生／吸 300 体力」已被客户端版取代，旧文留痕 data/seerapi/soul_full.json",
    ]
    item["play"] = (
        "成立条件：携带追加技能浩域森罗，己方场上没有苍茫树海，且玛洛迪斯是「下只出战精灵」。"
        "顺序：先由草王 3613 阵亡给下只 500 点临时体力上限，或大姐 4600 保持 3 级未来链接主动下场、"
        "把自身体力上限同步给下只；再由玛洛迪斯登场，按叠加后的临时体力上限创造树海——"
        "生命力每 210 点就是 1 次苍茫之森（对方用技能后）与灵魂指引（回合结束）的触发层数，"
        "所以提高体力上限就是提高层数。随后武心婵 4500 只要在出战背包，双方场下精灵体力与 PP 不减少，"
        "挡住「对方用技能→场下玛洛迪斯受等同威力真伤」这条负面，树海不被打空；"
        "娜诺 4814 是同位替代但要求自身存活且场下体力已不满，首次真伤仍会扣，保护更弱。"
        "资源：至少 3 个背包位、追加技能位与 PP、下只登场顺序、芳馨祝福免疫结束会失去临时体力上限。"
        "失效点：武心婵挡不住直接令不在场精灵死亡／交换体力；草王临时上限会随祝福结束消失；"
        "大姐需 3 级链接＋主动下场；对手高威力连发或断回合可直接打空树海。"
        "本条按客户端版魂印与技能页逐条核过，当月梯度待月榜复核，不推断胜率与名次。"
    )
    item["sources"] = ["T202606", "W:3739", "SA:1017", "SK:29211", "U202611"]
    item["deep_dive"] = DEEP_DIVE
    item["soul_version"] = "2026-11-06 客户端版（苍茫树海），BWIKI 旧摘要存 bw_wiki_text"
    # 显式边由 apply_link_cleanup.py 统一双向补齐，这里不手写 synergies。
    save(path, doc)

    core = REF / "catalog" / "core_roles.json"
    cdoc = load(core)
    cdoc["spirits"]["3739"] = ["体系轴", "持续压制"]
    cdoc["generated_at"] = date.today().isoformat()
    cdoc["stats"] = cdoc.get("stats", {})
    cdoc["stats"]["spirits"] = len(cdoc["spirits"])
    save(core, cdoc)


def build_system() -> dict:
    return {
        "key": SYSTEM_KEY,
        "name": SYSTEM_KEY,
        "aliases": ["苍茫树海", "马＋武婵", "树海层数流"],
        "core": [3739],
        "support": [3613, 4600, 4500, 4814],
        "counter": [],
        "kind": "同队联动",
        "evidence": "用户明确判定＋SeerAPI 客户端魂印与 BWIKI 技能页核验",
        "sources": ["W:3739", "SA:1017", "SK:29211", "W:3613", "W:4600",
                    "W:4500", "W:4814", "U202611"],
        "section": SECTION,
        "carrier": (
            "玛洛迪斯携带追加技能浩域森罗(29211) 登场，获得最大体力 21% 临时体力上限并创造苍茫树海；"
            "树海生命力等同该临时体力上限，每 210 点替在场精灵触发 1 次苍茫之森／灵魂指引。"
            "对方用技能后场下玛洛迪斯受等同威力真伤，临时上限打空树海即消失，"
            "因此需要先垫高体力上限、再锁住场下体力。"
        ),
        "status": "机制链已核；当月梯度待月榜复核",
        "evidence_grade": "社区／攻略",
        "chain_status_override": "顺序链已核",
        "chain_status": "顺序链已核",
        "chain_edges": [[3613, 3739], [4600, 3739], [4500, 3739]],
        "edge_meta": {
            "3613-3739": {
                "type": "resource",
                "note": "草王阵亡后芳馨祝福给下只出战精灵 500 点临时体力上限；玛洛迪斯必须是那只下只精灵，树海生命力按叠加后的临时体力上限计算，每 210 点多 1 次触发。",
            },
            "4600-3739": {
                "type": "resource",
                "note": "斯布林蒂保持 3 级未来链接并主动下场，把自身体力上限值同步给下只出战的玛洛迪斯；这一步决定树海生命力与 210 点分档层数，不是同队增伤。",
            },
            "4500-3739": {
                "type": "cover",
                "note": "武心婵只要在出战背包就令双方场下精灵体力、PP 不会减少，挡住「对方用技能→场下玛洛迪斯受等同威力真伤」，使临时体力上限不被打空、树海不消失；属常驻保护位而非登场先后顺序。",
            },
        },
        "alternatives": {
            "场下体力保护位（二选一，不是配合）": [4500, 4814],
            "临时体力上限供给位（二选一，不是配合）": [3613, 4600],
        },
        "review_note": (
            "用户 2026-11-06 点名「马＋武心婵/诺娜解决树海消失、草王/大姐提高体力上限增加层数」。"
            "「诺娜」＝4814 娜诺（字序倒置的俗称，不是另一只精灵）。机制按 SeerAPI soulmark:1017 客户端全文、"
            "BWIKI 技能:29211 浩域森罗及 4500/4814/3613/4600 魂印逐条核过；"
            "chain_status_override 只表示机制顺序成立，不代表有当季月榜或实战录像，当月梯度待月榜复核。"
            "4814 不在 227 只活跃总表且无深研定位，按项目口径登记为资料层同位参照："
            "它的保护要求自身存活且场下体力已不满，首次真伤仍会扣，弱于 4500；不写 chain_edges、不生成同队卡片。"
            "4500/4814 与 3613/4600 都是并列位，彼此不是配合、也不构成相似定位组；"
            "4921 天堂极龙兽的临时体力上限只来自自身恢复溢出且给对手加上限，不能交给玛洛迪斯，已排除。"
        ),
        "warning_edges": [],
        "chain_review": {
            "body_chars": 0,
            "elements": [],
            "short_body": False,
            "single_core": True,
        },
    }


def patch_systems() -> None:
    path = REF / "catalog" / "systems.json"
    doc = load(path)
    doc["systems"] = [x for x in doc["systems"] if x.get("key") != SYSTEM_KEY]
    doc["systems"].append(build_system())
    doc["version"] = "2026-11-06-tree-sea"
    save(path, doc)


def main() -> int:
    guard_legacy(__file__)
    full_text, desc = client_soul()
    patch_soul_full(full_text, desc)
    patch_pool(desc)
    patch_roster()
    patch_systems()
    print("tree-sea system registered:")
    print("  soul_full#3739 -> SeerAPI soulmark:1017 full (%d chars), old text kept" % len(full_text))
    print("  roster#3739   -> roles 体系轴/持续压制 + deep_dive 六要素 + 4 sources")
    print("  systems       -> %s, core [3739], 3 chain_edges, 2 alternatives" % SYSTEM_KEY)
    print("  note          -> 4814 娜诺 stays an outside-layer reference (not in master list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

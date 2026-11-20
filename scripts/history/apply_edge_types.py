#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 2026-11-05 那 18 条显式联动边标类型（幂等）

注：2026-11-06 新增的 4 条边（极渊／乌拉诺斯）与树海 3 条边的
edge_meta 由 scripts/apply_relation_completion.py 与
scripts/apply_tree_sea_system.py 自带，本脚本不处理这些体系的 key。

用户 2026-11-06：「不能关联别瞎关联，没关联就没关联直接说就行」。
上一版把所有正文可核的边一律叫「同队配合」，但其中只有一部分是直接资源
交接，其余是状态制造、保护位、共享事件或压制收割。标注类型后，前端不再
把「共享同一颗人头」与「把护盾交给下一棒」混为一谈。

类型：
  resource     直接资源交接（PP同步／传承／增伤／星赐）
  state        状态制造后由队友按该状态结算（烧伤→神惧劫炎、低PP→烛）
  cover        保护位／跳板／封属，为队友创造安全登场或站场窗口
  shared_event 两者共享同一个事件收益，但不互相改变结算
  pressure     压血线／压资源后由队友收割，属顺序兑现而非直接交接
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "references"

EDGE_META = {
    "清PP体系": {
        "4333-4620": ("state", "4333 让对手随机技能 PP 归零；4620 烛点燃期间按对手最低／最高 PP 技能封锁先制与命中，直接吃低 PP 状态"),
        "3613-4620": ("state", "3613 按对手所选技能类型随机归零 PP；4620 的烛按对手 PP 结构结算，属同一状态的两种挂载"),
    },
    "空贝罗体系": {
        "4169-4586": ("shared_event", "两者共享「己方阵亡」这一个事件：神罗给对手当前精灵叠致命裂痕，空元把阵亡的不在场精灵消逝成诗章；同一颗人头喂两个收益，但互不改变对方结算"),
        "4184-4586": ("pressure", "贝狄薇尔用领域限伤与 PP 压制把对手压到斩杀线，空元再抹诗章兑现击杀；是先后兑现，不是直接把资源交给空元"),
    },
    "多保一体系": {
        "4510-4515": ("resource", "卫岳阵亡时解放拥君之盾／绝缘之罩，给己方 2 回合攻击伤害 +100% 或固伤／百分比 +50%；霍光在窗口内拿首杀并转北冥狂刃"),
    },
    "伞邪双诛魔体系": {
        "4364-4554": ("resource", "尤莉米特死亡时消耗所有群辉加护，每层让下只精灵登场后首次技能附加「群芳加护消失时所受攻击伤害 20%」的百分比伤害；邪魇承接这一段，再用诛魔杀阵叠对手上次伤害固伤"),
    },
    "圣武星魂体系": {
        "4800-4677": ("cover", "4800 位于背包时双方登场受砥砺，改变 4677 的叠层与登场环境；砥砺对双方都生效，不是单向增益，因此只算环境位"),
    },
    "斯布林蒂PP同步体系": {
        "4600-4503": ("resource", "斯布林蒂主动下场后按未来链接等级把体力上限／体力／PP 同步给下只精灵；库坦把同步来的低 PP 转成零 PP 流血"),
    },
    "无为龙塔体系": {
        "4288-4661": ("cover", "龙塔的贤／威／霸之庇护给己方在场精灵免控、减先制、护盾，为无为准出安全中切与 PP 反转的回合"),
    },
    "蓓丽安特星执体系": {
        "4643-4648": ("resource", "蓓丽安特被击败后消逝并化身星执者，把己方进入记录异常转化为 3 回合星赐；鲁斯王承接星赐与真伤续航"),
    },
    "猫阵体系": {
        "4541-4808": ("cover", "莫塔里安登场护罩／免异常／束缚与全属性 +1，作为猫的安全登场跳板；是保护位，不是把增益交给猫"),
        "4169-4808": ("state", "神罗给对手当前精灵叠致命裂痕（受伤 +25% 起），猫用先制 +3 与消回合流血在裂痕窗口内撕开对手"),
    },
    "龟阵逼退体系": {
        "4676-4762": ("cover", "米斯蒂克登场 2 回合封属并压低对手输出，咤克斯靠满血消回合／非满血护盾护罩站住，属封属保护位"),
    },
    "烧伤流体系": {
        "4622-4875": ("state", "希拓回合开始 100% 烧伤；上古炎兽在对手烧伤时获得神惧劫炎，直接按该状态结算"),
        "4875-4219": ("state", "上古炎兽在对手使用攻击时挂烧伤；安卡在对手烧伤时全属性 -1 并获先制 +1，按同一状态结算"),
    },
    "天女传承体系": {
        "4872-4125": ("resource", "妙时天女防御位令己方下 1 只出战精灵挡 1 次攻击且出战时 100% 砥砺；列奥尼达承接砥砺并检测场上异常"),
        "4872-4800": ("resource", "同上，传承只给下 1 只；无极圣武承接砥砺，但砥砺是否计入英雄之耀仍待核"),
        "4872-4288": ("resource", "同上，传承只给下 1 只；机械塔克林按登场结算启动龙械图腾"),
    },
}


def main():
    guard_legacy(__file__)
    path = REF / "catalog" / "systems.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    missing = []
    for item in doc["systems"]:
        meta = EDGE_META.get(item["key"])
        if not meta:
            continue
        edges = {"%d-%d" % (a, b) for a, b in item.get("chain_edges", [])}
        out = {}
        for key, (etype, note) in meta.items():
            if key not in edges:
                missing.append((item["key"], key))
                continue
            out[key] = {"type": etype, "note": note}
        if out and item.get("edge_meta") != out:
            item["edge_meta"] = out
            changed += 1
    # 校验：每条边都必须有类型
    untyped = []
    for item in doc["systems"]:
        for a, b in item.get("chain_edges", []):
            if "%d-%d" % (a, b) not in (item.get("edge_meta") or {}):
                untyped.append((item["key"], a, b))
    if untyped:
        print("ERROR untyped edges:", untyped)
        raise SystemExit(1)
    if missing:
        print("WARN meta keys not on any edge:", missing)
    if changed:
        doc["version"] = "2026-11-06-edge-types"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print("systems with edge_meta: %d | edges typed: %d"
          % (sum(1 for x in doc["systems"] if x.get("edge_meta")),
             sum(len(x.get("edge_meta") or {}) for x in doc["systems"])))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按官方 seerapi-cli 复核结果修正数据层（幂等，可复现）

2026-11-06 用官方 CLI（SeerAPI/seerapi 自带 seerapi-cli skill）逐条核出：
  * soulmark:410 的 desc 比 BWIKI 精确：限定 100 级、受到致死伤害且死亡、
    附加的是「自身当回合所受技能伤害」的真实伤害、对手体力为 0 才回 1 点。
  * soulmark:1588 带 desc_formatting_adjustment（当前生效版），2080 只有 desc
    （旧版）→ 旧规则「取最长文本为当前版」在 4364 上是错的，已改 compare_souls.py。
  * skill:17908「诛魔杀阵」有三段效果，且确实在圣光灵神 3311 的技能表里；
    本地技能库此前没有收录该技能，体系第三段缺落盘数据。

用法: python scripts/apply_seerapi_cli_fixes.py
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REF = ROOT / "references"

# SeerAPI soulmark:1588 的 desc_formatting_adjustment 清洗版（当前生效版）
SOUL_4364 = """群芳加护：
自身每次登场后获得群芳加护：
对手拥有回合类效果时，100%闪避对手的技能
自身被技能命中后，恢复对手所携带不同类型技能数*120的体力
若自身被攻击技能命中，则群芳加护消失
群芳加护消失后，下回合对手先制效果失效且以回合类效果形式1回合内无法主动切换精灵

群辉加护：
己方每只其他精灵首次登场后，自身获得1层群辉加护
自身被击败时，消耗自身所有群辉加护，每有1层群辉加护：
所有不在场精灵所有技能恢复1点PP
己方下只精灵登场后首次技能附加群芳加护消失时自身所受到攻击伤害20%的百分比伤害"""

# soulmark:2080（旧版 desc），只留痕不采用
SOUL_2080_DESC = ("自身出战时获得群辉加护；自身拥有群辉加护时，若对手处于回合类效果则自身闪避对手的技能，"
                  "若对手的技能命中自身则命中后对手每有1个与此技能类型不同的技能自身恢复120点体力，"
                  "若对手的技能未命中自身则此次技能结束时本次在场每闪避成功1次，吸取对手120点体力|"
                  "己方其他精灵首次出战时自身获得1层群芳加护；自身拥有群芳加护时，双方使用技能后自身与对手受到1点固定伤害，"
                  "然后若对手的体力未减少则本次在场自身造成的攻击伤害提升20%，"
                  "若自身的体力未减少则本次在场造成的固定伤害、百分比伤害提升20%，伤害提升效果均可叠加，"
                  "自身每有1层群芳加护最高可叠加1次|（boss无效）")

SOUL_410_DESC = ("自身于战斗阶段内受到致死伤害且死亡时，若自身的等级为100级，"
                 "则附加等同于自身当回合所受技能伤害的真实伤害，"
                 "然后若对手的体力为0则自身主动恢复1点体力|"
                 "自身使用技能之后，每回合结束后恢复自身最大体力的1/3（boss有效）"
                 "（标注部分boss有效，其余无效）")


def main():
    # ---- 1) soul_full.json ----
    guard_legacy(__file__)
    sf = DATA / "seerapi/soul_full.json"
    sd = json.loads(sf.read_text(encoding="utf-8"))

    r3056 = sd["souls"]["3056"]
    r3056["desc"] = SOUL_410_DESC
    r3056["soulmark_id"] = 410
    r3056["current_source"] = "SeerAPI soulmark:410（客户端版，desc + desc_formatting_adjustment）"
    r3056["note"] = (
        "2026-11-06 官方 seerapi-cli 复核：BWIKI 魂印:410 仍是旧版「致死技能伤害→扣除对手等额体力」，"
        "SeerAPI soulmark:410 客户端版为「100 级限定，战斗阶段内受到致死伤害且死亡时→附加等同自身当回合所受技能伤害的真实伤害；"
        "对手体力为 0 时自身恢复 1 点体力」。两源冲突已记录，采信客户端版；BWIKI 旧文存 bw_wiki_text。"
        "注意触发限定：等级不足 100、或非技能伤害致死，不按本条结算。")

    r4364 = sd["souls"]["4364"]
    r4364["superseded_text"] = r4364.get("text", "")
    r4364["text"] = SOUL_4364
    r4364["full_len"] = len(SOUL_4364)
    r4364["raw_len"] = len(SOUL_4364)
    r4364["desc"] = ("自身出战时获得群辉加护；自身拥有群辉加护时，若对手处于回合类效果则自身闪避对手的技能，"
                     "若对手的技能命中自身则命中后对手每有1个与此技能类型不同的技能自身恢复120点体力|"
                     "己方其他精灵首次出战时自身获得1层群芳加护（boss无效）")
    r4364["soulmark_id"] = 1588
    r4364["superseded_soulmark"] = 2080
    r4364["superseded_desc"] = SOUL_2080_DESC
    r4364["current_source"] = "SeerAPI soulmark:1588（唯一带 desc_formatting_adjustment 的当前生效版）"
    r4364["note"] = (
        "2026-11-06 官方 seerapi-cli 复核：4364 有两条 soulmark，"
        "1588 带游戏内格式化结算文本（当前版，群芳闪避＋群辉被击败传承），"
        "2080 只有 desc（旧版，双方受 1 点固伤／吸血）。"
        "本项目此前误按文本长度判当前版，已改为 has_format 优先；旧文存 superseded_text / superseded_desc。")
    sf.write_text(json.dumps(sd, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("soul_full.json: 3056/4364 已按官方 CLI 校正")

    # ---- 2) pool.json 的 soul 摘要同步 ----
    pf = DATA / "bwiki/pool.json"
    pd = json.loads(pf.read_text(encoding="utf-8"))
    for e in pd["elves"]:
        if e["id"] == 4364:
            e["soul"] = SOUL_4364.replace("\n", "<br>")
    pf.write_text(json.dumps(pd, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("pool.json: 4364 soul 已同步")

    # ---- 3) roster.json 措辞与来源标记 ----
    rf = REF / "catalog" / "roster.json"
    rd = json.loads(rf.read_text(encoding="utf-8"))

    def get(sid):
        return next(x for x in rd["spirits"] if x["id"] == sid)

    m = get(3056)
    m["mechanics"] = [
        "100 级限定：战斗阶段内受到致死伤害且死亡时，附加等同于自身当回合所受技能伤害的真实伤害",
        "对手体力为 0 时自身主动恢复 1 点体力",
        "自身使用技能之后，每回合结束恢复最大体力 1/3",
        "功能位强度不体现在种族值",
    ]
    m["play"] = (
        "①成立：100 级机盖在战斗阶段内被技能伤害致死，且对手没有免真实伤害／锁伤／免死手段。"
        "②死亡结算时按「自身当回合所受技能伤害」附加等额真实伤害——真实伤害无视常规减伤与护盾，"
        "等于用一条命换对手同等血量；对手体力归 0 时自身主动恢复 1 点体力，可先手补刀或换人收割。"
        "③未被一击打死时，自身使用技能后每回合结束恢复最大体力 1/3，靠回复压场，逼对手改用低威力连击或粉伤。"
        "④资源：一个兑子拦截位、自身出手权（回血链要求「使用技能之后」）、对手伤害类型与锁血状态。"
        "⑤BP：当前期官方池（2026-10-16 起）准限制池仍在列，限制赛要占名额；占一个必死位，"
        "与要求全员存活或走消逝复活的体系互斥。"
        "⑥失效：等级不足 100；免真实伤害／锁伤／免死；粉伤、百分比与固定伤害不按「所受技能伤害」结算；"
        "低威力连击打不死时只按实际伤害算；死亡后对手仍有补刀或先制手段；被控、锁切或无法出手则回血链不启动。"
        "⑦版本注记：BWIKI 魂印:410 仍写旧版「扣除对手等同于其造成攻击伤害数值的体力」，"
        "SeerAPI soulmark:410 客户端版为「附加真实伤害」；两版触发条件不同，本条目按客户端版写，"
        "BWIKI 旧文保留在 data/seerapi/soul_full.json 的 bw_wiki_text。")
    m["sources"] = ["O20261016", "O202608", "T202407", "W:3056", "SA:410"]
    dd = m["deep_dive"]
    dd["conditions"] = ("100 级特性生效；机盖在战斗阶段内受到技能伤害致死；"
                        "对手无免真实伤害／锁伤／免死")
    dd["sequence"] = ("中切或首发承接高数值攻击 → 战斗阶段内死亡 → 按自身当回合所受技能伤害附加等额真实伤害 → "
                      "对手体力为 0 时自身恢复 1 点体力 → 存活时用技能后每回合结束回最大体力 1/3 压场")
    dd["failure_points"] = ("等级不足 100；免真实伤害／锁伤／免死；粉伤、百分比与固定伤害不按所受技能伤害结算；"
                            "低威力连击打不死；死后被补刀；被控锁切无法出手则回血不启动")
    dd["soul_source"] = "SeerAPI soulmark:410（客户端版，官方 CLI 复核）＋ BWIKI 魂印:410（旧版对照）"

    y = get(4364)
    y["mechanics"] = [
        "每次登场获得群芳加护：对手有回合类效果时 100% 闪避其技能",
        "被技能命中后按对手所携不同类型技能数×120 回血",
        "被攻击技能命中则群芳加护消失，下回合锁切且先制效果失效",
        "己方每只其他精灵首次登场后叠 1 层群辉加护",
        "自身被击败时消耗全部群辉加护：每层让不在场精灵全技能回 1 PP",
        "每层另使下只精灵首次技能附加「群芳加护消失时自身所受攻击伤害 20%」的百分比伤害，累计 20%×层数",
        "技能击杀后 1-2 回合令对手攻击无法造成伤害且命中失效（击杀盔）",
    ]
    y["play"] = (
        "核心是被击败传承：登场后用群芳加护闪避与回血拖回合，被攻击技能命中后锁切锁先制；"
        "被击败时把群辉加护转成全队回 PP＋下只精灵首次技能附加 20%×层数 的百分比伤害。"
        "配合圣光灵神 3311 的「诛魔杀阵」（技能:17908，附加对手上次造成伤害数值的固伤，"
        "下 2 回合攻击伤害翻倍，遇天敌先制 +1）与圣谕邪魇第五的封攻击，构成伞邪双诛魔；"
        "体系怕封属、怕不杀伞、怕免粉与锁伤，当前环境难以上场。"
        "注意 4364 有两条 soulmark：1588 是带游戏内格式化结算文本的当前版，2080 是旧版（双方受 1 点固伤）。")
    y["sources"] = ["W:4364", "SK:35846", "SK:37340", "SK:17908", "SA:1588"]
    rf.write_text(json.dumps(rd, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("roster.json: 3056/4364 措辞与 SA 来源已更新")

    # ---- 4) skills_full.json 补资料层参照技能 17908 ----
    skf = DATA / "seerapi/skills_full.json"
    sk = json.loads(skf.read_text(encoding="utf-8"))
    sk["skills"]["17908"] = {
        "id": "17908", "name": "诛魔杀阵", "type": "物理攻击",
        "attr": "远古圣灵", "power": "80", "pp": "10", "priority": "3",
        "effect": ("附加对手上次造成伤害数值的固定伤害；下2回合自身造成的攻击伤害翻倍；"
                   "遇到天敌时先制+1"),
        "source": "SeerAPI skill:17908（官方 CLI 复核）",
        "skill_effects": [
            {"info": "附加对手上次造成伤害数值的固定伤害", "effect_id": 807, "args": []},
            {"info": "下2回合自身造成的攻击伤害翻倍", "effect_id": 776, "args": [2]},
            {"info": "遇到天敌时先制+1", "effect_id": 610, "args": [1]},
        ],
    }
    sk.setdefault("external_elves", {})["3311"] = {
        "name": "圣光灵神",
        "skills": ["17908"],
        "note": "伞邪双诛魔体系第三段挂件；体系正文资料层参照，不在深研层、不进 227 只总表",
        "source": "SeerAPI pet:3311（官方 CLI 复核，技能表 31 条含 17908）",
    }
    skf.write_text(json.dumps(sk, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("skills_full.json: 补 17908 与 external_elves.3311")
    print("  技能总数 %d / 深研精灵 %d / 资料层参照 %d" % (
        len(sk["skills"]), len(sk["elves"]), len(sk["external_elves"])))


if __name__ == "__main__":
    main()

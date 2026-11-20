#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地魂印与 SeerAPI 交叉比对，只产出「版本差异线索」，不自动改数据

2026-11-06 案例：4364 尤莉米特在 SeerAPI 有两条 soulmark——1588 是当前版
（群芳／群辉加护死亡传承，带 desc_formatting_adjustment），2080 是旧版
（双方受 1 点固伤，只有 desc）；本地曾存 2080，导致误判「诛魔不存在」。
该结论由 BWIKI 网页原文＋用户明确指认支撑，不是自动规则推出来的。

本脚本对每只深研精灵：
  * 取本地魂印文本与 SeerAPI 每条 soulmark.full
  * 用 2-gram 覆盖率判断本地最像哪一条
  * 记录每条是否有 desc_formatting_adjustment（has_format，版本信号）
  * 仅当本地与所有版本相似度 < 0.6 时登记待人工复核；多魂印的版本信号
    全部留痕到 version_signals，不作「谁是当前版」的结论

**禁止**按文本长度、ID 大小或 has_format 自动判定当前版并替换本地文本：
3711／4354／4125 的本地 BWIKI 文本与「无格式化文本」那条 cov≈1.0，
而带格式化文本的那条机制完全不同，谁生效必须抓网页／公告人工核。

用法:
  python scripts/patch_seerapi_formats.py   # 先补 has_format 字段
  python scripts/compare_souls.py --json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
DATA = ROOT / "data"

KEY_MECHS = ["复活", "消逝", "秒杀", "死亡时", "被击败时", "继承", "传承",
             "上限", "真实伤害", "百分比伤害", "封印", "锁", "免疫"]


def norm(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    return re.sub(r"\s+", "", t)


def grams(t):
    t = norm(t)
    return [t[i:i + 2] for i in range(len(t) - 1)]


def cov(a, b):
    ga = grams(a)
    if not ga:
        return 0.0
    gb = norm(b)
    return sum(1 for g in ga if g in gb) / len(ga)


def main():
    api = json.loads((DATA / "seerapi/seerapi.json").read_text(encoding="utf-8"))["pets"]
    local = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))["souls"]
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    pool_soul = {x["id"]: x.get("soul") or "" for x in pool["elves"]}
    roster = json.loads((REF / "catalog" / "roster.json").read_text(encoding="utf-8"))

    rows = []
    signals = []
    multi = 0
    for sp in roster["spirits"]:
        sid = sp["id"]
        pet = api.get(str(sid))
        if not pet:
            continue
        local_text = (local.get(str(sid)) or {}).get("text") or pool_soul.get(sid, "")
        if not local_text:
            continue
        cands = pet.get("soulmarks") or []
        if not cands:
            continue
        scored = []
        for c in cands:
            scored.append({
                "id": c["id"],
                "cov": round(cov(local_text, c["full"]), 3),
                "head": (c["full"] or "")[:90].replace("\n", " / "),
                "len": len(c["full"] or ""),
                "has_format": bool(c.get("has_format")),
            })
        if len(cands) > 1:
            multi += 1
        # 2026-11-06（官方 seerapi-cli 复核后修正）：
        # ① 「取最长文本判当前版」是错的——4364 旧版 2080 的 desc 反而更长。
        # ② 但 desc_formatting_adjustment 也不能反过来当「自动改数据」的依据：
        #    3711／4354／4125 的本地 BWIKI 文本与「无格式化文本」的那条 cov≈1.0，
        #    而带格式化文本的那条机制完全不同；谁是当前版必须抓 BWIKI 网页／公告人工核。
        #    （用户反复强调：自动规则不得直接当机制结论。）
        # 因此本脚本只输出「差异线索 + 版本信号」，不自动判定、不自动替换本地文本。
        by_cov = sorted(scored, key=lambda x: -x["cov"])
        by_len = sorted(scored, key=lambda x: -x["len"])
        best = by_cov[0]
        formatted = [x["id"] for x in scored if x["has_format"]]
        if len(cands) > 1:
            signals.append({
                "id": sid, "name": sp["name"],
                "local_matches": best["id"], "best_cov": best["cov"],
                "formatted_versions": formatted,
                "other_versions": [x["id"] for x in by_len if x["id"] != best["id"]],
            })
        # 只有「本地与 API 任一版本都对不上」才进待核队列。
        # 0.6 阈值避开纯排版差异（2987 的 BWIKI 旧格式 vs API 格式化文本 cov=0.66），
        # 同时能抓到 4002 御象灵尊（0.55）这类需要回原文核的。
        flag = ""
        if best["cov"] < 0.6:
            flag = "本地与所有 API 版本相似度低（可能改版、抓取差异或排版差异，须回原文核）"
        if flag:
            rows.append({
                "id": sid, "name": sp["name"], "flag": flag,
                "local_len": len(local_text),
                "versions": by_len,
                "local_matches": best["id"],
                "best_cov": best["cov"],
                "formatted_versions": formatted,
                "action": "只登记待核，不自动改本地文本",
            })

    print("multi-soulmark pets: %d | flagged: %d" % (multi, len(rows)))
    for r in rows:
        print("!!! %s %s | %s" % (r["id"], r["name"], r["flag"]))
        print("    local: %s" % norm(
            ((local.get(str(r["id"])) or {}).get("text") or pool_soul.get(r["id"], "")))[:100])
        for v in r["versions"]:
            print("    v%-5s cov %.2f len %-4s %s" % (v["id"], v["cov"], v["len"], v["head"]))

    if "--json" in sys.argv:
        doc = {
            "generated_at": "2026-11-06",
            "purpose": ("本地 soul_full 与 SeerAPI soulmark 的版本比对；只登记差异线索与待人工复核队列，"
                        "不自动判定当前生效版、不自动替换本地文本。"),
            "source": "https://api.seerapi.com/v1（GitHub: SeerAPI/seerapi，官方 seerapi-cli skill）",
            "policy": ("desc_formatting_adjustment（has_format）只是版本信号，不是判据。"
                       "4364 当前版 1588 的成立依据是 BWIKI 网页原文＋用户明确指认；"
                       "其余多魂印精灵必须逐只抓网页／公告复核，禁止按文本长度、ID 或 has_format 自动改数据。"),
            "stats": {"multi_soulmark": multi, "flagged": len(rows),
                      "spirits": len(roster["spirits"]),
                      "version_signals": len(signals)},
            "items": rows,
            "version_signals": signals,
        }
        (REF / "catalog" / "soul_version_diff.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written -> references/catalog/soul_version_diff.json")


if __name__ == "__main__":
    main()

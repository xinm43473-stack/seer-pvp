#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 SeerAPI（https://api.seerapi.com/v1）的魂印与巅峰池，做交叉校验

背景：2026-11-06 发现本地 `data/seerapi/soul_full.json` 的 4364 尤莉米特魂印是旧版
（双方受 1 点固伤），而 BWIKI 网页与 SeerAPI 都已是「群芳／群辉加护死亡传承」
版。只信本地快照会漏掉改版。

SeerAPI 是结构化数据平台（GitHub: SeerAPI/seerapi），字段：
  pet.soulmark[]            → 魂印 ID
  soulmark.desc             → 简版文本
  soulmark.desc_formatting_adjustment → 完整结算文本（含 indent/sprite/color 标签）
  pet.skill[]               → 技能 ID（含 is_fifth / is_advanced / priority）
  skill.skill_effect[].info → 逐条技能效果文本
  pet.peak_pool / peak_expert_pool / peak_cost_pool → 官方巅峰池

用法:
  python scripts/fetch_seerapi.py --ids 4364 4925 4594
  python scripts/fetch_seerapi.py --all-deep
  python scripts/fetch_seerapi.py --all-deep --with-skills   # 连技能一起抓（慢）
  python scripts/fetch_seerapi.py --all-deep --skip-existing # 只补缺的（旧行为，省时但会漏新魂印）

2026-11-20：默认**每次都重抓**。以前只在「没有魂印／缺 has_format」时才抓，
游戏给老精灵追加一条新魂印（如 3396 灾厄女神潘多拉 → soulmark 2170）本地永远看不到。
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
API = "https://api.seerapi.com/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r]+")


def get(url, retry=4):
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.load(resp)
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(1.5 * (i + 1))


def clean(text):
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = TAG_RE.sub("", text)
    text = WS_RE.sub(" ", text)
    lines = [x.strip(" \u3000") for x in text.split("\n")]
    return "\n".join(x for x in lines if x)


def fetch_pet(pid, with_skills=False):
    p = get(f"{API}/pet/{pid}")
    out = {
        "id": p["id"],
        "name": p.get("name"),
        "base_stats": p.get("base_stats"),
        "peak_pool": (p.get("peak_pool") or {}).get("id"),
        "peak_expert_pool": (p.get("peak_expert_pool") or {}).get("id"),
        "peak_cost_pool": (p.get("peak_cost_pool") or {}).get("id"),
        "soulmarks": [],
        "skills": [],
    }
    for ref in p.get("soulmark") or []:
        try:
            s = get(f"{API}/soulmark/{ref['id']}")
        except Exception as exc:
            print("  soulmark %s failed: %s" % (ref["id"], exc))
            continue
        fmt = s.get("desc_formatting_adjustment")
        out["soulmarks"].append({
            "id": s["id"],
            "desc": clean(s.get("desc")),
            "full": clean(fmt) or clean(s.get("desc")),
            # 2026-11-06（官方 seerapi-cli 复核）：游戏内格式化结算文本
            # desc_formatting_adjustment 只挂在「当前生效版」上；旧版通常只有 desc。
            # 因此 has_format 是判定新旧版的可靠信号，比文本长度更准。
            "has_format": bool(fmt),
            "pve_effective": s.get("pve_effective"),
            "intensified": s.get("intensified"),
            "tag": [x.get("name") if isinstance(x, dict) else x for x in (s.get("tag") or [])],
        })
        time.sleep(0.15)

    # 同一只精灵可能挂多条魂印：老版在前、新版在后（SeerAPI 的 soulmark id 递增）。
    # 展示侧「只显示最新一版」＝ id 最大的那条，这里排好序并打 latest 标记留痕。
    out["soulmarks"].sort(key=lambda m: int(m["id"]))
    for i, m in enumerate(out["soulmarks"]):
        m["latest"] = (i == len(out["soulmarks"]) - 1)

    if with_skills:
        for ref in p.get("skill") or []:
            sid = ref.get("skill", {}).get("id")
            if not sid:
                continue
            try:
                sk = get(f"{API}/skill/{sid}")
            except Exception:
                continue
            out["skills"].append({
                "id": sid,
                "name": sk.get("name"),
                "power": sk.get("power"),
                "priority": sk.get("priority"),
                "is_fifth": ref.get("is_fifth"),
                "is_advanced": ref.get("is_advanced"),
                "effects": [x.get("info") for x in (sk.get("skill_effect") or []) if x.get("info")],
            })
            time.sleep(0.12)
    return out


def main():
    path = DATA / "seerapi/seerapi.json"
    store = {"generated_at": time.strftime("%Y-%m-%d"),
             "source": "https://api.seerapi.com/v1",
             "pets": {}}
    if path.exists():
        store = json.loads(path.read_text(encoding="utf-8"))

    if "--all-deep" in sys.argv:
        roster = json.loads((ROOT / "references" / "catalog" / "roster.json").read_text(encoding="utf-8"))
        targets = [int(x["id"]) for x in roster["spirits"]]
    elif "--ids" in sys.argv:
        pos = sys.argv.index("--ids")
        targets = []
        for a in sys.argv[pos + 1:]:
            if a.startswith("--"):
                break
            if a.strip(",").isdigit():
                targets.append(int(a.strip(",")))
    else:
        print(__doc__)
        return

    with_skills = "--with-skills" in sys.argv
    refresh = "--refresh" in sys.argv
    skip_existing = "--skip-existing" in sys.argv
    if skip_existing and not refresh:
        # 旧行为：只补「没有魂印／缺 has_format」的。会漏掉游戏后来追加的魂印，慎用。
        todo = [i for i in targets
                if str(i) not in store["pets"]
                or not store["pets"][str(i)].get("soulmarks")
                or "has_format" not in (store["pets"][str(i)]["soulmarks"][0] or {})
                or (with_skills and not store["pets"][str(i)].get("skills"))]
    else:
        # 默认全量重抓：本地永远跟上 SeerAPI 的最新结算文本与最新魂印条数。
        todo = list(targets)
    print("fetching %d/%d pets (skills=%s, mode=%s)"
          % (len(todo), len(targets), with_skills, "skip-existing" if skip_existing and not refresh else "refresh"))
    for n, pid in enumerate(todo, 1):
        prev = store["pets"].get(str(pid)) or {}
        old_ids = [int(m["id"]) for m in (prev.get("soulmarks") or []) if m.get("id") is not None]
        try:
            store["pets"][str(pid)] = fetch_pet(pid, with_skills)
            new_ids = [int(m["id"]) for m in store["pets"][str(pid)]["soulmarks"]]
            extra = [i for i in new_ids if i not in old_ids]
            print("  [%d/%d] %s %s%s" % (n, len(todo), pid,
                                         store["pets"][str(pid)]["name"],
                                         ("  +魂印 " + ",".join(map(str, extra))) if extra else ""))
        except Exception as exc:
            print("  [%d/%d] %s FAILED: %s" % (n, len(todo), pid, exc))
        time.sleep(0.2)

    path.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print("saved %d pets -> %s" % (len(store["pets"]), path))


if __name__ == "__main__":
    main()

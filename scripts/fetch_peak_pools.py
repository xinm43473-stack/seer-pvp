#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取当前官方巅峰池，写入 references/catalog/official_pool.json

旧版 `build_strength.py` 把 2026-08-29 生效的 O202608 池成员硬编码在脚本里，
到 2026-11 已经过期。SeerAPI（GitHub: SeerAPI/seerapi）提供结构化池数据：

  peak_pool/{0,2,3}          count=0 禁止池 / count=2 限制池 / count=3 准限制池
  peak_expert_pool/0         专家池
  peak_cost_pool/{6,10,20,35} 费用池（6/10/20/35 点）

每期带 start_time / end_time。本脚本只记录当前期次，不做梯度换算——
池只证明 BP 成本与环境地位。

用法:
  python scripts/fetch_peak_pools.py
"""
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
DATA = ROOT / "data"
API = "https://api.seerapi.com/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

POOL_LABEL = {
    0: ("ban", "禁止池（一只都不能带）"),
    2: ("limit", "限制池（最多带 2 只）"),
    3: ("semi_limit", "准限制池（最多带 3 只）"),
}


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


def main():
    names = {}
    for f in (DATA / "bwiki/pool.json", REF / "catalog" / "manual_overrides.json"):
        if not f.exists():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        for e in doc.get("elves", doc.get("spirits", [])):
            if isinstance(e, dict) and e.get("id"):
                names[e["id"]] = e.get("name")

    api_doc = DATA / "seerapi/seerapi.json"
    if api_doc.exists():
        for pid, p in json.loads(api_doc.read_text(encoding="utf-8"))["pets"].items():
            names.setdefault(int(pid), p.get("name"))

    pools = {}
    period = None
    for pid, (key, label) in POOL_LABEL.items():
        d = get(f"{API}/peak_pool/{pid}")
        ids = [x["id"] for x in (d.get("pet") or [])]
        pools[key] = {
            "count": d.get("count"),
            "label": label,
            "ids": ids,
            "names": [names.get(i, str(i)) for i in ids],
        }
        period = period or {"start": d.get("start_time"), "end": d.get("end_time")}
        time.sleep(0.2)

    expert = get(f"{API}/peak_expert_pool/0")
    eids = [x["id"] for x in (expert.get("pet") or [])]
    pools["expert"] = {
        "count": expert.get("count"),
        "label": "专家池",
        "ids": eids,
        "names": [names.get(i, str(i)) for i in eids],
    }

    costs = {}
    for c in (6, 10, 20, 35):
        d = get(f"{API}/peak_cost_pool/{c}")
        cids = [x["id"] for x in (d.get("pet") or [])]
        costs[str(c)] = {"count": len(cids), "ids": cids}
        time.sleep(0.2)

    doc = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "source": "https://api.seerapi.com/v1/peak_pool（GitHub: SeerAPI/seerapi）",
        "period": period,
        "policy": "官方池只证明 BP 成本与环境地位，不换算梯度、不作胜率依据；期次变化后必须重跑本脚本并重建 strength.json。",
        "pools": pools,
        "cost_pools": costs,
    }
    out = REF / "catalog" / "official_pool.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("period:", period)
    for k in ("ban", "limit", "semi_limit", "expert"):
        print("  %-10s count=%s pets=%d" % (k, pools[k]["count"], len(pools[k]["ids"])))
    print("written ->", out)


if __name__ == "__main__":
    main()

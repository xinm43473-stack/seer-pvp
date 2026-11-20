#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取 SeerAPI 术语表（glossary_entry）到本地，供魂印专属名词说明使用。

数据源：https://api.seerapi.com/v1/glossary_entry?expand=true&limit=200（598 条，3 页）
产物：data/seerapi_media/raw/glossary_entry/{id}.json ＋ _index.json

只做原文搬运，不生成任何释义；前端展示的解释逐字来自这里。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "seerapi_media" / "raw" / "glossary_entry"
API = "https://api.seerapi.com/v1/glossary_entry"
UA = {"User-Agent": "Mozilla/5.0 (compatible; seer-peak-pvp/1.0)"}
PAGE = 200


def get(url: str, tries: int = 4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise SystemExit(f"抓取失败：{url} → {last}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    offset = 0
    while True:
        doc = get(f"{API}?expand=true&offset={offset}&limit={PAGE}")
        batch = doc.get("results") or []
        rows.extend(batch)
        offset += len(batch)
        total = doc.get("count")
        print(f"  {offset}/{total}")
        if not batch or (total and offset >= total):
            break
        time.sleep(0.3)

    for row in rows:
        sid = int(row["id"])
        path = OUT / f"{sid}.json"
        if path.exists():
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("hash") == row.get("hash"):
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index = {
        "source": f"{API}?expand=true",
        "count": len(rows),
        "ids": [int(r["id"]) for r in rows],
        "kinds": sorted({int(r["kind"]) for r in rows if isinstance(r.get("kind"), int)}),
    }
    (OUT / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with_desc = sum(1 for r in rows if (r.get("desc") or "").strip())
    print(f"glossary_entry: {len(rows)} 条（有释义 {with_desc}），kinds={index['kinds']}")


if __name__ == "__main__":
    main()

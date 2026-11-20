#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch complete soul-ability text from BWIKI for every ID in scope.

``data/bwiki/pool.json`` was built from an older raw dump whose soul text is often
truncated (e.g. 至序圣华 only 41 characters). That truncation is the root cause
of several false "single-clause soul, no core mechanic" drops. This script
queries the Semantic MediaWiki ask API in batches and stores the cleaned full
text in ``data/seerapi/soul_full.json`` without changing the auto-built tiers.

Usage:
  python scripts/fetch_souls_full.py                 # resume, all IDs
  python scripts/fetch_souls_full.py --ids 4321,4600
  python scripts/fetch_souls_full.py --batch 10 --delay 0.4
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = DATA / "seerapi/soul_full.json"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://wiki.biligame.com/seer/",
}
API = "https://wiki.biligame.com/seer/api.php"


def clean(text: str) -> str:
    """Strip SMW markup while KEEPING tooltip text.

    BWIKI stores part of long soul effects inside ``smwttcontent`` hover boxes.
    Dropping those spans loses real clauses (e.g. 至序圣华's 1/2/3-柄圣剑
    effects), so only tags are removed and all visible/hover text is retained.
    """
    text = str(text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</(p|div|li|tr)\s*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def ask(ids: list[int], timeout: float) -> dict:
    query = "[[分类:" + "||".join(str(i) for i in ids) + "]][[分类:魂印]]|?魂印效果|limit=50"
    url = API + "?" + urllib.parse.urlencode({"action": "ask", "query": query, "format": "json"})
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "ignore")).get("query", {}).get("results", {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--ids", default="", help="comma-separated IDs; omit for full scope")
    parser.add_argument("--restart", action="store_true", help="ignore existing soul_full.json")
    args = parser.parse_args()

    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    overrides = json.loads((REF / "catalog" / "manual_overrides.json").read_text(encoding="utf-8"))
    raw_souls = json.loads((DATA / "bwiki" / "souls.json").read_text(encoding="utf-8"))
    roster = json.loads((ROOT / "references" / "catalog" / "roster.json").read_text(encoding="utf-8"))
    scope = roster["catalog"]["id_range"]
    all_ids = set(range(scope[0], scope[1] + 1))
    all_ids |= {item["id"] for item in pool["elves"]}
    all_ids |= {item["id"] for item in pool["dropped"] if isinstance(item, dict) and isinstance(item.get("id"), int)}
    all_ids |= {item["id"] for item in overrides["spirits"]}
    all_ids |= {item["id"] for item in roster["spirits"]}
    wanted = sorted(all_ids)
    if args.ids.strip():
        wanted = [int(x) for x in args.ids.split(",") if x.strip()]

    sid_to_elves: dict[int, list[int]] = {}
    raw_len: dict[int, int] = {}
    for soul in raw_souls:
        sid = soul.get("sid")
        for eid in soul.get("elves", []):
            sid_to_elves.setdefault(sid, []).append(eid)
            raw_len[eid] = max(raw_len.get(eid, 0), len(str(soul.get("effect", ""))))

    doc = {"generated_at": date.today().isoformat(), "source": "BWIKI SMW ask",
           "query": "[[分类:<ID>]][[分类:魂印]]|?魂印效果", "scope": [min(all_ids), max(all_ids)],
           "count": 0, "souls": {}, "failed_ids": []}
    if OUT.exists() and not args.restart:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    if args.ids.strip():
        for eid in wanted:
            doc["souls"].pop(str(eid), None)  # only explicit IDs are re-fetched
    todo = [i for i in wanted if str(i) not in doc["souls"]]
    print(f"scope={len(all_ids)} ids, todo={len(todo)}, batch={args.batch}", flush=True)

    failed: list[int] = []
    for start in range(0, len(todo), args.batch):
        batch = todo[start:start + args.batch]
        results = None
        for attempt in range(3):
            try:
                results = ask(batch, args.timeout)
                break
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                print(f"retry {batch[0]}..{batch[-1]} attempt {attempt + 1}: {str(exc)[:70]}", flush=True)
                time.sleep(1.5 + attempt * 2)
        if results is None:
            failed.extend(batch)
            continue
        if not isinstance(results, dict):
            results = {}  # SMW returns an empty list for batches with no soul pages
        found: dict[int, tuple[int, str]] = {}
        for key, value in results.items():
            try:
                sid = int(str(key).split(":")[-1])
            except ValueError:
                continue
            effects = value.get("printouts", {}).get("魂印效果", [])
            text = clean(effects[0]) if effects else ""
            if not text:
                continue
            for eid in sid_to_elves.get(sid, []):
                if eid in batch and (eid not in found or len(text) > len(found[eid][1])):
                    found[eid] = (sid, text)
        for eid in batch:
            sid, text = found.get(eid, (None, ""))
            doc["souls"][str(eid)] = {
                "sid": sid,
                "text": text,
                "full_len": len(text),
                "raw_len": raw_len.get(eid, 0),
                "url": f"https://wiki.biligame.com/seer/%E9%AD%82%E5%8D%B0:{sid}" if sid else "",
            }
        doc["count"] = len(doc["souls"])
        doc["failed_ids"] = failed
        if (start // args.batch) % 10 == 0 or start + args.batch >= len(todo):
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            tmp.replace(OUT)
            print(f"progress {min(start + args.batch, len(todo))}/{len(todo)}; "
                  f"saved {doc['count']} souls; failed {len(failed)}", flush=True)
        time.sleep(args.delay)

    doc["count"] = len(doc["souls"])
    doc["failed_ids"] = failed
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    with_text = sum(1 for v in doc["souls"].values() if v["text"])
    expanded = sum(1 for v in doc["souls"].values()
                   if v["text"] and v["full_len"] > v["raw_len"] * 1.3 + 30)
    print(f"done: {doc['count']} ids, {with_text} with soul text, {expanded} expanded vs raw, "
          f"{len(failed)} failed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

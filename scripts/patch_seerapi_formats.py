#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只补 data/seerapi/seerapi.json 的 soulmark 版本标记（并发，秒级）

全量 `--refresh` 要重抓 133 只 × 每个魂印一次请求，遇到网络抖动会跑很久。
本脚本只针对「已有快照里的 soulmark ID」并发补两个字段：
  has_format  → 是否有 desc_formatting_adjustment（当前生效版的判定信号）
  desc        → 客户端分析简版文本（旧版往往只有这一份）

用法: python scripts/patch_seerapi_formats.py
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "seerapi" / "seerapi.json"
API = "https://api.seerapi.com/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def get_soulmark(sid, retry=2):
    url = "%s/soulmark/%s" % (API, sid)
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return sid, json.load(resp)
        except Exception:
            if i == retry - 1:
                return sid, None
            time.sleep(0.4)
    return sid, None


def main():
    store = json.loads(STORE.read_text(encoding="utf-8"))
    refs = {}
    for pet in store["pets"].values():
        for sm in pet.get("soulmarks") or []:
            refs[sm["id"]] = True
    ids = sorted(refs)
    print("patching %d soulmarks ..." % len(ids))
    result, failed = {}, []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(get_soulmark, sid) for sid in ids]
        for f in as_completed(futures):
            sid, data = f.result()
            if data is None:
                failed.append(sid)
            else:
                result[sid] = {
                    "has_format": bool(data.get("desc_formatting_adjustment")),
                    "desc": data.get("desc"),
                }
    for pet in store["pets"].values():
        for sm in pet.get("soulmarks") or []:
            patch = result.get(sm["id"])
            if patch:
                sm["has_format"] = patch["has_format"]
                if patch["desc"]:
                    sm["desc"] = patch["desc"]
    # 2026-11-08 全量审计：只有实质内容变化才写文件。旧版每次重跑都把
    # format_check_at 改成当前时间，即使一个字段都没改，制造无意义 diff。
    stamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        original = json.loads(STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        original = {}
    strip_stamp = lambda d: {k: v for k, v in d.items() if k != "format_check_at"}
    if strip_stamp(original) == strip_stamp(store):
        print("no format changes; seerapi.json unchanged (skip timestamp-only rewrite)")
    else:
        store["format_check_at"] = stamp
        STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    print("done in %.1fs | patched %d | failed %d %s" % (
        time.time() - t0, len(result), len(failed), failed[:8]))
    print("with has_format: %d / %d pets" % (
        sum(1 for p in store["pets"].values()
            if p.get("soulmarks") and "has_format" in p["soulmarks"][0]),
        len(store["pets"])))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补抓指定精灵的完整技能文本，写入 data/seerapi/skills_full.json

与 fetch_skills.py 的区别：本脚本不依赖 data/bwiki/pool.json 的 tier 预筛，
直接按 ID 抓 精灵:<ID> 的技能列表，再批量抓 技能:<技能ID> 的 wikitext。
用于机制审计：判断 roster.mechanics / play 里的每条机制是否真能在
魂印原文或技能文本中找到依据。

用法:
  python scripts/fetch_skills_full.py --all-deep
  python scripts/fetch_skills_full.py --ids 4925 3430 4594
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
API = "https://wiki.biligame.com/seer/api.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
REFERER = "https://wiki.biligame.com/seer/"


def api(params, retry=5):
    params = dict(params)
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(retry):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": REFERER})
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp)
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(2.0 * (i + 1))


def wikitext(title):
    doc = api({"action": "query", "prop": "revisions", "rvprop": "content",
               "rvslots": "main", "titles": title})
    pages = doc.get("query", {}).get("pages", {})
    for page in pages.values():
        revs = page.get("revisions") or []
        if revs:
            return revs[0].get("slots", {}).get("main", {}).get("*", "")
    return ""


def parse_tpl(text):
    out = {}
    for m in re.finditer(r"\|([^=|{}\n]+)=([^|{}\n]*)", text):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def skill_ids_for(elf_id):
    text = wikitext("精灵:%d" % elf_id)
    m = re.search(r"\|技能=([^\n}]*)", text)
    if not m:
        return []
    out = []
    for chunk in m.group(1).split(";"):
        sid = chunk.strip().split("-")[0]
        if sid.isdigit():
            out.append(sid)
    return out


def fetch_skill_batch(ids):
    """Batch fetch up to 50 技能 pages per request."""
    titles = "|".join("技能:%s" % i for i in ids)
    doc = api({"action": "query", "prop": "revisions", "rvprop": "content",
               "rvslots": "main", "titles": titles})
    out = {}
    pages = doc.get("query", {}).get("pages", {})
    for page in pages.values():
        title = page.get("title", "")
        sid = title.split(":", 1)[-1]
        revs = page.get("revisions") or []
        if not revs:
            continue
        text = revs[0].get("slots", {}).get("main", {}).get("*", "")
        tpl = parse_tpl(text)
        if not tpl.get("技能名称"):
            continue
        out[sid] = {
            "id": sid,
            "name": tpl.get("技能名称", ""),
            "type": tpl.get("技能类型", ""),
            "attr": tpl.get("技能属性", ""),
            "power": tpl.get("威力", ""),
            "pp": tpl.get("次数", ""),
            "priority": tpl.get("先制", ""),
            "effect": tpl.get("技能效果", ""),
        }
    return out


def main():
    path = os.path.join(DATA, "seerapi/skills_full.json")
    store = {"generated_at": time.strftime("%Y-%m-%d"),
             "source": "BWIKI 技能页 wikitext（浏览器 UA + 同站 Referer）",
             "elves": {}, "skills": {}}
    if os.path.exists(path):
        store = json.load(open(path, encoding="utf-8"))

    if "--all-deep" in sys.argv:
        roster = json.load(open(os.path.join(ROOT, "references", "roster.json"),
                                encoding="utf-8"))
        targets = [int(x["id"]) for x in roster["spirits"]]
    elif "--ids" in sys.argv:
        pos = sys.argv.index("--ids")
        targets = []
        for a in sys.argv[pos + 1:]:
            if a.startswith("--"):
                break
            a = a.strip(",")
            if a.isdigit():
                targets.append(int(a))
    else:
        print(__doc__)
        return

    todo = [i for i in targets if str(i) not in store["elves"]]
    if not todo:
        print("nothing to fetch; all %d elves already cached" % len(targets))
        return
    print("fetching %d elves (cached %d)" % (len(todo), len(targets) - len(todo)))

    all_ids = []
    for n, eid in enumerate(todo, 1):
        try:
            ids = skill_ids_for(eid)
        except Exception as exc:
            print("  elf %d failed: %s" % (eid, exc))
            continue
        store["elves"][str(eid)] = ids
        all_ids.extend(x for x in ids if x not in store["skills"])
        print("  elf %d: %d skills" % (eid, len(ids)))
        time.sleep(0.35)

    pending = list(dict.fromkeys(all_ids))
    print("skills to fetch: %d" % len(pending))
    for start in range(0, len(pending), 45):
        batch = pending[start:start + 45]
        try:
            got = fetch_skill_batch(batch)
        except Exception as exc:
            print("  batch %d failed: %s" % (start, exc))
            continue
        store["skills"].update(got)
        print("  batch %d-%d: %d ok" % (start, start + len(batch) - 1, len(got)))
        time.sleep(0.5)

    json.dump(store, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("saved %d elves / %d skills -> %s"
          % (len(store["elves"]), len(store["skills"]), path))


if __name__ == "__main__":
    main()

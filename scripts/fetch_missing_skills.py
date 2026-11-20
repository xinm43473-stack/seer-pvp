#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐 data/derived/spirit_library.json 里技能为空的精灵。

背景（2026-11-18 用户提问「为什么无限自由没有技能」）：
    3383 无限自由在官方 SeerAPI 有 17 个技能，本地库却是 `skills: []`。
    原因是 build_spirit_library.py 只在「不在 data/seerapi/spirit_media.json 资料层」时内联技能，
    而这几只当时的 raw/pet 抓取没有落盘技能引用，于是留下空数组。
    raw 层（data/seerapi_media/raw）已于 2026-11-15 删除，无法再跑构建脚本，
    所以这里单独走 HTTP 补抓，产出与 build_spirit_library.skill_rows() 完全同格式的行。

口径（与构建脚本一致，不得自行发明）：
    * 只补 `skills` 为空的精灵；已有资料的绝不覆盖。
    * 行字段 n/p/pp/pr/cat/t/e/f/a/sp/lv，e 只放实际生效效果（skill_effect + hide_effect）。
    * 排序 key=(is_fifth, is_advanced, is_special, learning_level) 倒序，最多 30 条。
    * 文本过 safe()：去 [color]/<br>/标签、折叠空行、屏蔽前端禁用词。

用法:
    python scripts/fetch_missing_skills.py --dry-run     # 只报告要补哪些
    python scripts/fetch_missing_skills.py               # 补抓并写回
    python scripts/fetch_missing_skills.py --ids 3383    # 指定 id
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LIB = DATA / "derived/spirit_library.json"
MEDIA = DATA / "seerapi/spirit_media.json"
CACHE = DATA / "seerapi/seerapi_skills_cache.json"
API = "https://api.seerapi.com/v1"
UA = "seerapi-missing-skills/1.0 (+local project)"

SKILL_CAP = 30
EFFECT_CAP = 300
DESC_CAP = 120
BANNED = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
TAG_RE = re.compile(r"<[^>]+>")


def safe(text) -> str:
    s = re.sub(r"\[/?color[^\]]*\]", "", str(text or ""))
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\[sprite[^\]]*\]", "", s, flags=re.I)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    for word in BANNED:
        s = s.replace(word, "—")
    return s


def get_json(url: str, retry: int = 4) -> dict:
    last = None
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
            time.sleep(1.2 * (i + 1))
    raise RuntimeError("GET %s failed: %s" % (url, last))


def ref_id(obj):
    return obj.get("id") if isinstance(obj, dict) and isinstance(obj.get("id"), int) else None


class Names:
    """属性 / 技能分类的 id → 名称（数量很少，进程内缓存）。"""

    def __init__(self) -> None:
        self.types: dict[int, str] = {}
        self.cats: dict[int, str] = {}

    def type_name(self, ref) -> str:
        tid = ref_id(ref)
        if not tid:
            return ""
        if tid not in self.types:
            self.types[tid] = str(get_json(f"{API}/element_type_combination/{tid}").get("name") or "")
        return self.types[tid]

    def cat_name(self, ref) -> str:
        cid = ref_id(ref)
        if not cid:
            return ""
        if cid not in self.cats:
            self.cats[cid] = str(get_json(f"{API}/skill_category/{cid}").get("name") or "")
        return self.cats[cid]


def effect_list(raw) -> list[dict]:
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def hide_info(raw) -> str:
    """hide_effect 有时是引用（只有 id/url），需要再取一次。"""
    if not isinstance(raw, dict):
        return ""
    if raw.get("info"):
        return str(raw["info"])
    hid = ref_id(raw)
    if not hid:
        return ""
    try:
        row = get_json(f"{API}/skill_hide_effect/{hid}")
    except RuntimeError:
        return ""
    return str(row.get("info") or "")


def skill_row(skill: dict, ref: dict, names: Names) -> dict:
    effects = [safe(x.get("info", "")) for x in effect_list(skill.get("skill_effect"))
               if x.get("info")]
    effects += [safe(hide_info(skill.get("hide_effect")))]
    effect = "；".join(e for e in effects if e)
    desc = safe(skill.get("info") or "")
    return {
        "id": skill.get("id"),
        "n": safe(skill.get("name", "")),
        "p": skill.get("power"),
        "pp": skill.get("max_pp"),
        "pr": skill.get("priority"),
        "cat": names.cat_name(skill.get("category")),
        "t": names.type_name(skill.get("type")),
        "e": effect[:EFFECT_CAP],
        "d": desc[:DESC_CAP],
        "f": int(bool(ref.get("is_fifth"))),
        "a": int(bool(ref.get("is_advanced"))),
        "sp": int(bool(ref.get("is_special"))),
        "lv": ref.get("learning_level"),
    }


def sync_legacy(cache: dict, names: "Names", plans: dict) -> None:
    """同步 data/seerapi/skills.json（技能主表）与 data/seerapi/elf_skills.json（精灵→技能 id）。

    字段沿用老通道口径：name/type(技能分类)/attr(属性)/power/pp/priority/effect。
    只增不删，已有条目保留原样，避免覆盖历史人工校对值。
    """
    sk_path = DATA / "seerapi/skills.json"
    es_path = DATA / "seerapi/elf_skills.json"
    skills = json.loads(sk_path.read_text(encoding="utf-8")) if sk_path.exists() else {}
    elf = json.loads(es_path.read_text(encoding="utf-8")) if es_path.exists() else {}
    added = 0
    for key, refs in plans.items():
        ids = []
        for ref in refs:
            sid = ref_id(ref["skill"])
            raw = cache.get(sid)
            if not raw:
                continue
            ids.append(str(sid))
            if str(sid) in skills:
                continue
            effects = [safe(x.get("info", "")) for x in effect_list(raw.get("skill_effect"))
                       if x.get("info")]
            effects += [safe(hide_info(raw.get("hide_effect")))]
            skills[str(sid)] = {
                "name": safe(raw.get("name", "")),
                "type": names.cat_name(raw.get("category")),
                "attr": names.type_name(raw.get("type")),
                "power": str(raw.get("power") or ""),
                "pp": str(raw.get("max_pp") or ""),
                "priority": str(raw.get("priority") or 0),
                "effect": "；".join(e for e in effects if e)[:EFFECT_CAP],
            }
            added += 1
        if ids:
            elf[key] = ids
    if not added and not elf:
        return
    sk_path.write_text(json.dumps(skills, ensure_ascii=False, indent=1), encoding="utf-8")
    es_path.write_text(json.dumps(elf, ensure_ascii=False, indent=1), encoding="utf-8")
    print("旧通道同步：skills.json +%d 条（共 %d），elf_skills.json %d 只"
          % (added, len(skills), len(elf)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None, help="只处理这些精灵 id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    doc = json.loads(LIB.read_text(encoding="utf-8"))
    lib = doc["spirits"]
    media = (json.loads(MEDIA.read_text(encoding="utf-8")).get("spirits") or {})

    if args.ids:
        targets = [str(x) for x in args.ids]
    else:
        # media 层的精灵技能是「不重复内联」的设计，不能补；只补两边都空的
        targets = [k for k, v in lib.items()
                   if not (v.get("skills") or []) and k not in media]

    print("待补精灵 %d 只: %s" % (len(targets), targets[:20]))
    if args.dry_run or not targets:
        for k in targets:
            r = lib[k]
            print("  %s %s｜%s" % (k, r.get("name"), r.get("attr")))
        return 0

    names = Names()
    plans: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        pets = {k: pool.submit(get_json, f"{API}/pet/{k}") for k in targets}
        for k, fut in pets.items():
            try:
                pet = fut.result()
            except RuntimeError as exc:
                print("  %s pet 抓取失败: %s" % (k, exc))
                continue
            refs = [r for r in (pet.get("skill") or []) if ref_id(r and r.get("skill"))]
            plans[k] = refs
            print("  %s %s：技能引用 %d 条" % (k, pet.get("name"), len(refs)))

    # 技能详情去重后统一抓（同一技能会被多只精灵共用）
    sids = sorted({ref_id(r["skill"]) for refs in plans.values() for r in refs})
    print("技能详情 %d 条去重后抓取…" % len(sids))
    cache: dict[int, dict] = {}
    if CACHE.exists():
        try:
            cache = {int(k): v for k, v in json.loads(CACHE.read_text(encoding="utf-8")).items()}
        except (ValueError, OSError):
            cache = {}
    todo = [s for s in sids if s not in cache]

    def fetch_skill(sid: int) -> tuple[int, dict]:
        return sid, get_json(f"{API}/skill/{sid}")

    with ThreadPoolExecutor(max_workers=10) as pool:
        for sid, row in pool.map(fetch_skill, todo):
            cache[sid] = row
    print("命中缓存 %d 条，新抓 %d 条" % (len(sids) - len(todo), len(todo)))

    changed = []
    for k, refs in plans.items():
        rows = []
        for ref in refs:
            row = cache.get(ref_id(ref["skill"]))
            if not row:
                continue
            rows.append(skill_row(row, ref, names))
        rows.sort(key=lambda x: (x["f"], x["a"], x["sp"], int(x["lv"] or 0)), reverse=True)
        rows = rows[:SKILL_CAP]
        if not rows:
            print("  %s 仍然没有可用技能行，跳过" % k)
            continue
        if lib[k].get("skills") == rows:
            continue
        lib[k]["skills"] = rows
        changed.append((k, lib[k].get("name"), len(rows)))
        print("  %s %s：写入 %d 条（首条 %s）" % (k, lib[k].get("name"), len(rows), rows[0]["n"]))

    # 旧的查询通道先同步：即使库已补过，命令行这边也可能还缺。
    sync_legacy(cache, names, plans)

    if not changed:
        print("没有需要写入的精灵")
        return 0

    st = doc.get("stats") or {}
    st["with_skills"] = sum(1 for x in lib.values() if x.get("skills"))
    st["skill_rows"] = sum(len(x.get("skills") or []) for x in lib.values())
    doc["stats"] = st
    doc["generated_at"] = time.strftime("%Y-%m-%d")
    src = doc.get("source") or []
    note = "api.seerapi.com/v1（scripts/fetch_missing_skills.py 补抓）"
    if note not in src:
        src.append(note)
    doc["source"] = src

    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    LIB.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("写入 %d 只 / 共 %d 条技能行；库统计 with_skills=%d skill_rows=%d"
          % (len(changed), sum(c[2] for c in changed), st["with_skills"], st["skill_rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

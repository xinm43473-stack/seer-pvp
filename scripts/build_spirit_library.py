"""Build the hidden full spirit library used by the "+" picker.

2026-11-09 user request: 增加全量精灵库，但是不显示 / 只要添加就都有，格式为 seerapi 格式。
The library is a *data source*, never a display layer: nothing from it is rendered
in the spirit list until the user explicitly adds a spirit.  Every entry carries
the same SeerAPI-format payload as data/seerapi/spirit_media.json (soul marks + complete
skill rows), so an added spirit immediately shows a full skill table offline.

Local sources (no network at build time):
  * data/bwiki/elves.json                     - full game index (id / name / attr)
  * data/bwiki/pool.json#elves                    - BWIKI soul text
  * data/seerapi_media/raw/pet/*.json      - full SeerAPI pet catalogue
  * data/seerapi_media/raw/soulmark/*.json - all soul mark versions
  * data/seerapi_media/raw/skill/*.json    - all 27414 skills
  * data/seerapi_media/raw/{element_type_combination,skill_category}/*.json
  * data/seerapi/spirit_media.json                 - local WebP images
  * references/catalog/spirit_master_list.csv      - whether the id is already listed

（原始缓存已落盘；重建直接运行：）
    python scripts/build_spirit_library.py
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REF = ROOT / "references"
RAW = DATA / "seerapi_media" / "raw"
OUT = DATA / "derived/spirit_library.json"
MIN_ID, MAX_ID = 2987, 10**9   # 不设上限：SeerAPI 新增精灵（如 13311 圣光灵神SP）自动进库
SOUL_CAP = 900
EFFECT_CAP = 300
DESC_CAP = 120
SKILL_CAP = 30
H5 = "https://seerh5.61.com/resource/assets/"

def local_image(kind: str, sid: int) -> str:
    """本地已下载的头像/立绘（assets/seerapi/pet_*，离线落盘）。"""
    for ext in (".webp", ".png"):
        rel = f"assets/seerapi/pet_{kind}/{sid}{ext}"
        path = ROOT / rel
        if path.exists() and path.stat().st_size > 100:
            return "../" + rel
    return ""

def effect_entries(raw) -> list[dict]:
    """SeerAPI 的 skill_effect / hide_effect 有时是数组、有时是单个对象。"""
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


# 前端禁用词（总表口径 F20261104）；库内文本一律不把它们带到页面上。
BANNED = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")


def safe(text: str) -> str:
    s = re.sub(r"\[/?color[^\]]*\]", "", str(text or ""))
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    for word in BANNED:
        s = s.replace(word, "—")
    return s


def load(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def raw_index(resource: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for path in (RAW / resource).glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(row, dict) and isinstance(row.get("id"), int):
                out[row["id"]] = row
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return out


def ref_id(obj) -> int | None:
    return obj.get("id") if isinstance(obj, dict) and isinstance(obj.get("id"), int) else None


def main() -> int:
    raw_elves = load(DATA / "bwiki" / "elves.json", [])
    pool = load(DATA / "bwiki/pool.json", {})
    media = load(DATA / "seerapi/spirit_media.json", {})
    usable = {int(x["id"]): x for x in pool.get("elves", []) if isinstance(x.get("id"), int)}
    history = {int(x["id"]): x for x in pool.get("dropped", [])
               if isinstance(x, dict) and isinstance(x.get("id"), int)}
    media_rows = media.get("spirits", {}) or {}

    pets = raw_index("pet")
    souls = raw_index("soulmark")
    skills = raw_index("skill")
    types = raw_index("element_type_combination")
    cats = raw_index("skill_category")

    listed = set()
    csv_path = REF / "catalog" / "spirit_master_list.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    listed.add(int(row["序号"]))
                except (KeyError, TypeError, ValueError):
                    continue

    def type_name(obj) -> str:
        tid = ref_id(obj)
        return str(types.get(tid, {}).get("name", "")) if tid else ""

    def cat_name(obj) -> str:
        cid = ref_id(obj)
        return str(cats.get(cid, {}).get("name", "")) if cid else ""

    def soul_rows(pet: dict) -> list[dict]:
        out = []
        for ref in pet.get("soulmark") or []:
            sid = ref_id(ref)
            row = souls.get(sid) if sid else None
            if not row:
                continue
            text = safe(row.get("analyze_desc") or row.get("desc") or "")
            out.append({"id": sid, "text": text[:SOUL_CAP],
                        "source_field": "analyze_desc" if row.get("analyze_desc") else "desc",
                        "primary": False,
                        "has_format": bool(row.get("desc_formatting_adjustment"))})
        if out:
            # 同一只精灵会挂多条魂印：老版在前、新版在后（SeerAPI 的 soulmark id 递增）。
            # 口径是「只显示最新一版」：优先取带格式化结算文本的（＝当前生效版），
            # 都没有时取 id 最大的那条——不能再退化成 out[0]（那是老版）。
            primary = next((x for x in out if x["has_format"]), None) \
                or max(out, key=lambda x: int(x["id"]))
            primary["primary"] = True
        return out

    def skill_rows(pet: dict) -> list[dict]:
        out = []
        for ref in pet.get("skill") or []:
            sid = ref_id(ref.get("skill") if isinstance(ref, dict) else None)
            sk = skills.get(sid) if sid else None
            if not sk:
                continue
            # sk["info"] 是战报描述，另存 d；e 只放实际生效的效果（skill_effect / hide_effect）。
            effects = [safe(x.get("info", "")) for x in effect_entries(sk.get("skill_effect"))
                       if x.get("info")]
            effects += [safe(x.get("info", "")) for x in effect_entries(sk.get("hide_effect"))
                        if x.get("info")]
            effect = "；".join(e for e in effects if e)
            desc = safe(sk.get("info") or "")
            out.append({
                "id": sid, "n": safe(sk.get("name", "")),
                "p": sk.get("power"), "pp": sk.get("max_pp"), "pr": sk.get("priority"),
                "cat": cat_name(sk.get("category")), "t": type_name(sk.get("type")),
                "e": effect[:EFFECT_CAP], "d": desc[:DESC_CAP],
                "f": int(bool(ref.get("is_fifth"))), "a": int(bool(ref.get("is_advanced"))),
                "sp": int(bool(ref.get("is_special"))),
                "lv": ref.get("learning_level"),
            })
        out.sort(key=lambda x: (x["f"], x["a"], x["sp"], int(x["lv"] or 0)), reverse=True)
        return out[:SKILL_CAP]

    spirits: dict[str, dict] = {}
    # BWIKI elves.json 落后于 SeerAPI 时，用 raw/pet 补齐新增条目（如 SP 形态）；
    # 名称取 SeerAPI，属性从 element_type_combination 解析，魂印/技能仍走本地 raw。
    seen_ids = {r.get("id") for r in raw_elves if isinstance(r.get("id"), int)}
    extra_rows = [
        {"id": pid, "name": pet.get("name") or "—",
         "attr": (type_name(pet.get("type")).replace(" ", "") or "—")}
        for pid, pet in pets.items()
        if isinstance(pid, int) and pid >= MIN_ID and pid not in seen_ids
    ]
    for row in list(raw_elves) + extra_rows:
        sid = row.get("id")
        if not isinstance(sid, int) or not (MIN_ID <= sid <= MAX_ID):
            continue
        key = str(sid)
        u, h, m = usable.get(sid, {}), history.get(sid, {}), media_rows.get(key, {})
        pet = pets.get(sid, {})
        srows = soul_rows(pet)
        soul = next((x["text"] for x in srows if x["primary"]),
                    srows[0]["text"] if srows else "") or safe(u.get("soul", ""))[:SOUL_CAP]
        images = m.get("images") or {}
        spirits[key] = {
            "id": sid,
            "name": row.get("name") or u.get("name") or h.get("name") or "—",
            "attr": row.get("attr") or u.get("attr") or "—",
            "soul": soul[:SOUL_CAP],
            "soulmarks": srows,
            "skills": [] if m else skill_rows(pet),   # 已有资料层的精灵不重复内联
            "avatar": images.get("avatar") or local_image("head", sid) or f"{H5}pet/head/{sid}.png",
            "portrait": images.get("portrait") or local_image("body", sid) or f"{H5}fightResource/pet/{sid}.png",
            "listed": sid in listed,
        }

    doc = {
        "status": "ready",
        "generated_at": date.today().isoformat(),
        "scope": {"min_id": MIN_ID, "max_id": max((x["id"] for x in spirits.values()), default=MAX_ID)},
        "source": ["data/bwiki/elves.json", "data/bwiki/pool.json#elves", "data/bwiki/pool.json#dropped",
                   "data/seerapi_media/raw/{pet,soulmark,skill}", "data/seerapi/spirit_media.json",
                   "references/catalog/spirit_master_list.csv"],
        "format": "skill rows use the same keys as DATA.media.skills (n/p/pp/pr/cat/t/e/f/a/sp/lv)",
        "rule": "隐藏资料源：库内精灵不进入列表，只有用户在列表末尾点＋选中后才显示；不参与收录、强度与联动判断。",
        "stats": {
            "total": len(spirits),
            "listed": sum(1 for x in spirits.values() if x["listed"]),
            "with_soul": sum(1 for x in spirits.values() if x["soul"]),
            "with_skills": sum(1 for x in spirits.values() if x["skills"]),
            "skill_rows": sum(len(x["skills"]) for x in spirits.values()),
            "with_local_images": sum(1 for x in spirits.values()
                                     if x["avatar"].startswith("../")),
        },
        "spirits": spirits,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    st = doc["stats"]
    print("spirit library: %d spirits (listed %d, soul %d, skills %d / %d rows, local images %d) -> %s"
          % (st["total"], st["listed"], st["with_soul"], st["with_skills"],
             st["skill_rows"], st["with_local_images"], OUT.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

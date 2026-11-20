#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 fetch_seerapi_media.py 落盘的原始文件整理成项目可用的资料层（纯离线、幂等）。

输入：
  data/seerapi_media/raw/<resource>/<id>.json   SeerAPI 原始响应
  assets/seerapi/<kind>/<id>.(webp|png)          SeerAPI 组织仓库的图像
  data/seerapi_media/manifest.json               来源与失败留痕

输出：
  data/seerapi/spirit_media.json            结构化资料层（每只：魂印各版本／技能／图像／来源）
  data/seerapi/spirit_info.json             资料位（status=ready，供 import_spirit_info.py）
  references/catalog/spirit_media_report.json  统计、缺口与口径说明

设计要点：
  * 魂印文本保留三个版本：analyze_desc（当前 Unity 客户端版）、
    desc_formatting_adjustment（历史格式化版）、desc（简版）。
    「当前生效版」优先取带 desc_formatting_adjustment 的那条，正文再优先用
    analyze_desc；全部去标签但不改写措辞，与 SKILL.md 的 SA:<ID> 口径一致。
  * 只登记真正存在的文件，缺失写进 report.missing，不编造、不推断。
  * spirit_info.json 的三个字段严格满足 editor_schema 的长度／条数限制：
    soul_mark ≤8000 字、portrait ≤500 字、skills ≤30 条且每条 ≤200 字。

用法：python scripts/build_spirit_media.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REF = ROOT / "references"
CACHE = DATA / "seerapi_media" / "raw"
MANIFEST = DATA / "seerapi_media" / "manifest.json"
MEDIA_OUT = DATA / "seerapi/spirit_media.json"
INFO_OUT = DATA / "seerapi/spirit_info.json"
REPORT_OUT = REF / "catalog" / "spirit_media_report.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402

HTML_TAG = re.compile(r"<[^>]+>")
BB_TAG = re.compile(r"\[/?[A-Za-z][^\]]*\]")
WS = re.compile(r"[ \t\r]+")
FALLBACK_BASE = ("https://fastly.jsdelivr.net/gh/SeerAPI/seer-unity-assets@main/"
                 "newseer/assets/art/ui/assets/")
GH_SUBDIR = {
    "pet_head": "pet/head", "pet_body": "pet/body",
    "effecticon": "effecticon", "pettype": "pettype",
}
CAPS = {"soul_mark": 8000, "portrait": 500, "skills": 30, "skill_item": 200}


def clean(text: str | None) -> str:
    """去 Unity 富文本标签；`|` 是官方描述的分条符，转成换行。"""
    if not text:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("|", "\n")
    text = HTML_TAG.sub("", text)
    text = BB_TAG.sub("", text)
    lines = [WS.sub(" ", x).strip(" \u3000") for x in text.split("\n")]
    return "\n".join(x for x in lines if x)


def effect_entries(raw) -> list[dict]:
    """SeerAPI 的 skill_effect / hide_effect 有时是数组、有时是单个对象。"""
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def clip(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap - 1] + "…"


def write_if_changed(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_raw(resource: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for p in (CACHE / resource).glob("*.json"):
        try:
            out[int(p.stem)] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return out


def asset_index(manifest: dict) -> dict[tuple[str, int], dict]:
    """扫描 assets/seerapi 实际文件 → 前端相对路径 / 在线兜底 URL。

    以磁盘为准（中断的采集可能已写文件但没写 manifest），manifest 里有来源 URL
    就用来源 URL，否则按资源仓库路径拼一个兜底。
    """
    out: dict[tuple[str, int], dict] = {}
    known = manifest.get("assets") or {}
    root = ROOT / "assets" / "seerapi"
    if not root.exists():
        return out
    for path in root.glob("*/*"):
        if path.suffix.lower() not in (".webp", ".png") or not path.stem.isdigit():
            continue
        kind, rid = path.parent.name, int(path.stem)
        rel = path.relative_to(ROOT).as_posix()
        source = known.get(rel, "")
        url = source if isinstance(source, str) and source.startswith("http") else (
            f"{FALLBACK_BASE}{GH_SUBDIR.get(kind, kind)}/{rid}.png")
        out[(kind, rid)] = {
            "path": rel,
            "view": "../" + rel,          # references/*.html 的相对路径
            "url": url,                   # 缺少本地图片时的在线兜底
        }
    return out


def ref_id(obj) -> int | None:
    return obj.get("id") if isinstance(obj, dict) and isinstance(obj.get("id"), int) else None


def main() -> int:
    if not MANIFEST.exists():
        raise SystemExit("缺少 data/seerapi_media/manifest.json，请先跑 fetch_seerapi_media.py")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pets = load_raw("pet")
    souls = load_raw("soulmark")
    skills_raw = load_raw("skill")
    types = load_raw("element_type_combination")
    cats = load_raw("skill_category")
    tags_raw = load_raw("soulmark_tag")
    assets = asset_index(manifest)
    # 2026-11-09：从隐藏精灵库手动添加的序号用库内魂印/图像兜底，不算资料层缺口。
    targets = sorted(editor_schema.editable_ids() - editor_schema.library_add_ids())

    def img(kind: str, rid: int | None) -> dict | None:
        return assets.get((kind, rid)) if isinstance(rid, int) else None

    def type_name(tid: int | None) -> str:
        return (types.get(tid, {}) or {}).get("name", "") if isinstance(tid, int) else ""

    spirits: dict[str, dict] = {}
    info_rows: dict[str, dict] = {}
    missing_pets: list[int] = []
    missing_soul: list[int] = []
    missing_portrait: list[int] = []

    for pid in targets:
        pet = pets.get(pid)
        if not pet:
            missing_pets.append(pid)
            continue
        rid = pet.get("resource_id") if isinstance(pet.get("resource_id"), int) else pid
        tid = ref_id(pet.get("type"))
        # 实测 seer-unity-assets：pet/head 是方形头像，pet/body 才是全身立绘。
        head_icon = img("pet_head", rid)
        full_body = img("pet_body", rid)
        type_icon = img("pettype", tid)

        # --- 魂印：保留全部版本，标出当前生效版 ---
        soul_rows = []
        for ref in pet.get("soulmark") or []:
            sid = ref_id(ref)
            s = souls.get(sid) if sid is not None else None
            if not s:
                continue
            fmt = s.get("desc_formatting_adjustment")
            analyze = clean(s.get("analyze_desc"))
            desc = clean(s.get("desc"))
            formatted = clean(fmt)
            current = analyze or formatted or desc
            eid = ref_id((s.get("effect") or {}).get("effect"))
            soul_rows.append({
                "id": sid,
                "text": current,
                "source_field": ("analyze_desc" if analyze else
                                 "desc_formatting_adjustment" if formatted else "desc"),
                "desc": desc,
                "formatted": formatted,
                "has_format": bool(fmt),
                "pve_effective": s.get("pve_effective"),
                "intensified": s.get("intensified"),
                "is_adv": s.get("is_adv"),
                "effect_id": eid,
                "icon": (img("effecticon", eid) or {}).get("view", ""),
                "icon_url": (img("effecticon", eid) or {}).get("url", ""),
                "tags": [tags_raw.get(t.get("id"), {}).get("name", "")
                         for t in (s.get("tag") or [])
                         if isinstance(t, dict) and t.get("id") in tags_raw],
                "api_url": f"https://api.seerapi.com/v1/soulmark/{sid}",
            })
        if not soul_rows:
            missing_soul.append(pid)
        primary = next((x for x in soul_rows if x["has_format"]), None) or (
            soul_rows[0] if soul_rows else None)
        for row in soul_rows:
            row["is_primary"] = bool(primary and row["id"] == primary["id"])
        soul_text = (primary or {}).get("text", "")

        # --- 技能：保留完整结构化清单 ---
        skill_rows = []
        for ref in pet.get("skill") or []:
            if not isinstance(ref, dict):
                continue
            skid = ref_id(ref.get("skill"))
            sk = skills_raw.get(skid) if skid is not None else None
            if not sk:
                continue
            sk_tid = ref_id(sk.get("type"))
            cat_id = ref_id(sk.get("category"))
            # skill.info 是「释放技能后战报里显示的文字」（技能描述），不是实际生效的效果。
            # 实际效果只取 skill_effect[].info / hide_effect[].info；两者分字段保存，绝不混用。
            effects = [clean(e.get("info")) for e in effect_entries(sk.get("skill_effect"))
                       if e.get("info")]
            effects += [clean(e.get("info")) for e in effect_entries(sk.get("hide_effect"))
                        if e.get("info")]
            skill_rows.append({
                "id": skid,
                "name": sk.get("name", ""),
                "power": sk.get("power"),
                "max_pp": sk.get("max_pp"),
                "priority": sk.get("priority"),
                "accuracy": sk.get("accuracy"),
                "category": (cats.get(cat_id, {}) or {}).get("name", ""),
                "type": type_name(sk_tid),
                "type_icon": (img("pettype", sk_tid) or {}).get("view", ""),
                "info": clean(sk.get("info")),
                "effects": effects,
                "learning_level": ref.get("learning_level"),
                "is_fifth": bool(ref.get("is_fifth")),
                "is_advanced": bool(ref.get("is_advanced")),
                "is_special": bool(ref.get("is_special")),
                "api_url": f"https://api.seerapi.com/v1/skill/{skid}",
            })

        # spirit_info.skills 只有 30 条名额：第五／神谕／特训优先，再按学习等级倒序。
        def rank(s):
            return (int(s["is_fifth"]), int(s["is_advanced"]), int(s["is_special"]),
                    s["learning_level"] if isinstance(s["learning_level"], int) else -1)
        picked = sorted(skill_rows, key=rank, reverse=True)[:CAPS["skills"]]

        def line(s):
            flags = "".join(x for x, on in (("第五", s["is_fifth"]), ("神谕", s["is_advanced"]),
                                            ("特训", s["is_special"])) if on)
            head = f"{s['name']}｜{s['category']}·{s['type']}｜威力{s['power']}｜PP{s['max_pp']}｜先制{s['priority']}"
            if flags:
                head += "｜" + flags
            # 资料位每行尾段只放实际效果；战报描述留在 spirit_media.json 的 info 与前端短键 d。
            tail = "；".join(s["effects"])
            return clip(head + ("｜" + tail if tail else ""), CAPS["skill_item"])

        info_rows[str(pid)] = {
            "soul_mark": clip(soul_text, CAPS["soul_mark"]),
            "portrait": (full_body or {}).get("view", "")[:CAPS["portrait"]],
            "skills": [line(s) for s in picked],
        }
        if not (full_body or {}).get("view"):
            missing_portrait.append(pid)

        spirits[str(pid)] = {
            "id": pid,
            "name": pet.get("name", ""),
            "resource_id": rid,
            "type": {"id": tid, "name": type_name(tid),
                     "icon": (type_icon or {}).get("view", "")},
            "base_stats": pet.get("base_stats") or {},
            "peak_pool": {"id": ref_id(pet.get("peak_pool")),
                          "expert": ref_id(pet.get("peak_expert_pool")),
                          "cost": ref_id(pet.get("peak_cost_pool"))},
            "soulmarks": soul_rows,
            "soulmark_text": soul_text,
            "skills": skill_rows,
            "images": {
                "portrait": (full_body or {}).get("view", ""),
                "portrait_url": (full_body or {}).get("url", ""),
                "avatar": (head_icon or {}).get("view", ""),
                "avatar_url": (head_icon or {}).get("url", ""),
                "soul_icon": (primary or {}).get("icon", ""),
                "soul_icon_url": (primary or {}).get("icon_url", ""),
                "type_icon": (type_icon or {}).get("view", ""),
            },
            "api_url": f"https://api.seerapi.com/v1/pet/{pid}",
        }

    generated = date.today().isoformat()
    source = {
        "api": manifest.get("api"),
        "api_cli": manifest.get("api_cli"),
        "asset_repo": manifest.get("asset_repo"),
        "raw_cache": manifest.get("raw_cache"),
        "fetched_at": manifest.get("generated_at"),
    }
    media = {
        "schema_version": 1.0,
        "status": "ready" if spirits else "empty",
        "generated_at": generated,
        "source": source,
        "asset_root": "../assets/seerapi",
        "fallback_base": FALLBACK_BASE,
        "field_policy": {
            "soulmark_text": "analyze_desc 是当前 Unity 客户端文本；带 desc_formatting_adjustment 的魂印判为当前生效版；文本只去标签不改写",
            "images": "本地文件优先，加载失败才回退 SeerAPI 静态资源仓库 URL",
            "missing": "缺口写入 references/catalog/spirit_media_report.json，不推断、不编造",
        },
        "spirits": spirits,
        "stats": {
            "spirits": len(spirits),
            "with_soulmark": sum(1 for x in spirits.values() if x["soulmark_text"]),
            "with_portrait": sum(1 for x in spirits.values() if x["images"]["portrait"]),
            "with_avatar": sum(1 for x in spirits.values() if x["images"]["avatar"]),
            "soulmark_versions": sum(len(x["soulmarks"]) for x in spirits.values()),
            "skills": sum(len(x["skills"]) for x in spirits.values()),
            "images": len(assets),
        },
    }
    info = {
        "schema_version": 1.0,
        "status": "ready" if info_rows else "placeholder",
        "updated_at": generated,
        "note": ("资料位已导入：数据来自 SeerAPI 官方 API 与 SeerAPI 组织的 seer-unity-assets "
                 "静态资源仓库，由 scripts/fetch_seerapi_media.py 抓取、"
                 "scripts/build_spirit_media.py 整理。字段长度与条数按 editor_schema.json；"
                 "完整结构化版本、各版魂印与全部技能见 data/seerapi/spirit_media.json。"),
        "expected_fields": {
            "soul_mark": "字符串，当前生效版魂印全文（上限 8000 字）；去 Unity 富文本标签，不改写措辞",
            "portrait": "字符串，立绘的项目内相对路径（上限 500 字）；相对 references/*.html",
            "skills": "字符串数组，每行一条「技能名｜效果」（最多 30 条，每条 200 字）；第五/神谕/特训优先",
        },
        "spirits": info_rows,
    }
    report = {
        "schema_version": 1.0,
        "generated_at": generated,
        "source": source,
        "target_count": len(targets),
        "stats": media["stats"],
        "fetch_failures": manifest.get("failures", []),
        "missing_pets": missing_pets,
        "missing_soulmark": missing_soul,
        "missing_portrait": missing_portrait,
        "image_format": manifest.get("image_format", ""),
        "policy": "资料层只做机制与图像展示，不参与收录判断、强度分级或同队联动推导。",
    }
    write_if_changed(MEDIA_OUT, media)
    write_if_changed(INFO_OUT, info)
    write_if_changed(REPORT_OUT, report)
    print("spirit media: %d 只 / %d 条魂印版本 / %d 条技能 / %d 张图像" % (
        media["stats"]["spirits"], media["stats"]["soulmark_versions"],
        media["stats"]["skills"], media["stats"]["images"]))
    print("  missing pets=%d soulmark=%d portrait=%d | fetch failures=%d" % (
        len(missing_pets), len(missing_soul), len(missing_portrait),
        len(report["fetch_failures"])))
    print("  -> data/seerapi/spirit_media.json, data/seerapi/spirit_info.json, references/catalog/spirit_media_report.json")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

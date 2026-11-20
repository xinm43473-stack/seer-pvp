#!/usr/bin/env python3
"""Build the offline "pick a spirit -> see its partners / systems" front end.

Output: references/spirit_synergy_view.html (single file, data inlined, no server
and no fetch needed, so file:// works).

The selectable spirit list is reused verbatim from build_spirit_index.collect(),
which means it always matches the 227-row master list and its active-layer rules.
System members that are not on that list are shown only as relationship targets
(labelled 资料层), never added to the selectable list.

Relationship sources (2026-11-05 strict-link correction):
  * references/catalog/systems.json    - explicit chain_edges (teammates), warning_edges,
                                 counter (opposing side); core/support/alternatives
                                 are member lists and are NEVER expanded
  * references/catalog/role_groups.json - similar-role groups (same functional slot,
                                 NOT combos, NOT counters, NOT replacements)
  * references/catalog/matchups.json   - opposing-side relations
  * references/catalog/strength.json   - human strength layer (complexity tier is NOT strength)
  * references/docs/tactics.md      - section bodies attached to each system

The old build expanded core+support into a Cartesian product and also rendered
349 historical leads as "关联线索" cards. Both were invented relationships.
A spirit with no explicit edge, no similar-role group and no opposing-side
no teammate/partner cards are generated; only system chains and similar-role groups remain.
Run python scripts/build_chain_audit.py before rebuilding this page.

Usage: python scripts/build_synergy_view.py
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REF = ROOT / "references"
DATA = ROOT / "data"
sys.path.insert(0, str(HERE))

from build_spirit_index import collect  # noqa: E402

# 层级/分组顺序改由 editor_schema.json 提供，新增层级不必改代码。
from query import load_aliases  # noqa: E402
from edge_consts import edges_fingerprint  # noqa: E402
import editor_schema  # noqa: E402

_SCHEMA_DOC = editor_schema.load_schema()
LAYER_ORDER = list(_SCHEMA_DOC.get("layers", []))
PRIORITY = list(_SCHEMA_DOC.get("relationship_priority", []))

TEMPLATE = HERE / "synergy_view_template.html"
OUTPUT = REF / "spirit_synergy_view.html"

# Display-layer terminology alignment. The source documents keep their original
# wording; only the generated front end uses the current vocabulary.
TERMS = {
    "全量图鉴层": "资料层（未写战术链）",
    "全量图鉴": "资料层",
    "整链作废": "整链不成立",
    "全链作废": "全链不成立",
    "自动留痕": "历史记录",
    "种族值过低": "种族值门槛",
    "单条魂印": "魂印摘要",
    # Historical auto-filter vocabulary -> current wording in the front end.
    "与自动剔除原因「魂印摘要且无核心机制」冲突": "已按 BWIKI 魂印全文复核，旧自动判断不再采用",
    "自动剔除记录": "历史自动筛选记录",
    "带原因剔除记录": "带原因的历史筛选记录",
    "自动剔除原因": "历史自动判断",
    "已作废": "不再采用",
    "自动剔除": "历史自动筛选",
    "剔除记录": "历史筛选记录",
    "剔除": "排除",
    "作废": "不再采用",
}

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def align(text: str) -> str:
    if not isinstance(text, str):
        return text
    for old, new in TERMS.items():
        text = text.replace(old, new)
    return text


def align_tree(value):
    if isinstance(value, str):
        return align(value)
    if isinstance(value, list):
        return [align_tree(x) for x in value]
    if isinstance(value, dict):
        return {k: align_tree(v) for k, v in value.items()}
    return value


def media_payload() -> dict:
    """SeerAPI 结构化资料层内联进单文件前端（只读面板的数据源）。

    data/seerapi/spirit_media.json 由 scripts/build_spirit_media.py 从 SeerAPI 原始响应
    整理而来；这里压成短键以控制 HTML 体积。可编辑资料位仍走
    references/catalog/spirit_info_overlay.json，二者互不覆盖。
    """
    path = DATA / "seerapi/spirit_media.json"
    if not path.exists():
        return {"status": "placeholder", "spirits": {}, "stats": {}}
    doc = load(path)
    out: dict[str, dict] = {}
    for key, s in (doc.get("spirits") or {}).items():
        soul_rows = [{
            "id": r.get("id"), "text": r.get("text", ""), "desc": r.get("desc", ""),
            "formatted": r.get("formatted", ""), "field": r.get("source_field", ""),
            "primary": bool(r.get("is_primary")), "tags": r.get("tags", []),
            "api": r.get("api_url", ""),
        } for r in s.get("soulmarks", [])]
        skill_rows = []
        for r in s.get("skills", []):
            # info = 技能描述（战报文字），effects = 技能效果（实际生效）；分列保存，不互相顶替。
            effect = "；".join(str(x).strip() for x in (r.get("effects") or []) if str(x).strip())[:300]
            desc = str(r.get("info") or "").strip()[:120]
            skill_rows.append({
                "id": r.get("id"), "n": r.get("name", ""), "p": r.get("power"),
                "pp": r.get("max_pp"), "pr": r.get("priority"),
                "cat": r.get("category", ""), "t": r.get("type", ""),
                "icon": r.get("type_icon", ""),
                "f": int(bool(r.get("is_fifth"))), "a": int(bool(r.get("is_advanced"))),
                "sp": int(bool(r.get("is_special"))), "lv": r.get("learning_level"),
                "e": effect, "d": desc, "api": r.get("api_url", ""),
            })
        out[str(key)] = {
            "name": s.get("name", ""), "rid": s.get("resource_id"),
            "type": (s.get("type") or {}).get("name", ""),
            "images": s.get("images", {}), "soul": soul_rows,
            "skills": skill_rows, "api": s.get("api_url", ""),
        }
    return {
        "status": doc.get("status", "placeholder"),
        "generated_at": doc.get("generated_at", ""),
        "source": doc.get("source", {}),
        "asset_root": doc.get("asset_root", "../assets/seerapi"),
        "field_policy": doc.get("field_policy", {}),
        "stats": doc.get("stats", {}),
        "spirits": out,
    }


def race_payload() -> dict:
    """2026-11-09：种族值（六维 + 总和），详情页名称与魂印之间展示。

    SeerAPI 全库 pet 的 base_stats 覆盖所有 id（含 5000 圣灵谱尼），优先使用；
    BWIKI data/bwiki/elves.json 的 stats/total 作兜底。紧凑数组顺序固定为
    [体力, 攻击, 防御, 特攻, 特防, 速度, 总和]。
    """
    out: dict[str, list] = {}
    raw_path = DATA / "bwiki" / "elves.json"
    if raw_path.exists():
        for row in json.loads(raw_path.read_text(encoding="utf-8")):
            sid, s = row.get("id"), row.get("stats") or {}
            if not isinstance(sid, int) or not s:
                continue
            vals = [s.get("体力"), s.get("攻击"), s.get("防御"),
                    s.get("特攻"), s.get("特防"), s.get("速度"), row.get("total")]
            if all(isinstance(v, (int, float)) for v in vals[:6]):
                out[str(sid)] = vals
    pet_dir = DATA / "seerapi_media" / "raw" / "pet"
    if pet_dir.exists():
        for path in pet_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                sid, b = row.get("id"), row.get("base_stats") or {}
                if not isinstance(sid, int) or not b:
                    continue
                vals = [b.get("hp"), b.get("atk"), b.get("def"), b.get("sp_atk"),
                        b.get("sp_def"), b.get("spd"), b.get("total")]
                if all(isinstance(v, (int, float)) for v in vals[:6]):
                    out[str(sid)] = vals
            except (OSError, json.JSONDecodeError, ValueError):
                continue
    return out


def soul_tags_payload(nodes: list, media: dict) -> dict:
    """2026-11-11：魂印效果标签（SeerAPI `soulmark.tag`，官方 20 类）。

    原始 `data/seerapi_media/raw/soulmark/*.json#tag` 只是 `{id,url}` 数组，
    中文名在 `raw/soulmark_tag/{id}.json`。标签描述的是「这条魂印涉及哪些
    效果维度」，不参与收录、强度与联动判断，只作魂印下方的分类提示。

    资料层只覆盖 234 只，剩余精灵回落到隐藏库 `spirit_library.json` 的魂印 id
    反查同一张原始表，避免 354 只里一百多只没有标签。只输出当前列表里
    存在的精灵，控制内联体积。
    """
    tag_dir = DATA / "seerapi_media" / "raw" / "soulmark_tag"
    names: dict[int, str] = {}
    if tag_dir.exists():
        for path in sorted(tag_dir.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            tid, name = doc.get("id"), str(doc.get("name") or "").strip()
            if isinstance(tid, int) and name:
                names[tid] = name

    by_mark: dict[str, list[str]] = {}
    mark_dir = DATA / "seerapi_media" / "raw" / "soulmark"
    if names and mark_dir.exists():
        for path in mark_dir.glob("*.json"):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            ids = sorted({int(x["id"]) for x in (doc.get("tag") or [])
                          if isinstance(x, dict) and isinstance(x.get("id"), int)})
            labels = [names[i] for i in ids if i in names]
            if labels:
                by_mark[str(doc.get("id"))] = labels

    lib: dict = {}
    lib_path = DATA / "derived/spirit_library.json"
    if lib_path.exists():
        try:
            rows = json.loads(lib_path.read_text(encoding="utf-8")).get("spirits") or {}
        except (OSError, json.JSONDecodeError, ValueError):
            rows = {}
        lib = {str(x.get("id")): x for x in rows} if isinstance(rows, list) else rows

    out: dict[str, list[str]] = {}
    for n in nodes:
        sid = str(n.get("id"))
        souls = ((media.get("spirits") or {}).get(sid) or {}).get("soul") or []
        labels: list[str] = []
        # 主魂印优先（与页面实际展示的那条一致），其次任一有标签的版本。
        for pick in [x for x in souls if x.get("primary")] + souls:
            tags = [str(t).strip() for t in (pick.get("tags") or []) if str(t).strip()]
            if tags:
                labels = tags
                break
        if not labels:
            marks = (lib.get(sid) or {}).get("soulmarks") or []
            for pick in [x for x in marks if x.get("primary")] + marks:
                tags = by_mark.get(str(pick.get("id")))
                if tags:
                    labels = tags
                    break
        if labels:
            out[sid] = labels[:8]

    # 2026-11-11：点击魂印标签要能看到全库同标签精灵，所以库内其余精灵
    # 也按魂印 id 反查补齐（约 1600 条，压缩后 50KB 左右）。
    for sid, row in lib.items():
        if sid in out:
            continue
        marks = row.get("soulmarks") or []
        for pick in [x for x in marks if x.get("primary")] + marks:
            tags = by_mark.get(str(pick.get("id")))
            if tags:
                out[str(sid)] = tags[:8]
                break
    return out


def role_adds_payload() -> dict:
    """2026-11-10：用户在相似定位区块点＋添加的同定位精灵与备注。

    references/catalog/view_role_adds.json 由 scripts/apply_view_edits.py 从前端补丁落库；
    这里只内联展示层数据，不改动 role_groups.json 的严格分组口径。
    """
    path = REF / "catalog" / "view_role_adds.json"
    groups: dict = {}
    if path.exists():
        try:
            groups = load(path).get("groups", {}) or {}
        except (OSError, ValueError, AttributeError):
            groups = {}
    return {"groups": groups}


def pull_selection_payload() -> list[int]:
    """精选拉取序号表（references/catalog/pull_selection.json 的 ids）。"""
    path = REF / "catalog" / "pull_selection.json"
    if not path.exists():
        return []
    try:
        doc = load(path)
    except (OSError, ValueError, AttributeError):
        return []
    rows = doc.get("ids") if isinstance(doc, dict) else doc
    out: list[int] = []
    for x in rows or []:
        try:
            sid = int(x)
        except (TypeError, ValueError):
            continue
        if sid >= 2987 and sid not in out:
            out.append(sid)
    return out


def terms_payload() -> dict:
    """2026-11-10：魂印名词解释词典（`data/derived/soul_terms.json`）。

    只搬运可溯源释义：SeerAPI 官方术语表 + 魂印原文自带 `名称：释义` 段。
    每条 = [释义, 来源代码, 类别]，类别按官方 kind 分三档：
    `ex` 精灵专属名词 / `eff` 通用效果名词 / `timing` 时点名词，
    前端用三色三扇圆环切换显示（参考官方客户端）。
    """
    path = DATA / "derived/soul_terms.json"
    if not path.exists():
        return {"terms": {}, "stats": {"terms": 0}, "status": "missing"}
    doc = load(path)
    src_code = {"glossary": "g", "battle_effect": "b", "inline": "i"}
    cats = doc.get("cats") or {"eff": "通用效果名词", "ex": "精灵专属名词", "timing": "时点名词"}
    out: dict[str, list] = {}
    for name, row in (doc.get("terms") or {}).items():
        desc = str(row.get("d") or "").strip()
        if not desc:
            continue
        cat = row.get("c")
        out[name] = [desc, src_code.get(row.get("s", ""), "g"), cat if cat in cats else "ex"]
    return {
        "terms": out,
        "cats": cats,
        "stats": doc.get("stats", {}),
        "rule": doc.get("rule", ""),
        "generated_at": doc.get("generated_at", ""),
    }


def library_payload() -> dict:
    """2026-11-09：隐藏全量精灵库 + 用户已添加的序号。

    库内 1960 只精灵只作为「＋」选择器的数据源，**不进入 nodes**、不渲染；
    只有 references/view_library_adds.json 里登记的序号才由前端动态加入列表。
    """
    path = DATA / "derived/spirit_library.json"
    if not path.exists():
        return {"status": "missing", "spirits": [], "adds": [], "total": 0}
    doc = load(path)
    rows = []
    h5 = "https://seerh5.61.com/resource/assets/"
    for key, x in sorted((doc.get("spirits") or {}).items(), key=lambda kv: int(kv[0])):
        sid = int(key)
        # 技能行已经是 DATA.media.skills 的同款短键格式，添加后可直接进技能表。
        rows.append({
            "id": sid, "name": x.get("name", ""), "attr": x.get("attr", ""),
            "soul": x.get("soul", ""),
            "avatar": x.get("avatar") or f"{h5}pet/head/{sid}.png",
            "portrait": x.get("portrait") or f"{h5}fightResource/pet/{sid}.png",
            "skills": x.get("skills") or [],
        })
    adds: list[int] = []
    state_path = REF / "view_library_adds.json"
    if state_path.exists():
        for raw in load(state_path).get("ids", []):
            try:
                adds.append(int(raw))
            except (TypeError, ValueError):
                continue
    return {"status": doc.get("status", "ready"), "total": len(rows),
            "listed": doc.get("stats", {}).get("listed", 0),
            "adds": adds, "spirits": rows}


def tactic_sections(text: str) -> dict[str, str]:
    """Map every heading to its own body (stop at the next same/higher level)."""
    heads = list(re.finditer(r"^(#{2,4})\s+(.+?)\s*$", text, re.M))
    out: dict[str, str] = {}
    for i, m in enumerate(heads):
        level = len(m.group(1))
        end = len(text)
        for nxt in heads[i + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        out[m.group(2).strip()] = text[m.end():end].strip()
    return out


def parse_sources(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"^- \*\*([^*]+)\*\*[｜|]\s*(.+)$", text, re.M):
        key = m.group(1).strip()
        desc = re.sub(r"\s+", " ", m.group(2).strip())
        out[key] = desc[:170]
    return out


def build_nodes(rows, roster, idx, overrides, pool, alias_by_id, strength_doc, audit_doc,
                roles_doc):
    spirit_map = {x["id"]: x for x in roster["spirits"]}
    rated = {x["id"]: x for x in strength_doc.get("ratings", [])}
    watch = {x["id"] for x in strength_doc.get("watchlist", [])}
    bias = {x["id"] for x in strength_doc.get("bias_review", {}).get("items", [])}
    audit_by_id = {x["id"]: x for x in audit_doc.get("spirits", []) if x.get("id") is not None}
    audit_by_name = {x["name"]: x for x in audit_doc.get("spirits", []) if x.get("id") is None}

    def strength_of(sid):
        if sid in rated:
            return {"grade": rated[sid]["grade"], "basis": rated[sid]["basis"]}
        if sid in watch:
            return {"grade": "未评级（月榜观察名单）", "basis": "月榜点名，无当季梯度证据"}
        if sid in bias:
            return {"grade": "未评级（功能位待复核）", "basis": "机制复杂度分与功能位价值冲突，须人工定级"}
        return {"grade": "未评级", "basis": "无当季证据，不推断 T 级"}

    pending_map = {x.get("id"): x for x in roster["pending_research"] if x.get("id") is not None}
    themed = {x["id"]: x for x in idx["themed_spirits"]}
    override_map = {x["id"]: x for x in overrides["spirits"]}

    nodes = []
    for pos, row in enumerate(rows):
        sid = row["id"]
        key = str(sid) if sid is not None else "pending-%02d" % pos
        node = {
            "k": key,
            "id": sid,
            "name": row["name"],
            "attr": row["attr"],
            "main": row["main"],
            "layers": row["layers"],
            "tier": row["tier"],
            "strength": strength_of(sid),
            "audit": audit_by_id.get(sid) or audit_by_name.get(row["name"]) or {},
            "note": row["note"],
            "aliases": alias_by_id.get(sid, []),
            **editor_schema.empty_fields(_SCHEMA_DOC),   # 所有 schema 字段统一铺空值，避免缺键
            "systems": [],
        }
        sp = spirit_map.get(sid)
        if sp:
            node.update({
                "roles": sp.get("roles", []),
                "classes": sp.get("classes", []),
                "editor_note": sp.get("editor_note", ""),
                "mechanics": sp.get("mechanics", []),
                "play": sp.get("play", ""),
                "status": sp.get("status", ""),
                "deep_dive": sp.get("deep_dive"),
                "sources": sp.get("sources", []),
                "url4399": sp.get("url4399"),
            })
        if sid in pending_map:
            item = pending_map[sid]
            node["candidate"] = {
                "source": item.get("source", ""),
                "note": item.get("note", ""),
                "priority": item.get("priority", ""),
            }
        if sid in themed:
            node["work"] = {
                "count": themed[sid].get("work_count", 0),
                "example": themed[sid].get("example_work", ""),
            }
        if sid in override_map:
            node["soul"] = override_map[sid].get("soul", "")
        nodes.append(node)

    elves = {x["id"]: x for x in pool["elves"]}
    dropped = {x["id"]: x for x in pool["dropped"] if isinstance(x, dict) and isinstance(x.get("id"), int)}
    active_ids = {n["id"] for n in nodes if n["id"] is not None}

    system_doc = load(REF / "catalog" / "systems.json")
    system_ids = set()
    for item in system_doc["systems"]:
        for field in ("core", "support", "counter"):
            system_ids.update(item.get(field, []))
    role_ids = {int(x) for g in roles_doc.get("groups", []) for x in g.get("members", [])}

    outside = {}
    for sid in sorted((system_ids | role_ids) - active_ids):
        src = elves.get(sid) or dropped.get(sid) or {}
        in_system = sid in system_ids
        outside[str(sid)] = {
            "k": str(sid), "id": sid,
            "name": src.get("name") or "序号 %d" % sid,
            "attr": src.get("attr") or "—",
            "main": "资料层（未写战术链）",
            "layers": ["资料层"],
            "aliases": alias_by_id.get(sid, []),
            **editor_schema.empty_fields(_SCHEMA_DOC),
            "outside": True,
            "hint": ("体系正文点名的组件／对位对象，未进入可选精灵列表，仅作参照"
                     if in_system else
                     "相似定位组的资料层成员，只作同类位参照，不加入可选精灵列表"),
        }
    return nodes, outside, spirit_map, system_doc


def build_links(nodes, outside, spirit_map, system_doc, chain_doc, matchups_doc,
                roles_doc):
    """2026-11-10：不再生成「可配合精灵 / 同队」关系对。

    只保留相似定位、反向对位、组件互斥这几组（供 check_roster 做证据校验）。
    systems.json 的 chain_edges 仍在「所属体系 / 联动」画布里按体系原样展示，
    但不再被展开成一只只「可配合精灵」卡片。成员名单、并列位、历史线索一律不成对。
    """
    valid = {n["k"] for n in nodes} | set(outside)
    buckets = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "systems": [], "roles": [], "notes": [],
        "status": [], "evidence": [],
    })))

    def add(a, b, kind, sys_name, role, note, status="", evidence=""):
        a, b = str(a), str(b)
        if a not in valid or b not in valid or a == b:
            return
        cell = buckets[a][b][kind]
        for field, value in (("systems", sys_name), ("roles", role),
                             ("notes", note), ("status", status),
                             ("evidence", evidence)):
            if value and value not in cell[field]:
                cell[field].append(value)

    # 2) Opposing side, plus only the mutual-exclusion pairs the text names.
    for item in system_doc["systems"]:
        name = item["name"]
        core = [int(x) for x in item.get("core", [])]
        counter = [int(x) for x in item.get("counter", [])]
        status = item.get("chain_status", "")
        evidence = item.get("evidence_grade", "")
        counter_note = ("对手方限二／BP 对象，不是己方队友"
                        if item.get("kind") == "放谱对策" else
                        "用来打该体系／该精灵，属于反向对位，不是同队推荐")
        if item.get("external"):
            counter_note += "；" + "；".join(item["external"])
        for c in counter:
            for p in (core[:1] or core):
                add(p, c, "对位", name, "反向对位（对手侧）", counter_note, status, evidence)
                add(c, p, "对位", name, "针对目标", counter_note, status, evidence)
        for a, b in item.get("warning_edges", []):
            note = "正文明确写出同时上场会对冲；%s" % item.get("review_note", "")
            add(a, b, "互斥", name, "组件互斥（警示）", note, status, evidence)
            add(b, a, "互斥", name, "组件互斥（警示）", note, status, evidence)

    for m in matchups_doc.get("items", []):
        # Unverified combo ideas are not relationships: no card, not even a
        # warning, so a spirit with no real link shows 「暂无已核实关联」.
        if m.get("relation") != "反向对位" or m.get("grade") == "待核线索":
            continue
        a, b = int(m["a"]), int(m["b"])
        typ = "对位"
        tag = (m.get("section") or "实战对位")[:24]
        note = m.get("direction", "") + "；" + m.get("note", "")
        add(a, b, typ, tag, m.get("relation", ""), note,
            m.get("grade", ""), m.get("evidence", ""))
        add(b, a, typ, tag, m.get("relation", ""), note,
            m.get("grade", ""), m.get("evidence", ""))

    # 3) Similar roles: same functional slot, explicitly NOT a combo.
    role_pairs = defaultdict(list)
    for group in roles_doc.get("groups", []):
        members = [int(x) for x in group.get("members", [])]
        diff_by_id = {}
        for line in group.get("differences", []):
            hit = re.match(r"^(\d+)", str(line))
            if hit:
                diff_by_id[int(hit.group(1))] = line
        for a, b in itertools.permutations(members, 2):
            role_pairs[(str(a), str(b))].append({
                "group": group["name"],
                "shared": group["shared"],
                "mine": diff_by_id.get(a, ""),
                "peer": diff_by_id.get(b, ""),
                "relation": group["relation"],
                "evidence": group.get("evidence_grade", ""),
                "sources": group.get("sources", []),
            })
            add(a, b, "相似定位", group["name"], "同类功能位（不是配合）",
                group["relation"], "", group.get("evidence_grade", ""))

    links = {}
    for a, targets in buckets.items():
        entries = []
        for b, by_kind in targets.items():
            types = [t for t in PRIORITY if t in by_kind]
            best = types[0] if types else "对位"
            # Only the winning group's own evidence is shown on the card.
            cell = by_kind.get(best, {})
            entries.append({
                "to": b,
                "types": types,
                "group": best,
                "systems": cell.get("systems", []),
                "roles": cell.get("roles", []),
                "notes": cell.get("notes", []),
                "status": cell.get("status", []),
                "evidence": cell.get("evidence", []),
                "role_info": role_pairs.get((a, b), []),
                "also": [t for t in types if t != best],
            })
        entries.sort(key=lambda x: (PRIORITY.index(x["group"]) if x["group"] in PRIORITY else 9,
                                    -len(x["systems"]), str(x["to"])))
        links[a] = entries

    sys_by_spirit = defaultdict(list)
    for item in system_doc["systems"]:
        members = set(item.get("core", [])) | set(item.get("support", [])) | set(item.get("counter", []))
        for sid in members:
            sys_by_spirit[str(sid)].append(item["name"])
    return links, sys_by_spirit


def main():
    rows, roster, idx = collect()
    overrides = load(REF / "catalog" / "manual_overrides.json")
    pool = load(DATA / "bwiki/pool.json")
    chain_doc = load(REF / "catalog" / "chain_audit.json")
    matchups_doc = load(REF / "catalog" / "matchups.json")
    strength_doc = load(REF / "catalog" / "strength.json")
    roles_path = REF / "catalog" / "role_groups.json"
    roles_doc = load(roles_path) if roles_path.exists() else {"groups": []}
    audit_path = REF / "catalog" / "full_audit.json"
    audit_doc = load(audit_path) if audit_path.exists() else {"spirits": []}
    tactics = (REF / "docs" / "tactics.md").read_text(encoding="utf-8")
    sources_text = (REF / "docs" / "sources.md").read_text(encoding="utf-8")
    bodies = tactic_sections(tactics)
    sources = parse_sources(sources_text)

    aliases = load_aliases()
    alias_by_id = defaultdict(list)
    for alias, ids in aliases.items():
        for sid in ids:
            alias_by_id[sid].append(alias)

    nodes, outside, spirit_map, system_doc = build_nodes(
        rows, roster, idx, overrides, pool, alias_by_id, strength_doc, audit_doc,
        roles_doc)
    links, sys_by_spirit = build_links(
        nodes, outside, spirit_map, system_doc, chain_doc, matchups_doc, roles_doc)

    del_path = REF / "view_deletions.json"
    deleted_ids: set[int] = set()
    if del_path.exists():
        deleted_ids = {int(x) for x in load(del_path).get("deleted", []) if str(x).isdigit()}

    # 2026-11-08 重构：schema 驱动的可编辑字段注册表；落库编辑覆盖层直接应用到
    # 全部节点（含候选池／专题层／资料层参照），不改动 roster.json 的收录口径。
    schema_view = editor_schema.view_schema()
    schema_field_keys = [f["key"] for f in schema_view["fields"]]
    system_labels = editor_schema.system_labels()
    name_to_key = {v: k for k, v in system_labels.items()}
    edit_path = REF / "view_edits.json"
    persisted: dict[str, dict] = {}
    if edit_path.exists():
        for item in load(edit_path).get("edits", []):
            k = str(item.get("key") or item.get("id"))
            row = {key: item[key] for key in schema_field_keys if key in item}
            if row:
                persisted[k] = row
    # 资料导入层（占位阶段为空），优先级低于用户编辑层。
    info_path = REF / "catalog" / "spirit_info_overlay.json"
    info_overlay: dict[str, dict] = {}
    if info_path.exists():
        info_overlay = (load(info_path).get("spirits", {}) or {})
    for n in list(nodes) + list(outside.values()):
        n["systems"] = sorted(set(sys_by_spirit.get(n["k"], [])))
        n["system_keys"] = [name_to_key[x] for x in n["systems"] if x in name_to_key]
        info = info_overlay.get(n["k"])
        if info:
            n.update(info)
        overlay = persisted.get(n["k"]) or {}
        n.update(overlay)
        # 所属体系恒由 systems.json 成员名单判定：补丁里的 system_keys 不再覆盖，
        # 避免编辑面板手工勾选的体系与实际成员不一致（前端已改为只读派生展示）。
        n["systems"] = sorted(set(sys_by_spirit.get(n["k"], [])))
        n["system_keys"] = [name_to_key[x] for x in n["systems"] if x in name_to_key]
        n["rel_count"] = len(links.get(n["k"], []))
        n["marked_deleted"] = n.get("id") in deleted_ids
        # 2026-11-09：层级不再展示，右栏统一显示用户自维护评级，默认 T0（可编辑）。
        n["rating"] = str(n.get("rating") or "T0").strip()[:8] or "T0"
        n["key_skills"] = [x for x in (n.get("key_skills") or []) if isinstance(x, str)][:12]

    systems = []
    for item in system_doc["systems"]:
        row = dict(item)
        row["body"] = bodies.get(item.get("section", ""), "")[:9000]
        systems.append(row)

    linked = sum(1 for n in nodes if n["rel_count"])
    pairs = sum(len(v) for v in links.values())
    # 可配合板块删除后 rel_count 只统计对位/相似定位，不再适合挑默认精灵；
    # 固定回原来的默认 4808（讳迹·米修莉），避免重建后首页莫名换人。
    default = "4808" if any(n["k"] == "4808" for n in nodes) else max(
        nodes, key=lambda n: (n["rel_count"], n["main"] == "深研层"))["k"]

    core_limits: dict = {}
    for spec in schema_view["fields"]:
        if spec["type"] == "multi_enum":
            core_limits[spec["key"]] = [spec.get("min", 0), spec.get("max", 99)]
        elif spec["type"] == "textarea":
            core_limits[spec["key"] + "_max"] = spec.get("max", 2000)
        elif spec["type"] == "lines":
            core_limits[spec["key"] + "_max_items"] = spec.get("max_items", 12)
            core_limits[spec["key"] + "_item_max"] = spec.get("item_max", 300)
    editor_limits = dict(schema_view["limits"], **core_limits)

    # 2026-11-08 前端关系联动编辑：把全部显式边与类型词表内联，供编辑弹窗使用。
    edge_rows = []
    for item in system_doc["systems"]:
        for a, b in item.get("chain_edges", []):
            meta = (item.get("edge_meta") or {}).get("%d-%d" % (a, b), {})
            edge_rows.append({
                "system_key": item["key"],
                "system_name": item["name"],
                "a": int(a), "b": int(b),
                "type": meta.get("type", "resource"),
                "note": meta.get("note", ""),
                "chain_status": item.get("chain_status", ""),
            })
    media = media_payload()
    race = race_payload()
    terms = terms_payload()
    pull_selection = pull_selection_payload()
    role_adds = role_adds_payload()
    # 边类型词表以落库校验脚本为唯一来源，避免前后端两处定义漂移。
    payload = {
        "generated_at": date.today().isoformat(),
        "stats": {
            "spirits": len(nodes),
            "systems": len(systems),
            "linked": linked,
            "no_relation": len(nodes) - linked,
            "pairs": pairs,
            "kinds": dict(Counter(x["kind"] for x in systems)),
            "layers": dict(Counter(n["main"] for n in nodes)),
            "explicit_edges": chain_doc["stats"].get("explicit_chain_edges", 0),
            "verified_pairs": chain_doc["stats"].get("verified_ordered_pairs", 0),
            "role_groups": len(roles_doc.get("groups", [])),
            "role_pairs": sum(1 for arr in links.values()
                              for x in arr if x["group"] == "相似定位"),
            "warn_pairs": sum(1 for arr in links.values()
                              for x in arr if x["group"] in ("对位", "互斥", "对策")),
            "human_ratings": len(strength_doc.get("ratings", [])),
            "media_spirits": media.get("stats", {}).get("spirits", 0),
            "media_images": media.get("stats", {}).get("images", 0),
            "media_skills": media.get("stats", {}).get("skills", 0),
            "audit_spirits": audit_doc.get("stats", {}).get("spirits", 0),
            "audit_conflicts": audit_doc.get("stats", {}).get("conflicts", 0),
            "verified_synergies": chain_doc["stats"].get("by_source_field", {}).get("synergies", 0),
            "archived_leads": chain_doc["stats"].get("archived_historical_leads", 0),
        },
        "layers": LAYER_ORDER,
        "status_labels": schema_view.get("status_labels", {}),
        "deep_labels": schema_view.get("deep_labels", {}),
        "kinds": system_doc.get("kinds", {}),
        "evidence_levels": system_doc.get("evidence_levels", {}),
        "evidence_grades": system_doc.get("evidence_grades", {}),
        "chain_statuses": system_doc.get("chain_statuses", {}),
        "chain_stats": chain_doc.get("stats", {}),
        "chain_rule": chain_doc.get("rule", ""),
        "strength_policy": strength_doc.get("policy", {}),
        "role_rule": roles_doc.get("rule", ""),
        "role_policy": roles_doc.get("policy", {}),
        "roles": roles_doc.get("groups", []),
        "class_terms": schema_view["terms"]["classes"],
        "role_terms": schema_view["terms"]["roles"],
        "edges": edge_rows,
        "edge_types": schema_view["terms"]["edge_types"],
        "deletion_policy": {
            "mode": "soft",
            "count": len(deleted_ids),
            "note": "标记删除只从活跃视图隐藏、可恢复，不物理删除数据；由前端编辑补丁经 scripts/apply_view_edits.py 写入 references/view_deletions.json。",
        },
        "editor": {
            "schema_version": schema_view["schema_version"],
            "storage_key": schema_view["storage"]["key"],
            "export_name": schema_view["storage"]["export_name"],
            "editable": schema_field_keys + ["edge_state", "deletions"],
            "limits": editor_limits,
            "schema": schema_view,
            "edge_baseline": edges_fingerprint(edge_rows),
            "persisted": persisted,
            "note": "所有前端节点均可编辑；字段由 editor_schema.json 驱动。改动先存本机 localStorage，导出补丁后运行 scripts/apply_view_edits.py 才会落库。",
        },
        "default": default,
        "media": media,
        "race": race,
        "soul_tags": soul_tags_payload(nodes, media),
        "terms": terms,
        "pull_selection": pull_selection,
        "role_adds": role_adds,
        "library": library_payload(),
        "nodes": nodes,
        "outside": outside,
        "systems": systems,
        "links": links,
        "sources": sources,
    }
    payload = align_tree(payload)

    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    js = js.replace("</", "<\\/")
    tpl = TEMPLATE.read_text(encoding="utf-8")
    if tpl.count("/*__SYNERGY_DATA__*/") != 1:
        raise RuntimeError("template placeholder must appear exactly once")
    OUTPUT.write_text(tpl.replace("/*__SYNERGY_DATA__*/", "const DATA = " + js + ";"),
                      encoding="utf-8")

    print("built:", OUTPUT)
    print("  selectable spirits : %d" % len(nodes))
    print("  systems            : %d (bodies matched %d)" %
          (len(systems), sum(1 for x in systems if x["body"])))
    print("  explicit edges     : %d | similar-role groups: %d" %
          (chain_doc["stats"].get("explicit_chain_edges", 0), len(roles_doc.get("groups", []))))
    print("  relationship pairs : %d (spirits with links: %d, none: %d)" %
          (pairs, linked, len(nodes) - linked))
    print("  seerapi media      : %d spirits / %d skills / %d images (status=%s)" %
          (media.get("stats", {}).get("spirits", 0),
           media.get("stats", {}).get("skills", 0),
           media.get("stats", {}).get("images", 0), media.get("status", "")))
    print("  soul terms         : %d entries (%s)" %
          (terms.get("stats", {}).get("terms", 0), terms.get("generated_at", "")))
    print("  hidden library     : %d spirits (hidden, %d added by user)" %
          (payload["library"].get("total", 0), len(payload["library"].get("adds", []))))
    print("  race values        : %d spirits" % len(race))
    print("  soul tags          : %d spirits tagged" % len(payload["soul_tags"]))
    print("  outside references : %d (%s)" % (len(outside), ", ".join(sorted(outside))))
    print("  default selection  : %s" % default)
    print("  size               : %.1f KB" % (OUTPUT.stat().st_size / 1024))


if __name__ == "__main__":
    main()

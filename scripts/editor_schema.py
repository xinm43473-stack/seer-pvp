#!/usr/bin/env python3
"""前端可编辑字段的唯一口径源（schema 驱动，2026-11-08 重构）

    references/catalog/editor_schema.json   声明可编辑字段、类型、词表来源与限制
    本文件                          加载 + 通用校验 + 可编辑精灵集合解析

调用方：
    build_synergy_view.py   -> view_schema() 内联进 DATA.editor.schema
    apply_view_edits.py     -> validate_spirit_edit() 校验并规范化补丁条目
    apply_edge_view_edits.py-> editable_ids() / terms() / limits()
    check_roster.py         -> check_invariants() 防 schema 与前端漂移

新增可编辑字段只需改 editor_schema.json；只有引入全新的字段类型时才需要
在本文件的 _FIELD_VALIDATORS 里加一个分支。
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import viewdata

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"
SCHEMA_PATH = REF / "catalog" / "editor_schema.json"
MASTER_CSV = REF / "catalog" / "spirit_master_list.csv"
CORE_ROLES = REF / "catalog" / "core_roles.json"
SYSTEMS = REF / "catalog" / "systems.json"
SOURCE_MARKERS = REF / "catalog" / "source_markers.json"
ROLE_GROUPS = REF / "catalog" / "role_groups.json"
POOL = ROOT / "data" / "bwiki" / "pool.json"
VIEW_EDITS = REF / "view_edits.json"
ROSTER = REF / "catalog" / "roster.json"

SCHEMA_VERSION = 3.1          # 最低兼容版本：新增字段类型/字段不必再改这里
FIELD_TYPES = {"multi_enum", "enum", "textarea", "lines", "text", "kv", "roles"}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return _load(SCHEMA_PATH)


def terms(schema: dict | None = None) -> dict:
    """词表统一出口：classes/roles 来自 core_roles.json，其余在 schema 内联。"""
    s = schema or load_schema()
    core = _load(CORE_ROLES)
    systems_doc = _load(SYSTEMS)
    # 体系注册表：key -> 展示名（带 kind）。前端只能选已登记项；新增走 system_state。
    systems = {}
    for item in systems_doc.get("systems", []):
        label = item.get("name") or item["key"]
        if item.get("kind") and item["kind"] not in label:
            label = "%s（%s）" % (label, item["kind"])
        systems[item["key"]] = label
    return {
        "classes": core.get("role_classes", {}),
        "roles": core.get("core_roles", {}),
        "systems": systems,
        "system_kinds": dict(systems_doc.get("kinds", {})),
        "statuses": list(s.get("statuses", [])),
        "edge_types": dict(s.get("edge_types", {})),
    }


def library_add_ids() -> set[int]:
    """用户在列表末尾点＋从隐藏精灵库添加的序号（不属于 SeerAPI 资料层目标）。"""
    path = REF / "view_library_adds.json"
    if not path.exists():
        return set()
    try:
        return {int(x) for x in (_load(path).get("ids") or [])}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return set()


def editable_ids() -> set[int]:
    """所有前端可编辑节点：总表 227 只 + 资料层参照。

    与 build_synergy_view.collect_nodes 的 outside 构造保持同一套来源，
    避免「前端能编辑、后端拒绝」或反之。
    """
    active: set[int] = set()
    if MASTER_CSV.exists():
        with MASTER_CSV.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    active.add(int(row["序号"]))
                except (KeyError, TypeError, ValueError):
                    continue
    systems = _load(SYSTEMS).get("systems", [])
    system_ids: set[int] = set()
    for item in systems:
        for field in ("core", "support", "counter"):
            system_ids.update(int(x) for x in item.get(field, []) if isinstance(x, int))
    role_ids = {int(x) for g in _load(ROLE_GROUPS).get("groups", [])
                for x in g.get("members", [])}
    outside = (system_ids | role_ids) - active
    # 2026-11-09：用户在列表末尾点＋从隐藏精灵库添加的序号也要能当联动边端点。
    return active | outside | library_add_ids()


def editable_keys() -> set[str]:
    """2026-11-09：4 只待核候选已解析为正式序号，总表全部是整数 id，
    因此这里通常返回空集合；保留函数以兼容旧补丁里的 pending-* key。"""
    from build_spirit_index import collect  # noqa: PLC0415
    rows, _, _ = collect()
    return {"pending-%02d" % pos for pos, row in enumerate(rows) if row.get("id") is None}


def spirit_names() -> dict[int, str]:
    out: dict[int, str] = {}
    if MASTER_CSV.exists():
        with MASTER_CSV.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    out[int(row["序号"])] = row.get("名称", "")
                except (KeyError, TypeError, ValueError):
                    continue
    pool = _load(POOL)
    for entry in pool.get("elves", []) + [x for x in pool.get("dropped", []) if isinstance(x, dict)]:
        if entry.get("id") is not None and entry.get("name"):
            out.setdefault(int(entry["id"]), entry["name"])
    return out


def limits(schema: dict | None = None) -> dict:
    return dict((schema or load_schema()).get("limits", {}))


def system_labels() -> dict[str, str]:
    """体系 key -> 名称（不含 kind 后缀），供前端生成后把勾选的 key 映射成展示名。"""
    return {x["key"]: x["name"] for x in _load(SYSTEMS).get("systems", [])}


def empty_fields(schema: dict | None = None) -> dict:
    """按字段类型给出空值；生成前端节点时统一铺底，避免「未编辑的精灵缺字段」。"""
    s = schema or load_schema()
    out = {}
    for spec in s["fields"]:
        out[spec["key"]] = [] if spec["type"] in ("multi_enum", "lines", "kv", "roles") else ""
    return out


def view_schema() -> dict:
    """精简后内联进前端 DATA.editor.schema。"""
    s = load_schema()
    return {
        "schema_version": s["schema_version"],
        "scope": s["spirit_scope"],
        "fields": s["fields"],
        "terms": terms(s),
        "registries": s.get("registries", {}),
        "forbidden_patch_keys": s.get("forbidden_patch_keys", []),
        "status_labels": s.get("status_labels", {}),
        "layers": s.get("layers", []),
        "deep_labels": s.get("deep_labels", {}),
        "limits": s["limits"],
        "edge": s["edge"],
        "deep_layer": s.get("deep_layer", {}),
        "storage": s["storage"],
        "media_import": s.get("media_import", {}),
        "system_edit": s.get("system_edit", {}),
        "system_fields": s.get("system_fields", []),
        "source_markers": list(_load(SOURCE_MARKERS).get("markers", [])) if SOURCE_MARKERS.exists() else [],
        "extension_slots": s.get("extension_slots", {}),
    }


# ---------------------------------------------------------------- 通用字段校验
def _validate_roles(value, spec: dict, term_map: dict, label: str, s: dict) -> list[str]:
    """合并后的「定位」：定位分类（词表内）＋「特色」自定义文本。

    2026-11-18 用户口径：界面上只有一组定位，分类之外可自己写一条特色。
    分类上限、特色上限、特色字数都从 schema 读（spec 优先，其次 limits），
    所以增删词表或调上限不需要改本函数。
    """
    items = list(value or [])
    if any(not isinstance(x, str) for x in items):
        raise SystemExit(f"{label} 必须是字符串数组")
    items = [x.strip() for x in items if str(x).strip()]
    items = list(dict.fromkeys(items))
    lim = s.get("limits") or {}
    max_all = int(spec.get("max", lim.get("role_max", 5)))
    cls_max = int(spec.get("class_max", lim.get("role_class_max", 3)))
    own_max = int(spec.get("custom_max", lim.get("role_custom_max", 2)))
    own_len = int(spec.get("custom_len", lim.get("role_custom_len", 20)))
    if len(items) > max_all:
        raise SystemExit(f"{label} 最多 {max_all} 个，当前 {len(items)} 个")
    classes = [x for x in items if x in term_map]
    customs = [x for x in items if x not in term_map]
    if len(classes) > cls_max:
        raise SystemExit(f"{label} 的定位分类最多 {cls_max} 个，当前 {len(classes)} 个")
    if len(customs) > own_max:
        raise SystemExit(f"{label} 的特色最多 {own_max} 条，当前 {len(customs)} 条")
    too_long = [x for x in customs if len(x) > own_len]
    if too_long:
        raise SystemExit(f"{label} 的特色超过 {own_len} 字：{too_long}")
    # 允许清空：图鉴对空定位显示「未标注」，check_roster 只给警告，不阻断保存
    return items


def _validate_multi_enum(value, spec: dict, term_map: dict, label: str) -> list[str]:
    items = list(value or [])
    if any(not isinstance(x, str) for x in items):
        raise SystemExit(f"{label} 必须是字符串数组")
    items = list(dict.fromkeys(items))
    lo = int(spec.get("min", 0))
    hi = len(term_map) if spec.get("max_from_terms") else int(spec.get("max", 99))
    if not (lo <= len(items) <= hi):
        raise SystemExit(f"{label} 必须 {lo}-{hi} 个，当前 {len(items)} 个")
    bad = [x for x in items if x not in term_map]
    if bad:
        raise SystemExit(f"{label} 含词表外的值：{bad}")
    return items


def _validate_enum(value, spec: dict, term_map: dict, label: str) -> str:
    v = "" if value is None else str(value).strip()
    if not v:
        if spec.get("optional"):
            return ""
        raise SystemExit(f"{label} 不能为空")
    if v not in term_map:
        raise SystemExit(f"{label} 含词表外的值：{v}")
    return v


def _validate_textarea(value, spec: dict, label: str) -> str:
    v = "" if value is None else str(value).strip()
    cap = int(spec.get("max", 2000))
    if len(v) > cap:
        raise SystemExit(f"{label} 超过 {cap} 字（当前 {len(v)} 字）")
    return v


def _validate_text(value, spec: dict, label: str) -> str:
    v = "" if value is None else str(value).strip()
    cap = int(spec.get("max", 500))
    if len(v) > cap:
        raise SystemExit(f"{label} 超过 {cap} 字（当前 {len(v)} 字）")
    return v


def _validate_kv(value, spec: dict, label: str, s: dict) -> list[str]:
    """扩展位：「键: 值」每行一条，保留原始行以便前端回显。"""
    if isinstance(value, str):
        items = [x.strip() for x in value.splitlines()]
    elif isinstance(value, list):
        items = [str(x).strip() for x in value]
    else:
        raise SystemExit(f"{label} 必须是数组或换行分隔的文本")
    items = [x for x in items if x]
    cap = int(spec.get("max_items", 24))
    if len(items) > cap:
        raise SystemExit(f"{label} 最多 {cap} 条（当前 {len(items)} 条）")
    item_cap = int(spec.get("item_max", limits(s).get("list_item_max", 300)))
    for line in items:
        if len(line) > item_cap:
            raise SystemExit(f"{label} 单条超过 {item_cap} 字：{line[:40]}")
        if ":" not in line and "：" not in line:
            raise SystemExit(f"{label} 每行必须写成「键: 值」：{line[:40]}")
    return items


def _validate_lines(value, spec: dict, label: str, s: dict) -> list[str]:
    if isinstance(value, str):
        items = [x.strip() for x in value.splitlines()]
    elif isinstance(value, list):
        items = [str(x).strip() for x in value]
    else:
        raise SystemExit(f"{label} 必须是数组或换行分隔的文本")
    items = [x for x in items if x]
    cap = int(spec.get("max_items", 12))
    if len(items) > cap:
        raise SystemExit(f"{label} 最多 {cap} 条（当前 {len(items)} 条）")
    item_cap = int(spec.get("item_max", limits(s).get("list_item_max", 300)))
    bad = [x for x in items if len(x) > item_cap]
    if bad:
        raise SystemExit(f"{label} 单条超过 {item_cap} 字：{bad[0][:40]}")
    return items


_FIELD_VALIDATORS = {
    "roles": lambda v, spec, tm, label, s: _validate_roles(v, spec, tm, label, s),
    "multi_enum": lambda v, spec, tm, label, s: _validate_multi_enum(v, spec, tm, label),
    "enum": lambda v, spec, tm, label, s: _validate_enum(v, spec, tm, label),
    "textarea": lambda v, spec, tm, label, s: _validate_textarea(v, spec, label),
    "lines": lambda v, spec, tm, label, s: _validate_lines(v, spec, label, s),
    "text": lambda v, spec, tm, label, s: _validate_text(v, spec, label),
    "kv": lambda v, spec, tm, label, s: _validate_kv(v, spec, label, s),
}


def validate_spirit_edit(item: dict, *, schema: dict | None = None,
                         term_map: dict | None = None,
                         allowed_ids: set[int] | None = None) -> dict:
    """按 schema 校验并规范化一条精灵编辑；不合法的直接 SystemExit。"""
    s = schema or load_schema()
    tm = term_map or terms(s)
    allowed = allowed_ids if allowed_ids is not None else editable_ids()
    if not isinstance(item, dict):
        raise SystemExit("每条编辑必须是对象")
    raw_id = item.get("id")
    if raw_id is None or str(raw_id).strip() in ("", "None", "待核"):
        key = str(item.get("key") or "")
        if key not in editable_keys():
            raise SystemExit(f"无序号精灵的 key 不在可编辑集合：{key!r}")
        sid = None
    else:
        try:
            sid = int(raw_id)
        except (TypeError, ValueError):
            raise SystemExit("编辑缺少合法 id：" + repr(item)[:120])
        if sid not in allowed:
            raise SystemExit(f"#{sid} 不在可编辑精灵集合（总表 + 资料层参照）内")
        key = str(sid)          # 有序号时忽略客户端 key，防止把编辑落到别的精灵上
        if item.get("key") and str(item["key"]) != key:
            print(f"WARN: #{sid} 补丁 key 与 id 不一致，已按 id 规范化：{item.get('key')!r}")

    out = {"id": sid, "key": key,
           "name": str((spirit_names().get(sid, "") if sid else "") or item.get("name") or "")}
    deep_ids = {int(x["id"]) for x in _load(ROSTER)["spirits"]}
    is_deep = sid in deep_ids
    for spec in s["fields"]:
        key, typ, label = spec["key"], spec["type"], spec["label"]
        if typ not in _FIELD_VALIDATORS:
            raise SystemExit(f"schema 字段 {key} 用了未支持的类型 {typ}")
        term_map_for_field = tm.get(spec["terms"], {}) if spec.get("terms") else {}
        if isinstance(term_map_for_field, list):
            term_map_for_field = set(term_map_for_field)
        effective_spec = spec
        if is_deep and "min_deep" in spec:
            effective_spec = dict(spec, min=spec["min_deep"])
        out[key] = _FIELD_VALIDATORS[typ](item.get(key), effective_spec,
                                          term_map_for_field, label, s)

    # 定位规范化：前端「定位」是一组（分类＋特色），数据层分存 classes / roles。
    # 若补丁把分类值塞进 roles（旧补丁或手写），这里按词表拆回去，保证两个字段语义不混。
    tag_terms = tm.get("classes") or {}
    if isinstance(out.get("roles"), list):
        cls = [x for x in out["roles"] if x in tag_terms]
        own = [x for x in out["roles"] if x not in tag_terms]
        if cls:
            out["classes"] = list(dict.fromkeys([*(out.get("classes") or []), *cls]))
        out["roles"] = own

    # 相似定位组成员的定位里必须包含该组的 core_role（只对已登记组员生效）。
    roles = out.get("roles", [])
    if roles:
        for g in _load(ROLE_GROUPS).get("groups", []):
            members = {int(x) for x in g.get("members", [])}
            outside = {int(x) for x in g.get("outside_layer_members", [])}
            if sid in members and sid not in outside and g.get("core_role") not in roles:
                raise SystemExit(
                    f"#{sid} 属于相似定位组「{g.get('name')}」，定位里必须包含"
                    f"「{g.get('core_role')}」，当前为 {roles!r}")
    return out


def _deep_ids() -> set[int]:
    return {int(x["id"]) for x in _load(ROSTER).get("spirits", [])}


def _id_list(value, label: str, lo: int, hi: int) -> list[int]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise SystemExit(f"{label} 必须是数组")
    out: list[int] = []
    for raw in value:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            raise SystemExit(f"{label} 含非法序号：{raw!r}")
        if sid not in out:
            out.append(sid)
    if not (lo <= len(out) <= hi):
        raise SystemExit(f"{label} 必须 {lo}-{hi} 个，当前 {len(out)} 个")
    return out


def _str_list(value, label: str, hi: int, item_cap: int) -> list[str]:
    if value is None:
        value = []
    if isinstance(value, str):
        value = re.split(r"[,，\n]", value)
    if not isinstance(value, list):
        raise SystemExit(f"{label} 必须是数组")
    out: list[str] = []
    for raw in value:
        text = str(raw).strip()
        if not text:
            continue
        if len(text) > item_cap:
            raise SystemExit(f"{label} 单条超过 {item_cap} 字：{text[:20]}…")
        if text not in out:
            out.append(text)
    if len(out) > hi:
        raise SystemExit(f"{label} 最多 {hi} 条")
    return out


def _marker_ok(marker: str) -> bool:
    if SOURCE_MARKERS.exists() and marker in set(_load(SOURCE_MARKERS).get("markers", [])):
        return True
    return bool(re.match(r"^(W|G):\d+$", marker) or re.match(r"^(SK|SA):\d+$", marker))


def _system_section(name: str, carrier: str) -> str:
    tail = re.sub(r"\s+", " ", carrier).strip()[:80] or "前端新建待补正文"
    return f"{name}：{tail}"[:160]


_CANVAS_LIMIT_KEYS = (
    "nodes_max", "notes_max", "skills_max", "skill_links_max", "note_links_max",
    "edge_colors_max", "coord_min", "coord_max", "coord_decimals",
    "note_text_max", "note_id_max", "skill_key_max", "skill_name_max",
    "link_type_max", "link_note_max",
)


def canvas_limits(schema: dict | None = None) -> dict[str, int]:
    """画布容量与长度上限：唯一来源 editor_schema.json#system_edit.canvas。

    前端读的是同一份数据（``SYS_CFG.canvas``），两边不再各写一套字面量；
    这里只列键名，数值缺失即报错，避免默认值又变成第二份真相。
    """
    cfg = ((schema or load_schema()).get("system_edit") or {}).get("canvas") or {}
    missing = [k for k in _CANVAS_LIMIT_KEYS if not isinstance(cfg.get(k), int)]
    if missing:
        raise KeyError("editor_schema.json system_edit.canvas missing or non-int: "
                       + ", ".join(missing))
    return {k: int(cfg[k]) for k in _CANVAS_LIMIT_KEYS}


def _system_canvas(raw_canvas, allowed: set[int],
                   limits: dict[str, int] | None = None) -> dict | None:
    """图形画布：成员几何位置 + 备注便签 + 技能卡及三类连线。

    2026-11-17：便签可当连线端点（``note_links``）；技能卡与其连线以前只在
    前端内存里，补丁落库会丢，这里一并保留。三类边都不进 ``chain_edges``。
    ``edge_colors`` 是逐条线色（键为两端 key 排序拼接），只收 ``#rrggbb``，
    未设色的线不写字段，保证历史体系落库前后一致。
    所有容量／长度上限来自 ``canvas_limits()``（即 editor_schema.json），不写字面量。
    """
    if not isinstance(raw_canvas, dict) or not isinstance(raw_canvas.get("nodes"), list):
        return None
    lim = limits or canvas_limits()
    dec = lim["coord_decimals"]
    lo, hi = lim["coord_min"], lim["coord_max"]
    in_range = lambda x, y: lo <= x <= hi and lo <= y <= hi  # noqa: E731
    out, seen = [], set()
    for row in raw_canvas["nodes"][:lim["nodes_max"]]:
        if not isinstance(row, dict):
            continue
        try:
            sid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        if sid not in allowed or sid in seen:
            continue
        try:
            x, y = float(row.get("x")), float(row.get("y"))
        except (TypeError, ValueError):
            continue
        if not in_range(x, y):
            continue
        seen.add(sid)
        out.append({"id": sid, "x": round(x, dec), "y": round(y, dec)})
    notes: list[dict] = []
    raw_notes = raw_canvas.get("notes")
    if isinstance(raw_notes, list):
        for row in raw_notes[:lim["notes_max"]]:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()[:lim["note_text_max"]]
            if not text:
                continue
            try:
                x, y = float(row.get("x")), float(row.get("y"))
            except (TypeError, ValueError):
                x, y = 0.0, 0.0
            if not in_range(x, y):
                continue
            notes.append({"id": str(row.get("id") or ("n%d" % len(notes)))[:lim["note_id_max"]],
                          "x": round(x, dec), "y": round(y, dec), "text": text})
    if not out and not notes:
        return None

    note_ids = {n["id"] for n in notes}
    skill_keys = set()

    skills: list[dict] = []
    raw_skills = raw_canvas.get("skills")
    if isinstance(raw_skills, list):
        for row in raw_skills[:lim["skills_max"]]:
            if not isinstance(row, dict):
                continue
            key = str(row.get("key") or "").strip()[:lim["skill_key_max"]]
            if not key.startswith("s:"):
                continue
            try:
                pet = int(row.get("pet"))
            except (TypeError, ValueError):
                continue
            if pet not in allowed:
                continue
            try:
                x, y = float(row.get("x")), float(row.get("y"))
            except (TypeError, ValueError):
                x, y = 0.0, 0.0
            if not in_range(x, y):
                continue
            try:
                sid = int(row.get("sid") or 0)
            except (TypeError, ValueError):
                sid = 0
            skills.append({"key": key, "pet": pet, "sid": sid,
                           "name": str(row.get("name") or "")[:lim["skill_name_max"]],
                           "x": round(x, dec), "y": round(y, dec)})
            skill_keys.add(key)

    def _pair(row):
        if isinstance(row, (list, tuple)) and len(row) == 2:
            return str(row[0]), str(row[1])
        if isinstance(row, dict) and row.get("a") and row.get("b"):
            return str(row["a"]), str(row["b"])
        return None

    def _endpoint_ok(k: str) -> bool:
        if k in note_ids:
            return True
        if k.startswith("s:"):
            return k in skill_keys
        try:
            return int(k) in allowed
        except (TypeError, ValueError):
            return False

    skill_links: list[list[str]] = []
    raw_links = raw_canvas.get("skill_links")
    if isinstance(raw_links, list):
        for row in raw_links[:lim["skill_links_max"]]:
            pair = _pair(row)
            if not pair:
                continue
            a, b = pair
            if a == b or (a, b) in {(x[0], x[1]) for x in skill_links}:
                continue
            if not (a.startswith("s:") or b.startswith("s:")):
                continue
            if not (_endpoint_ok(a) and _endpoint_ok(b)):
                continue
            skill_links.append([a, b])

    note_links: list[dict] = []
    seen_note: set[tuple[str, str]] = set()
    raw_note_links = raw_canvas.get("note_links")
    if isinstance(raw_note_links, list):
        for row in raw_note_links[:lim["note_links_max"]]:
            if not isinstance(row, dict):
                continue
            a, b = str(row.get("a") or ""), str(row.get("b") or "")
            if not a or not b or a == b:
                continue
            if a not in note_ids and b not in note_ids:
                continue
            if not (_endpoint_ok(a) and _endpoint_ok(b)):
                continue
            pair = tuple(sorted((a, b)))
            if pair in seen_note:
                continue
            seen_note.add(pair)
            note_links.append({"a": a, "b": b,
                               "type": str(row.get("type") or "")[:lim["link_type_max"]],
                               "note": str(row.get("note") or "").strip()[:lim["link_note_max"]]})

    # 连线颜色：键为两端 key（精灵 id／s:…／n…）排序后拼接，三类边共用一张表。
    # 未设色的边不写字段，历史体系落库前后完全一致。
    edge_colors: dict[str, str] = {}
    raw_colors = raw_canvas.get("edge_colors")
    if isinstance(raw_colors, dict):
        def _hex(v: str) -> str:
            return v.lower() if len(v) == 7 and v[0] == "#" and all(
                c in "0123456789abcdefABCDEF" for c in v[1:]) else ""
        for raw_key, raw_val in list(raw_colors.items())[:lim["edge_colors_max"]]:
            parts = str(raw_key).split("|")
            if len(parts) != 2:
                continue
            a, b = parts[0].strip(), parts[1].strip()
            if not a or not b or a == b:
                continue
            if not (_endpoint_ok(a) and _endpoint_ok(b)):
                continue
            color = _hex(str(raw_val or "").strip())
            if color:
                edge_colors[a + "|" + b] = color

    # 连线备注：键同 edge_colors（两端 key 排序拼接），只用于技能卡／备注文本这两类边；
    # 精灵↔精灵的备注仍走 edge_meta（键必须是精灵 id）。
    link_notes: dict[str, str] = {}
    raw_link_notes = raw_canvas.get("link_notes")
    if isinstance(raw_link_notes, dict):
        for raw_key, raw_val in list(raw_link_notes.items())[:96]:
            parts = str(raw_key).split("|")
            if len(parts) != 2:
                continue
            a, b = parts[0].strip(), parts[1].strip()
            if not a or not b or a == b:
                continue
            if not (_endpoint_ok(a) and _endpoint_ok(b)):
                continue
            text = str(raw_val or "").strip()[:800]
            if text:
                link_notes[a + "|" + b] = text

    canvas = {"nodes": out, "notes": notes}
    if skills:
        canvas["skills"] = skills
    if skill_links:
        canvas["skill_links"] = skill_links
    if note_links:
        canvas["note_links"] = note_links
    if edge_colors:
        canvas["edge_colors"] = edge_colors
    if link_notes:
        canvas["link_notes"] = link_notes
    return canvas


def _system_edges(raw_edges, raw_meta, allowed: set[int]) -> tuple[list[list[int]], dict]:
    """显式边全量状态：同一无序对只一条，端点须可编辑。

    2026-11-09 用户口径：备注不再有字数下限，允许留空；每条边都会补一条
    ``edge_meta``（type 取词表首项），避免落库后 check_roster 报「边缺类型」。
    """
    if not isinstance(raw_edges, list):
        raise SystemExit("chain_edges 必须是数组")
    edge_types = (load_schema().get("edge_types") or {})
    lim = (load_schema().get("limits") or {})
    lo = lim.get("edge_note_min", 0)
    hi = lim.get("edge_note_max", 800)
    default_type = next(iter(edge_types), "resource")
    edges, seen = [], set()
    for pair in raw_edges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise SystemExit("chain_edges 必须是 [起点, 终点] 数组")
        try:
            a, b = int(pair[0]), int(pair[1])
        except (TypeError, ValueError):
            raise SystemExit("chain_edges 端点必须是整数序号")
        if a == b or a not in allowed or b not in allowed:
            raise SystemExit(f"联动边端点不合法：{a}→{b}")
        key = tuple(sorted((a, b)))
        if key in seen:
            raise SystemExit(f"同一对精灵只能有一条有向边：{a}-{b}")
        seen.add(key)
        edges.append([a, b])
    meta: dict = {}
    supplied = raw_meta if isinstance(raw_meta, dict) else {}
    for a, b in edges:
        key = "%d-%d" % (a, b)
        v = supplied.get(key) or {}
        if not isinstance(v, dict):
            v = {}
        typ = str(v.get("type") or "")
        note = str(v.get("note") or "").strip()
        if typ and typ not in edge_types:
            raise SystemExit(f"边类型不在词表内：{typ}")
        if not (lo <= len(note) <= hi):
            raise SystemExit(f"边 {key} 的说明需 {lo}-{hi} 字")
        meta[key] = {"type": typ or default_type, "note": note}
    return edges, meta


def validate_system_create(raw: dict, schema: dict | None = None,
                           existing_keys: set[str] | None = None) -> dict:
    """校验并规范化前端新建的体系；不写盘，由 apply_system_view_edits.py 落库。"""
    if not isinstance(raw, dict):
        raise SystemExit("system_state.create 的每一项必须是对象")
    s = schema or load_schema()
    cfg = s.get("system_edit") or {}
    lim = cfg.get("limits") or {}
    systems_doc = _load(SYSTEMS)
    existing = existing_keys or {x["key"] for x in systems_doc.get("systems", [])}
    names = {x.get("name") for x in systems_doc.get("systems", [])}

    name = str(raw.get("name", "")).strip()
    # 2026-11-09 用户口径：名称不再要求以「体系」结尾，也不设 4 字下限。
    if not (lim.get("name_min", 1) <= len(name) <= lim.get("name_max", 60)):
        raise SystemExit(f"体系名称需 1-{lim.get('name_max', 60)} 字")
    kind = str(raw.get("kind") or cfg.get("defaults", {}).get("kind") or "同队联动").strip()
    if kind not in systems_doc.get("kinds", {}):
        raise SystemExit(f"体系类型不在 systems.json#kinds 内：{kind!r}")
    if name in existing or name in names:
        raise SystemExit(f"体系已存在，不能重复创建：{name}")
    banned = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
    hit = [x for x in banned if x in name]
    if hit:
        raise SystemExit(f"体系名称含前端禁用词：{hit}")

    core = _id_list(raw.get("core"), "核心", 1, lim.get("core_max", 6))
    # 2026-11-09 用户口径：新建体系不再区分深研层，核心成员从全部可编辑精灵里选。
    allowed = editable_ids()
    bad_core = set(core) - allowed
    if bad_core:
        raise SystemExit(f"核心含不可编辑精灵（须为总表／资料层序号）：{sorted(bad_core)}")
    support = _id_list(raw.get("support"), "补位", 0, lim.get("support_max", 8))
    counter = _id_list(raw.get("counter"), "反向对位", 0, lim.get("counter_max", 8))
    bad = (set(support) | set(counter)) - allowed
    if bad:
        raise SystemExit(f"补位／对位含不可编辑精灵：{sorted(bad)}")

    evidence = str(raw.get("evidence", "")).strip()
    if not (lim.get("evidence_min", 0) <= len(evidence) <= lim.get("evidence_max", 600)):
        raise SystemExit(f"证据说明需 0-{lim.get('evidence_max', 600)} 字")
    carrier = str(raw.get("carrier", "")).strip()
    if len(carrier) > lim.get("carrier_max", 200):
        raise SystemExit("载体／定位超过长度上限")
    status = str(raw.get("status") or cfg.get("defaults", {}).get("status", "")).strip()
    if len(status) > lim.get("status_max", 200):
        raise SystemExit("状态文案超过长度上限")
    review = str(raw.get("review_note", "")).strip()
    if len(review) > lim.get("review_max", 600):
        raise SystemExit("复核备注超过长度上限")
    aliases = _str_list(raw.get("aliases"), "别名", lim.get("aliases_max", 8),
                        lim.get("alias_item_max", 20))
    sources = _str_list(raw.get("sources"), "来源标记", lim.get("sources_max", 8),
                        lim.get("source_item_max", 40))
    if not sources:
        sources = [f"W:{core[0]}"]
    bad_sources = [x for x in sources if not _marker_ok(x)]
    if bad_sources:
        raise SystemExit(f"来源标记未登记或格式不正确：{bad_sources}")
    article = str(raw.get("section_note", "")).strip()
    if len(article) > lim.get("article_max", 2000):
        raise SystemExit("正文补充超过长度上限")

    defaults = cfg.get("defaults", {})
    blob = "".join([name, kind, carrier, evidence, status, review, article] + aliases)
    banned_hits = [x for x in ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
                   if x in blob]
    if banned_hits:
        raise SystemExit(f"体系资料含前端禁用词：{banned_hits}")
    return {
        "key": name,
        "name": name,
        "core": core,
        "support": support,
        "counter": counter,
        "kind": kind,
        "evidence": evidence,
        "sources": sources,
        "section": _system_section(name, carrier),
        "carrier": carrier,
        "status": status,
        "review_note": review,
        "aliases": aliases,
        "chain_edges": [],
        "edge_meta": {},
        "alternatives": {},
        "warning_edges": [],
        "external": [],
        "evidence_grade": defaults.get("evidence_grade", "机制推演／待核"),
        "chain_status": defaults.get("chain_status", "顺序链待核（证据不足）"),
        "origin": "view_edit",
        "created_at": date.today().isoformat(),
        "section_note": article,
        "canvas": _system_canvas(raw.get("canvas"), set(core) | set(support) | set(counter)),
    }


def validate_system_edit(raw: dict, schema: dict | None = None) -> dict:
    """已有体系只允许改文本字段；名称／类型／成员/章节不可通过补丁修改。"""
    if not isinstance(raw, dict):
        raise SystemExit("system_edits 的每一项必须是对象")
    s = schema or load_schema()
    lim = (s.get("system_edit") or {}).get("limits") or {}
    doc = _load(SYSTEMS)
    items = {x["key"]: x for x in doc.get("systems", [])}
    key = str(raw.get("key") or raw.get("name") or "").strip()
    item = items.get(key)
    if not item:
        raise SystemExit(f"要编辑的体系不存在：{key!r}")
    if raw.get("name") is not None and str(raw["name"]).strip() != item["name"]:
        raise SystemExit("体系名称不可修改；如确需改名，请由维护者手工迁移并保留留痕")
    allowed = {"evidence", "sources", "status", "carrier", "review_note", "aliases"}
    unknown = sorted(set(raw) - allowed - {"key", "name"})
    if unknown:
        raise SystemExit(f"体系编辑含不可修改字段：{unknown}（名称／类型／成员／章节不可改）")
    out: dict = {"key": key}
    if "evidence" in raw:
        text = str(raw["evidence"]).strip()
        if not (lim.get("evidence_min", 0) <= len(text) <= lim.get("evidence_max", 600)):
            raise SystemExit(f"证据说明需 0-{lim.get('evidence_max', 600)} 字")
        out["evidence"] = text
    if "status" in raw:
        text = str(raw["status"]).strip()
        if len(text) > lim.get("status_max", 200):
            raise SystemExit("状态文案超过长度上限")
        out["status"] = text
    if "carrier" in raw:
        text = str(raw["carrier"]).strip()
        if len(text) > lim.get("carrier_max", 200):
            raise SystemExit("载体／定位超过长度上限")
        out["carrier"] = text
    if "review_note" in raw:
        text = str(raw["review_note"]).strip()
        if len(text) > lim.get("review_max", 600):
            raise SystemExit("复核备注超过长度上限")
        out["review_note"] = text
    if "aliases" in raw:
        out["aliases"] = _str_list(raw.get("aliases"), "别名", lim.get("aliases_max", 8),
                                   lim.get("alias_item_max", 20))
    if "sources" in raw:
        sources = _str_list(raw.get("sources"), "来源标记", lim.get("sources_max", 8),
                            lim.get("source_item_max", 40))
        if not sources:
            raise SystemExit("来源标记不能为空")
        bad = [x for x in sources if not _marker_ok(x)]
        if bad:
            raise SystemExit(f"来源标记未登记或格式不正确：{bad}")
        out["sources"] = sources
    if len(out) == 1:
        raise SystemExit("体系编辑没有实际字段变化")
    blob = json.dumps(out, ensure_ascii=False)
    banned_hits = [x for x in ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
                   if x in blob]
    if banned_hits:
        raise SystemExit(f"体系资料含前端禁用词：{banned_hits}")
    return out


def validate_system_overwrite(raw: dict, schema: dict | None = None) -> dict:
    """2026-11-09：既有体系可整体编辑（成员／位置／连边／备注／文本），
    但名称、类型、章节不可改，避免破坏 tactics.md 与 SKILL.md 的登记。"""
    if not isinstance(raw, dict):
        raise SystemExit("system_state.overwrite 的每一项必须是对象")
    s = schema or load_schema()
    lim = (s.get("system_edit") or {}).get("limits") or {}
    doc = _load(SYSTEMS)
    items = {x["key"]: x for x in doc.get("systems", [])}
    key = str(raw.get("key") or raw.get("name") or "").strip()
    item = items.get(key)
    if not item:
        raise SystemExit(f"要编辑的体系不存在：{key!r}")
    if raw.get("name") is not None and str(raw["name"]).strip() != item["name"]:
        raise SystemExit("体系名称不可修改（章节与速查表按名称登记）")
    allowed_fields = {"core", "support", "counter", "canvas", "chain_edges", "edge_meta",
                      "carrier", "evidence", "status", "review_note", "aliases", "sources",
                      "section_note"}
    unknown = sorted(set(raw) - allowed_fields - {"key", "name"})
    if unknown:
        raise SystemExit(f"体系编辑含不支持字段：{unknown}")
    ids = editable_ids()
    out: dict = {"key": key}
    members = set(map(int, item.get("core") or []))
    for field, cap, minimum in (("core", lim.get("core_max", 6), 1),
                                ("support", lim.get("support_max", 8), 0),
                                ("counter", lim.get("counter_max", 8), 0)):
        if field not in raw:
            continue
        vals = _id_list(raw.get(field), field, minimum, cap)
        bad = set(vals) - ids
        if bad:
            raise SystemExit(f"{field} 含不可编辑精灵：{sorted(bad)}")
        out[field] = vals
        if field == "core":
            members = set(vals)
    if "core" in out:
        members |= set(out.get("support") or item.get("support") or [])
        members |= set(out.get("counter") or item.get("counter") or [])
    if "canvas" in raw:
        out["canvas"] = _system_canvas(raw.get("canvas"), members)
    if "chain_edges" in raw:
        edges, meta = _system_edges(raw.get("chain_edges"), raw.get("edge_meta"), ids)
        out["chain_edges"] = edges
        out["edge_meta"] = meta
    for field, cap in (("carrier", lim.get("carrier_max", 200)),
                       ("status", lim.get("status_max", 200)),
                       ("review_note", lim.get("review_max", 600)),
                       ("section_note", lim.get("article_max", 2000))):
        if field in raw:
            text = str(raw.get(field) or "").strip()
            if len(text) > cap:
                raise SystemExit(f"{field} 超过 {cap} 字")
            out[field] = text
    if "evidence" in raw:
        text = str(raw.get("evidence") or "").strip()
        if not (lim.get("evidence_min", 0) <= len(text) <= lim.get("evidence_max", 600)):
            raise SystemExit("证据说明长度不合法")
        out["evidence"] = text
    if "aliases" in raw:
        out["aliases"] = _str_list(raw.get("aliases"), "别名",
                                   lim.get("aliases_max", 8), lim.get("alias_item_max", 20))
    if "sources" in raw:
        sources = _str_list(raw.get("sources"), "来源标记",
                            lim.get("sources_max", 8), lim.get("source_item_max", 40))
        if not sources:
            raise SystemExit("来源标记不能为空")
        bad_sources = [x for x in sources if not _marker_ok(x)]
        if bad_sources:
            raise SystemExit(f"来源标记未登记：{bad_sources}")
        out["sources"] = sources
    if len(out) == 1:
        raise SystemExit("体系编辑没有实际字段变化")
    blob = json.dumps(out, ensure_ascii=False)
    banned = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
    hit = [x for x in banned if x in blob]
    if hit:
        raise SystemExit(f"体系资料含前端禁用词：{hit}")
    return out


def validate_system_delete(raw, schema: dict | None = None) -> str:
    """删除既有体系：返回 key，落库脚本同步移除 tactics.md 章节与 SKILL 速查行。"""
    key = str(raw.get("key") if isinstance(raw, dict) else raw or "").strip()
    if not key:
        raise SystemExit("system_state.delete 的每一项必须是体系 key")
    doc = _load(SYSTEMS)
    if key not in {x["key"] for x in doc.get("systems", [])}:
        raise SystemExit(f"要删除的体系不存在：{key!r}")
    return key


def check_invariants() -> list[str]:
    """给 check_roster.py 用：schema 自身、前端内联 schema、落库 id 的一致性。"""
    errors: list[str] = []
    if not SCHEMA_PATH.exists():
        return ["references/catalog/editor_schema.json is missing"]
    s = load_schema()
    ver = float(s.get("schema_version", 0) or 0)
    if ver < SCHEMA_VERSION:
        errors.append(f"editor_schema.json schema_version must be >= {SCHEMA_VERSION}, got {ver}")
    keys = [f.get("key") for f in s.get("fields", [])]
    if len(keys) != len(set(keys)) or not keys:
        errors.append("editor_schema.json fields have duplicate or empty keys")
    tm = terms(s)
    for f in s.get("fields", []):
        if f.get("type") not in FIELD_TYPES:
            errors.append(f"editor_schema.json field {f['key']}: unsupported type {f.get('type')}")
        if f.get("terms") and f["terms"] not in tm:
            errors.append(f"editor_schema.json field {f['key']}: unknown terms {f['terms']}")
    if not s.get("edge_types"):
        errors.append("editor_schema.json edge_types is empty")

    for name, spec in (s.get("registries") or {}).items():
        if name.startswith("_"):
            continue
        if not isinstance(spec, dict) or not spec.get("select_only"):
            errors.append(f"editor_schema.json registry {name} must declare select_only=true")
    registry_systems = set(terms(s).get("systems", {}))
    if not registry_systems:
        errors.append("editor_schema.json systems registry is empty")
    # 2026-11-08：体系注册表从「只读」放宽为「可新增、不可删除/改名」。
    sys_reg = (s.get("registries") or {}).get("systems") or {}
    if not sys_reg.get("creatable"):
        errors.append("editor_schema.json registries.systems must declare creatable=true")
    if sys_reg.get("deletable") or sys_reg.get("rename"):
        errors.append("editor_schema.json registries.systems must be non-deletable and non-renamable")
    sys_cfg = s.get("system_edit") or {}
    if not sys_cfg.get("enabled"):
        errors.append("editor_schema.json system_edit.enabled must be true")
    if (sys_cfg.get("create_key") or "") in set(s.get("forbidden_patch_keys", [])):
        errors.append("editor_schema.json system_edit.create_key must not be a forbidden patch key")
    field_keys = {f.get("key") for f in s.get("system_fields", [])}
    required_fields = {"name", "kind", "core", "support", "counter", "evidence", "sources"}
    if not required_fields.issubset(field_keys):
        errors.append(f"editor_schema.json system_fields missing: {sorted(required_fields - field_keys)}")

    view_path = REF / "spirit_synergy_view.html"
    if view_path.exists():
        text = view_path.read_text(encoding="utf-8")
        try:
            payload = viewdata.parse(text)
            inline = (payload.get("editor") or {}).get("schema") or {}
            if inline.get("schema_version") != s["schema_version"] or \
                    [f["key"] for f in inline.get("fields", [])] != keys:
                errors.append("synergy view inlined editor schema differs from editor_schema.json; rebuild it")
            if inline.get("system_edit") != s.get("system_edit") or \
                    [f.get("key") for f in inline.get("system_fields", [])] != \
                    [f.get("key") for f in s.get("system_fields", [])]:
                errors.append("synergy view inlined system manager schema differs; rebuild it")
            inline_systems = set((inline.get("terms") or {}).get("systems", {}))
            if inline_systems and inline_systems != registry_systems:
                errors.append("synergy view inlined system registry differs from systems.json; rebuild it")
            for name, spec in (inline.get("registries") or {}).items():
                if not name.startswith("_") and not (isinstance(spec, dict) and spec.get("select_only")):
                    errors.append(f"synergy view registry {name} is not marked select_only")
        except (viewdata.ViewDataError, KeyError, TypeError) as exc:
            errors.append(f"synergy view inlined editor schema unreadable: {exc}")

    allowed = editable_ids()
    keys = editable_keys()
    if VIEW_EDITS.exists():
        try:
            for item in _load(VIEW_EDITS).get("edits", []):
                raw = item.get("id")
                if raw is None:
                    if str(item.get("key")) not in keys:
                        errors.append(f"view_edits.json key {item.get('key')!r} is not editable")
                elif int(raw) not in allowed:
                    errors.append(f"view_edits.json id {raw} is not an editable spirit")
                for sys_key in item.get("system_keys", []) or []:
                    if sys_key not in registry_systems:
                        errors.append(f"view_edits.json #{raw} references unknown system {sys_key!r}")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"view_edits.json unreadable: {exc}")
    return errors


if __name__ == "__main__":
    s = load_schema()
    print("schema %.1f | %d fields | %d editable spirits | edge types %d" %
          (s["schema_version"], len(s["fields"]), len(editable_ids()), len(s["edge_types"])))
    problems = check_invariants()
    print("invariants:", problems or "OK")
    raise SystemExit(1 if problems else 0)

#!/usr/bin/env python3
"""Validate the curated Seer PvP roster.

Offline checks run without third-party packages. It validates both layers:
the curated deep-dive roster and the full 1203-spirit BWIKI catalog shipped in
``data/bwiki/pool.json``. ``--online`` checks 4399 source pages when available and
otherwise falls back to the BWIKI spirit page. A soul-ability keyword must
still be present; network failures are reported separately and never mean
“no soul ability”.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from collections import Counter
from pathlib import Path

import viewdata

ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = ROOT / "references" / "catalog" / "roster.json"
SOURCES_PATH = ROOT / "references" / "docs" / "sources.md"
CATALOG_PATH = ROOT / "data" / "bwiki" / "pool.json"
OVERRIDES_PATH = ROOT / "references" / "catalog" / "manual_overrides.json"
SOUL_FULL_PATH = ROOT / "data" / "seerapi" / "soul_full.json"
SOUL_GAP_PATH = ROOT / "references" / "catalog" / "soul_text_gaps.json"
VOIDED_PATH = ROOT / "references" / "catalog" / "voided_drops.json"
GAP_PATH = ROOT / "references" / "catalog" / "tier_gaps.json"
MIN_ID = 2987
# 状态词表与 editor_schema.json 同源，避免两处硬编码漂移。
VALID_STATUS = set(json.loads(
    (ROOT / "references" / "catalog" / "editor_schema.json").read_text(encoding="utf-8"))["statuses"])
# 2026-11-08：来源白名单改为数据文件驱动，新增体系/来源标记不用改 Python。
_MARKERS_PATH = ROOT / "references" / "catalog" / "source_markers.json"
KNOWN_SOURCES = (set(json.loads(_MARKERS_PATH.read_text(encoding="utf-8"))["markers"])
                 if _MARKERS_PATH.exists() else set())


def load_roster() -> dict:
    try:
        with ROSTER_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON at {exc.lineno}:{exc.colno}: {exc.msg}") from exc


def validate_systems(active_ids: set[int], source_index: str) -> tuple[list[str], list[str]]:
    """Every named 「XX 体系」 must be indexed in SKILL.md and documented in tactics.md."""
    errors: list[str] = []
    warnings: list[str] = []
    systems_path = ROOT / "references" / "catalog" / "systems.json"
    tactics_path = ROOT / "references" / "docs" / "tactics.md"
    skill_path = ROOT / "SKILL.md"
    if not systems_path.exists():
        return ["references/catalog/systems.json is missing"], warnings
    try:
        doc = json.loads(systems_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"systems.json invalid JSON: {exc}"], warnings
    items = doc.get("systems", [])
    if not items:
        return ["systems.json has no named systems"], warnings
    tactics = tactics_path.read_text(encoding="utf-8") if tactics_path.exists() else ""
    skill = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    if not tactics:
        errors.append("references/docs/tactics.md is missing or empty")
    if not skill:
        errors.append("SKILL.md is missing or empty")
    catalog_ids: set[int] = set()
    if CATALOG_PATH.exists():
        catalog_ids = {x.get("id") for x in
                       json.loads(CATALOG_PATH.read_text(encoding="utf-8")).get("elves", [])}
    # 2026-11-08：所有前端可编辑精灵都可作为显式边端点（含候选池／专题层／资料层参照），
    # 白名单与 editor_schema.editable_ids() 保持一致；只算一次，别在循环里重复读文件。
    sys.path.insert(0, str(ROOT / "scripts"))
    import editor_schema  # noqa: PLC0415
    editable_ids = editor_schema.editable_ids()

    keys = [item.get("key") for item in items]
    duplicate_keys = sorted(k for k, v in Counter(keys).items() if v > 1)
    if duplicate_keys:
        errors.append(f"systems.json duplicate keys: {duplicate_keys}")
    for item in items:
        label = item.get("name") or item.get("key") or "?"
        for field in ("core", "support", "counter"):
            values = item.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, int) for v in values):
                errors.append(f"system {label}: {field} must be a list of integer ids")
        edge_ids = set()
        for edge in item.get("chain_edges", []):
            if not isinstance(edge, (list, tuple)) or len(edge) != 2 or \
                    any(not isinstance(v, int) for v in edge):
                errors.append(f"system {label}: chain_edges must be [int, int] pairs")
                continue
            edge_ids.update(edge)
        missing_edge_ids = edge_ids - active_ids - catalog_ids - editable_ids
        if missing_edge_ids:
            errors.append(f"system {label}: chain_edges ids absent from roster/catalog/editable: "
                          f"{sorted(missing_edge_ids)}")
        override = item.get("chain_status_override")
        if override and override not in doc.get("chain_statuses", {}):
            errors.append(f"system {label}: unregistered chain_status_override {override!r}")
        core = set(item.get("core", []))
        # 2026-11-09：新建体系不再区分深研层，核心与补位／对位统一按
        # 深研层＋候选池＋资料层参照＋全量图鉴判定，只要序号有据即可。
        core_missing = core - active_ids - catalog_ids - editable_ids
        if core_missing:
            errors.append(f"system {label}: core ids absent from roster/catalog/editable: "
                          f"{sorted(core_missing)}")
        # 2026-11-09：画布几何位置只允许登记该体系成员，坐标必须是有限非负数。
        canvas = item.get("canvas")
        if canvas is not None:
            nodes = canvas.get("nodes") if isinstance(canvas, dict) else None
            if not isinstance(nodes, list):
                errors.append(f"system {label}: canvas.nodes must be a list")
            else:
                members = core | set(item.get("support", [])) | set(item.get("counter", []))
                for row in nodes:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), int):
                        errors.append(f"system {label}: canvas node lacks integer id")
                        continue
                    if row["id"] not in members:
                        errors.append(f"system {label}: canvas id {row['id']} is not a member")
                    for axis in ("x", "y"):
                        val = row.get(axis)
                        if not isinstance(val, (int, float)) or not (0 <= val <= 4000):
                            errors.append(f"system {label}: canvas {axis} invalid for #{row['id']}")
            notes = canvas.get("notes") if isinstance(canvas, dict) else None
            if notes is not None:
                if not isinstance(notes, list):
                    errors.append(f"system {label}: canvas.notes must be a list")
                else:
                    for row in notes:
                        if not isinstance(row, dict) or len(str(row.get("text") or "")) > 300:
                            errors.append(f"system {label}: canvas note malformed")
        extra = (set(item.get("support", [])) | set(item.get("counter", []))) - active_ids - catalog_ids
        if extra:
            errors.append(f"system {label}: support/counter ids absent from catalog: {sorted(extra)}")
        section = item.get("section")
        if not section or section not in tactics:
            errors.append(f"system {label}: section is missing from tactics.md")
        for source in item.get("sources", []):
            if source in KNOWN_SOURCES:
                if f"**{source}**" not in source_index:
                    errors.append(f"system {label}: source {source!r} is not documented in sources.md")
            elif not ((source.startswith(("W:", "G:")) and source[2:].isdigit())
                      or (source.startswith(("SK:", "SA:")) and source[3:].isdigit())):
                errors.append(f"system {label}: unknown source marker {source!r}")
        if label not in skill:
            errors.append(f"system {label}: missing from SKILL.md 体系速查")
    if f"{len(items)} 项" not in skill:
        errors.append(f"SKILL.md system count is stale: expected {len(items)} 项")
    if not doc.get("naming_rule"):
        warnings.append("systems.json has no naming_rule")
    return errors, warnings


def validate_synergy_view() -> tuple[list[str], list[str]]:
    """Keep the offline partner/systems front end in sync with the data layers."""
    errors: list[str] = []
    warnings: list[str] = []
    view_path = ROOT / "references" / "spirit_synergy_view.html"
    if not view_path.exists():
        return ["references/spirit_synergy_view.html is missing; restore it from dist/seer-peak-pvp.zip "
            "then run python scripts/rebuild_view.py"], warnings
    text = view_path.read_text(encoding="utf-8")
    try:
        payload = viewdata.parse(text)
    except viewdata.ViewDataError as exc:
        return [f"spirit_synergy_view.html inlined data is invalid: {exc}"], warnings

    systems = json.loads((ROOT / "references" / "catalog" / "systems.json").read_text(encoding="utf-8"))["systems"]
    stats = payload.get("stats", {})
    if stats.get("systems") != len(systems):
        errors.append(f"synergy view system count is stale: {stats.get('systems')} != {len(systems)}; rebuild it")
    if sorted(x["name"] for x in payload.get("systems", [])) != sorted(x["name"] for x in systems):
        errors.append("synergy view systems differ from systems.json; rebuild it")

    import csv
    master = ROOT / "references" / "catalog" / "spirit_master_list.csv"
    if master.exists():
        with master.open(encoding="utf-8-sig", newline="") as fh:
            rows = sum(1 for _ in csv.reader(fh)) - 1
        if stats.get("spirits") != rows:
            errors.append(f"synergy view spirit count is stale: {stats.get('spirits')} != master list {rows}; rebuild it")

    # 2026-11-08 防回归：前端内联的显式边清单／类型词表必须与数据层一致，
    # 否则「关系联动编辑」会用过期快照全量覆盖 systems.json。
    expected = []
    for item in systems:
        for a, b in item.get("chain_edges", []):
            meta = (item.get("edge_meta") or {}).get("%s-%s" % (a, b), {})
            expected.append((item["key"], int(a), int(b), meta.get("type", "resource"),
                             str(meta.get("note", "")).strip()))
    got = []
    for e in payload.get("edges", []):
        try:
            got.append((str(e.get("system_key")), int(e.get("a")), int(e.get("b")),
                        e.get("type"), str(e.get("note", "")).strip()))
        except (TypeError, ValueError):
            errors.append(f"synergy view has malformed inlined edge: {e!r}"[:200])
    if sorted(got) != sorted(expected):
        errors.append("synergy view inlined edges are stale or differ from systems.json; rebuild it")
    from edge_consts import EDGE_TYPES  # noqa: PLC0415
    if set(payload.get("edge_types", {})) != set(EDGE_TYPES):
        errors.append("synergy view edge_types differ from edge_consts.EDGE_TYPES; rebuild it")

    legacy_terms = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")
    hits = [w for w in legacy_terms if w in text]
    if hits:
        errors.append(f"synergy view contains retired filter wording: {hits}")

    # 2026-11-10：魂印专属名词词典必须与 data/derived/soul_terms.json 同步（前端内联为 DATA.terms）。
    terms_doc = ROOT / "data" / "derived" / "soul_terms.json"
    inlined = payload.get("terms") or {}
    if not terms_doc.exists():
        errors.append("data/derived/soul_terms.json is missing; run python scripts/build_soul_terms.py")
    else:
        try:
            src = json.loads(terms_doc.read_text(encoding="utf-8"))
            names = {k for k, v in (src.get("terms") or {}).items() if (v.get("d") or "").strip()}
            if not names:
                errors.append("data/derived/soul_terms.json carries no terms")
            elif set(inlined.get("terms", {})) != names:
                errors.append("synergy view soul terms are stale or differ from soul_terms.json; rebuild it")
            elif inlined.get("stats", {}).get("terms") != len(names):
                errors.append("synergy view soul term count is stale; rebuild it")
            elif sorted(inlined.get("cats", {})) != ["eff", "ex", "timing"]:
                errors.append("synergy view soul term categories must be eff/ex/timing; rebuild it")
            else:
                # 每条内联名词必须是 [释义, 来源代码, 类别]，类别供三色圆环切换使用。
                bad_cat = [k for k, v in (inlined.get("terms") or {}).items()
                           if not isinstance(v, list) or len(v) != 3 or v[2] not in ("eff", "ex", "timing")]
                if bad_cat:
                    errors.append(f"synergy view soul terms missing category: {bad_cat[:5]}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"soul_terms.json unreadable: {exc}")

    keys = {n["k"] for n in payload.get("nodes", [])} | set(payload.get("outside", {}))
    dangling = [(a, x["to"]) for a, entries in payload.get("links", {}).items()
                for x in entries if a not in keys or x["to"] not in keys]
    if dangling:
        errors.append(f"synergy view has dangling links: {dangling[:6]}")
    team = [(a, x["to"]) for a, entries in payload.get("links", {}).items()
            for x in entries if x.get("group") == "同队"]
    if team:
        errors.append(f"synergy view still materializes teammate/partner links: {team[:6]}")
    if "team_pairs" in payload.get("stats", {}) or "groups" in payload or "priority" in payload:
        errors.append("synergy view still inlines retired teammate view data")
    # 2026-11-10：同定位精灵自定义分组必须与落库文件一致（导出补丁后重建才会同步）。
    role_path = ROOT / "references" / "catalog" / "view_role_adds.json"
    expected_roles: dict = {}
    if role_path.exists():
        try:
            expected_roles = json.loads(role_path.read_text(encoding="utf-8")).get("groups", {}) or {}
        except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            errors.append(f"view_role_adds.json unreadable: {exc}")
    got_roles = (payload.get("role_adds") or {}).get("groups", {}) or {}
    if got_roles != expected_roles:
        errors.append("synergy view role additions are stale; rebuild it")
    for owner, rows in got_roles.items():
        if not isinstance(rows, list) or any(
                not isinstance(x, dict) or "id" not in x for x in rows):
            errors.append(f"synergy view role additions malformed for #{owner}")
    return errors, warnings


def validate_media_layer() -> tuple[list[str], list[str]]:
    """2026-11-08：SeerAPI 资料层（数据文件、图像、覆盖层、前端内联）一致性。"""
    errors: list[str] = []
    warnings: list[str] = []
    media_path = ROOT / "data" / "seerapi" / "spirit_media.json"
    info_path = ROOT / "data" / "seerapi" / "spirit_info.json"
    overlay_path = ROOT / "references" / "catalog" / "spirit_info_overlay.json"
    report_path = ROOT / "references" / "catalog" / "spirit_media_report.json"
    if not media_path.exists():
        return ["data/seerapi/spirit_media.json is missing; run python scripts/build_spirit_media.py"], warnings
    try:
        media = json.loads(media_path.read_text(encoding="utf-8"))
        info = json.loads(info_path.read_text(encoding="utf-8"))
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "references" / "catalog" / "editor_schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"SeerAPI media layer unreadable: {exc}"], warnings

    if media.get("status") != "ready" or not media.get("spirits"):
        errors.append("spirit_media.json must be status=ready with spirits")
    if info.get("status") != "ready":
        errors.append("spirit_info.json must be status=ready after media import")
    if overlay.get("status") != "ready":
        errors.append("spirit_info_overlay.json is stale; run python scripts/import_spirit_info.py")
    if (schema.get("media_import") or {}).get("status") != "ready":
        errors.append("editor_schema.json#media_import.status must be ready")
    if not report_path.exists():
        warnings.append("references/catalog/spirit_media_report.json missing; run build_spirit_media.py")

    sys.path.insert(0, str(ROOT / "scripts"))
    import editor_schema  # noqa: PLC0415
    allowed = editor_schema.editable_ids()
    media_target = allowed - editor_schema.library_add_ids()
    ids = set()
    for key, row in (media.get("spirits") or {}).items():
        try:
            ids.add(int(key))
        except ValueError:
            errors.append(f"spirit_media.json key {key!r} is not an integer id")
            continue
        if not isinstance(row, dict) or not all(k in row for k in ("name", "soulmarks", "skills", "images")):
            errors.append(f"spirit_media.json #{key}: missing name/soulmarks/skills/images")
            continue
        for field in ("portrait", "avatar", "soul_icon", "type_icon"):
            rel = (row["images"] or {}).get(field)
            if rel and not (ROOT / "references" / rel).resolve().exists():
                errors.append(f"spirit_media.json #{key}: declared local image missing: {rel}")
    if ids - allowed:
        errors.append(f"spirit_media.json has non-editable ids: {sorted(ids - allowed)[:10]}")
    if media_target - ids:
        warnings.append("%d editable spirits have no SeerAPI media (see spirit_media_report.json)"
                        % len(media_target - ids))

    info_ids = set()
    for key, row in (info.get("spirits") or {}).items():
        try:
            info_ids.add(int(key))
        except ValueError:
            errors.append(f"spirit_info.json key {key!r} is not an integer id")
            continue
        if set(row) != {"soul_mark", "portrait", "skills"}:
            errors.append(f"spirit_info.json #{key}: fields must be soul_mark/portrait/skills")
        if len(str(row.get("soul_mark", ""))) > 8000 or len(str(row.get("portrait", ""))) > 500:
            errors.append(f"spirit_info.json #{key}: field exceeds editor_schema limit")
        skills = row.get("skills") or []
        if len(skills) > 30 or any(len(str(x)) > 200 for x in skills):
            errors.append(f"spirit_info.json #{key}: skills exceed 30 items / 200 chars")
    if info_ids != ids:
        errors.append("spirit_info.json ids differ from spirit_media.json")
    if set(str(k) for k in (overlay.get("spirits") or {})) != set(str(k) for k in (info.get("spirits") or {})):
        errors.append("spirit_info_overlay.json ids differ from spirit_info.json")

    view_path = ROOT / "references" / "spirit_synergy_view.html"
    if view_path.exists():
        text = view_path.read_text(encoding="utf-8")
        try:
            payload = viewdata.parse(text)
            inline = payload.get("media") or {}
            if inline.get("status") != "ready":
                errors.append("synergy view has no ready inlined media layer; rebuild it")
            if set((inline.get("spirits") or {})) != set(media.get("spirits") or {}):
                errors.append("synergy view inlined media spirits differ from spirit_media.json; rebuild it")
            if (inline.get("stats") or {}).get("spirits") != (media.get("stats") or {}).get("spirits"):
                errors.append("synergy view inlined media stats are stale; rebuild it")
            # 2026-11-09 极简重构：资料不再单独成面板，改为详情区直接使用 DATA.media。
            if "DATA.media" not in text or "mediaRow" not in text:
                errors.append("synergy view no longer uses the SeerAPI media layer")
        except (viewdata.ViewDataError, AttributeError) as exc:
            errors.append(f"synergy view inlined media unreadable: {exc}")
    skill_md = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if "data/seerapi/spirit_media.json" not in skill_md:
        errors.append("SKILL.md does not document data/seerapi/spirit_media.json")
    return errors, warnings


def validate_program_invariants() -> tuple[list[str], list[str]]:
    """2026-11-08 全量审计：历史脚本守卫与撤销留痕不得被绕过。"""
    errors: list[str] = []
    warnings: list[str] = []
    scripts = ROOT / "scripts"
    state_path = ROOT / "references" / "catalog" / "schema_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for name in state.get("superseded_scripts", []):
            # 历史脚本 2026-11-15 起归档到 scripts/history/，两个目录都认
            path = scripts / name
            if not path.exists():
                path = scripts / "history" / name
            if not path.exists():
                errors.append(f"schema_state.json lists missing legacy script: {name}")
            elif "guard_legacy(__file__)" not in path.read_text(encoding="utf-8"):
                errors.append(f"legacy script lost its guard (would roll back data if rerun): {name}")
    else:
        warnings.append("references/catalog/schema_state.json missing: legacy scripts are unguarded")
    # 2026-11-08：编辑层 schema 与前端内联副本、落库 id 必须一致。
    sys.path.insert(0, str(ROOT / "scripts"))
    import editor_schema  # noqa: PLC0415
    errors.extend("editor schema: " + x for x in editor_schema.check_invariants())
    media_errors, media_warnings = validate_media_layer()
    errors.extend(media_errors)
    warnings.extend(media_warnings)

    retired_path = ROOT / "references" / "catalog" / "retired_edges.json"
    if retired_path.exists():
        systems_doc = json.loads((ROOT / "references" / "catalog" / "systems.json").read_text(encoding="utf-8"))
        live = {tuple(e) for item in systems_doc["systems"] for e in item.get("chain_edges", [])}
        for item in json.loads(retired_path.read_text(encoding="utf-8")).get("items", []):
            if (item.get("a"), item.get("b")) in live:
                errors.append(f"retired edge #{item.get('a')}→#{item.get('b')} is active again")
    return errors, warnings


RETIRED_VIEW_TERMS = ("剔除", "作废", "自动留痕", "种族值过低", "单条魂印", "全量图鉴")


def validate_role_groups() -> tuple[list[str], list[str], dict]:
    """Guard the similar-role layer and the strict-link (no-clue) front end."""
    errors: list[str] = []
    warnings: list[str] = []
    ref = ROOT / "references"
    path = ref / "catalog" / "role_groups.json"
    if not path.exists():
        return ["references/catalog/role_groups.json is missing"], warnings, {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        systems_doc = json.loads((ref / "catalog" / "systems.json").read_text(encoding="utf-8"))
        chain = json.loads((ref / "catalog" / "chain_audit.json").read_text(encoding="utf-8"))
        view_text = (ref / "spirit_synergy_view.html").read_text(encoding="utf-8")
    except (json.JSONDecodeError, OSError) as exc:
        return [f"role-group layer unreadable: {exc}"], warnings, {}

    raw = json.dumps(doc, ensure_ascii=False)
    hits = [w for w in RETIRED_VIEW_TERMS if w in raw]
    if hits:
        errors.append(f"role_groups.json contains retired filter wording: {hits}")

    groups = doc.get("groups", [])
    if not groups:
        errors.append("role_groups.json has no groups")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    tactics = (ref / "docs" / "tactics.md").read_text(encoding="utf-8")
    sources_text = SOURCES_PATH.read_text(encoding="utf-8") if SOURCES_PATH.exists() else ""
    roster = load_roster()
    active = {x["id"] for x in roster["spirits"]}
    active |= {x.get("id") for x in roster.get("pending_research", []) if x.get("id") is not None}

    # 2026-11-06: 特色定位是唯一口径。每只 1-2 个、必须在词表内；
    # 相似定位组的 core_role 必须等于成员的第 1 个定位，同一只不得跨组。
    core_path = ref / "catalog" / "core_roles.json"
    if not core_path.exists():
        errors.append("references/catalog/core_roles.json is missing")
        return errors, warnings, {}
    core_doc = json.loads(core_path.read_text(encoding="utf-8"))
    terms = set(core_doc.get("core_roles", {}))
    class_terms = set(core_doc.get("role_classes", {}))
    # 上限统一从 editor_schema 读（与前端 roleLimit() 同一份 limits），避免两套数字
    try:
        import editor_schema as _es  # noqa: PLC0415
        _lim = _es.limits()
    except (ImportError, OSError, json.JSONDecodeError):
        _lim = {}
    class_max = int(_lim.get("role_class_max", 3))
    custom_max = int(_lim.get("role_custom_max", 2))
    custom_len = int(_lim.get("role_custom_len", 20))
    by_id = {x["id"]: x for x in roster["spirits"]}
    for sid, sp in by_id.items():
        cs = sp.get("classes", [])
        if not (0 <= len(cs) <= class_max) or len(set(cs)) != len(cs) \
                or any(c not in class_terms for c in cs):
            errors.append(f"spirit #{sid}: invalid role classes {cs!r} "
                          f"(must be 0-{class_max} from role_classes)")
        # 2026-11-18：定位分类可在前端编辑，core_roles.json#spirit_classes 只作参考快照，
        # 不一致改为警告（提示同步词表文件），不再阻断校验
        snapshot = core_doc.get("spirit_classes", {}).get(str(sid))
        if snapshot is not None and list(cs) != snapshot:
            warnings.append(f"spirit #{sid}: classes differ from core_roles.json spirit_classes snapshot")
    for sid, sp in by_id.items():
        rs = [str(x).strip() for x in (sp.get("roles") or [])]
        # 2026-11-18 用户口径：定位分类与特色定位合并，特色可由用户自己写。
        # 因此这里不再强制词表，只保证：最多 2 条、不重复、每条 2-20 字。
        if len(rs) > custom_max:
            errors.append(f"spirit #{sid}: feature roles must be <={custom_max}, got {len(rs)}")
        if len(set(rs)) != len(rs):
            errors.append(f"spirit #{sid}: duplicate role")
        for r in rs:
            if not (2 <= len(r) <= custom_len):
                errors.append(f"spirit #{sid}: role {r!r} must be 2-{custom_len} chars")
        if not (rs or sp.get("classes")):
            # 定位可为空（图鉴显示「未标注」），收录精灵建议补一条，但不阻断校验
            warnings.append(f"spirit #{sid}: 没有定位（classes/roles 都为空）")
    seen: dict[int, str] = {}
    for group in groups:
        label = group.get("name") or group.get("key") or "?"
        cr = group.get("core_role")
        if cr not in terms:
            errors.append(f"role group {label}: core_role {cr!r} is not in core_roles.json")
        outside = set(group.get("outside_layer_members", []))
        for sid in group.get("members", []):
            if sid in seen:
                errors.append(f"role group {label}: #{sid} already in {seen[sid]} (no cross-group)")
            seen[sid] = label
            if sid in outside:
                continue
            sp = by_id.get(sid)
            if not sp:
                errors.append(f"role group {label}: #{sid} has no deep-dive core role")
            elif cr not in [str(x) for x in (sp.get("roles") or [])]:
                errors.append(f"role group {label}: #{sid} roles "
                              f"{sp.get('roles')!r} do not include {cr!r}")
    if "core_roles.json" not in skill:
        errors.append("SKILL.md does not document core_roles.json")
    idx = json.loads((ref / "catalog" / "creator_index.json").read_text(encoding="utf-8"))
    active |= {x["id"] for x in idx.get("themed_spirits", [])}
    overrides = json.loads((ROOT / "references" / "catalog" / "manual_overrides.json").read_text(encoding="utf-8"))
    active |= {x["id"] for x in overrides.get("spirits", [])}
    catalog_ids = {x["id"] for x in
                   json.loads((ROOT / "data" / "bwiki" / "pool.json").read_text(encoding="utf-8"))["elves"]}
    verified = {tuple(x) for x in chain.get("verified_pairs", [])}

    duplicate_keys = sorted(k for k, v in
                            Counter(g.get("key") for g in groups).items() if v > 1)
    if duplicate_keys:
        errors.append(f"role_groups.json duplicate keys: {duplicate_keys}")
    if f"{len(groups)} 组" not in skill:
        errors.append(f"SKILL.md similar-role count is stale: expected {len(groups)} 组")
    if "暂无已核实关联" not in skill:
        errors.append("SKILL.md does not state the no-relation rule")
    section = doc.get("section", "")
    if section and section not in tactics:
        errors.append(f"role_groups.json section {section!r} is missing from tactics.md")

    for group in groups:
        label = group.get("name") or group.get("key") or "?"
        if label not in skill:
            errors.append(f"role group {label}: missing from SKILL.md 相似定位速查")
        for field in ("shared", "differences", "relation", "sources"):
            if not group.get(field):
                errors.append(f"role group {label}: missing {field}")
        if group.get("evidence_grade") not in doc.get("grade_defs", {}):
            errors.append(f"role group {label}: unregistered evidence_grade")
        members = group.get("members", [])
        if len(members) < 2 or len(set(members)) != len(members):
            errors.append(f"role group {label}: members must be >= 2 unique ids")
        for sid in members:
            if not isinstance(sid, int) or (sid not in active and sid not in catalog_ids):
                errors.append(f"role group {label}: unknown member id {sid}")
        if len(group.get("differences", [])) != len(members):
            warnings.append(f"role group {label}: differences count != member count")
        for a, b in itertools.combinations(sorted(m for m in members if isinstance(m, int)), 2):
            if (a, b) in verified or (b, a) in verified:
                errors.append(f"role group {label}: #{a}/#{b} is a verified teammate link, not a similar role")
        for code in group.get("sources", []):
            if code in KNOWN_SOURCES:
                if f"**{code}**" not in sources_text:
                    warnings.append(f"role group {label}: source {code} is not in sources.md")
            elif not (isinstance(code, str)
                      and ((code.startswith(("W:", "G:")) and code[2:].isdigit())
                           or (code.startswith(("SK:", "SA:")) and code[3:].isdigit()))):
                errors.append(f"role group {label}: unknown source marker {code!r}")

    edge_count = sum(len(x.get("chain_edges", [])) for x in systems_doc.get("systems", []))
    if edge_count != chain.get("stats", {}).get("explicit_chain_edges"):
        errors.append("systems.json chain_edges count is stale; rerun build_chain_audit.py")

    # 2026-11-06: every explicit edge must declare what kind of link it is.
    from edge_consts import EDGE_TYPES, MIN_NOTE  # noqa: PLC0415
    allowed_edge_types = set(EDGE_TYPES)
    for item in systems_doc.get("systems", []):
        label = item.get("name") or item.get("key")
        meta = item.get("edge_meta") or {}
        edge_keys = {"%d-%d" % (a, b) for a, b in item.get("chain_edges", [])}
        for key in edge_keys:
            entry = meta.get(key)
            if not isinstance(entry, dict):
                errors.append(f"system {label}: edge {key} has no edge_meta type")
                continue
            if entry.get("type") not in allowed_edge_types:
                errors.append(f"system {label}: edge {key} has invalid type {entry.get('type')!r}")
            if len(str(entry.get("note", ""))) < MIN_NOTE:
                errors.append(f"system {label}: edge {key} note is too short")
        for key in set(meta) - edge_keys:
            errors.append(f"system {label}: edge_meta {key} does not match any chain_edge")

    try:
        payload = viewdata.parse(view_text)
    except viewdata.ViewDataError as exc:
        return errors + [f"synergy view inlined data invalid: {exc}"], warnings, {}
    stats = payload.get("stats", {})
    role_entries = [(a, x) for a, arr in payload.get("links", {}).items()
                    for x in arr if x.get("group") == "相似定位"]
    if stats.get("role_groups") != len(groups):
        errors.append("synergy view role_groups stat is stale")
    if stats.get("role_pairs") != len(role_entries):
        errors.append("synergy view role_pairs stat is stale")
    if stats.get("explicit_edges") != edge_count:
        errors.append("synergy view explicit_edges stat is stale")
    nodes = payload.get("nodes", [])
    if stats.get("no_relation") != sum(1 for n in nodes if not n.get("rel_count")):
        errors.append("synergy view no_relation stat is stale")
    for a, x in ((a, x) for a, arr in payload.get("links", {}).items() for x in arr):
        if x.get("group") in ("待核", "战术链"):
            errors.append(f"synergy view still shows an unverified clue link: {a}->{x['to']}")
        if x.get("group") == "相似定位" and not x.get("role_info"):
            errors.append(f"synergy view similar-role card lacks evidence: {a}->{x['to']}")

    # 2026-11-06: 用户反馈「换精灵但相似定位组一直不变」。面板必须按当前
    # 选中精灵过滤，不能恒定渲染全库清单；全库清单只能由显式开关打开。
    role_start = view_text.find("function renderRoles()")
    role_end = view_text.find("function renderAll()", role_start)
    role_fn = view_text[role_start:role_end] if role_start >= 0 else ""
    if ("state.sel" not in role_fn and "state.selected" not in role_fn) or "DATA.roles" not in role_fn:
        errors.append("synergy view similar-role panel is not selection-aware; "
                      "修 scripts/synergy_view_template.html 后 rerun rebuild_view.py")

    return errors, warnings, {
        "groups": len(groups),
        "role_pairs": len(role_entries),
        "explicit_edges": edge_count,
        "no_relation": stats.get("no_relation", 0),
    }


def validate_strength_and_chains() -> tuple[list[str], list[str], dict]:
    """Guard the human strength layer and the ordered-chain audit."""
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict = {}
    ref = ROOT / "references"
    needed = ("strength.json", "chain_audit.json", "matchups.json", "systems.json")
    for name in needed:
        if not (ref / "catalog" / name).exists():
            errors.append(f"references/catalog/{name} is missing; run build_strength.py / build_chain_audit.py")
    if errors:
        return errors, warnings, stats
    try:
        strength = json.loads((ref / "catalog" / "strength.json").read_text(encoding="utf-8"))
        chain = json.loads((ref / "catalog" / "chain_audit.json").read_text(encoding="utf-8"))
        matchups = json.loads((ref / "catalog" / "matchups.json").read_text(encoding="utf-8"))
        systems_doc = json.loads((ref / "catalog" / "systems.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"strength/chain layer has invalid JSON: {exc}"], warnings, stats

    for name, doc in (("strength.json", strength), ("chain_audit.json", chain),
                      ("matchups.json", matchups)):
        raw = json.dumps(doc, ensure_ascii=False)
        hits = [w for w in RETIRED_VIEW_TERMS if w in raw]
        if hits:
            errors.append(f"{name} contains retired filter wording: {hits}")

    roster = load_roster()
    active = {x["id"] for x in roster["spirits"]}
    active |= {x["id"] for x in roster.get("pending_research", []) if x.get("id") is not None}
    idx = json.loads((ref / "catalog" / "creator_index.json").read_text(encoding="utf-8"))
    active |= {x["id"] for x in idx.get("themed_spirits", [])}
    overrides = json.loads((ROOT / "references" / "catalog" / "manual_overrides.json").read_text(encoding="utf-8"))
    active |= {x["id"] for x in overrides.get("spirits", [])}
    sources_text = SOURCES_PATH.read_text(encoding="utf-8") if SOURCES_PATH.exists() else ""
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    tactics_text = (ref / "docs" / "tactics.md").read_text(encoding="utf-8")

    # 1) Human strength layer.
    policy = strength.get("policy", {})
    if not policy.get("auto_score_definition") or not policy.get("unrated_default"):
        errors.append("strength.json policy is incomplete")
    if "非强度" not in strength.get("display", {}).get("complexity_label", ""):
        errors.append("strength.json must label the complexity tier as 非强度")
    ratings = strength.get("ratings", [])
    if not ratings:
        errors.append("strength.json has no human ratings")
    for item in ratings:
        if item.get("id") not in active:
            errors.append(f"strength.json rated #{item.get('id')} is not an active spirit")
        if not item.get("basis") or not item.get("sources") or not item.get("evidence"):
            errors.append(f"strength.json rating #{item.get('id')} lacks basis/evidence/sources")
        for code in item.get("sources", []):
            if f"**{code}**" not in sources_text:
                warnings.append(f"strength.json source marker {code} is not registered in sources.md")
    bias = strength.get("bias_review", {})
    if bias.get("count") != len(bias.get("items", [])):
        errors.append("strength.json bias_review.count is stale")
    for item in bias.get("items", []):
        if item.get("id") in {x["id"] for x in ratings}:
            errors.append(f"strength.json bias_review still lists rated #{item['id']}")
    if "references/catalog/strength.json" not in skill_text or "机制复杂度" not in skill_text:
        errors.append("SKILL.md does not document the human strength layer")

    # 2) System grades and ordered chains.
    systems = systems_doc.get("systems", [])
    grade_defs = systems_doc.get("evidence_grades", {})
    chain_defs = systems_doc.get("chain_statuses", {})
    if not grade_defs or not chain_defs:
        errors.append("systems.json lacks evidence_grades / chain_statuses definitions")
    verified_names = set()
    recomputed: set[tuple[int, int]] = set()
    for item in systems:
        if item.get("evidence_grade") not in grade_defs:
            errors.append(f"systems.json {item['key']}: invalid evidence_grade")
        status = item.get("chain_status")
        if status not in chain_defs:
            errors.append(f"systems.json {item['key']}: invalid chain_status")
        if status == "顺序链已核":
            verified_names.add(item["name"])
        # Only explicit chain_edges count. core/support are member lists and
        # must never be unfolded into teammate pairs again.
        # 2026-11-15：41 个历史体系退役后，保留体系均为用户口径录入（无逐回合正文）。
        # 若仍只认 chain_status=顺序链已核，关系层会整体归零；显式边本身就是登记依据。
        for edge in item.get("chain_edges", []):
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                errors.append(f"systems.json {item['key']}: malformed chain_edge {edge}")
                continue
            a, b = int(edge[0]), int(edge[1])
            if a != b:
                recomputed.add((a, b))
                recomputed.add((b, a))
    declared = {tuple(x) for x in chain.get("verified_pairs", [])}
    if declared != recomputed:
        errors.append("chain_audit.json verified_pairs does not match systems.json ordered chains")
    cs = chain.get("stats", {})
    if cs.get("systems") != len(systems):
        errors.append("chain_audit.json systems count is stale")
    if cs.get("declared_links") != len(chain.get("items", [])):
        errors.append("chain_audit.json declared-link count is stale")
    if len(chain.get("verified_directional_pairs", [])) * 2 != len(declared):
        errors.append("chain_audit.json verified_directional_pairs is stale")
    if sum(cs.get("by_source_field", {}).values()) and \
            sum(cs.get("by_source_field", {}).values()) != len(chain.get("items", [])):
        errors.append("chain_audit.json source-field counts are stale")
    if cs.get("verified_ordered_pairs") != len(declared):
        errors.append("chain_audit.json verified_ordered_pairs is stale")
    syn_ids = {x["id"] for x in roster["spirits"]}
    for rec in chain.get("items", []):
        if rec.get("a") not in syn_ids or rec.get("b") not in syn_ids:
            errors.append(f"chain_audit.json declaration {rec.get('a')}->{rec.get('b')} has unknown id")
    if "chain_audit.json" not in skill_text or "顺序链" not in skill_text:
        errors.append("SKILL.md does not document the ordered-chain rule")

    # 3) Opposing-side relations.
    all_ids = active | {x["id"] for x in
                        json.loads((ROOT / "data" / "bwiki" / "pool.json").read_text(encoding="utf-8"))["elves"]}
    for m in matchups.get("items", []):
        if m.get("a") not in all_ids or m.get("b") not in all_ids:
            errors.append(f"matchups.json {m.get('key')} references an unknown spirit id")
        if m.get("section") not in tactics_text:
            errors.append(f"matchups.json {m.get('key')} section is missing from tactics.md")
        if m.get("grade") not in matchups.get("grades", {}):
            errors.append(f"matchups.json {m.get('key')} has an unregistered grade")

    # 4) 2026-11-10：可配合精灵板块已删除；显式边仍只作体系画布数据，不展开成关系对。
    view = ref / "spirit_synergy_view.html"
    if view.exists():
        text = view.read_text(encoding="utf-8")
        payload = viewdata.parse(text)
        if any(x.get("group") == "同队" for arr in payload.get("links", {}).values() for x in arr):
            errors.append("synergy view still contains teammate/partner relationship entries")
        if "可配合精灵" in text or "renderLinks" in text:
            errors.append("synergy view still renders the retired teammate section")
        if payload.get("stats", {}).get("verified_pairs") != len(declared):
            errors.append("synergy view verified_pairs stat is stale")
        if any(not n.get("strength", {}).get("grade") for n in payload.get("nodes", [])):
            errors.append("synergy view nodes are missing human strength grades")
        if "机制梯度" in text or "自动梯度" in text:
            errors.append("synergy view still labels the complexity tier as a strength tier")

    stats = {
        "ratings": len(ratings),
        "bias": bias.get("count", 0),
        "verified_systems": len(verified_names),
        "verified_pairs": len(declared),
        "declarations": len(chain.get("items", [])),
        "matchups": len(matchups.get("items", [])),
    }
    return errors, warnings, stats


def validate_full_audit() -> tuple[list[str], list[str], dict]:
    """Second-pass invariants: every spirit / system / link must be audited."""
    errors: list[str] = []
    warnings: list[str] = []
    ref = ROOT / "references"
    path = ref / "catalog" / "full_audit.json"
    if not path.exists():
        return ["references/catalog/full_audit.json is missing; run python scripts/build_full_audit.py"], warnings, {}
    try:
        audit = json.loads(path.read_text(encoding="utf-8"))
        systems = json.loads((ref / "catalog" / "systems.json").read_text(encoding="utf-8"))
        chain = json.loads((ref / "catalog" / "chain_audit.json").read_text(encoding="utf-8"))
        strength = json.loads((ref / "catalog" / "strength.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"full-audit layer has invalid JSON: {exc}"], warnings, {}

    raw = json.dumps(audit, ensure_ascii=False)
    hits = [w for w in RETIRED_VIEW_TERMS if w in raw]
    if hits:
        errors.append(f"full_audit.json contains retired filter wording: {hits}")

    stats = audit.get("stats", {})
    if len(audit.get("spirits", [])) != stats.get("spirits"):
        errors.append("full_audit.json spirit count is stale")
    if len(audit.get("systems", [])) != len(systems.get("systems", [])):
        errors.append("full_audit.json system count is stale")
    if len(audit.get("links", [])) != len(chain.get("items", [])):
        errors.append("full_audit.json link count is stale; rebuild after chain audit")
    import csv
    master = ref / "catalog" / "spirit_master_list.csv"
    if master.exists():
        with master.open(encoding="utf-8-sig", newline="") as fh:
            count = sum(1 for _ in csv.reader(fh)) - 1
        if len(audit.get("spirits", [])) != count:
            errors.append(f"full_audit.json does not cover all master-list spirits: {len(audit.get('spirits', []))} != {count}")

    roster = load_roster()
    spirits = roster.get("spirits", [])
    by_id = {x["id"]: x for x in spirits}
    verified = {tuple(x) for x in chain.get("verified_pairs", [])}
    syn_total = lead_total = 0
    for item in spirits:
        syn = set(item.get("synergies", []))
        leads = set(item.get("leads", []))
        syn_total += len(syn)
        lead_total += len(leads)
        if syn & leads:
            errors.append(f"#{item['id']} {item['name']}: id listed in both synergies and leads")
        for other in syn:
            if (item["id"], other) not in verified:
                errors.append(f"#{item['id']} {item['name']}: synergies contains unverified link -> {other}")
            back = by_id.get(other, {}).get("synergies", [])
            if item["id"] not in back:
                errors.append(f"#{item['id']} {item['name']}: synergies link -> {other} is not mutual")
    if syn_total + lead_total != len(chain.get("items", [])):
        errors.append("roster synergies + leads do not match chain_audit.json declarations")

    verified_names = {x["name"] for x in systems["systems"]
                      if x.get("chain_status") == "顺序链已核"}
    for rec in chain.get("items", []):
        if rec.get("group") == "同队":
            if rec.get("source_field") != "synergies" or not rec.get("mutual"):
                errors.append(f"chain_audit {rec['a']}->{rec['b']}: teammate group needs mutual synergies")
            if any(s not in verified_names for s in rec.get("systems", [])):
                errors.append(f"chain_audit {rec['a']}->{rec['b']}: teammate card cites unverified system")
        if set(rec.get("systems", [])) & set(rec.get("also_systems", [])):
            errors.append(f"chain_audit {rec['a']}->{rec['b']}: systems / also_systems overlap")

    missing_review = [x["key"] for x in systems["systems"] if not x.get("chain_review")]
    if missing_review:
        errors.append(f"systems.json entries lack chain_review: {missing_review[:6]}")
    if not strength.get("full_review", {}).get("file"):
        errors.append("strength.json does not point at the full audit layer")
    pool_ids = {i for entry in strength.get("official_pools", [])
                for level in ("banned", "limited", "semi_limited")
                for i in entry.get(level, [])}
    registered = {x["id"] for x in strength.get("official_pool_members", [])}
    if registered != pool_ids:
        errors.append("strength.json official_pool_members does not cover every pool id")
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if "full_audit.json" not in skill_text:
        errors.append("SKILL.md does not document the full audit layer")

    return errors, warnings, {
        "spirits": len(audit.get("spirits", [])),
        "systems": len(audit.get("systems", [])),
        "links": len(audit.get("links", [])),
        "verified_synergies": syn_total,
        "leads": lead_total,
    }


DEPTH_FIELDS = ("conditions", "sequence", "resources", "bp_cost",
                "failure_points", "replacement_check")


def validate_depth(data: dict) -> tuple[list[str], dict]:
    """Audit whether each completed deep-dive chain carries the six tactical elements."""
    errors: list[str] = []
    spirits = data.get("spirits", [])
    active = {x["id"] for x in spirits}
    if CATALOG_PATH.exists():
        active |= {x.get("id") for x in
                   json.loads(CATALOG_PATH.read_text(encoding="utf-8")).get("elves", [])}
    full = [x for x in spirits if x.get("deep_dive")]
    for item in full:
        missing = [k for k in DEPTH_FIELDS if not item["deep_dive"].get(k)]
        if missing:
            errors.append(f"deep dive #{item['id']} {item['name']}: missing {missing}")
        if len(item.get("play", "")) < 120:
            errors.append(f"deep dive #{item['id']} {item['name']}: play is still a one-liner")
    queued = len(spirits) - len(full)
    high = 0
    audit_path = ROOT / "references" / "catalog" / "depth_audit.json"
    if audit_path.exists():
        doc = json.loads(audit_path.read_text(encoding="utf-8"))
        if doc.get("total_spirits") != len(spirits):
            errors.append("depth_audit.json: total_spirits is stale")
        if set(doc.get("full_chain_ids", [])) != {x["id"] for x in full}:
            errors.append("depth_audit.json: full_chain_ids is stale")
        if doc.get("pending_count") != queued:
            errors.append("depth_audit.json: pending_count is stale")
        high = sum(1 for x in doc.get("queue", []) if x.get("priority") == "high")
    expansions = 0
    exp_path = ROOT / "references" / "catalog" / "soul_expansions.json"
    if exp_path.exists():
        doc = json.loads(exp_path.read_text(encoding="utf-8"))
        marker = doc.get("source_marker", "")
        sources = (ROOT / "references" / "docs" / "sources.md").read_text(encoding="utf-8")
        if marker not in KNOWN_SOURCES or f"**{marker}**" not in sources:
            errors.append(f"soul_expansions.json: source marker {marker!r} is not registered")
        for entry in doc.get("entries", []):
            if entry.get("id") not in active:
                errors.append(f"soul_expansions.json: id {entry.get('id')} absent from roster/catalog")
            if not entry.get("verified_mechanics") or not entry.get("skill_pages"):
                errors.append(f"soul_expansions.json: id {entry.get('id')} lacks verified mechanics")
            expansions += 1
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if f"{len(full)} 只已写完整六要素链" not in skill:
        errors.append("SKILL.md deep-dive full-chain count is stale")
    if f"{expansions} 只已补核" not in skill:
        errors.append("SKILL.md soul-expansion count is stale")
    return errors, {"full": len(full), "queued": queued, "high": high,
                    "expansions": expansions}


def validate(data: dict) -> tuple[list[str], list[str], list[dict], list[dict]]:
    errors: list[str] = []
    warnings: list[str] = []
    spirits = data.get("spirits")
    excluded = data.get("excluded_examples", [])

    if data.get("scope", {}).get("min_id") != MIN_ID:
        errors.append("scope.min_id must be 2987")
    if not isinstance(spirits, list) or not spirits:
        errors.append("spirits must be a non-empty list")
        return errors, warnings, [], []

    source_index = SOURCES_PATH.read_text(encoding="utf-8") if SOURCES_PATH.exists() else ""
    if not source_index:
        errors.append("references/docs/sources.md is missing or empty")

    ids: list[int] = []
    names: list[str] = []
    for index, item in enumerate(spirits):
        label = item.get("name") or f"entry[{index}]"
        spirit_id = item.get("id")
        name = item.get("name")
        if not isinstance(spirit_id, int) or spirit_id < MIN_ID:
            errors.append(f"{label}: id must be an integer >= {MIN_ID}")
        else:
            ids.append(spirit_id)
        if not name or not isinstance(name, str):
            errors.append(f"{label}: missing name")
        else:
            names.append(name)
        if item.get("status") not in VALID_STATUS:
            errors.append(f"{label}: invalid status {item.get('status')!r}")
        if not item.get("roles"):
            errors.append(f"{label}: roles must not be empty")
        if not item.get("mechanics"):
            errors.append(f"{label}: mechanics must not be empty; this skill excludes no-soul entries")
        if len(str(item.get("play", ""))) < 10:
            errors.append(f"{label}: play summary is missing or too short")
        if not item.get("sources"):
            warnings.append(f"{label}: no source marker")
        for source in item.get("sources", []):
            if source in KNOWN_SOURCES:
                if f"**{source}**" not in source_index:
                    errors.append(f"{label}: source marker {source!r} is not documented in sources.md")
                continue
            if ((source.startswith(("W:", "G:")) and source[2:].isdigit())
                    or (source.startswith(("SK:", "SA:")) and source[3:].isdigit())):
                continue
            errors.append(f"{label}: unknown source marker {source!r}")
        url = item.get("url4399")
        if url and "4399" not in url:
            errors.append(f"{label}: url4399 is not a 4399 URL")
        for linked in item.get("synergies", []):
            if not isinstance(linked, int) or linked < MIN_ID:
                errors.append(f"{label}: invalid linked spirit id {linked!r}")

    duplicate_ids = sorted(k for k, v in Counter(ids).items() if v > 1)
    duplicate_names = sorted(k for k, v in Counter(names).items() if v > 1)
    if duplicate_ids:
        errors.append(f"duplicate ids: {duplicate_ids}")
    if duplicate_names:
        errors.append(f"duplicate names: {duplicate_names}")

    active_ids = set(ids)
    for item in spirits:
        missing_links = sorted(set(item.get("synergies", [])) - active_ids)
        if missing_links:
            errors.append(f"{item['name']}: linked ids absent from active roster: {missing_links}")
    excluded_ids = {item.get("id") for item in excluded}
    conflicts = sorted(active_ids & excluded_ids)
    if conflicts:
        errors.append(f"excluded spirits re-entered active roster: {conflicts}")

    legacy_count = sum(1 for item in spirits if item.get("status") == "legacy")
    if legacy_count > max(8, len(spirits) // 5):
        warnings.append(f"legacy entries are {legacy_count}/{len(spirits)}; keep current recommendations separate")

    # Candidates are recorded before deep research; they must never duplicate
    # the curated roster or be mistaken for recommendation-ready spirits.
    active_names = {item.get("name") for item in spirits}
    pending = data.get("pending_research", [])
    if not isinstance(pending, list):
        errors.append("pending_research must be a list")
        pending = []
    pending_ids: list[int] = []
    pending_names: list[str] = []
    for index, item in enumerate(pending):
        label = item.get("name") or f"pending[{index}]"
        name = item.get("name")
        spirit_id = item.get("id")
        if not name or not isinstance(name, str):
            errors.append(f"{label}: missing candidate name")
        elif name in active_names:
            errors.append(f"{label}: candidate already exists in active roster")
        else:
            pending_names.append(name)
        if spirit_id is not None:
            if not isinstance(spirit_id, int) or spirit_id < MIN_ID:
                errors.append(f"{label}: candidate id must be null or an integer >= {MIN_ID}")
            else:
                pending_ids.append(spirit_id)
        if item.get("priority") not in {"high", "normal"}:
            errors.append(f"{label}: invalid candidate priority {item.get('priority')!r}")
        source = item.get("source")
        if source in KNOWN_SOURCES:
            if f"**{source}**" not in source_index:
                errors.append(f"{label}: candidate source {source!r} is not documented in sources.md")
        else:
            errors.append(f"{label}: unknown candidate source {source!r}")
        if len(str(item.get("note", ""))) < 8:
            errors.append(f"{label}: candidate note is missing or too short")
    duplicate_pending = sorted(k for k, v in Counter(pending_ids).items() if v > 1)
    duplicate_pending_names = sorted(k for k, v in Counter(pending_names).items() if v > 1)
    if duplicate_pending:
        errors.append(f"duplicate candidate ids: {duplicate_pending}")
    if duplicate_pending_names:
        errors.append(f"duplicate candidate names: {duplicate_pending_names}")
    if set(pending_ids) & active_ids:
        errors.append(f"candidate ids already active: {sorted(set(pending_ids) & active_ids)}")
    if set(pending_ids) & excluded_ids:
        errors.append(f"candidate ids already excluded: {sorted(set(pending_ids) & excluded_ids)}")

    # Creator coverage: themed spirits are recorded in full, never strength-filtered.
    coverage = data.get("creator_coverage", {})
    if not isinstance(coverage, dict) or not coverage.get("themed_spirit_ids"):
        errors.append("creator_coverage.themed_spirit_ids is missing")
    else:
        themed = coverage["themed_spirit_ids"]
        index_path = ROOT / "references" / "catalog" / "creator_index.json"
        if not index_path.exists():
            errors.append("references/catalog/creator_index.json is missing")
        else:
            try:
                index_data = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"creator_index.json invalid JSON: {exc}")
                index_data = None
            if index_data is not None:
                index_ids = [item["id"] for item in index_data.get("themed_spirits", [])]
                if sorted(set(themed)) != sorted(set(index_ids)):
                    errors.append("creator_coverage and creator_index.json themed ids disagree")
        missing = sorted(set(themed) - (active_ids | set(pending_ids)))
        if missing:
            errors.append(f"creator-themed spirits missing from roster/pending: {missing}")
        if coverage.get("themed_count") != len(themed):
            errors.append("creator_coverage.themed_count does not match themed_spirit_ids")

    queue = data.get("deep_dive_queue", [])
    if not isinstance(queue, list):
        errors.append("deep_dive_queue must be a list")
        queue = []
    for index, item in enumerate(queue):
        label = item.get("name") or f"queue[{index}]"
        if item.get("id") not in active_ids:
            errors.append(f"{label}: deep-dive id must refer to an active spirit")
        if len(str(item.get("reason", ""))) < 8:
            errors.append(f"{label}: deep-dive reason is missing or too short")

    # Full catalog layer: all 1203 soul-bearing spirits are queryable even when
    # they have no hand-written tactic. A missing deep-dive entry must never be
    # reported as "this spirit is not in the skill".
    catalog = data.get("catalog", {})
    if not isinstance(catalog, dict) or not catalog.get("available_count"):
        errors.append("roster.catalog metadata is missing")
    elif not CATALOG_PATH.exists():
        errors.append("data/bwiki/pool.json is missing")
    else:
        try:
            pool = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"data/bwiki/pool.json invalid JSON: {exc}")
            pool = None
        if pool is not None:
            elves = pool.get("elves", [])
            dropped = pool.get("dropped", [])
            elf_ids = {item.get("id") for item in elves}
            all_ids = elf_ids | {item.get("id") for item in dropped if isinstance(item, dict)}
            if len(elves) != catalog.get("available_count"):
                errors.append("catalog.available_count does not match pool.elves")
            if len(dropped) != catalog.get("dropped_count"):
                errors.append("catalog.dropped_count does not match pool.dropped")
            no_soul = [item.get("id") for item in elves if not str(item.get("soul", "")).strip()]
            if no_soul:
                errors.append(f"catalog elves without soul ability: {no_soul[:10]}")
            id_range = catalog.get("id_range", [MIN_ID, 4950])
            range_ids = set(range(id_range[0], id_range[1] + 1))
            if sorted(range_ids - all_ids) != catalog.get("jump_ids"):
                errors.append("catalog.jump_ids does not match pool id coverage")
            if len(all_ids) != catalog.get("covered_ids"):
                errors.append("catalog.covered_ids does not match pool")
            manual_only = sorted(active_ids - elf_ids)
            if manual_only:
                warnings.append(
                    f"{len(manual_only)} deep-dive spirits override the auto-filtered catalog "
                    f"(manual decisions win): {manual_only}"
                )
            if sorted(catalog.get("manual_only_ids", [])) != manual_only:
                errors.append("catalog.manual_only_ids does not match deep-dive/catalog difference")
            unknown_themed = sorted(set(coverage.get("themed_spirit_ids", [])) - all_ids)
            if unknown_themed:
                errors.append(f"creator-themed ids absent from full catalog: {unknown_themed}")
            if not GAP_PATH.exists():
                errors.append("references/catalog/tier_gaps.json is missing")
            else:
                try:
                    gap = json.loads(GAP_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"tier_gaps.json invalid JSON: {exc}")
                    gap = None
                if gap is not None:
                    gap_ids = {item["id"] for item in gap.get("items", [])}
                    expected = ({item["id"] for item in elves
                                 if item.get("tier") in {"T0", "T1", "T2"}}
                                - active_ids - excluded_ids)
                    if gap_ids != expected:
                        errors.append("tier_gaps.json does not match T0-T2 minus deep-dive roster")
                    if gap.get("missing_deep_dive") != len(gap.get("items", [])):
                        errors.append("tier_gaps.json count mismatch")
                    if catalog.get("high_tier_missing_deep_dive") != len(gap.get("items", [])):
                        errors.append("catalog.high_tier_missing_deep_dive does not match tier_gaps.json")

            # Complete BWIKI soul text and manually restored spirits.
            if not OVERRIDES_PATH.exists():
                errors.append("references/catalog/manual_overrides.json is missing")
            else:
                try:
                    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"manual_overrides.json invalid JSON: {exc}")
                    overrides = None
                if overrides is not None:
                    ov_items = overrides.get("spirits", [])
                    if {x["id"] for x in ov_items} != set(manual_only):
                        errors.append("manual_overrides.json ids do not match deep-dive/catalog difference")
                    if overrides.get("count") != len(ov_items):
                        errors.append("manual_overrides.json count mismatch")
                    if any(not str(x.get("soul", "")).strip() for x in ov_items):
                        errors.append("manual override is missing soul text")
            if not SOUL_FULL_PATH.exists():
                errors.append("data/seerapi/soul_full.json is missing")
            else:
                try:
                    soul_doc = json.loads(SOUL_FULL_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"soul_full.json invalid JSON: {exc}")
                    soul_doc = None
                if soul_doc is not None:
                    souls = soul_doc.get("souls", {})
                    stats = catalog.get("soul_full", {})
                    with_text = sum(1 for v in souls.values() if v.get("text"))
                    if stats.get("id_count") != len(souls):
                        errors.append("catalog.soul_full.id_count does not match soul_full.json")
                    if stats.get("with_text") != with_text:
                        errors.append("catalog.soul_full.with_text does not match soul_full.json")
                    if len(souls) < len(all_ids):
                        warnings.append(f"soul_full.json covers {len(souls)}/{len(all_ids)} ids")
                    missing_souls = [i for i in manual_only if not souls.get(str(i), {}).get("text")]
                    if missing_souls:
                        warnings.append(f"manual overrides still without full soul text: {missing_souls}")
            if not SOUL_GAP_PATH.exists():
                errors.append("references/catalog/soul_text_gaps.json is missing")
            else:
                try:
                    gaps_doc = json.loads(SOUL_GAP_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"soul_text_gaps.json invalid JSON: {exc}")
                    gaps_doc = None
                if gaps_doc is not None:
                    if gaps_doc.get("dropped_total") != len(dropped):
                        errors.append("soul_text_gaps.json dropped_total does not match pool.dropped")
                    if gaps_doc.get("suspect_total") != len(gaps_doc.get("suspects", [])):
                        errors.append("soul_text_gaps.json suspect_total mismatch")
                    if gaps_doc.get("queue_total") != len(gaps_doc.get("all_items", [])):
                        errors.append("soul_text_gaps.json queue_total mismatch")
                    if catalog.get("soul_full", {}).get("suspect_review") != len(gaps_doc.get("suspects", [])):
                        errors.append("catalog.soul_full.suspect_review does not match soul_text_gaps.json")
                    suspect_ids = {x["id"] for x in gaps_doc.get("suspects", [])}
                    unlisted = sorted(suspect_ids - active_ids - set(pending_ids) - excluded_ids)
                    if unlisted:
                        errors.append(f"suspected false drops absent from roster/pending: {unlisted}")

            # F20261104: inclusion is decided by creator-work coverage, never
            # by soul-clause count or stat total. Verify the policy and audit queue.
            policy = data.get("filter_policy", {})
            if not isinstance(policy, dict) or not policy.get("standard"):
                errors.append("roster.filter_policy is missing")
            elif sorted(policy.get("voided_rules", [])) != sorted(["单条魂印且无核心机制", "种族值过低"]):
                errors.append("filter_policy.voided_rules must list both voided auto rules")
            voided_reasons = [x for x in dropped
                              if str(x.get("reason", "")).startswith(("单条魂印", "种族值过低"))]
            if not VOIDED_PATH.exists():
                errors.append("references/catalog/voided_drops.json is missing")
            else:
                try:
                    voided = json.loads(VOIDED_PATH.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"voided_drops.json invalid JSON: {exc}")
                    voided = None
                if voided is not None:
                    if voided.get("total") != len(voided_reasons):
                        errors.append("voided_drops.json total does not match voided auto reasons")
                    if voided.get("total") != len(voided.get("items", [])):
                        errors.append("voided_drops.json item count mismatch")
                    uncovered = sorted(x["id"] for x in voided.get("items", [])
                                       if x.get("creator_coverage") == "配置/攻略专题"
                                       and x.get("state") not in {"spirits", "pending_research", "excluded_examples"})
                    if uncovered:
                        errors.append(f"creator-themed spirits still blocked by voided reasons: {uncovered}")
            creator_index_path = ROOT / "references" / "catalog" / "creator_index.json"
            if not creator_index_path.exists():
                errors.append("references/catalog/creator_index.json is missing")
            else:
                creator_index = json.loads(creator_index_path.read_text(encoding="utf-8"))
                if not creator_index.get("filter_standard"):
                    errors.append("creator_index.json filter_standard is missing")
                if "mentioned_spirits" in creator_index:
                    errors.append("creator_index.json still contains the deprecated 作品提及 layer")

    # F20261104 review rules: upper replacement, first-gen kings, legacy sources.
    rules = data.get("review_rules", {})
    if not isinstance(rules, dict) or not rules.get("effective"):
        errors.append("roster.review_rules is missing")
    else:
        first_kings = set(rules.get("first_gen_kings_excluded_names", []))
        leaked_kings = sorted(
            ({x.get("name") for x in spirits} | {x.get("name") for x in pending}) & first_kings
        )
        if leaked_kings:
            errors.append(f"first-gen king base forms must not be recorded: {leaked_kings}")
        master_csv = ROOT / "references" / "catalog" / "spirit_master_list.csv"
        if master_csv.exists():
            import csv as _csv
            with master_csv.open(encoding="utf-8-sig") as fh:
                csv_rows = list(_csv.reader(fh))[1:]
            leaked_csv = sorted({row[1] for row in csv_rows if len(row) > 1 and row[1] in first_kings})
            if leaked_csv:
                errors.append(f"master list still contains first-gen king base forms: {leaked_csv}")
            leaked_mentions = [row[1] for row in csv_rows
                               if len(row) > 4 and "作品提及" in row[4]]
            if leaked_mentions:
                errors.append(f"master list still contains 作品提及 rows: {leaked_mentions[:10]}")
            excluded_ids = {item.get("id") for item in excluded}
            leaked_excluded = [row[0] for row in csv_rows
                               if row and row[0].isdigit() and int(row[0]) in excluded_ids]
            if leaked_excluded:
                errors.append(f"master list contains user-excluded weak spirits: {leaked_excluded[:10]}")
        legacy = set(rules.get("legacy_markers", []))
        legacy_only_meta = [x.get("name") for x in spirits
                            if x.get("status") == "meta" and x.get("sources")
                            and set(x["sources"]) <= legacy]
        if legacy_only_meta:
            warnings.append(f"meta entries relying only on legacy sources, review carefully: {legacy_only_meta}")

    system_errors, system_warnings = validate_systems(active_ids, source_index)
    errors.extend(system_errors)
    warnings.extend(system_warnings)

    view_errors, view_warnings = validate_synergy_view()
    errors.extend(view_errors)
    warnings.extend(view_warnings)

    layer_errors, layer_warnings, _ = validate_strength_and_chains()
    errors.extend(layer_errors)
    warnings.extend(layer_warnings)

    audit_errors, audit_warnings, _ = validate_full_audit()
    errors.extend(audit_errors)
    warnings.extend(audit_warnings)

    role_errors, role_warnings, _ = validate_role_groups()
    errors.extend(role_errors)
    warnings.extend(role_warnings)

    program_errors, program_warnings = validate_program_invariants()
    errors.extend(program_errors)
    warnings.extend(program_warnings)

    return errors, warnings, spirits, excluded


def fetch_has_soul(url: str, timeout: float) -> tuple[bool | None, str]:
    # BWIKI's WAF returns HTTP 567 for terse script-style User-Agents, even
    # when the page exists. Use a browser UA plus a same-site Referer.
    referer = "https://news.4399.com/" if "4399" in url else "https://searchwiki.biligame.com/seer/"
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Referer": referer,
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1_500_000)
            content_type = response.headers.get("Content-Type", "")
    except (urllib.error.URLError, TimeoutError) as exc:
        return None, str(exc)

    # 4399 pages may declare one charset in HTTP headers and another in HTML.
    # Search raw bytes in both common encodings to avoid a false “no soul” result.
    needles = []
    for word in ("魂印", "专属特性"):
        needles.extend((word.encode("utf-8"), word.encode("gb18030", errors="ignore")))
    if any(needle in body for needle in needles):
        return True, "soul keyword found"
    return False, "no soul keyword found; inspect manually before changing roster"


def online_check(spirits: list[dict], limit: int, delay: float, timeout: float) -> int:
    checked = failed = suspicious = 0
    for item in spirits:
        if checked >= limit:
            break
        url = item.get("url4399")
        source = "4399"
        if not url:
            url = "https://searchwiki.biligame.com/seer/" + quote(f"精灵:{item['id']}")
            source = "BWIKI"
        checked += 1
        result, detail = fetch_has_soul(url, timeout)
        # BWIKI occasionally answers 567 under burst traffic. A rate-limit
        # response is a network failure, never evidence of a missing soul ability.
        for attempt in range(2):
            if result is not None:
                break
            time.sleep(2.0 + attempt * 2)
            result, detail = fetch_has_soul(url, timeout)
        if result is None:
            failed += 1
            print(f"NETWORK {item['id']} {item['name']} ({source}): {detail}")
        elif result:
            print(f"OK      {item['id']} {item['name']} ({source})")
        else:
            suspicious += 1
            print(f"REVIEW  {item['id']} {item['name']} ({source}): {detail}")
        time.sleep(delay)
    print(f"online summary: checked={checked}, ok={checked - failed - suspicious}, review={suspicious}, network_failed={failed}")
    return suspicious


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="check 4399 or BWIKI pages for soul-ability keywords")
    parser.add_argument("--limit", type=int, default=12, help="maximum pages to request online")
    parser.add_argument("--delay", type=float, default=0.8, help="delay between online requests")
    parser.add_argument("--timeout", type=float, default=20.0, help="online request timeout")
    parser.add_argument("--ids", default="", help="comma-separated spirit IDs to recheck online")
    args = parser.parse_args()

    errors, warnings, spirits, _ = validate(load_roster())
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    counts = Counter(item["status"] for item in spirits)
    data = load_roster()
    pending = data.get("pending_research", [])
    priorities = Counter(item.get("priority") for item in pending)
    print(f"roster ok: {len(spirits)} spirits; status={dict(sorted(counts.items()))}")
    print(f"candidates: {len(pending)} pending research; priority={dict(sorted(priorities.items()))}; "
          f"deep-dive queue: {len(data.get('deep_dive_queue', []))}")
    catalog = data.get("catalog", {})
    print(f"catalog: {catalog.get('available_count', 0)} soul-bearing spirits, "
          f"{catalog.get('dropped_count', 0)} dropped, "
          f"{catalog.get('covered_ids', 0)} ids covered; "
          f"T0-T2 deep-dive gap: {catalog.get('high_tier_missing_deep_dive', 0)}/"
          f"{catalog.get('high_tier_total', 0)}")
    soul_stats = catalog.get("soul_full", {})
    print(f"soul text: {soul_stats.get('with_text', 0)}/{soul_stats.get('id_count', 0)} BWIKI full texts; "
          f"false-drop review: {soul_stats.get('suspect_review', 0)}; "
          f"manual overrides: {catalog.get('manual_override_count', 0)}")
    review = data.get("review_summary", {})
    print(f"manual review: {review.get('removed_count', 0)} weak spirits removed by user; "
          f"approved candidates={sum(1 for x in data.get('pending_research', []) if x.get('review_status') == 'approved')}")
    rules = data.get("review_rules", {})
    print(f"review rules: first-gen kings excluded except 3355 莫妮卡; "
          f"legacy source markers tracked={len(rules.get('legacy_markers', []))}")
    if VOIDED_PATH.exists():
        voided_doc = json.loads(VOIDED_PATH.read_text(encoding="utf-8"))
        print(f"filter policy: creator-work coverage (F20261104); "
              f"voided auto drops={voided_doc.get('total', 0)}, "
              f"newly enqueued={len(voided_doc.get('newly_enqueued', []))}")
    coverage = data.get("creator_coverage", {})
    print(f"creator coverage: {len(coverage.get('themed_spirit_ids', []))} themed, "
          f"{coverage.get('mentioned_count', 0)} mentioned; "
          f"in_spirits={len(coverage.get('in_spirits', []))}, "
          f"in_pending={len(coverage.get('in_pending_research', []))}")
    systems_doc = json.loads((ROOT / "references" / "catalog" / "systems.json").read_text(encoding="utf-8"))
    systems = systems_doc.get("systems", [])
    print(f"systems index: {len(systems)} named 体系; "
          f"kinds={dict(sorted(Counter(x.get('kind') for x in systems).items()))}")
    chain_doc = json.loads((ROOT / "references" / "catalog" / "chain_audit.json").read_text(encoding="utf-8"))
    strength_doc = json.loads((ROOT / "references" / "catalog" / "strength.json").read_text(encoding="utf-8"))
    print(f"strength layer: {len(strength_doc.get('ratings', []))} human ratings, "
          f"{strength_doc.get('bias_review', {}).get('count', 0)} complexity-bias slots; "
          f"complexity tier is NOT a strength tier")
    print(f"chain audit: {chain_doc['stats']['verified_ordered_pairs']} verified ordered pairs, "
          f"{chain_doc['stats']['declared_links']} declarations graded "
          f"({chain_doc['stats']['one_way_declarations']} one-way, "
          f"{chain_doc['stats'].get('by_source_field', {}).get('synergies', 0)} verified links); "
          f"{len(json.loads((ROOT / 'references' / 'catalog' / 'matchups.json').read_text(encoding='utf-8'))['items'])} matchups")
    audit_doc = json.loads((ROOT / "references" / "catalog" / "full_audit.json").read_text(encoding="utf-8"))
    print(f"full audit: {audit_doc['stats']['spirits']} spirits / "
          f"{audit_doc['stats']['systems']} systems / {audit_doc['stats']['links']} links; "
          f"{audit_doc['stats']['conflicts']} evidence conflicts, "
          f"{chain_doc['stats'].get('by_source_field', {}).get('synergies', 0)} verified synergies")
    role_doc = json.loads((ROOT / "references" / "catalog" / "role_groups.json").read_text(encoding="utf-8"))
    view_stats = viewdata.read(ROOT / "references" / "spirit_synergy_view.html")["stats"]
    print(f"similar roles: {len(role_doc['groups'])} groups / {view_stats['role_pairs']} peer cards / "
          f"{chain_doc['stats']['explicit_chain_edges']} explicit edges; "
          f"{view_stats['no_relation']} spirits with no verified relation")
    depth_errors, depth_stats = validate_depth(data)
    if depth_errors:
        for error in depth_errors:
            print(f"ERROR: {error}")
        return 1
    print(f"deep-dive depth: {depth_stats['full']}/{len(spirits)} full chains; "
          f"{depth_stats['queued']} queued (high={depth_stats['high']}); "
          f"soul expansions: {depth_stats['expansions']}")
    if args.online:
        selected = spirits
        if args.ids.strip():
            wanted = {int(value.strip()) for value in args.ids.split(",") if value.strip()}
            selected = [item for item in spirits if item["id"] in wanted]
            print(f"rechecking {len(selected)} selected spirits")
        return online_check(selected, args.limit, args.delay, args.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())

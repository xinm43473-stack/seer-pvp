"""把前端「关系联动编辑」补丁应用到 systems.json（幂等，全量状态语义）

前端弹窗把 systems.json 的全部显式联动边内联进 DATA.edges，用户可改类型／
机制说明、删除、在已属同队联动体系内新增。导出补丁里的 ``edge_state.edges``
是**当前全部显式边的最终态**（不是增量），本脚本按它全量替换各体系的
chain_edges / edge_meta，因此新增、删除、修改、恢复都是同一套逻辑。

    python scripts/apply_edge_view_edits.py                  # 应用 view_edge_edits.json
    python scripts/apply_edge_view_edits.py --refresh-baseline  # 数据层手动改边后刷新恢复基线

``references/view_edge_edits.json`` 结构：
    edge_state = null            -> --clear 时用 baseline 恢复库内默认边
    edge_state = {"edges": [...]} -> 用这份全量清单替换
    baseline                     -> 首次接管时的数据层原始边，供 --clear 恢复

约束与 check_roster.py 保持一致：两端在可编辑精灵集合（总表＋资料层参照）、
同一无序对全库只有一条有向边、type 在词表内、note 可留空（上限 800 字）、体系必须是
「同队联动」。2026-11-08 起不再要求精灵已属该体系，词表与限制值均来自
references/catalog/editor_schema.json。

用法: python scripts/apply_edge_view_edits.py [--refresh-baseline] [--no-write]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "references"
SYSTEMS = REF / "catalog" / "systems.json"
STATE = REF / "view_edge_edits.json"

# 2026-11-08 重构：边类型词表与说明长度改由 references/catalog/editor_schema.json 唯一提供，
# 不再在本脚本、check_roster.py、build_synergy_view.py 各写一份。
_SCHEMA = editor_schema.load_schema()
EDGE_TYPES = dict(_SCHEMA["edge_types"])
MIN_NOTE = int(_SCHEMA["limits"]["edge_note_min"])
MAX_NOTE = int(_SCHEMA["limits"]["edge_note_max"])
SYSTEM_KIND = _SCHEMA["edge"]["system_kind"]
REQUIRE_MEMBER = bool(_SCHEMA["edge"]["require_member"])
SYSTEM_NAME_EDITABLE = bool(_SCHEMA["edge"].get("system_name_editable", False))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def active_ids() -> set[int]:
    """所有可编辑节点（总表 + 资料层参照）；与前端 allMap 一致。"""
    return editor_schema.editable_ids()


def edges_from_systems(doc: dict) -> list[dict]:
    out = []
    for item in doc["systems"]:
        for a, b in item.get("chain_edges", []):
            meta = (item.get("edge_meta") or {}).get("%d-%d" % (a, b), {})
            out.append({
                "system_key": item["key"],
                "system_name": item["name"],
                "a": int(a), "b": int(b),
                "type": meta.get("type", "resource"),
                "note": meta.get("note", ""),
                "chain_status": item.get("chain_status", ""),
            })
    return out


def edges_fingerprint(edges: list[dict]) -> str:
    """当前显式边集合的短指纹。前端导出补丁时带上，落库时比对，
    防止「旧页面快照」把之后新增/修改的边整批覆盖掉。"""
    rows = sorted((str(e.get("system_key") or ""), int(e.get("a") or 0),
                   int(e.get("b") or 0), str(e.get("type") or ""),
                   str(e.get("note") or "").strip()) for e in edges)
    blob = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def validate_edges(edges: list, systems_doc: dict | None = None) -> list[dict]:
    if not isinstance(edges, list):
        raise SystemExit("edge_state.edges 必须是数组")
    if systems_doc is None:
        systems_doc = load(SYSTEMS)
    systems = {x["key"]: x for x in systems_doc["systems"]}
    active = active_ids()
    seen: set[tuple[int, int]] = set()
    out: list[dict] = []
    for i, raw in enumerate(edges):
        if not isinstance(raw, dict):
            raise SystemExit(f"第 {i+1} 条联动边必须是对象")
        key = str(raw.get("system_key") or "")
        item = systems.get(key)
        if item is None:
            raise SystemExit(f"第 {i+1} 条边的体系不存在（体系注册表只读，不能新增）：{key}")
        # 体系名称只读：客户端下发的 system_name 必须与注册表一致，服务端始终以注册表为准。
        supplied_name = raw.get("system_name")
        if not SYSTEM_NAME_EDITABLE and supplied_name is not None and str(supplied_name) != item["name"]:
            raise SystemExit(
                f"第 {i+1} 条边的体系名称不可修改：注册表为「{item['name']}」，补丁给了「{supplied_name}」")
        if item.get("kind") != SYSTEM_KIND:
            raise SystemExit(f"第 {i+1} 条边的体系不是「{SYSTEM_KIND}」：{item.get('name')}")
        try:
            a, b = int(raw["a"]), int(raw["b"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"第 {i+1} 条边缺少合法 a/b：{raw!r}"[:160])
        if a == b:
            raise SystemExit(f"第 {i+1} 条边两端相同：#{a}")
        missing = {a, b} - active
        if missing:
            raise SystemExit(f"第 {i+1} 条边 #{a}→#{b} 的精灵不在活跃总表：{sorted(missing)}")
        # 2026-11-08：不再要求两端已是体系成员（所有精灵都能编辑关系联动）。
        # 若 schema 把 require_member 打开，才恢复该约束。
        if REQUIRE_MEMBER:
            members = set(item.get("core", [])) | set(item.get("support", [])) | set(item.get("counter", []))
            if not ({a, b} & members):
                raise SystemExit(f"第 {i+1} 条边 #{a}→#{b} 两端都不是体系「{item['name']}」的成员")
        typ = str(raw.get("type") or "")
        if typ not in EDGE_TYPES:
            raise SystemExit(f"第 {i+1} 条边的类型不在词表内：{typ}")
        note = str(raw.get("note") or "").strip()
        # 2026-11-09：备注不再有字数下限，留空也允许（仍保留上限保护）。
        if len(note) < MIN_NOTE:
            raise SystemExit(f"第 {i+1} 条边 #{a}→#{b} 的机制说明至少 {MIN_NOTE} 字（当前 {len(note)} 字）")
        if len(note) > MAX_NOTE:
            raise SystemExit(f"第 {i+1} 条边的机制说明超过 {MAX_NOTE} 字")
        pair = tuple(sorted((a, b)))
        if pair in seen:
            raise SystemExit(f"同一对精灵只能有一条有向边（含跨体系）：{pair[0]}-{pair[1]}")
        seen.add(pair)
        out.append({"system_key": key, "system_name": item["name"],
                    "a": a, "b": b, "type": typ, "note": note})
    return out


def apply_edges_to_doc(doc: dict, edges: list[dict]) -> dict:
    """全量替换各体系的 chain_edges / edge_meta（幂等）。"""
    grouped: dict[str, list[dict]] = {}
    for e in edges:
        grouped.setdefault(e["system_key"], []).append(e)
    for item in doc["systems"]:
        rows = grouped.get(item["key"], [])
        item["chain_edges"] = [[e["a"], e["b"]] for e in rows]
        item["edge_meta"] = {
            "%d-%d" % (e["a"], e["b"]): {"type": e["type"], "note": e["note"]}
            for e in rows
        }
    return doc


def read_state() -> dict | None:
    if not STATE.exists():
        return None
    try:
        return load(STATE)
    except (json.JSONDecodeError, OSError):
        return None


def apply_current_state(doc: dict) -> bool:
    """供 apply_strict_links.py 在 PATCH 之后调用，避免前端编辑被回退。"""
    state = read_state()
    if not state:
        return False
    es = state.get("edge_state")
    target = es.get("edges") if isinstance(es, dict) else state.get("baseline")
    if target is None:
        return False
    edges = validate_edges(target, doc)
    apply_edges_to_doc(doc, edges)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="应用前端关系联动编辑补丁")
    ap.add_argument("--refresh-baseline", action="store_true",
                    help="数据层手动改过 chain_edges 后，用当前 systems.json 刷新 --clear 的恢复基线")
    ap.add_argument("--no-write", action="store_true", help="只校验，不写 systems.json")
    args = ap.parse_args()

    doc = load(SYSTEMS)
    state = read_state()
    if state is None:
        # 没有前端补丁时保持零副作用：不创建文件、不改写 systems.json。
        if not args.refresh_baseline:
            print("edge edits: no active state, systems.json unchanged")
            return 0
        state = {
            "schema_version": 1.0, "mode": "full-state",
            "edge_state": None, "baseline": edges_from_systems(doc),
        }

    if args.refresh_baseline:
        active = state.get("edge_state")
        if isinstance(active, dict) and active.get("edges"):
            raise SystemExit(
                "--refresh-baseline 拒绝执行：当前仍有前端联动编辑生效，若用 systems.json 刷新基线，"
                "会把「编辑后的边」当成默认边，导致 --clear 无法恢复。"
                "请先运行 python scripts/apply_view_edits.py --clear，再刷新基线。")
    if args.refresh_baseline or not state.get("baseline"):
        state["baseline"] = edges_from_systems(doc)
        state.setdefault("schema_version", 1.0)
        state.setdefault("mode", "full-state")
        state.setdefault("edge_state", None)
        state["updated_at"] = date.today().isoformat()
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"baseline refreshed: {len(state['baseline'])} edges (source: current systems.json)")

    changed = apply_current_state(doc)
    if not changed:
        print("edge edits: no active state, systems.json unchanged")
        return 0
    total = sum(len(x.get("chain_edges", [])) for x in doc["systems"])
    if not args.no_write:
        SYSTEMS.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"edge edits applied: {total} explicit edges across {len(doc['systems'])} systems"
          + (" (dry-run)" if args.no_write else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

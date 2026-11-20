"""把配合前端导出的编辑补丁写回数据层（幂等，带口径校验）

前端 references/spirit_synergy_view.html 是单文件离线页面，浏览器不能直接写本地文件。
编辑结果先存 localStorage，再用页面上的「导出编辑补丁」下载 spirit_view_edits.json，
最后运行本脚本落库：

    python scripts/apply_view_edits.py [补丁路径] [--no-rebuild]
    python scripts/apply_view_edits.py --clear        # 清除全部前端编辑，恢复库内默认值

落库链路：
  1. 校验补丁（**所有前端节点均可编辑**，字段与限制由 references/catalog/editor_schema.json
     驱动，editor_schema.validate_spirit_edit 通用校验；相似定位组成员 roles[0]
     必须等于组 core_role；edge_state.edges 全量校验：体系合法、两端在可编辑
     集合、同一无序对唯一、type 词表内、机制说明可留空（上限 800 字））
  2. **分层接管**：补丁里出现的键才接管对应层，未出现的层保留已落库结果——
     定位编辑按 id 增量合并（edits 为 upsert、reset_edits 为撤销），
     deletions／edge_state 只在键存在时全量替换。这样「只改定位」的补丁不会
     清掉已落库的联动边，「只改联动」的补丁也不会清掉已落库的定位编辑。
     写 references/view_edits.json（apply_core_roles.py 会优先读取它）
     与 references/view_edge_edits.json（关系联动全量状态 + 恢复基线）
  3. 跑 apply_core_roles.py 写回 roster.json / core_roles.json
  4. 默认先跑 apply_edge_view_edits.py 应用联动编辑，再重建派生层并跑 check_roster.py
     （--no-rebuild 可跳过）

用法: python scripts/apply_view_edits.py [patch.json] [--no-rebuild] [--clear]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "references"
OUT = REF / "view_edits.json"
DEL_OUT = REF / "view_deletions.json"
EDGE_OUT = REF / "view_edge_edits.json"
SYS_OUT = REF / "view_system_edits.json"
LIB_OUT = REF / "view_library_adds.json"
ROLE_OUT = REF / "catalog" / "view_role_adds.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402
from apply_edge_view_edits import (  # noqa: E402
    edges_from_systems, validate_edges, edges_fingerprint,
)

REBUILD = [
    "scripts/import_spirit_info.py",
    "scripts/apply_edge_view_edits.py",
    "scripts/build_chain_audit.py",
    "scripts/apply_link_cleanup.py",
    "scripts/build_chain_audit.py",
    "scripts/build_full_audit.py",
    "scripts/build_spirit_index.py",
    "scripts/build_spirit_library.py",
    "scripts/build_synergy_view.py",
    "scripts/check_roster.py",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_patch(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            raise SystemExit("补丁文件不存在：" + str(p))
        return p
    for rel in ("spirit_view_edits.json", "references/spirit_view_edits.json",
                "downloads/spirit_view_edits.json"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def validate(edits: list[dict]) -> list[dict]:
    """2026-11-08 重构：字段与限制全部交给 editor_schema.json 驱动。"""
    if not isinstance(edits, list):
        raise SystemExit("edits 必须是数组")
    schema = editor_schema.load_schema()
    term_map = editor_schema.terms(schema)
    allowed = editor_schema.editable_ids()
    out: dict[int, dict] = {}
    for item in edits:
        row = editor_schema.validate_spirit_edit(
            item, schema=schema, term_map=term_map, allowed_ids=allowed)
        out[row["id"]] = row
    return [out[k] for k in sorted(out)]


def validate_deletions(items) -> list[int]:
    if not isinstance(items, list):
        raise SystemExit("deletions 必须是数组")
    active = editor_schema.editable_ids()
    out = set()
    for x in items:
        try:
            sid = int(x)
        except (TypeError, ValueError):
            raise SystemExit(f"删除标记含非法 id：{x!r}")
        if sid not in active:
            raise SystemExit(f"删除标记 #{sid} 不在可编辑精灵集合（总表＋资料层参照）内")
        out.add(sid)
    return sorted(out)


def validate_reset_keys(value) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit("reset_edits 必须是数组")
    return [str(x) for x in value]


def existing_deletions() -> list[int]:
    """补丁未声明 deletions 时保留已落库的软删除标记。"""
    if not DEL_OUT.exists():
        return []
    try:
        return validate_deletions(load(DEL_OUT).get("deleted", []))
    except (json.JSONDecodeError, OSError):
        return []


def merge_edits(patch_edits: list[dict], reset_keys: list[str]) -> list[dict]:
    """定位层按 id 增量合并；--clear 由调用方直接写空列表。"""
    current: dict[str, dict] = {}
    merge_key = lambda row: str(row.get("key") or row.get("id"))  # noqa: E731
    if OUT.exists():
        try:
            for item in load(OUT).get("edits", []):
                current[merge_key(item)] = item
        except (json.JSONDecodeError, OSError):
            current = {}
    for item in patch_edits:
        current[merge_key(item)] = item
    for key in reset_keys:
        current.pop(str(key), None)
    return [current[k] for k in sorted(current)]


def validate_system_state(value) -> dict | None:
    """system_state = {create: [...], edits: [...]}；也接受纯 create 数组。"""
    if value is None:
        return None
    if isinstance(value, list):
        value = {"create": value, "edits": []}
    if not isinstance(value, dict):
        raise SystemExit("system_state 必须是 {create: [...], edits: [...]} 或数组")
    old = {}
    if SYS_OUT.exists():
        try:
            old = load(SYS_OUT)
        except (json.JSONDecodeError, OSError):
            old = {}
    # 分层接管：补丁没写的键沿用已落库的前端体系状态，避免「只改文本」把新建记录冲掉。
    creates = value.get("create", old.get("create", [])) or []
    edits = value.get("edits", old.get("edits", [])) or []
    overwrites = value.get("overwrite", old.get("overwrite", [])) or []
    deletes = value.get("delete", old.get("delete", [])) or []
    for name, arr in (("create", creates), ("edits", edits),
                      ("overwrite", overwrites), ("delete", deletes)):
        if not isinstance(arr, list):
            raise SystemExit(f"system_state.{name} 必须是数组")
    existing_items = {x["key"]: x for x in load(REF / "catalog" / "systems.json").get("systems", [])}
    existing = set(existing_items)
    out_create = []
    for raw in creates:
        name = str(raw.get("name", "")).strip()
        if name in existing_items and existing_items[name].get("origin") == "view_edit":
            continue  # 幂等：同一补丁重复执行时跳过已创建的前端体系
        item = editor_schema.validate_system_create(raw, existing_keys=existing)
        existing.add(item["key"])
        out_create.append(item)
    out_edits = [editor_schema.validate_system_edit(x) for x in edits]
    out_overwrite = [editor_schema.validate_system_overwrite(x) for x in overwrites]
    out_delete = [editor_schema.validate_system_delete(x) for x in deletes]
    if not (creates or edits or overwrites or deletes):
        raise SystemExit("system_state 为空：至少新建、编辑或删除一个体系")
    return {"create": out_create, "edits": out_edits,
            "overwrite": out_overwrite, "delete": out_delete}


def write_system_state(state: dict, src: str) -> None:
    old = {}
    if SYS_OUT.exists():
        try:
            old = load(SYS_OUT)
        except (json.JSONDecodeError, OSError):
            old = {}
    payload = {
        "schema_version": 1.0,
        "updated_at": date.today().isoformat(),
        "source": src,
        "create": state["create"],
        "edits": state["edits"],
        "overwrite": state["overwrite"],
        "delete": state["delete"],
        # 多次补丁叠加时保留最初的 before 快照，--clear 才能回到人工维护值。
        "before": old.get("before") or {},
        "before_files": old.get("before_files") or {},
        "rule": "前端体系管理补丁；支持新建、整体编辑（成员/几何位置/连边/备注）、删除。--clear 用首次快照恢复三个文件。",
    }
    SYS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_library_adds(value) -> list[int]:
    """列表末尾「＋」从隐藏精灵库添加的序号；必须是库内整数序号。"""
    if not isinstance(value, list):
        raise SystemExit("library_add 必须是数组")
    lib_path = ROOT / "data" / "derived" / "spirit_library.json"
    if not lib_path.exists():
        raise SystemExit("data/derived/spirit_library.json 缺失；先跑 scripts/build_spirit_library.py")
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    allowed = {int(k) for k in (lib.get("spirits") or {})}
    out: list[int] = []
    for raw in value:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            raise SystemExit(f"library_add 含非整数序号：{raw!r}")
        if sid not in allowed:
            raise SystemExit(f"library_add 的 #{sid} 不在全量精灵库内")
        if sid not in out:
            out.append(sid)
    return out


def existing_library_adds() -> list[int]:
    if not LIB_OUT.exists():
        return []
    try:
        return [int(x) for x in json.loads(LIB_OUT.read_text(encoding="utf-8")).get("ids", [])]
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []


def write_library_adds(ids: list[int], src: str) -> None:
    payload = {
        "schema_version": 1.0,
        "updated_at": date.today().isoformat(),
        "source": src,
        "rule": "用户在列表末尾点＋从隐藏精灵库添加的序号；build_synergy_view.py 内联后由前端动态加入列表。",
        "ids": ids,
    }
    LIB_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_role_adds(value) -> dict:
    """同定位精灵自定义分组：{owner_id: [{id, note}]}；id 必须在全量精灵库或可编辑集合。"""
    if not isinstance(value, dict):
        raise SystemExit("role_add 必须是对象")
    allowed = editor_schema.editable_ids()
    lib_path = ROOT / "data" / "derived" / "spirit_library.json"
    lib_ids: set[int] = set()
    if lib_path.exists():
        lib_ids = {int(k) for k in (json.loads(lib_path.read_text(encoding="utf-8")).get("spirits") or {})}
    out: dict[str, list[dict]] = {}
    for owner, members in value.items():
        try:
            oid = int(owner)
        except (TypeError, ValueError):
            raise SystemExit(f"role_add 的 owner 不是整数序号：{owner!r}")
        if oid not in allowed:
            raise SystemExit(f"role_add 的 owner #{oid} 不在可编辑精灵集合内")
        if not isinstance(members, list):
            raise SystemExit(f"role_add #{oid} 的成员必须是数组")
        rows: list[dict] = []
        seen: set[int] = set()
        for m in members:
            if not isinstance(m, dict):
                raise SystemExit(f"role_add #{oid} 的成员必须是对象")
            try:
                mid = int(m.get("id"))
            except (TypeError, ValueError):
                raise SystemExit(f"role_add #{oid} 含非法成员序号：{m.get('id')!r}")
            if mid not in lib_ids and mid not in allowed:
                raise SystemExit(f"role_add #{oid} 的成员 #{mid} 不在全量精灵库内")
            note = str(m.get("note") or "").strip()[:300]
            if mid in seen:
                continue
            seen.add(mid)
            row = {"id": mid, "note": note}
            if m.get("hidden") is True:      # 从同定位分组里删除的成员（软隐藏，可再次添加）
                row["hidden"] = True
            rows.append(row)
        if rows:
            out[str(oid)] = rows
    return out


def existing_role_adds() -> dict:
    if not ROLE_OUT.exists():
        return {}
    try:
        return json.loads(ROLE_OUT.read_text(encoding="utf-8")).get("groups", {}) or {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def write_role_adds(groups: dict, src: str) -> None:
    payload = {
        "schema_version": 1.0,
        "updated_at": date.today().isoformat(),
        "source": src,
        "rule": "用户在相似定位区块点＋添加的同定位精灵与备注；build_synergy_view.py 内联 DATA.role_adds，"
                "只影响展示层，不改动 role_groups.json 的严格分组口径。",
        "groups": groups,
    }
    ROLE_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_edge_state(value) -> dict | None:
    """edge_state 为 None 表示不接管；否则必须是 {'edges': [...]} 且通过全量校验。"""
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("edges"), list):
        raise SystemExit("edge_state 必须是 {'edges': [...]} 或 null")
    edges = validate_edges(value["edges"])
    return {"edges": edges}


def write_edge_state(edge_state, src: str) -> None:
    old = {}
    if EDGE_OUT.exists():
        try:
            old = load(EDGE_OUT)
        except (json.JSONDecodeError, OSError):
            old = {}
    baseline = old.get("baseline")
    if not baseline:
        baseline = edges_from_systems(load(REF / "catalog" / "systems.json"))
    payload = {
        "schema_version": 1.0,
        "mode": "full-state",
        "updated_at": date.today().isoformat(),
        "source": src,
        "rule": "前端关系联动编辑的全量状态；apply_edge_view_edits.py 按 edge_state.edges 全量替换各体系 chain_edges/edge_meta，edge_state=null 时用 baseline 恢复库内默认边。",
        "edge_state": edge_state,
        "baseline": baseline,
    }
    EDGE_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *extra: str) -> None:
    print("  >", script, *extra)
    r = subprocess.run([sys.executable, script, *extra], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.stdout:
        print("    " + r.stdout.strip().replace("\n", "\n    ")[:900])
    if r.returncode != 0:
        print(r.stderr or "")
        raise SystemExit(f"{script} 失败（退出码 {r.returncode}），已停止后续重建")


def main() -> int:
    ap = argparse.ArgumentParser(description="把前端编辑补丁写回数据层")
    ap.add_argument("patch", nargs="?", help="spirit_view_edits.json 路径")
    ap.add_argument("--no-rebuild", action="store_true", help="只落库，不重建派生层")
    ap.add_argument("--clear", action="store_true", help="清除全部前端编辑，恢复库内默认值")
    args = ap.parse_args()

    if args.clear:
        edits: list[dict] = []
        deletions: list[int] = []
        edge_state = None
        has_edge_state = True          # --clear 明确恢复边层
        library_adds: list[int] = []
        has_library_adds = True        # --clear 明确清空精灵库添加
        role_adds: dict = {}
        has_role_adds = True
        src = "--clear"
    else:
        patch = find_patch(args.patch)
        if patch is None:
            print("未找到 spirit_view_edits.json：本次无改动。请先在前端点「导出编辑补丁」，"
                  "把文件放到项目根目录，或显式传入路径。")
            return 0
        doc = load(patch)
        if float(doc.get("schema_version", 0)) < 1.0:
            raise SystemExit("补丁 schema_version 不支持：" + repr(doc.get("schema_version")))
        src = str(patch.relative_to(ROOT)) if patch.is_relative_to(ROOT) else str(patch)
        # 体系注册表仍是只读键（禁止整表下发/改名），但允许 system_state 新增体系。
        forbidden = set(editor_schema.load_schema().get("forbidden_patch_keys", []))
        injected = sorted(forbidden.intersection(doc))
        if injected:
            raise SystemExit("补丁包含只读注册表键，禁止下发（体系/词表只能在数据层维护）：" + ", ".join(injected))
        system_state = (validate_system_state(doc.get("system_state"))
                        if "system_state" in doc else None)
        if system_state:
            write_system_state(system_state, src)
            # 先落体系，再校验联动边：新体系的 key 在同一补丁里必须可用。
            run("scripts/apply_system_view_edits.py")
        # 页面快照过期保护：带 edge_baseline 的补丁必须与当前 systems.json 的边一致。
        # 新建/编辑体系的补丁会改变体系集合，跳过该检查（否则同一补丁永远无法落库）。
        if "edge_state" in doc and not system_state:
            supplied = doc.get("edge_baseline")
            if supplied:
                current = edges_fingerprint(edges_from_systems(load(REF / "catalog" / "systems.json")))
                if str(supplied) != current:
                    raise SystemExit(
                        "页面联动边数据已过期（基线不一致）：请重新运行 build_synergy_view.py "
                        "并刷新前端后再导出补丁；本次落库已中止以免覆盖新边。")
            else:
                print("WARN: 补丁缺少 edge_baseline，跳过过期校验（建议用新版前端导出）")
        elif "edge_state" in doc and system_state:
            print("WARN: 补丁含 system_state，跳过 edge_baseline 过期校验（体系集合已变化）")
        patch_edits = validate(doc.get("edits", []))
        reset_keys = validate_reset_keys(doc.get("reset_edits", []))
        edits = merge_edits(patch_edits, reset_keys)
        deletions = (validate_deletions(doc["deletions"]) if "deletions" in doc
                     else existing_deletions())
        has_edge_state = "edge_state" in doc
        edge_state = validate_edge_state(doc.get("edge_state")) if has_edge_state else None
        has_library_adds = "library_add" in doc
        library_adds = (validate_library_adds(doc.get("library_add")) if has_library_adds
                        else existing_library_adds())
        has_role_adds = "role_add" in doc
        role_adds = (validate_role_adds(doc.get("role_add")) if has_role_adds
                     else existing_role_adds())

    payload = {
        "schema_version": 1.0,
        "updated_at": date.today().isoformat(),
        "source": src,
        "rule": "前端编辑补丁；apply_core_roles.py 优先读取本文件覆盖 ASSIGN 与 CLASS_OVERRIDE，重跑不会丢失编辑。",
        "edits": edits,
        "deletions": deletions,
        "note": "定位编辑按 id 增量合并；edits 为 upsert、reset_edits 为撤销、--clear 全清。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    del_payload = {
        "schema_version": 1.0,
        "updated_at": date.today().isoformat(),
        "source": src,
        "mode": "soft",
        "rule": "标记删除只从活跃视图隐藏、可恢复；不改动 roster.json / pool.json，不物理删除任何精灵数据。",
        "deleted": deletions,
    }
    DEL_OUT.write_text(json.dumps(del_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if has_library_adds:
        write_library_adds(library_adds, src)
    if has_role_adds:
        write_role_adds(role_adds, src)
    if has_edge_state:
        write_edge_state(edge_state, src)
        edge_msg = f"{len(edge_state['edges']) if edge_state else 0} 条联动边（已接管）" \
                   if edge_state else "联动边恢复为 baseline 默认态"
    else:
        edge_msg = "联动边层未接管，保持已落库结果"
    lib_msg = (f"、精灵库添加 {len(library_adds)} 只" if has_library_adds else "、精灵库添加层未接管")
    role_msg = (f"、同定位精灵 {sum(len(v) for v in role_adds.values())} 条"
                if has_role_adds else "、同定位精灵层未接管")
    print(f"view edits: {len(edits)} 条定位编辑、{len(deletions)} 只标记删除、{edge_msg}{lib_msg}{role_msg}（来源 {src}）")

    if args.clear:
        run("scripts/apply_system_view_edits.py", "--clear")
    run("scripts/apply_core_roles.py")
    if not args.no_rebuild:
        for s in REBUILD:
            run(s)
    else:
        print("跳过重建；请手动运行重建链与 check_roster.py")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

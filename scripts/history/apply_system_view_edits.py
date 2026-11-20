#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把前端「体系管理」补丁落库到 systems.json / tactics.md / SKILL.md（幂等）。

2026-11-08：体系注册表从「只读」放宽为「可新增、不可删除/改名」。
前端可以新建体系并登记核心/补位/对位与证据；本脚本负责：

  1. 校验 system_state.create（名称、类型、核心／补位／对位须为可编辑序号、来源标记合法）
  2. 追加 systems.json 条目（origin=view_edit、chain_status=顺序链待核）
  3. 在 tactics.md 追加对应章节（section 必须存在，否则 check_roster 报错）
  4. 在 SKILL.md 速查表追加一行，并更新体系计数
  5. system_edits：只改既有体系的文本字段（证据/来源/状态/载体/备注/别名），
     名称、类型、成员、章节一律不可改

    python scripts/apply_system_view_edits.py             # 应用 view_system_edits.json
    python scripts/apply_system_view_edits.py --clear     # 撤销前端新建体系与文本编辑
    python scripts/apply_system_view_edits.py --no-write  # 只校验

状态文件 `references/view_system_edits.json` 由 apply_view_edits.py 写入；
`--clear` 用首次快照恢复三个文件。2026-11-09 起体系名称不必以「体系」结尾、关系备注可留空。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REF = ROOT / "references"
SYSTEMS = REF / "catalog" / "systems.json"
TACTICS = REF / "docs" / "tactics.md"
SKILL = ROOT / "SKILL.md"
STATE = REF / "view_system_edits.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_tactics(text: str, system: dict) -> str:
    heading = f"## {system['section']}"
    if heading in text:
        return text
    article = str(system.pop("section_note", "") or "").strip()
    if not article:
        article = (f"- **成立条件**：{system.get('evidence', '')}\n"
                   f"- **逐回合顺序**：待补；先到「关系联动」编辑器登记显式边。\n"
                   f"- **资源／BP 成本**：待补。\n"
                   f"- **失效点**：{system.get('review_note') or '待补当季证据'}。")
    return text.rstrip() + f"\n\n{heading}\n\n{article}\n"


def skill_count(text: str) -> int | None:
    m = re.search(r"注册表 `references/systems\.json`（(\d+) 项）", text)
    return int(m.group(1)) if m else None


def update_skill(text: str, old_count: int, new_count: int, created: list[dict]) -> str:
    if old_count and new_count and old_count != new_count:
        text = text.replace(f"（{old_count} 项）", f"（{new_count} 项）")
        text = text.replace(f"**{old_count} 项「XX 体系」**", f"**{new_count} 项「XX 体系」**")
        text = text.replace(f"**227 只／{old_count} 项体系／",
                            f"**227 只／{new_count} 项体系／")
        text = text.replace(f"{old_count} 项体系分级", f"{new_count} 项体系分级")
    if created:
        rows = "\n".join(
            f"| {s['name']} | {'/'.join(str(x) for x in s['core'])} | "
            f"{s.get('carrier') or s.get('evidence', '')[:40]} | "
            f"{s.get('kind', '')}；{s.get('status', '')} |" for s in created)
        lines = text.splitlines()
        try:
            start = next(i for i, line in enumerate(lines) if line.startswith("## 体系速查"))
        except StopIteration:
            start = 0
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("## ")), len(lines))
        last_table = max((i for i in range(start, end) if lines[i].startswith("|")), default=None)
        if last_table is None:
            raise SystemExit("SKILL.md 体系速查里找不到表格，无法登记新体系")
        lines[last_table + 1:last_table + 1] = rows.splitlines()
        text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    if new_count and f"当前体系数：{new_count} 项" not in text:
        text = re.sub(r"当前体系数：\d+ 项", f"当前体系数：{new_count} 项", text)
        if f"当前体系数：{new_count} 项" not in text:
            text = text.replace("## 体系速查（XX 体系）",
                                "## 体系速查（XX 体系）\n\n当前体系数：%d 项（数据以 "
                                "`systems.json` 为准，含前端新增体系）。" % new_count, 1)
    return text


def remove_tactics_section(text: str, section: str) -> str:
    if not section:
        return text
    heading = "## " + section
    return re.sub(r"\n*" + re.escape(heading) + r".*?(?=\n## |\Z)", "\n", text, flags=re.S)


def replace_tactics_section(text: str, section: str, article: str) -> str:
    heading = "## " + section
    if heading not in text:
        return text.rstrip() + f"\n\n{heading}\n\n{article}\n"
    pattern = re.compile(r"(?m)(^" + re.escape(heading) + r"\n)(.*?)(?=^## |\Z)", re.S)
    return pattern.sub(lambda m: m.group(1) + article.strip() + "\n\n", text, count=1)


def remove_skill_rows(text: str, names: list[str]) -> str:
    prefixes = ["| " + n + " |" for n in names]
    return "\n".join(line for line in text.splitlines()
                      if not any(line.startswith(p) for p in prefixes)) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="落库前端体系管理补丁")
    ap.add_argument("--clear", action="store_true", help="撤销前端新建体系与文本编辑")
    ap.add_argument("--no-write", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    doc = load(SYSTEMS)
    skill_text = SKILL.read_text(encoding="utf-8")
    tactics_text = TACTICS.read_text(encoding="utf-8")
    old_count = skill_count(skill_text) or len(doc["systems"])
    state = load(STATE) if STATE.exists() else None

    if args.clear:
        if not state:
            print("system edits: no active state, nothing to clear")
            return 0
        snap = state.get("before_files") or {}
        if snap and all(k in snap for k in ("systems", "tactics", "skill")):
            # 2026-11-09：整体编辑/删除可能改动任何条目，用首次快照精确恢复。
            if not args.no_write:
                SYSTEMS.write_text(snap["systems"], encoding="utf-8")
                TACTICS.write_text(snap["tactics"], encoding="utf-8")
                SKILL.write_text(snap["skill"], encoding="utf-8")
                STATE.unlink(missing_ok=True)
            print("system edits cleared: restored systems.json / tactics.md / SKILL.md snapshot")
            return 0
        removed = [s for s in doc["systems"] if s.get("origin") == "view_edit"]
        doc["systems"] = [s for s in doc["systems"] if s.get("origin") != "view_edit"]
        for s in removed:
            tactics_text = remove_tactics_section(tactics_text, s.get("section", ""))
        for key, before in (state.get("before") or {}).items():
            for item in doc["systems"]:
                if item["key"] == key:
                    item.update(before)
        skill_text = remove_skill_rows(skill_text, [s.get("name", "") for s in removed])
        if not args.no_write:
            write(SYSTEMS, doc)
            TACTICS.write_text(tactics_text.rstrip() + "\n", encoding="utf-8")
            SKILL.write_text(update_skill(skill_text, old_count, len(doc["systems"]), []),
                             encoding="utf-8")
            STATE.unlink(missing_ok=True)
        print(f"system edits cleared: removed {len(removed)} view-created systems; "
              f"now {len(doc['systems'])} systems")
        return 0

    if not state:
        print("system edits: no active state, systems.json unchanged")
        return 0

    # 2026-11-09：首次落库时保存三份文件原文，--clear 可精确恢复（含删除/整体编辑）。
    snapshot = state.get("before_files") or {
        "systems": SYSTEMS.read_text(encoding="utf-8"),
        "tactics": tactics_text,
        "skill": skill_text,
    }
    created = []
    existing_items = {x["key"]: x for x in doc["systems"]}
    existing = set(existing_items)
    for raw in state.get("create", []) or []:
        name = str(raw.get("name", "")).strip()
        if name in existing_items:
            # 幂等：同一补丁重复执行时，已由前端创建的体系直接跳过；
            # 人工维护的同名体系仍视为冲突，避免误覆盖。
            if existing_items[name].get("origin") == "view_edit":
                continue
            raise SystemExit(f"体系已存在且不是前端新建，拒绝覆盖：{name}")
        item = editor_schema.validate_system_create(raw, existing_keys=existing)
        existing.add(item["key"])
        created.append(item)
    edits = [editor_schema.validate_system_edit(x) for x in (state.get("edits", []) or [])]
    overwrites = [editor_schema.validate_system_overwrite(x)
                  for x in (state.get("overwrite", []) or [])]
    deletes = [editor_schema.validate_system_delete(x)
               for x in (state.get("delete", []) or [])]

    # 幂等：已存在同名 view_edit 体系时跳过创建；已存在体系不重复追加。
    added = []
    for item in created:
        if any(x["key"] == item["key"] for x in doc["systems"]):
            continue
        article = item.pop("section_note", "")
        item["section_note"] = article
        tactics_text = ensure_tactics(tactics_text, item)
        item.pop("section_note", None)
        doc["systems"].append(item)
        added.append(item)

    before = dict(state.get("before") or {})
    for patch in edits:
        item = next((x for x in doc["systems"] if x["key"] == patch["key"]), None)
        if not item:
            raise SystemExit(f"体系编辑目标不存在：{patch['key']}")
        if patch["key"] not in before:
            before[patch["key"]] = {k: item.get(k) for k in patch if k != "key"}
        for k, v in patch.items():
            if k != "key":
                item[k] = v

    # 整体编辑：成员／几何位置／连边／备注／文本按补丁覆盖（名称、类型、章节不变）。
    for patch in overwrites:
        item = next((x for x in doc["systems"] if x["key"] == patch["key"]), None)
        if not item:
            raise SystemExit(f"体系编辑目标不存在：{patch['key']}")
        article = patch.pop("section_note", None)
        for k, v in patch.items():
            if k != "key":
                item[k] = v
        if article:
            tactics_text = replace_tactics_section(tactics_text, item["section"], article)

    # 删除：同时移除 tactics.md 章节与 SKILL.md 速查行，避免 check_roster 报错。
    removed_names = []
    for key in deletes:
        item = next((x for x in doc["systems"] if x["key"] == key), None)
        if not item:
            continue
        doc["systems"] = [x for x in doc["systems"] if x["key"] != key]
        tactics_text = remove_tactics_section(tactics_text, item.get("section", ""))
        removed_names.append(item.get("name", key))
    if removed_names:
        skill_text = remove_skill_rows(skill_text, removed_names)

    new_count = len(doc["systems"])
    new_skill = update_skill(skill_text, old_count, new_count, added)
    if not args.no_write:
        write(SYSTEMS, doc)
        TACTICS.write_text(tactics_text.rstrip() + "\n", encoding="utf-8")
        SKILL.write_text(new_skill, encoding="utf-8")
        state_payload = {
            "schema_version": 1.0,
            "updated_at": date.today().isoformat(),
            "source": state.get("source", ""),
            "create": state.get("create", []),
            "edits": state.get("edits", []),
            "overwrite": state.get("overwrite", []),
            "delete": state.get("delete", []),
            "before": before,
            "before_files": snapshot,
            "rule": "前端新建/整体编辑/删除体系；--clear 用首次快照恢复 systems.json / tactics.md / SKILL.md。",
        }
        write(STATE, state_payload)
    print(f"system edits applied: +{len(added)} created, {len(edits)} text edits, "
          f"{len(overwrites)} full edits, -{len(deletes)} deleted, "
          f"{old_count} -> {new_count} systems" + (" (dry-run)" if args.no_write else ""))
    for item in added:
        print(f"  + {item['name']} | core {item['core']} | {item['chain_status']}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

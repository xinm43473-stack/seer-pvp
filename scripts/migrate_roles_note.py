#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把实战备注与核心机制合并成单个 note 字段（2026-11-18 用户口径）。

用户要求：编辑里的「实战备注」与「核心机制」合并为「备注」，并在图鉴显示。
数据层不删旧字段（mechanics / editor_note 继续保留，供 audit_mechanics 与
历史补丁兼容），只新增 `note`：

    note = mechanics（每行一条，保持原有顺序）
           + 空行 + editor_note（若历史上有内容）

迁移幂等：已有 note 的精灵跳过；--force 才会按 mechanics 重算（覆盖手工编辑）。

用法:
    python scripts/migrate_roles_note.py --dry-run
    python scripts/migrate_roles_note.py
    python scripts/migrate_roles_note.py --force        # 用 mechanics 重算覆盖现有 note
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "references" / "catalog" / "roster.json"


def build_note(sp: dict) -> str:
    lines = [str(x).strip() for x in (sp.get("mechanics") or []) if str(x).strip()]
    note = str(sp.get("editor_note") or "").strip()
    if note:
        lines.append("")
        lines.append(note)
    return "\n".join(lines).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已有 note")
    args = ap.parse_args()

    doc = json.loads(ROSTER.read_text(encoding="utf-8"))
    spirits = doc.get("spirits") or []
    filled = kept = empty = 0
    for sp in spirits:
        note = build_note(sp)
        if not note:
            empty += 1
            continue
        if (sp.get("note") or "").strip() and not args.force:
            kept += 1
            continue
        if sp.get("note") == note:
            kept += 1
            continue
        sp["note"] = note
        filled += 1

    print("roster 精灵 %d 只｜写 note %d｜已有保留 %d｜无内容 %d"
          % (len(spirits), filled, kept, empty))
    for sp in spirits[:3]:
        head = (sp.get("note") or "").split("\n")
        print("  样例 #%s %s：%d 行｜首行 %s" % (sp.get("id"), sp.get("name"), len(head),
                                                head[0][:36] if head else "-"))

    if args.dry_run or not filled:
        return 0
    doc["note_rule"] = "note 为「实战备注＋核心机制」合并后的展示文本；mechanics/editor_note 保留供审计与补丁兼容"
    ROSTER.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written ->", ROSTER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

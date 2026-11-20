# -*- coding: utf-8 -*-
"""关系边常量：唯一来源是 references/catalog/editor_schema.json。

历史上 check_roster.py / build_synergy_view.py 都从「一次性脚本」
apply_edge_view_edits.py 里 import 这些常量；那个脚本归档到 scripts/history/
之后，把常量收在这里，活脚本不再依赖历史目录。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402

_SCHEMA = editor_schema.load_schema()
EDGE_TYPES = dict(_SCHEMA["edge_types"])
MIN_NOTE = int(_SCHEMA["limits"]["edge_note_min"])
MAX_NOTE = int(_SCHEMA["limits"]["edge_note_max"])
SYSTEM_KIND = _SCHEMA["edge"]["system_kind"]
REQUIRE_MEMBER = bool(_SCHEMA["edge"]["require_member"])
SYSTEM_NAME_EDITABLE = bool(_SCHEMA["edge"].get("system_name_editable", False))


def edges_fingerprint(edges: list[dict]) -> str:
    """当前显式边集合的短指纹（前端导出补丁时带上，落库时比对）。"""
    rows = sorted(
        (
            str(e.get("system_key") or ""),
            int(e.get("a") or 0),
            int(e.get("b") or 0),
            str(e.get("type") or ""),
            str(e.get("note") or "").strip(),
        )
        for e in edges
    )
    blob = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

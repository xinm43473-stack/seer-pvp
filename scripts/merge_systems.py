# -*- coding: utf-8 -*-
"""把 references/systems/ 的单体系文件合回 references/catalog/systems.json。

改完某个体系后的标准流程::

    python scripts/merge_systems.py     # 单文件 → 聚合
    python scripts/rebuild_view.py      # 聚合 → 前端内联 DATA（自动同步 systems/）

聚合文件保留给 check_roster / editor_schema / audit 等旧脚本使用。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import systems_store as store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "references" / "systems"
DST = ROOT / "references" / "catalog" / "systems.json"


def main() -> int:
    meta, systems = store.load_dir(SRC)
    if not systems:
        raise SystemExit(f"{SRC} 里没有体系文件")
    out = dict(meta)
    out["systems"] = systems
    store.write_json(DST, out)
    print(f"merged {len(systems)} systems -> {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

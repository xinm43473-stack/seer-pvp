# -*- coding: utf-8 -*-
"""把 references/catalog/systems.json 拆成「一个体系一个文件」（references/systems/）。

一次性迁移脚本；之后应直接编辑 references/systems/ 下的单文件，
再用 merge_systems.py 合回聚合文件供旧脚本使用。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import systems_store as store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "references" / "catalog" / "systems.json"
DST = ROOT / "references" / "systems"


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"找不到 {SRC}")
    data = store.read_json(SRC)
    meta = {k: v for k, v in data.items() if k != "systems"}
    systems = data.get("systems") or []
    n = store.write_dir(DST, meta, systems)
    print(f"split {len(systems)} systems -> {DST} ({n} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

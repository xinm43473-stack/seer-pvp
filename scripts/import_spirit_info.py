#!/usr/bin/env python3
"""把 data/seerapi/spirit_info.json 的魂印／立绘／技能资料转成前端覆盖层（幂等）。

2026-11-08 起资料位已由 SeerAPI 导入：data/seerapi/spirit_info.json 的 status=ready、
spirits 覆盖全部有整数序号的前端节点。本脚本只做字段/长度校验并生成覆盖层，
不联网、不抓取；status 为 placeholder 或 spirits 为空时生成空覆盖层。

    python scripts/fetch_seerapi_media.py     # 联网抓原始文件（增量）
    python scripts/build_spirit_media.py      # 离线整理出 spirit_info.json
    python scripts/import_spirit_info.py      # 本脚本，生成覆盖层

产物 references/catalog/spirit_info_overlay.json 由 build_synergy_view.py 应用到节点；
用户前端编辑覆盖层（view_edits.json）优先级更高，不会被导入数据覆盖。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "references"
SOURCE = ROOT / "data" / "seerapi" / "spirit_info.json"
OVERLAY = REF / "catalog" / "spirit_info_overlay.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_schema  # noqa: E402

FIELDS = {"soul_mark": 8000, "portrait": 500, "skills": (30, 200)}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_row(key: str, row: dict, allowed: set[int], keys: set[str]) -> dict:
    if not isinstance(row, dict):
        raise SystemExit(f"{key} 的资料必须是对象")
    extra = sorted(set(row) - set(FIELDS))
    if extra:
        raise SystemExit(f"{key} 含未登记资料字段：{extra}；新字段请先在 editor_schema.json 注册")
    if key.startswith("pending-"):
        if key not in keys:
            raise SystemExit(f"{key} 不是可编辑精灵")
    else:
        try:
            sid = int(key)
        except ValueError:
            raise SystemExit(f"{key} 不是合法精灵 key")
        if sid not in allowed:
            raise SystemExit(f"#{sid} 不在可编辑精灵集合内")
    out: dict = {}
    for field, cap in FIELDS.items():
        value = row.get(field)
        if field == "skills":
            items = value if isinstance(value, list) else ([] if value is None else [value])
            items = [str(x).strip() for x in items if str(x).strip()]
            max_items, item_cap = cap
            if len(items) > max_items:
                raise SystemExit(f"{key}.skills 最多 {max_items} 条")
            if any(len(x) > item_cap for x in items):
                raise SystemExit(f"{key}.skills 单条超过 {item_cap} 字")
            out[field] = items
        else:
            text = "" if value is None else str(value).strip()
            if len(text) > cap:
                raise SystemExit(f"{key}.{field} 超过 {cap} 字")
            out[field] = text
    return out


def main() -> int:
    doc = _load(SOURCE)
    status = doc.get("status", "placeholder")
    raw = doc.get("spirits", {}) or {}
    if status != "ready" or not raw:
        payload = {"schema_version": 1.0, "status": "placeholder",
                   "updated_at": date.today().isoformat(), "spirits": {}}
        print("spirit info: 占位阶段（status=%s, %d 只），未导入数据；覆盖层为空" % (status, len(raw)))
    else:
        allowed = editor_schema.editable_ids()
        keys = editor_schema.editable_keys()
        payload = {"schema_version": 1.0, "status": "ready",
                   "updated_at": date.today().isoformat(),
                   "source": "data/seerapi/spirit_info.json",
                   "spirits": {str(k): validate_row(str(k), v, allowed, keys)
                               for k, v in raw.items()}}
        print("spirit info: 导入 %d 只精灵的魂印／立绘／技能" % len(payload["spirits"]))
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if OVERLAY.exists() and OVERLAY.read_text(encoding="utf-8") == text:
        print("spirit info: 覆盖层无变化，跳过写入")
        return 0
    OVERLAY.write_text(text, encoding="utf-8")
    print("spirit info: 已写", OVERLAY.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""体系文件仓库：一个体系一个 JSON 文件。

目录结构（默认 references/systems/）::

    index.json          元信息 + 顺序（version / naming_rule / usage / kinds / evidence_levels / order）
    清PP体系.json       单个体系（扁平存 system 对象，首键 $schema）

这样单个体系可以独立拷贝／转发；前端「导入体系文件」读的就是这种格式，
`split_systems.py` / `merge_systems.py` 负责与旧的聚合文件 systems.json 互转。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA = "seer-system/1"
INDEX_SCHEMA = "seer-system-index/1"
# index.json 里除 order 外都是元信息；这里列出常用的，实际按「除 systems 外全保留」处理
META_KEYS = ("version", "naming_rule", "usage", "kinds", "evidence_levels")

_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def slug(key: str) -> str:
    """体系名 → 文件名（去掉非法字符，中文保留）。"""
    s = _BAD.sub("_", str(key or "")).strip().strip(".")
    return s or "system"


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_system_file(path: Path) -> dict:
    """读一个体系文件；兼容扁平对象与 {system: {...}} 两种写法。"""
    d = read_json(path)
    if isinstance(d, dict) and isinstance(d.get("system"), dict):
        d = d["system"]
    if not isinstance(d, dict):
        raise ValueError(f"{path}: 不是对象")
    d.pop("$schema", None)
    d.pop("exported_at", None)
    d.pop("members", None)
    return d


def load_dir(root: Path) -> tuple[dict, list[dict]]:
    """读整个目录；返回 (meta, systems)，顺序按 index.json 的 order。"""
    root = Path(root)
    if not root.is_dir():
        return {}, []
    meta: dict = {}
    order: list[str] = []
    index = root / "index.json"
    if index.exists():
        d = read_json(index)
        meta = {k: v for k, v in d.items() if k not in ("$schema", "order", "systems")}
        order = [str(x) for x in (d.get("order") or [])]
    items: dict[str, dict] = {}
    for p in sorted(root.glob("*.json")):
        if p.name == "index.json":
            continue
        s = load_system_file(p)
        key = str(s.get("key") or "")
        if key:
            items[key] = s
    rank = {k: i for i, k in enumerate(order)}
    systems = sorted(items.values(), key=lambda s: (rank.get(str(s["key"]), 10 ** 6), str(s["key"])))
    return meta, systems


def write_dir(root: Path, meta: dict, systems: list[dict]) -> int:
    """按一个体系一个文件写回；清掉已不存在的旧文件。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    for s in systems:
        key = str(s.get("key") or s.get("name") or "").strip()
        if not key:
            continue
        s = dict(s)
        s["key"] = key
        name = slug(key) + ".json"
        if name in keep:                     # 极少见：两个 key 归一化后撞名
            name = slug(key) + "-" + str(abs(hash(key)) % 10000) + ".json"
        keep.add(name)
        payload = {"$schema": SCHEMA}
        payload.update(s)
        write_json(root / name, payload)
    for p in root.glob("*.json"):
        if p.name != "index.json" and p.name not in keep:
            p.unlink()
    index = {"$schema": INDEX_SCHEMA}
    index.update({k: v for k, v in meta.items() if k not in ("order", "systems")})
    index["order"] = [str(s["key"]) for s in systems if s.get("key")]
    write_json(root / "index.json", index)
    return len(keep)


def merge_into(dst: dict, src: dict) -> dict:
    """把单体系文件合并进前端 DATA.systems 的既有条目（只覆盖已有 key，不新增）。"""
    by_key = {str(s.get("key")): s for s in src.get("systems") or []}
    changed = 0
    for i, s in enumerate(dst.get("systems") or []):
        hit = by_key.get(str(s.get("key")))
        if hit is not None and hit != s:
            dst["systems"][i] = hit
            changed += 1
    return {"changed": changed}

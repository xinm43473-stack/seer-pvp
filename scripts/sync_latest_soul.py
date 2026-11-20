# -*- coding: utf-8 -*-
"""把 SeerAPI 抓到的最新魂印同步到展示层——「每次拉取都拉到最新」的离线侧配对脚本。

为什么要有它（2026-11-20）：用户问「灾厄女神潘多拉的加强魂印为什么不显示」。
`data/seerapi/seerapi.json` 的 11-06 快照里 3396 只有 soulmark 709；游戏后来追加了
2170（「自身登场时令对手全属性-1……以最优系别结算」），而当时的抓取判据只重抓
「没有魂印／缺 has_format」的精灵，永远不会补新条；库构建又把 `out[0]` 当主版。
抓取侧已改成默认全量重抓（`fetch_seerapi.py`），本脚本把新抓到的条目落到展示层：

  1. `data/seerapi/seerapi.json`        读：每只精灵 id 最大的那条 = 最新结算文本
  2. `data/derived/spirit_library.json` 写：soul / soulmarks（最新那条 primary）
  3. `data/seerapi/spirit_info.json`    写：soul_mark（当前生效版全文）
  4. 内联 `const DATA`                  写：nodes[].soul_mark、library 行

两条护栏，保证幂等、不推翻已核过的文本：

* **只升级「还在显示旧版」的精灵**：节点的 `soul_mark` 为空，或与内联快照 `DATA.media`
  的主版文本一致时才算「旧版」；已经不一样（＝有人按强化后版本核过，如 22 只强化形态）
  一律不动。
* **只有新抓到的魂印 id 比内联主版 id 大才写**，所以反复跑不会抖动。

内联 DATA 一律走 `scripts/viewdata.py`，不手切 `const DATA = `。

用法：
  python scripts/fetch_seerapi.py --all-deep    # 先重抓（默认全量刷新）
  python scripts/sync_latest_soul.py            # 再同步到展示层（--dry-run 只看差异）
  python scripts/rebuild_view.py                # 然后重建前端
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import viewdata  # noqa: E402

API = ROOT / "data" / "seerapi" / "seerapi.json"
INFO = ROOT / "data" / "seerapi" / "spirit_info.json"
LIB = ROOT / "data" / "derived" / "spirit_library.json"
VIEW = ROOT / "references" / "spirit_synergy_view.html"

NOISE_RE = re.compile(r"\[[^\]]*\]|[\s|｜]")


def load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(text) -> str:
    """比对用：去掉图标/换行/竖线/空白，只留正文字符。"""
    return NOISE_RE.sub("", str(text or ""))


def latest_marks(api: dict) -> dict[int, tuple[int, str]]:
    """每只精灵 → (最新魂印 id, 全文)。老版在前、新版在后，取 id 最大的一条。"""
    out: dict[int, tuple[int, str]] = {}
    for key, pet in (api.get("pets") or {}).items():
        marks = [m for m in (pet.get("soulmarks") or [])
                 if isinstance(m, dict) and m.get("id") is not None]
        if not marks:
            continue
        best = max(marks, key=lambda m: int(m["id"]))
        text = str(best.get("full") or best.get("desc") or "").strip()
        if not text:
            continue
        try:
            out[int(key)] = (int(best["id"]), text)
        except ValueError:
            continue
    return out


def media_primary(payload: dict, sid: int) -> tuple[int | None, str]:
    """内联资料层的主版魂印：id 与正文（构建期快照，可能已过时）。"""
    row = ((payload.get("media") or {}).get("spirits") or {}).get(str(sid)) or {}
    marks = [m for m in (row.get("soul") or []) if isinstance(m, dict)]
    if not marks:
        return None, ""
    prim = next((m for m in marks if m.get("primary")), marks[0])
    try:
        return int(prim["id"]), str(prim.get("text") or "")
    except (KeyError, TypeError, ValueError):
        return None, str(prim.get("text") or "")


def showing_old(current: str, snapshot: str) -> bool:
    """节点/资料位当前文本是不是「内联快照那一版」（空也算旧）。"""
    cur = norm(current)
    return (not cur) or cur == norm(snapshot)


def main() -> int:
    dry = "--dry-run" in sys.argv
    api = load(API, {})
    info = load(INFO, {})
    lib = load(LIB, {})
    payload = viewdata.read(VIEW)

    latest = latest_marks(api)
    if not latest:
        print("没有从 %s 读到魂印，先跑 fetch_seerapi.py" % API)
        return 1

    nodes = {str(n.get("id")): n for n in (payload.get("nodes") or [])}
    lib_inline = {str(r.get("id")): r for r in ((payload.get("library") or {}).get("spirits") or [])}
    lib_rows = lib.get("spirits") or {}
    info_rows = info.get("spirits") or {}

    nodes_up, lib_up, info_up = [], [], []

    for sid, (mid, text) in sorted(latest.items()):
        key = str(sid)
        cur_id, cur_text = media_primary(payload, sid)
        newer = cur_id is None or mid > cur_id

        # ---- 1) 内联节点（左侧列表）：还在显示旧版才升级 ----
        node = nodes.get(key)
        if node is not None and newer and showing_old(node.get("soul_mark"), cur_text):
            node["soul_mark"] = text.replace("|", "|\n")
            nodes_up.append((sid, node.get("name"), cur_id, mid))

        # ---- 2) 资料位（spirit_info：当前生效版全文）----
        inf = info_rows.get(key)
        if inf is not None and newer and showing_old(inf.get("soul_mark"), cur_text):
            inf["soul_mark"] = text.replace("|", "\n")
            info_up.append((sid, mid))

        # ---- 3) 隐藏库行（1977 只）----
        row = lib_rows.get(key)
        if row is None:
            continue
        ids = []
        for m in row.get("soulmarks") or []:
            try:
                ids.append(int(m.get("id")))
            except (TypeError, ValueError):
                continue
        if ids and mid <= max(ids):
            continue
        marks = [m for m in (row.get("soulmarks") or []) if isinstance(m, dict)]
        for m in marks:
            m["primary"] = False
        marks.append({"id": mid, "text": text, "source_field": "desc",
                      "primary": True, "has_format": False})
        row["soulmarks"] = marks
        row["soul"] = text
        lib_up.append((sid, row.get("name"), max(ids) if ids else None, mid))
        inline = lib_inline.get(key)
        if inline is not None:
            inline["soul"] = row["soul"]
            inline["soulmarks"] = marks

    print("SeerAPI 最新魂印 %d 条" % len(latest))
    for label, rows in (("节点 soul_mark", nodes_up), ("库行 soul", lib_up)):
        print("  %s 更新 %d 只" % (label, len(rows)))
        for r in rows[:10]:
            print("    %-6s %-16s %s → %s" % (r[0], r[1] or "", r[2], r[3]))
    print("  资料位 soul_mark 更新 %d 只" % len(info_up))

    if dry:
        print("--dry-run：没有写文件")
        return 0
    if not (nodes_up or lib_up or info_up):
        print("已是最新，无需改动")
        return 0

    if lib_up:
        dump(LIB, lib)
    if info_up:
        dump(INFO, info)
    if nodes_up or lib_up:
        viewdata.save_payload(VIEW, payload)
    print("写回：%s" % "、".join(x for x, on in (
        ("data/derived/spirit_library.json", lib_up),
        ("data/seerapi/spirit_info.json", info_up),
        ("内联 DATA", nodes_up or lib_up)) if on))
    print("下一步：python scripts/rebuild_view.py")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

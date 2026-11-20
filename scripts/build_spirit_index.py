#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a single browsable index of every spirit recorded by this skill.

Outputs:
  references/catalog/spirit_master_list.csv  Excel-friendly full table (UTF-8 BOM)
  references/docs/spirit_master_list.md   human-readable layered summary + active-layer list

Also exports collect(), shared by build_strength.py / build_full_audit.py /
editor_schema.py -- keep this module importable.

Scope: ID 2987-4950 plus special IDs used by the roster (e.g. 5000), and
candidate entries whose ID is still unknown. Every ID gets a row; nothing is
hidden behind a JSON file.

Usage: python scripts/build_spirit_index.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
REF = ROOT / "references"

LAYERS = ["深研层", "候选池", "配置/攻略专题", "人工回捞",
          "旧理由作废", "全量图鉴", "剔除记录", "未收录序号"]
ACTIVE_LAYERS = set(LAYERS[:4])
# 2026-11-04: only 自然王 (3355 莫妮卡) may be recorded among first-gen kings.
FIRST_GEN_KINGS = {"凡尔斯", "乔特鲁德", "米斯蒂克", "沧岚", "格劳瑞", "莱茵哈特",
                   "霍德尔", "海瑟薇", "阿尔斯兰", "茉蕊儿", "欧德奈瑞", "列奥尼达",
                   "马尔修斯", "奥佩娅", "格斯塔丝", "艾恩斯", "斯嘉丽", "柯尔德", "弗里德"}


def collect():
    roster = json.loads((REF / "catalog" / "roster.json").read_text(encoding="utf-8"))
    pool = json.loads((DATA / "bwiki/pool.json").read_text(encoding="utf-8"))
    idx = json.loads((REF / "catalog" / "creator_index.json").read_text(encoding="utf-8"))
    overrides = json.loads((REF / "catalog" / "manual_overrides.json").read_text(encoding="utf-8"))
    voided = json.loads((REF / "catalog" / "voided_drops.json").read_text(encoding="utf-8"))
    strength_path = REF / "catalog" / "strength.json"
    strength_doc = (json.loads(strength_path.read_text(encoding="utf-8"))
                    if strength_path.exists() else {})
    rated = {x["id"]: x["grade"] for x in strength_doc.get("ratings", [])}
    watch_ids = {x["id"] for x in strength_doc.get("watchlist", [])}
    bias_ids = {x["id"] for x in strength_doc.get("bias_review", {}).get("items", [])}

    def strength_of(sid):
        if sid in rated:
            return rated[sid]
        if sid in watch_ids:
            return "未评级（月榜观察名单）"
        if sid in bias_ids:
            return "未评级（功能位待复核）"
        return "未评级"

    souls = json.loads((DATA / "seerapi/soul_full.json").read_text(encoding="utf-8"))["souls"]
    raw_elves = {x["id"]: x for x in json.loads((DATA / "bwiki" / "elves.json").read_text(encoding="utf-8"))}
    elves = {x["id"]: x for x in pool["elves"]}
    dropped = {x["id"]: x for x in pool["dropped"] if isinstance(x, dict) and isinstance(x.get("id"), int)}
    themed = {x["id"]: x for x in idx["themed_spirits"]}
    voided_map = {x["id"]: x for x in voided["items"]}
    spirit_map = {x["id"]: x for x in roster["spirits"]}
    pending_map = {x.get("id"): x for x in roster["pending_research"]}
    override_map = {x["id"]: x for x in overrides["spirits"]}

    ids = set(range(2987, 4951)) | set(elves) | set(dropped) | set(spirit_map) | set(override_map)
    rows = []
    for sid in sorted(ids):
        layers = []
        if sid in spirit_map:
            layers.append("深研层")
        if sid in pending_map:
            layers.append("候选池")
        if sid in themed:
            layers.append("配置/攻略专题")
        if sid in override_map:
            layers.append("人工回捞")
        if sid in voided_map:
            layers.append("旧理由作废")
        if sid in elves:
            layers.append("全量图鉴")
        if sid in dropped:
            layers.append("剔除记录")
        if not layers:
            layers.append("未收录序号")

        name = (spirit_map.get(sid, {}).get("name") or pending_map.get(sid, {}).get("name")
                or override_map.get(sid, {}).get("name") or themed.get(sid, {}).get("name")
                or elves.get(sid, {}).get("name")
                or dropped.get(sid, {}).get("name") or raw_elves.get(sid, {}).get("name") or "—")
        attr = (elves.get(sid, {}).get("attr") or spirit_map.get(sid, {}).get("attr")
                or override_map.get(sid, {}).get("attr") or raw_elves.get(sid, {}).get("attr") or "—")
        tier = elves.get(sid, {}).get("tier", "—")
        soul = souls.get(str(sid), {})
        notes = []
        if sid in spirit_map:
            notes.append("/".join(spirit_map[sid].get("roles", [])[:3]))
        if sid in themed:
            notes.append("专题：" + str(themed[sid].get("example_work", ""))[:26])
        if sid in pending_map:
            notes.append(str(pending_map[sid].get("source", "")))
        main = next((x for x in LAYERS if x in layers and x in ACTIVE_LAYERS), layers[0])
        rows.append({
            "id": sid, "name": name, "attr": attr, "tier": tier,
            "strength": strength_of(sid),
            "layers": layers, "main": main, "active": any(x in ACTIVE_LAYERS for x in layers),
            "soul_len": soul.get("full_len", 0), "note": "；".join(dict.fromkeys(notes))[:120],
        })

    # Candidate entries whose正式名/序号 still need verification.
    for item in roster["pending_research"]:
        if item.get("id") is not None:
            continue
        rows.append({"id": None, "name": item.get("name", "待核"), "attr": "待核", "tier": "—",
                     "strength": "未评级",
                     "layers": ["候选池"], "main": "候选池", "active": True,
                     "soul_len": 0, "note": item.get("note", "")[:110]})

    # User decision 2026-11-04: "被剔除的就不要放了". The master list shows
    # only recorded (active-layer) spirits. Historical auto-drop rows and jump
    # IDs are excluded; the "剔除记录" tag is also dropped from remaining rows
    # because under F20261104 it is only an audit trail, never a status.
    rows = [x for x in rows if x["active"]
            and (x["name"] not in FIRST_GEN_KINGS or x["id"] == 3355)]
    for x in rows:
        x["layers"] = [l for l in x["layers"] if l in ACTIVE_LAYERS]
    # 2026-11-09 用户口径：不再展示层级，右侧/表内只显示可自维护的 T 评级，默认 T0。
    ratings = {}
    vp = REF / "view_edits.json"
    if vp.exists():
        for item in json.loads(vp.read_text(encoding="utf-8")).get("edits", []):
            if item.get("rating"):
                ratings[item.get("id")] = str(item["rating"])[:8]
    for x in rows:
        x["rating"] = ratings.get(x["id"], "T0")
    return rows, roster, idx


def write_csv(rows):
    path = REF / "catalog" / "spirit_master_list.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["序号", "名称", "属性", "评级", "人工强度", "BWIKI魂印全文字数", "备注/作品线索"])
        for x in rows:
            w.writerow([x["id"] if x["id"] is not None else "—", x["name"], x["attr"],
                        x.get("rating", "T0"), x["strength"], x["soul_len"], x["note"]])
    return path


def write_markdown(rows, roster, idx):
    counts = Counter(x["main"] for x in rows)
    active = [x for x in rows if x["active"]]
    lines = [
        "# 全部录入精灵总表",
        "",
        f"生成日期：{date.today().isoformat()}｜口径：**F20261104** —— 是否录入只看两位 UP 主是否出过配置／攻略视频或专题作品，不以魂印条数、种族值或自动评分判断。**总表只收录已录入精灵与配置/攻略专题覆盖；旧自动筛选留痕、标题提及层与一代王基础形态（自然王 3355 莫妮卡除外）不进表**。",
        "",
        "## 一眼看全（两个入口）",
        "",
        "| 想做什么 | 打开哪里 |",
        "|---|---|",
        "| 用 Excel / WPS 筛选、排序、另存 | `references/catalog/spirit_master_list.csv`（UTF-8 BOM，共 %d 行） |" % len(rows),
        "| 看全部录入名单 | 本文件下方 |",
        "| 查单只魂印全文与逐回合战术 | `python scripts/query.py 名称 --full` |",
        "| 查旧自动筛选记录（不进总表） | `python scripts/query.py --dropped 名称` |",
        "| 看各层数量汇总 | `python scripts/query.py`（无参数）或 `python scripts/check_roster.py` |",
        "",
        "**原始机读数据**：`references/catalog/roster.json`（深研层 `spirits`、候选池 `pending_research`）、`data/bwiki/pool.json`（资料层 `elves` 与历史筛选记录 `dropped`）、`references/catalog/strength.json`（人工强度）、`references/catalog/manual_overrides.json`、`references/catalog/creator_index.json`、`references/catalog/voided_drops.json`。",
        "",
        "## 全部录入精灵（%d 只）" % len(active),
        "",
        "| 序号 | 名称 | 属性 | 评级 | 人工强度 | 魂印字数 | 备注 / 作品线索 |",
        "|---|---|---|---|---|---|---|",
    ]
    for x in active:
        sid = x["id"] if x["id"] is not None else "—"
        lines.append(f"| {sid} | {x['name']} | {x['attr']} | {x.get('rating','T0')} | {x['strength']} | {x['soul_len']} | {x['note'] or '—'} |")
    lines.append("")
    lines += [
        "## 其余去哪看",
        "",
        "- 旧自动筛选留痕（757 条）、官方跳号与仅图鉴层未录入的精灵**不在本总表**；查 `data/bwiki/pool.json` 的 `dropped`、`python scripts/query.py --dropped 名称` 或 `references/docs/catalog.md`。",
        "- 蝶夏Channel 430 篇专栏 / 97 篇专题、狗子 6 条可核验视频线索见 `references/catalog/creator_index.json`；狗子 711 个视频因作品太杂且无分类合集，用户已于 2026-11-04 决定不再补齐，不臆造名单。",
        "- 机制复杂度高分但尚未写战术链的队列 `references/catalog/tier_gaps.json`、魂印文本复核队列 `references/catalog/soul_text_gaps.json`、历史理由队列 `references/catalog/voided_drops.json`；人工强度与复杂度分冲突清单见 `references/catalog/strength.json`。",
        "",
        "重新生成：`python scripts/build_spirit_index.py`（改动精灵库或作品索引后重跑）。",
        "",
    ]
    path = REF / "docs" / "spirit_master_list.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    rows, roster, idx = collect()
    paths = [write_csv(rows), write_markdown(rows, roster, idx)]
    print(f"master list: {len(rows)} rows; active layers="
          f"{sum(1 for x in rows if x['active'])}")
    for p in paths:
        print(f"  {p.name}: {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()

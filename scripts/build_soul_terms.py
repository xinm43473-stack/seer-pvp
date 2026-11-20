#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""魂印专属名词词典：只搬运可溯源释义，不生成任何解释。

来源（按优先级）：
1. SeerAPI 术语表 `glossary_entry`（`scripts/fetch_glossary.py` 落盘，官方释义）
   - kind 1 专属效果名 / 2 异常状态 / 3 吸取体力 / 6 特殊机制 全部收录
   - kind 4 规则名词只收 4 字及以上（`回合类效果`、`技能先制`、`真实伤害` 等），
     1-3 字通用词（`以`/`转`/`合`/`当回合`/`己方`）不收，避免整段文字被划线
   - `待补` 占位条目丢弃
2. SeerAPI `battle_effect`（异常状态官方释义，术语表未收时补位）
3. 魂印原文自带定义：`名称：释义` 段（如 `帝君之赐：…`、`太阳牌：…`），
   逐字取自魂印文本，来源标记 inline

产物：data/derived/soul_terms.json
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "seerapi_media" / "raw"
OUT = DATA / "derived/soul_terms.json"

# 官方术语表 kind 语义 → 三档名词解释类别（前端三色圆环切换）
#   ex     精灵专属名词：1 专属效果名（该精灵独有机制，如「神魂之器」）+ 魂印原文自带定义
#   eff    通用效果名词：2 异常状态 / 3 吸取体力 / 6 特殊机制（跨精灵通用效果）
#   timing 时点名词：5（回合开始时、登场时、被击败…）
#   kind 4 规则词（回合类效果、固定伤害、先制）仍不收：属语法性通用规则词，
#          在魂印里几乎逐句出现，划线无信息量。
KIND_CAT = {1: "ex", 2: "eff", 3: "eff", 6: "eff", 5: "timing"}
KIND_KEEP = set(KIND_CAT)
CAT_NAME = {"eff": "通用效果名词", "ex": "精灵专属名词", "timing": "时点名词"}
PLACEHOLDER = "待补"

STOP_PREFIX = (
    "自身", "对手", "己方", "对方", "我方", "双方", "若", "则", "当", "每", "该", "此",
    "其", "且", "并", "同时", "如果", "否则", "以上", "以下", "所有", "每次", "每回合",
    "攻击", "技能", "属性", "能力", "体力", "伤害", "效果", "回合", "回合开始", "回合结束",
    "进入", "存在", "拥有", "获得", "消耗", "使用", "造成", "受到",
    "处于", "位于", "拥有", "携带", "视为", "视为处于",
)
# 换行/分号截断出来的通用词碎片，不能当成专属名词（原文列如 `…异常状态：…`）
STOP_SUFFIX = ("状态", "效果", "技能", "能力", "伤害", "体力", "精灵", "属性", "等级")
# 名字以这些结尾说明是被截断的半截词（`狩杀之`），丢弃
BAD_TAIL = ("之", "的", "与", "和", "或")
NAME_RE = re.compile(r"^([\u4e00-\u9fa5·]{2,8})[：:](.{8,})$")
CLEAN_RE = re.compile(r"\[sprite[^\]]*\]|\[color=[^\]]*\]|\[/color\]|\[/?b\]")
LEVEL_RE = re.compile(r"^\d+层$")


def clean(text: str) -> str:
    t = str(text or "")
    t = CLEAN_RE.sub("", t)
    t = t.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    t = t.replace("{", "").replace("}", "")          # {吸取} → 吸取（原文术语标记）
    t = t.replace("\u3000", " ").replace("\xa0", " ")
    return t


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def souls() -> list[tuple[str, str]]:
    """所有可扫的魂印文本：(来源标签, 文本)。"""
    out: list[tuple[str, str]] = []

    media = load_json(DATA / "seerapi/spirit_media.json") or {}
    for sid, row in (media.get("spirits") or {}).items():
        for ver in row.get("soulmarks") or []:
            for field in ("formatted", "text", "desc"):
                if ver.get(field):
                    out.append((f"media:{sid}", clean(ver[field])))

    lib = load_json(DATA / "derived/spirit_library.json") or {}
    for sid, row in (lib.get("spirits") or {}).items():
        if row.get("soul"):
            out.append((f"library:{sid}", clean(row["soul"])))

    full = load_json(DATA / "seerapi/soul_full.json") or {}
    for sid, row in (full.get("souls") or {}).items():
        if row.get("text"):
            out.append((f"bwiki:{sid}", clean(row["text"])))

    pool = load_json(DATA / "bwiki/pool.json") or {}
    for row in (pool.get("elves") or []):
        if row.get("soul"):
            out.append((f"pool:{row.get('id')}", clean(row["soul"])))
    return out


def glossary_terms() -> dict[str, dict]:
    terms: dict[str, dict] = {}
    folder = RAW / "glossary_entry"
    if not folder.exists():
        raise SystemExit("缺 data/seerapi_media/raw/glossary_entry；先跑 scripts/fetch_glossary.py")
    for path in sorted(folder.glob("*.json")):
        if path.name.startswith("_"):
            continue
        row = load_json(path) or {}
        name = str(row.get("name") or "").strip()
        desc = str(row.get("desc") or "").strip()
        kind = row.get("kind")
        if not name or name == PLACEHOLDER or desc in ("", PLACEHOLDER):
            continue
        if not isinstance(kind, int):
            continue
        if kind in KIND_KEEP:
            keep = len(name) >= 2
        else:
            keep = False          # 4 规则词：语法性通用词，不在魂印里逐句划线
        if not keep:
            continue
        # 同一名称可能多条，取释义更长的那条
        old = terms.get(name)
        if old and len(old["d"]) >= len(desc):
            continue
        terms[name] = {"d": desc, "s": "glossary", "k": kind, "c": KIND_CAT[kind]}

    for path in sorted((RAW / "battle_effect").glob("*.json")):
        row = load_json(path) or {}
        name = str(row.get("name") or "").strip()
        desc = str(row.get("desc") or "").strip()
        if name and desc and name not in terms:
            terms[name] = {"d": desc, "s": "battle_effect", "k": 0, "c": "eff"}
    return terms


def spirit_names() -> set[str]:
    lib = load_json(DATA / "derived/spirit_library.json") or {}
    return {str(v.get("name") or "").strip() for v in (lib.get("spirits") or {}).values()} - {""}


def inline_terms(terms: dict[str, dict], corpus: list[tuple[str, str]]) -> int:
    """从魂印原文的 `名称：释义` 段抽取，逐字引用，不改写。"""
    found: dict[str, list[tuple[str, int]]] = {}
    names = spirit_names()          # 精灵名不是名词，别当成术语
    for src, text in corpus:
        for seg in re.split(r"[\n|;；]", text):
            seg = seg.strip()
            m = NAME_RE.match(seg)
            if not m:
                continue
            name, body = m.group(1).strip(), m.group(2).strip()
            name = name.replace("BUFF说明", "").replace("Buff说明", "").replace("buff说明", "").strip()
            name = name.rstrip("的")
            if name in terms or LEVEL_RE.match(name) or len(name) < 2:
                continue
            if name.startswith(STOP_PREFIX) or name.endswith(STOP_SUFFIX) or name.endswith(BAD_TAIL):
                continue
            if name in names:
                continue
            body = body.split("，若")[0].strip() if len(body) > 90 else body
            if len(body) < 8:
                continue
            found.setdefault(name, []).append((body, len(body)))

    added = 0
    for name, rows in found.items():
        best = max(rows, key=lambda x: x[1] if x[1] <= 140 else 0)
        terms[name] = {"d": best[0][:140], "s": "inline", "k": 0, "n": len(rows), "c": "ex"}
        added += 1
    return added


def main() -> None:
    terms = glossary_terms()
    corpus = souls()
    inline = inline_terms(terms, corpus)

    # 覆盖率自检：词典能被多少条魂印命中
    texts = [t for _, t in corpus]
    hit = sum(1 for t in texts if any(name in t for name in terms))
    payload = {
        "generated_at": date.today().isoformat(),
        "source": {
            "glossary": "https://api.seerapi.com/v1/glossary_entry（SeerAPI 官方术语表，原文搬运）",
            "battle_effect": "https://api.seerapi.com/v1/battle_effect",
            "inline": "魂印原文 `名称：释义` 段（逐字引用，不改写）",
        },
        "cats": CAT_NAME,
        "rule": "只收可溯源释义；按官方术语表 kind 分三档：1 专属效果名→ex（精灵专属名词），"
                "2 异常状态／3 吸取体力／6 特殊机制→eff（通用效果名词），5 时点词→timing（时点名词）；"
                "`待补` 丢弃；4 规则词（回合类效果、固定伤害、先制…）属语法性通用词不收；"
                "原文自带定义仅当名称未被术语表收录时补位，归 ex。",
        "stats": {
            "terms": len(terms),
            "glossary": sum(1 for v in terms.values() if v["s"] == "glossary"),
            "battle_effect": sum(1 for v in terms.values() if v["s"] == "battle_effect"),
            "inline": inline,
            "ex": sum(1 for v in terms.values() if v.get("c") == "ex"),
            "eff": sum(1 for v in terms.values() if v.get("c") == "eff"),
            "timing": sum(1 for v in terms.values() if v.get("c") == "timing"),
            "soul_texts": len(texts),
            "soul_texts_hit": hit,
        },
        "terms": dict(sorted(terms.items())),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    st = payload["stats"]
    print(f"soul_terms: {st['terms']} 条（术语表 {st['glossary']} / 异常状态 {st['battle_effect']} / 原文定义 {st['inline']}）")
    print(f"  分类：精灵专属 {st['ex']} / 通用效果 {st['eff']} / 时点 {st['timing']}")
    print(f"  魂印文本 {st['soul_texts']} 条，命中 {st['soul_texts_hit']} 条；{OUT.stat().st_size/1024:.0f}KB")
    freq = Counter()
    for t in texts:
        for name in terms:
            if name in t:
                freq[name] += 1
    print("  常见名词:", freq.most_common(8))


if __name__ == "__main__":
    main()

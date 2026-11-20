#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛尔号巅峰 PvP 全量精灵查询工具

用法：
  python query.py 至序圣华 --full       # 名称/序号（魂印全文 + 深研战术）
  python query.py --id 4321            # 按序号
  python query.py --tag 复活 驱逐       # 按机制标签
  python query.py --attr 混沌           # 按属性
  python query.py --tier T0 T1         # 按机制文本复杂度分档（非强度、非月榜）
  python query.py --top 15             # 机制文本复杂度排序（非强度榜）
  python query.py --strength            # 列出全部人工强度评级
  python query.py --audit 机盖          # 查单只全量评级依据／冲突／复核优先级
  python query.py --audit               # 全量复查汇总
  python query.py --dropped 至序圣华    # 查历史筛选记录及原因
  python query.py --system 猫阵         # 按「XX 体系」名称/别名查成员与证据
  python query.py --system             # 列出全部已命名体系
  python query.py --role 机盖           # 按精灵查相似定位（同类功能位，不是配合）
  python query.py --role               # 列出全部相似定位组
  python query.py --media 机盖         # SeerAPI 资料层：魂印各版本/技能/图像文件
  python query.py --media              # 资料层统计与前 20 只
  python query.py                      # 显示各数据层数量

数据层（各层数量以 check_roster.py 输出为准，不在本文件写死）：
  data/bwiki/pool.json            自动图鉴 + 历史筛选留痕
  references/catalog/manual_overrides.json 人工深研回捞精灵
  data/seerapi/soul_full.json       BWIKI 魂印全文（未抓取完成时退回本地快照）
  references/catalog/roster.json    人工逐只写过的战术链
  references/catalog/systems.json   统一命名的「XX 体系」注册表
  references/catalog/strength.json  人工强度层（自动评分只是机制文本复杂度，不是强度）
  references/catalog/chain_audit.json 关联链路审计（只认 systems.json 的显式 chain_edges）
  references/catalog/role_groups.json 相似定位层（按核心定位判定，不是同队配合）
  references/catalog/full_audit.json  全量复查（复核队列，不是强度榜）
  references/catalog/editor_schema.json 前端可编辑字段的唯一注册表（含只读注册表与扩展位）
  references/catalog/source_markers.json 来源标记白名单（新增来源只改这里）
  data/seerapi/spirit_info.json        魂印/立绘/技能资料位（SeerAPI 已导入，status=ready）
  data/seerapi/spirit_media.json       SeerAPI 结构化资料层（魂印各版本/完整技能/图像路径）
  assets/seerapi/              SeerAPI 静态资源仓库下载的立绘/头像/图标（本地文件）
  HANDOVER.md                 自包含交接文档（新会话先读）
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
REF = os.path.join(ROOT, "references")


def _load(path, default):
    p = os.path.join(DATA, path) if not path.startswith("references/") else os.path.join(ROOT, path)
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def load_aliases():
    """Read exact aliases from references/docs/aliases.md without fuzzy matching."""
    path = os.path.join(REF, "aliases.md")
    aliases = {}
    if not os.path.exists(path):
        return aliases
    with open(path, encoding="utf-8") as file:
        for line in file:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            spirit_id = int(cells[0])
            alias_cell = cells[2]
            # Text before the first full-width semicolon is the explicit alias
            # list. Parentheses only annotate context or the kind of typo.
            candidates = alias_cell.split("；", 1)[0].split("、")
            # Several historical rows put an additional common typo after the
            # semicolon, e.g. "孤独灯使为常见误写".
            candidates += re.findall(r"([^；、]+?)为常见(?:误写|异写)", alias_cell)
            for alias in candidates:
                alias = re.sub(r"（[^）]*）\s*$", "", alias.strip()).strip()
                if alias and len(alias) <= 30:
                    aliases.setdefault(alias.casefold(), set()).add(spirit_id)
    return aliases


def load():
    pool = _load("bwiki/pool.json", {"elves": [], "dropped": []})
    overrides = _load("references/catalog/manual_overrides.json", {"spirits": []})
    roster = _load("references/catalog/roster.json", {"spirits": []})
    soul_doc = _load("seerapi/soul_full.json", {"souls": {}})
    by_id = {e["id"]: e for e in pool["elves"]}
    override_count = 0
    for item in overrides.get("spirits", []):
        if item["id"] not in by_id:
            by_id[item["id"]] = item
            override_count += 1
    skills = _load("seerapi/skills.json", {})
    elf_skills = _load("seerapi/elf_skills.json", {})
    systems = _load("references/catalog/systems.json", {"systems": []})
    strength = _load("references/catalog/strength.json", {"ratings": [], "policy": {}})
    chain = _load("references/catalog/chain_audit.json", {"items": [], "verified_pairs": []})
    return (list(by_id.values()), skills, elf_skills, pool.get("dropped", []),
            {x["id"]: x for x in roster.get("spirits", [])}, soul_doc.get("souls", {}),
            override_count, systems, strength, chain)


def soul_text(e, soul_full):
    entry = soul_full.get(str(e["id"]), {})
    text = entry.get("text") or ""
    if text:
        return text, "BWIKI 魂印全文"
    return str(e.get("soul", "")), "本地快照（全文待补）"


def show(e, skills, elf_skills, full, deep, soul_full, systems=None,
         strength=None, chain=None, roles=None, media=None):
    tier = e.get("tier_display") or e.get("tier", "—")
    extra = "｜人工深研回捞" if e.get("manual_override") else ("｜环境位" if e.get("meta") else "")
    print(f"\n#{e['id']} {e['name']}｜{e.get('attr','?')}系｜种族值 {e.get('total', 0)}｜"
          f"机制文本复杂度 {tier}（非强度）{extra}")
    strength = strength or {}
    rating = next((x for x in strength.get("ratings", []) if x.get("id") == e["id"]), None)
    if rating:
        print(f"  人工强度：{rating['grade']}｜{rating.get('season','')}｜{rating.get('status','')}")
        print(f"  依据：{rating.get('basis','')}｜来源：{'、'.join(rating.get('sources', []))}")
    else:
        print(f"  人工强度：{strength.get('policy', {}).get('unrated_default', '未评级（不推断）')}")
    if systems:
        belong = []
        for item in systems.get("systems", []):
            if e["id"] in item.get("core", []):
                belong.append(item["name"] + "（核心）")
            elif e["id"] in item.get("support", []):
                belong.append(item["name"] + "（补位）")
        if belong:
            print(f"  所属体系：{'、'.join(belong)}")
    role_hits = [g for g in (roles or {}).get("groups", []) if e["id"] in g.get("members", [])]
    if role_hits:
        print("  相似定位（共享同一特色机制位，不是同队配合）：")
        for g in role_hits:
            peers = [f"#{i}" for i in g["members"] if i != e["id"]]
            print(f"    {g['name']}［core_role {g.get('core_role', '?')}］｜同类位 {'、'.join(peers)}｜{g['relation'] if full else g['shared'][:70]}")
    st = e.get("stats") or {}
    if st and any(st.get(k) for k in ("体力", "攻击", "防御", "特攻", "特防", "速度")):
        print(f"  六维：体力{st.get('体力',0)} 攻击{st.get('攻击',0)} 防御{st.get('防御',0)} "
              f"特攻{st.get('特攻',0)} 特防{st.get('特防',0)} 速度{st.get('速度',0)}")
    else:
        print("  六维：原始快照未提供（不影响魂印与战术查询）")
    print(f"  标签：{' / '.join(e.get('tags') or []) or '—'}")
    text, src = soul_text(e, soul_full)
    formatted = re.sub(r"<br\s*/?>", "\n        ", text, flags=re.I)
    formatted = re.sub(r"\s*\n\s*", "\n        ", formatted)
    print(f"  魂印（{src}）：{formatted.strip() or '—'}")
    if media:
        row = (media.get("spirits") or {}).get(str(e["id"]))
        if row:
            imgs = row.get("images") or {}
            print("  SeerAPI 资料：魂印 %d 版（当前版 #%s）｜技能 %d 条｜立绘 %s｜完整资料 --media %s" % (
                len(row.get("soulmarks", [])),
                next((x.get("id") for x in row.get("soulmarks", []) if x.get("is_primary")), "—"),
                len(row.get("skills", [])), imgs.get("portrait") or "未取回", e["id"]))
    expansions = {x["id"]: x for x in
                  _load("references/catalog/soul_expansions.json", {"entries": []}).get("entries", [])}
    exp = expansions.get(e["id"])
    if exp:
        print(f"  状态补核（{exp.get('soul_page', 'BWIKI')}，魂印页只写状态名）：")
        lines = exp.get("verified_mechanics", [])
        for item in (lines if full else lines[:3]):
            print(f"    - {item}")
        if full:
            for item in exp.get("limits", []):
                print(f"    边界：{item}")
    if e.get("beats"):
        print(f"  克制：{'、'.join(e['beats'][:6])}")
    if e.get("weak_to"):
        print(f"  被克：{'、'.join(e['weak_to'][:6])}")
    if e.get("manual_override"):
        print(f"  自动筛选曾剔除：{e.get('override_reason','')} → 人工深研回捞，以人工结论为准")
    d = deep.get(e["id"])
    if d:
        print(f"  深研层：{d.get('status','')}｜定位分类 {' / '.join(d.get('classes', [])) or '未登记'}｜特色 {' / '.join(d.get('roles', []))}")
        print(f"  战术：{d.get('play','')}")
        if full:
            print(f"  机制：{'；'.join(d.get('mechanics', []))}")
            grades = {}
            for rec in (chain or {}).get("items", []):
                if rec.get("a") == e["id"]:
                    grades[rec.get("b")] = rec.get("group") + "／" + rec.get("grade", "")
            links = d.get("synergies", [])
            print(f"  已核联动：{len(links)} 条（synergies 只保留双向互证的已核顺序链）")
            for other in links:
                print(f"    #{other} {grades.get(other, '未审计')}")
            if not links:
                print("  暂无已核实同队联动；没有显式 chain_edges 就是没有关联，不拿骨架备选位凑数。")
            print(f"  来源：{d.get('sources', [])}")
        dd = d.get("deep_dive") or {}
        if full and dd:
            print("  深研六要素：")
            for key, label in (("conditions", "成立条件"), ("sequence", "逐回合顺序"),
                               ("resources", "资源"), ("bp_cost", "BP 成本"),
                               ("failure_points", "失效点"), ("replacement_check", "上位替代")):
                print(f"    {label}：{dd.get(key, '—')}")
    if full:
        ids = elf_skills.get(str(e["id"]), [])
        print("  技能：")
        shown = 0
        for sid in ids:
            s = skills.get(sid)
            if not s:
                continue
            eff = re.sub(r"<[^>]+>", "", str(s.get("effect", "")))[:70]
            print(f"    {s.get('name','')}｜{s.get('type','')}｜威力{s.get('power','')}｜"
                  f"PP{s.get('pp','')}｜先制{s.get('priority','')}｜{eff}")
            shown += 1
        if not shown:
            print("    （本地技能映射暂无；以游戏内/图鉴为准）")


def show_system(systems, keyword, names):
    """Look up a named 「XX 体系」 and print its members and evidence."""
    items = systems.get("systems", [])
    if not items:
        print("体系注册表为空或缺失：references/catalog/systems.json")
        return

    def label(spirit_id):
        return f"{spirit_id} {names.get(spirit_id, '')}".strip()

    if not keyword:
        print(f"已命名体系 {len(items)} 项（python query.py --system 名称 查详情）：")
        for item in items:
            print(f"  {item['name']}｜核心 {'/'.join(str(i) for i in item.get('core', []))}"
                  f"｜{item['kind']}｜{item.get('chain_status', item['status'])}"
                  f"｜证据 {item.get('evidence_grade', '—')}")
        return
    kw = keyword.casefold()
    hit = [item for item in items
           if kw in item["name"].casefold() or kw in item["key"].casefold()
           or any(kw in alias.casefold() for alias in item.get("aliases", []))
           or kw in item.get("evidence", "").casefold()]
    if not hit:
        print(f"没有匹配的体系：{keyword}（可用 --system 不带参数列出全部）")
        return
    for item in hit:
        print(f"\n【{item['name']}】｜{item['kind']}｜证据：{item['evidence']}｜状态：{item['status']}")
        print(f"  证据等级：{item.get('evidence_grade', '—')}｜链路状态：{item.get('chain_status', '—')}"
              f"｜{'成员按正文顺序链联动' if item.get('chain_status') == '顺序链已核' else '未核顺序链，禁止按成员名单两两配对'}")
        if item.get("aliases"):
            print(f"  别名：{'、'.join(item['aliases'])}")
        print(f"  核心：{'、'.join(label(i) for i in item.get('core', [])) or '—'}")
        if item.get("support"):
            print(f"  补位：{'、'.join(label(i) for i in item['support'])}")
        if item.get("counter"):
            print(f"  反向对位：{'、'.join(label(i) for i in item['counter'])}")
        print(f"  载体：{item.get('carrier', '')}")
        edges = item.get("chain_edges", [])
        if edges:
            print("  显式联动边：" + "；".join(f"{a}→{b} {label(a)} ⇒ {label(b)}" for a, b in edges))
        else:
            print("  显式联动边：无（成员名单不是联动；这只体系里没有可推荐的两两配合）")
        for slot_name, ids in (item.get("alternatives") or {}).items():
            print(f"  并列位·{slot_name}：{'、'.join(label(i) for i in ids)}（同一骨架按对局择一，不是同队配合，也不等于相似定位组）")
        print(f"  来源：{'、'.join(item.get('sources', [])) or '—'}")
        if item.get("external"):
            print(f"  范围外线索：{'；'.join(item['external'])}")
        print(f"  正文：references/docs/tactics.md → {item['section']}")


def show_role(roles, keyword, names, alias_ids=None):
    """Same-role lookup: identical PRIMARY core role, explicitly NOT a combo."""
    groups = roles.get("groups", [])
    if not groups:
        print("相似定位层为空或缺失：references/catalog/role_groups.json")
        return

    def label(spirit_id):
        return f"{spirit_id} {names.get(spirit_id, '')}".strip()

    if not keyword:
        print(f"相似定位 {len(groups)} 组（python query.py --role 名称 查详情）：")
        for g in groups:
            print(f"  {g['name']}｜core_role {g.get('core_role', '?')}｜{len(g['members'])} 只｜{'、'.join(label(i) for i in g['members'])}")
        print("口径：" + roles.get("rule", "相似定位不是同队联动"))
        return
    kw = keyword.casefold()
    hit = [g for g in groups
           if kw in g["name"].casefold() or kw in g.get("key", "").casefold()
           or any(kw in a.casefold() for a in g.get("aliases", []))
           or any(kw in names.get(i, "").casefold() or kw == str(i)
                  or i in (alias_ids or set())
                  for i in g.get("members", []))]
    if not hit:
        print(f"没有匹配的相似定位：{keyword}（可用 --role 不带参数列出全部）")
        return
    for g in hit:
        print(f"\n【{g['name']}】｜core_role：{g.get('core_role', '?')}｜证据：{g['evidence_grade']}｜同类位 {len(g['members'])} 只")
        print("  ★ 只按同一可辨识结算机制判定，不按能力清单；同类位通常择一，不是同队配合、不是反向对位、不是上位替代结论")
        print(f"  成员：{'、'.join(label(i) for i in g['members'])}")
        print(f"  共享机制：{g['shared']}")
        print("  逐只差异：")
        for line in g["differences"]:
            print(f"    - {line}")
        print(f"  边界：{g['relation']}")
        print(f"  来源：{'、'.join(g.get('sources', [])) or '—'}")
        print(f"  正文：references/docs/tactics.md → {roles.get('section', '相似定位（同类功能位，不是联动）')}")
        if g.get("user_hint"):
            print(f"  用户点名：{g['user_hint']}")


def show_media(media: dict, keyword: str):
    """SeerAPI 结构化资料层：只显示真正取回的文件与文本。"""
    spirits = media.get("spirits") or {}
    stats = media.get("stats") or {}
    if not keyword:
        print("SeerAPI 资料层 %d 只｜魂印版本 %d 条｜技能 %d 条｜图像 %d 张｜状态 %s" % (
            stats.get("spirits", len(spirits)), stats.get("soulmark_versions", 0),
            stats.get("skills", 0), stats.get("images", 0), media.get("status", "—")))
        print("数据源：%s｜静态资源：%s｜抓取 %s" % (
            media.get("source", {}).get("api", "—"),
            media.get("source", {}).get("asset_repo", "—"),
            media.get("source", {}).get("fetched_at", "—")))
        for key in sorted(spirits, key=lambda x: int(x))[:20]:
            row = spirits[key]
            print("  #%-5s %-14s 魂印 %d 版｜技能 %2d 条｜立绘 %s" % (
                key, row.get("name", ""), len(row.get("soulmarks", [])),
                len(row.get("skills", [])),
                "有" if (row.get("images") or {}).get("portrait") else "缺"))
        print("……用 python query.py --media 名称/序号 查单只完整资料；缺口见 references/catalog/spirit_media_report.json")
        return
    alias_ids = load_aliases().get(keyword.strip().casefold(), set())
    hits = [(k, v) for k, v in spirits.items()
            if keyword == k or keyword in str(v.get("name", "")) or int(k) in alias_ids]
    if not hits:
        print("SeerAPI 资料层没有这只精灵：%s（缺口见 references/catalog/spirit_media_report.json）" % keyword)
        return
    for key, row in sorted(hits, key=lambda x: int(x[0])):
        imgs = row.get("images") or {}
        print("\n#%s %s｜资源号 %s｜属性 %s｜SeerAPI 资料层（只读）" % (
            key, row.get("name", ""), row.get("resource_id"),
            (row.get("type") or {}).get("name", "—")))
        print("  API：%s｜图像：%s" % (row.get("api_url", "—"), media.get("asset_root", "")))
        for label, field in (("立绘", "portrait"), ("头像", "avatar"),
                             ("魂印图标", "soul_icon"), ("属性图标", "type_icon")):
            if imgs.get(field):
                print("  %s：%s" % (label, imgs[field]))
        for s in row.get("soulmarks", []):
            tag = "当前生效版" if s.get("is_primary") else "其它版本"
            print("  魂印 #%s［%s｜%s］：%s" % (
                s.get("id"), tag, s.get("source_field", "—"),
                (s.get("text") or "—").replace("\n", " / ")[:400]))
        for s in row.get("skills", []):
            flags = "".join(x for x, on in (("第五", s.get("is_fifth")),
                                            ("神谕", s.get("is_advanced")),
                                            ("特训", s.get("is_special"))) if on)
            # info 是战报描述，effects 才是实际生效的效果；两者不能互相顶替。
            eff = "；".join(str(x).strip() for x in (s.get("effects") or []) if str(x).strip())[:150]
            desc = str(s.get("info") or "").strip()[:120]
            print("    技能 %-12s｜%s·%s｜威力%-4s PP%-3s 先制%-3s %s｜效果：%s%s" % (
                s.get("name", ""), s.get("category", "—"), s.get("type", "—"),
                s.get("power", "—"), s.get("max_pp", "—"), s.get("priority", "—"),
                flags, eff or "—", ("｜战报：" + desc) if desc else ""))
    print("\n资料层只作机制与图像展示，不参与收录判断、强度分级或同队联动推导。")


def show_dropped(items, soul_full, deep, overrides):
    for item in items[:20]:
        eid = item.get("id")
        text = soul_full.get(str(eid), {}).get("text", "")
        label = "已人工回捞，可用 query 名称 --full 查完整战术" if eid in overrides or eid in deep else "仍为剔除记录，不直接推荐"
        print(f"\n#{eid} {item.get('name','')}｜自动剔除原因：{item.get('reason','')}")
        print(f"  状态：{label}")
        if text:
            print(f"  魂印全文（BWIKI，前 300 字）：{text[:300].replace(chr(10), ' ')}")
        else:
            print("  BWIKI 未检出魂印（符合「无魂印剔除」）")
    if len(items) > 20:
        print(f"\n……共 {len(items)} 条，已显示前 20 条。")


def main():
    args = sys.argv[1:]
    (elves, skills, elf_skills, dropped, deep, soul_full,
     override_count, systems, strength, chain) = load()
    kw = ""
    full = "--full" in args
    args = [a for a in args if a != "--full"]
    roles = _load("references/catalog/role_groups.json", {"groups": []})
    media = _load("seerapi/spirit_media.json", {"spirits": {}, "stats": {}, "source": {}})

    if "--media" in args:
        pos = args.index("--media")
        keyword = "".join(args[pos + 1:]).strip()
        show_media(media, keyword)
        return

    if "--strength" in args:
        pos = args.index("--strength")
        keyword = "".join(args[pos + 1:]).strip()
        ratings = strength.get("ratings", [])
        if keyword:
            alias_ids = load_aliases().get(keyword.casefold(), set())
            ratings = [x for x in ratings
                       if keyword in x.get("name", "") or keyword == str(x.get("id"))
                       or x.get("id") in alias_ids]
        print(f"人工强度评级 {len(ratings)} 只（已评 {len(strength.get('ratings', []))} 只）｜"
              f"机制复杂度偏差待复核 {strength.get('bias_review', {}).get('count', 0)} 只")
        print(f"口径：{strength.get('policy', {}).get('auto_score_definition', '—')}")
        for item in ratings:
            print(f"  #{item['id']} {item['name']}｜{item['grade']}｜{item.get('season','')}｜"
                  f"{item.get('basis','')}")
        if not ratings and keyword:
            print(f"  {keyword}：未评级（不推断），不得按机制复杂度推算 T 级。")
        members = strength.get("official_pool_members", [])
        if not keyword:
            print(f"  官方限制池逐只登记 {len(members)} 只（只证明 BP 成本与环境地位，不换算梯度）：")
            for m in members:
                print(f"    #{m['id']} {m['name']}｜{m['code']} {m['level']}｜{m['human_strength']}")
        print("未列者一律未评级（不推断）；自动评分只衡量机制文本复杂度，不是强度。")
        print(f"逐只依据与复核优先级见 {strength.get('full_review', {}).get('file', 'references/catalog/full_audit.json')}。")
        return

    if "--audit" in args:
        doc_path = os.path.join(REF, "full_audit.json")
        if not os.path.exists(doc_path):
            print("references/catalog/full_audit.json 不存在；先运行 python scripts/build_full_audit.py")
            return
        audit = json.load(open(doc_path, encoding="utf-8"))
        pos = args.index("--audit")
        keyword = "".join(args[pos + 1:]).strip()
        if not keyword:
            s = audit["stats"]
            print("全量复查：%d 只精灵／%d 项体系／%d 条链路｜已评级 %d 只｜冲突 %d 项" %
                  (s["spirits"], s["systems"], s["links"], s["rated"], s["conflicts"]))
            for k, v in s["priority_counts"].items():
                print(f"  {k}: {v}")
            for k, v in s["conflict_counts"].items():
                print(f"  冲突 {k}: {v}")
            for f in audit["findings"]:
                print(f"  [{f['status']}] {f['key']}: {f['action']}")
            return
        alias_ids = load_aliases().get(keyword.casefold(), set())
        hit = [x for x in audit["spirits"]
               if keyword in x["name"] or keyword == str(x["id"]) or x["id"] in alias_ids]
        for x in hit:
            print(f"\n#{x['id']} {x['name']}｜{x['main_layer']}｜"
                  f"机制复杂度 {x['complexity_tier']}（非强度）｜人工强度 {x['human_strength']}")
            print(f"  深研状态：{x['deep_status'] or '—'}｜完整战术链：{'是' if x['has_full_chain'] else '否'}"
                  f"｜战术说明 {x['play_chars']} 字")
            print(f"  证据：{'、'.join(x['evidence_flags']) or '无当季证据'}")
            print(f"  复核优先级：{x['review_priority']}")
            for c in x["conflicts"]:
                print(f"  冲突：{c}")
        if not hit:
            print(f"没有匹配的精灵：{keyword}")
        return

    if "--system" in args:
        pos = args.index("--system")
        keyword = "".join(args[pos + 1:]).strip()
        names = {e["id"]: e["name"] for e in elves}
        names.update({sid: item["name"] for sid, item in deep.items()})
        show_system(systems, keyword, names)
        return

    if "--role" in args:
        pos = args.index("--role")
        keyword = "".join(args[pos + 1:]).strip()
        names = {e["id"]: e["name"] for e in elves}
        names.update({sid: item["name"] for sid, item in deep.items()})
        alias_ids = load_aliases().get(keyword.casefold(), set()) if keyword else set()
        show_role(roles, keyword, names, alias_ids)
        return

    if "--dropped" in args:
        i = args.index("--dropped")
        kw = "".join(args[i + 1:]).strip()
        hit = [x for x in dropped if not kw or kw in str(x.get("name", "")) or kw == str(x.get("id"))]
        if not hit:
            print("剔除记录中没有匹配的精灵。")
        else:
            show_dropped(hit, soul_full, deep,
                         {x["id"] for x in _load("references/catalog/manual_overrides.json", {"spirits": []})["spirits"]})
        return

    if "--id" in args:
        want = args[args.index("--id") + 1]
        hit = [e for e in elves if str(e["id"]) == want]
    elif "--tag" in args:
        tags = args[args.index("--tag") + 1:]
        hit = [e for e in elves if all(t in (e.get("tags") or []) for t in tags)]
        hit.sort(key=lambda e: ("T0T1T2T3T4".index(str(e.get("tier", "T4"))[1]), -e.get("score", 0)))
    elif "--attr" in args:
        want = args[args.index("--attr") + 1]
        hit = [e for e in elves if str(e.get("attr", "")).startswith(want)]
        hit.sort(key=lambda e: -e.get("score", 0))
    elif "--tier" in args:
        lv = args[args.index("--tier") + 1:]
        hit = [e for e in elves if e.get("tier") in lv]
        hit.sort(key=lambda e: -e.get("score", 0))
    elif "--top" in args:
        n = int(args[args.index("--top") + 1])
        hit = sorted(elves, key=lambda e: -e.get("score", 0))[:n]
    elif args:
        kw = "".join(args)
        hit = [e for e in elves if kw in str(e.get("name", "")) or kw.lower() in str(e["id"])]
        if not hit:
            alias_ids = load_aliases().get(kw.strip().casefold(), set())
            hit = [e for e in elves if e["id"] in alias_ids]
        hit.sort(key=lambda e: -e.get("score", 0))
    else:
        print(__doc__)
        print(f"全量图鉴可用 {len(elves)} 只（含人工回捞 {override_count} 只）｜"
              f"历史筛选记录 {len(dropped)} 只｜深研战术层 {len(deep)} 只｜"
              f"BWIKI 魂印全文 {len(soul_full)} 条｜"
              f"已命名体系 {len(systems.get('systems', []))} 项｜"
              f"显式联动边 {len(chain.get('verified_directional_pairs', []))} 条｜"
              f"相似定位 {len(roles.get('groups', []))} 组｜"
              f"人工强度评级 {len(strength.get('ratings', []))} 只｜"
              f"SeerAPI 资料 {len(media.get('spirits', {}))} 只（--media 查魂印／技能／图像）｜"
              f"已核顺序链 {len(chain.get('verified_pairs', []))} 对")
        return

    if not hit:
        hint = [x for x in dropped if kw in str(x.get("name", ""))] if args else []
        print("可用图鉴层没有匹配的精灵。")
        if hint:
            print(f"但剔除记录中有 {len(hint)} 条：{[(x['id'], x['name'], x['reason']) for x in hint[:5]]}"
                  "；可用 --dropped 查看。")
        return
    for e in hit[:20]:
        show(e, skills, elf_skills, full, deep, soul_full, systems, strength, chain, roles, media)
    if len(hit) > 20:
        print(f"\n……共 {len(hit)} 条，已显示前 20 条。")


if __name__ == "__main__":
    main()

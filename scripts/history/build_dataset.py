#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛尔号巅峰之战 PVP 精灵库构建脚本

输入：data/bwiki/elves.json, data/bwiki/souls.json, data/bwiki/typeChart.lua
输出：data/bwiki/pool.json, data/derived/typechart.json
规则（F20261104 口径，与 references/docs/filtering.md 一致）：
  1) 只收序号 >= 2987 (2016 年费「重生之翼」起)
  2) 无魂印 -> 记录为待复核（不沿用自动结论作删除依据）
  3) 一代精灵王且存在二代 -> 形态规则剔除
  4) 同名族存在明显上位（种族值更高且机制覆盖）-> 只留上位
  5) 不再按「魂印条数」或「种族值」剔除：raw/souls.json 会把多段魂印截断，
     单条/多条不可判定；种族值也不等于 PvP 价值。两者只写入 auto_flags 留痕。
  6) 是否录入以 references/catalog/creator_index.json 中两位 UP 主的作品覆盖为准，
     见 scripts/apply_creator_filter.py。
"""
import sys as _legacy_sys
from pathlib import Path as _LegacyPath
_legacy_sys.path.insert(0, str(_LegacyPath(__file__).resolve().parent))
from legacy_guard import guard_legacy  # noqa: E402
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, 'data', 'raw')
DATA = os.path.join(ROOT, 'data')

MIN_ID = 2987
MIN_TOTAL = 680          # 低于此总能力值基本无 PVP 价值
STRONG_TOTAL = 700

# ---------------------------------------------------------------- 属性克制
def load_typechart():
    """从 wiki 模块:属性克制 的 Lua 里抽出单属性攻/防倍率表"""
    path = os.path.join(RAW, 'typeChart.lua')
    text = open(path, encoding='utf-8').read()
    chart = {}
    for m in re.finditer(r'\["([^"]{1,4})"\]\s*=\s*\{(.*?)\n    \}', text, re.S):
        attr, body = m.group(1), m.group(2)
        am = re.search(r'\["attack"\]\s*=\s*\{(.*?)\},', body, re.S)
        dm = re.search(r'\["defense"\]\s*=\s*\{(.*?)\}\s*$', body, re.S)
        if not (am and dm):
            continue
        def parse(block):
            out = {}
            for k, v in re.findall(r'\["([^"]+)"\]\s*=\s*([0-9.]+)', block):
                try:
                    out[k] = float(v)
                except ValueError:
                    pass
            return out
        chart[attr] = {'attack': parse(am.group(1)), 'defense': parse(dm.group(1))}
    return chart


def type_mult(chart, atk_attr, def_attr):
    """双属性按乘法叠乘；返回攻击方打防守方的倍率"""
    parts_a = [p for p in atk_attr.replace('·', '').replace('系', '').split(' ') if p] if atk_attr else []
    if '·' in atk_attr:
        parts_a = atk_attr.split('·')
    parts_d = def_attr.split('·') if '·' in def_attr else [def_attr]
    total = 1.0
    for a in parts_a:
        for d in parts_d:
            base = chart.get(a, {}).get('attack', {}).get(d)
            if base is None:
                base = 1.0
            total *= base
    return total


# ---------------------------------------------------------------- 魂印解析
CLAUSE_SPLIT = re.compile(r'[；;。\n]|<br\s*/?>')

TAGS = [
    # (标签, 正则, 权重)
    ('免控', r'免疫(所有)?异常|免疫.{0,6}异常状态|异常状态无效', 3.0),
    ('免疫弱化', r'免疫(所有)?能力下降|能力下降状态无效', 2.0),
    ('免红', r'受到的?(所有)?攻击伤害(减少|降低)|减免.{0,6}攻击伤害|攻击伤害减少', 3.0),
    ('免粉', r'免疫.{0,8}(固定伤害|百分比伤害)|不受.{0,4}(固定伤害|百分比伤害)', 3.0),
    ('弹固伤', r'反弹.{0,8}固定伤害|固定伤害.{0,4}反弹', 3.0),
    ('复活', r'复活', 3.5),
    ('复活队友', r'复活.{0,10}(背包|队友|出战)|被击败后.{0,10}复活', 2.5),
    ('续航', r'(恢复|回复).{0,10}体力', 2.0),
    ('吸血', r'(吸取|吸取对手|造成伤害.{0,6}恢复)', 2.0),
    ('先制', r'先制', 2.5),
    ('增伤', r'(伤害|威力)(提升|增加)|威力提升', 2.0),
    ('减伤', r'(受到|承受)的?伤害(减少|降低)|伤害减免', 2.0),
    ('斩杀', r'直接击败|击溃|秒杀|体力低于.{0,6}(击败|秒杀)', 3.0),
    ('清PP', r'PP', 2.0),
    ('消强', r'消除.{0,8}(能力提升|强化)|解除.{0,6}强化', 2.2),
    ('控场', r'害怕|麻痹|睡眠|中毒|烧伤|冻伤|冰冻|石化|混乱|疲惫|失明|诅咒|寄生', 2.2),
    ('驱逐', r'驱逐|换下|替换|送回', 3.0),
    ('护盾', r'护盾', 2.0),
    ('转伤', r'(转移|转化).{0,8}(伤害|体力)', 2.5),
    ('真伤', r'真实伤害', 2.5),
    ('死亡收益', r'(被击败|阵亡|离场)后', 2.5),
    ('层数成长', r'层(数|效果)|印记|标记|能量', 2.5),
    ('属性压制', r'全属性-1|全属性下降', 1.8),
    ('锁血', r'(体力|HP).{0,6}(不会|不再)(低于|下降)', 2.2),
    ('反伤', r'反弹|反伤', 2.0),
    ('命中/闪避', r'闪避|命中', 1.2),
    ('封属', r'无法使用属性技能|属性技能无效|封属', 2.5),
    ('封回血', r'(无法|不能).{0,6}恢复|回复效果.{0,4}(无效|反转)', 2.5),
]

CORE_TAGS = {'免控', '免红', '免粉', '复活', '复活队友', '斩杀', '驱逐', '控场',
             '免粉', '转伤', '真伤', '封属', '封回血', '锁血'}

# 一代精灵王（2015 首批，690/700 档）-> 有二代则剔除
FIRST_GEN_KINGS = {
    '凡尔斯': '飞行', '乔特鲁德': '龙', '米斯蒂克': '神秘', '沧岚': '水',
    '格劳瑞': '电', '莱茵哈特': '地面', '霍德尔': '暗影', '海瑟薇': '超能',
    '阿尔斯兰': '战斗', '茉蕊儿': '草', '欧德奈瑞': '普通', '莫妮卡': '自然',
    '列奥尼达': '远古', '马尔修斯': '机械', '奥佩娅': '虫', '格斯塔丝': '邪灵',
    '艾恩斯': '火', '斯嘉丽': '光', '柯尔德': '冰', '弗里德': '次元',
}
# 对应二代（存在则一代剔除）
SECOND_GEN = {
    # 仅收录「确有二代/更强形态」的属性；其余一代精灵王保留
    '龙': ['龙神哈莫', '战龙哈莫', '王之哈莫'],
    '神秘': ['神觉·米斯蒂克'],
    '电': ['怒雷神裁·雷伊', '王·雷伊'],
    '地面': ['王·卡修斯'],
    '暗影': ['混沌布莱克', '王·布莱克'],
    '超能': ['王·缪斯', '圣瞳缪斯'],
    '战斗': ['灭战神决·盖亚', '王·盖亚'],
    '火': ['不灭·艾恩斯'],
    '邪灵': ['万妖王·摩哥斯'],
}

# 环境强势手工校准（来源见 references/07-筛选口径.md）
META_TIER = {
    # 来源：2025-2026 年手游/页游公开强度榜（OSLink、233乐园、游侠等）+ 社区共识
    '光之惩戒·英卡洛斯': 'T0', '灭战神决·盖亚': 'T0', '怒雷神裁·雷伊': 'T0',
    '混沌魔君索伦森': 'T1', '天启帝君': 'T1', '圣王·萨格罗斯': 'T1',
    '混元天尊': 'T1', '王之哈莫': 'T1', '重生之翼': 'T1', '瀚宇星皇': 'T1',
    '万霆神律·雷伊': 'T1', '不灭战魂·盖亚': 'T1',
    '星辰万象·天启星魂': 'T2', '圣谕邪魇': 'T2', '空元行者': 'T2',
    '武心婵': 'T2', '帝天战佛': 'T2', '命运之轮·莫伊莱': 'T2',
    '星光·魔焰猩猩': 'T2', '星光·鲁斯王': 'T2', '星光·丽莎布布': 'T2',
    '王·雷伊': 'T2', '不灭·艾恩斯': 'T2', '弑序神罗': 'T2',
}

TIER_ORDER = ['T0', 'T1', 'T2', 'T3', 'T4']


def clauses(effect):
    parts = [p.strip() for p in CLAUSE_SPLIT.split(effect or '') if len(p.strip()) > 3]
    return parts


def tag_effect(effect):
    hits = []
    for name, pat, w in TAGS:
        if re.search(pat, effect or ''):
            hits.append(name)
    return hits


def stat_norm(total):
    return max(0.0, (total - MIN_TOTAL) / 5.0)


def score_elf(elf, soul):
    cl = clauses(soul['effect'])
    tags = tag_effect(soul['effect'])
    w = sum(t[2] for t in TAGS if t[0] in tags)
    s = stat_norm(elf['total']) + w + min(len(cl), 6) * 1.2
    # 越新越强（官方迭代倾向）
    s += max(0, (elf['id'] - MIN_ID) / 120.0)
    # 核心机制加权
    if len(CORE_TAGS & set(tags)) >= 3:
        s += 4
    # 单条魂印但有核心机制，仍可留
    if len(cl) <= 1 and not (CORE_TAGS & set(tags)):
        s -= 12
    return round(s, 1), tags, cl


def family_key(name):
    """去掉修饰前缀，取核心名：命运之轮·莫伊莱 -> 莫伊莱；怒雷神裁·雷伊 -> 雷伊"""
    return re.sub(r'[·・\s]', '', name)


def family_group(rows):
    """后缀归并：A 的核心名是 B 的后缀，则视为同一精灵族"""
    names = sorted({r['name'] for r in rows}, key=len, reverse=True)
    core = {n: family_key(n) for n in names}
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ca, cb = core[a], core[b]
            short, long_ = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
            if len(short) < 3:            # 过短的核心名容易误并（如「娅」「岚」）
                continue
            if len(short) / len(long_) < 0.5:
                continue
            if long_.endswith(short):
                union(a, b)
    groups = {}
    for r in rows:
        groups.setdefault(find(r['name']), []).append(r)
    return groups


def build():
    guard_legacy(__file__)
    chart = load_typechart()
    elves = {e['id']: e for e in json.load(open(os.path.join(RAW, 'elves.json'), encoding='utf-8'))}
    souls = json.load(open(os.path.join(RAW, 'souls.json'), encoding='utf-8'))
    byelf = {}
    for s in souls:
        for eid in s['elves']:
            byelf.setdefault(eid, []).append(s)

    names = {e['name'] for e in elves.values()}
    rows, dropped = [], []

    for eid, elf in sorted(elves.items()):
        if eid < MIN_ID:
            continue
        souls_e = byelf.get(eid)
        if not souls_e:
            dropped.append({'id': eid, 'name': elf['name'], 'reason': '无魂印'})
            continue
        soul = max(souls_e, key=lambda s: len(s['effect'] or ''))
        sc, tags, cl = score_elf(elf, soul)
        # F20261104: old auto drops based on stat total / soul-clause count are
        # void. Keep them only as informational flags; inclusion is decided by
        # creator-work coverage in apply_creator_filter.py.
        auto_flags = []
        if elf['total'] < MIN_TOTAL:
            auto_flags.append(f'低种族({elf["total"]})，旧规则已作废')
        if len(cl) <= 1 and not (CORE_TAGS & set(tags)):
            auto_flags.append('旧快照单条魂印（可能截断），旧规则已作废')
        if elf['name'] in FIRST_GEN_KINGS:
            sec = [n for n in SECOND_GEN.get(FIRST_GEN_KINGS[elf['name']], []) if n in names]
            why = f'一代精灵王，已有二代（{sec[0]}）' if sec else '一代精灵王，按规则不录入'
            dropped.append({'id': eid, 'name': elf['name'], 'reason': why})
            continue
        rows.append({
            'id': eid, 'name': elf['name'], 'attr': elf['attr'],
            'total': elf['total'], 'stats': elf['stats'],
            'intro': elf['intro'], 'series': elf.get('series',''),
            'skill_ids': elf.get('skills',''), 'soul': soul['effect'],
            'soul_id': soul['sid'], 'clauses': cl, 'tags': tags,
            'score': sc, 'auto_flags': auto_flags,
        })

    # ---- 同名族上位替代合并
    groups = family_group(rows)
    keep = []
    for key, group in groups.items():
        group.sort(key=lambda r: (-r['total'], -r['id']))
        top = group[0]
        keep.append(top)
        for r in group[1:]:
            if r['name'] in META_TIER:          # 明确的环境成员，机制不可替代
                keep.append(r)
                continue
            cover = len(set(r['tags']) & set(top['tags'])) / max(1, len(set(r['tags'])))
            if cover < 0.55 and r['total'] >= top['total'] - 40:
                keep.append(r)
            else:
                dropped.append({'id': r['id'], 'name': r['name'],
                                'reason': f'同名上位替代（{top["name"]}）'})

    # ---- 分层：环境榜 > 自动初评
    keep.sort(key=lambda r: -r['score'])
    n = len(keep)
    for i, r in enumerate(keep):
        p = i / max(1, n - 1)
        r['auto_tier'] = ('T0' if p < 0.03 else 'T1' if p < 0.12 else
                          'T2' if p < 0.30 else 'T3' if p < 0.60 else 'T4')
        r['tier'] = r['auto_tier']
    for r in keep:
        if r['name'] in META_TIER:
            r['tier'] = META_TIER[r['name']]
            r['meta'] = True
        else:
            r['meta'] = False

    # 环境榜 T0 名额有限，自动初评的 T0 降为 T1，避免误读
    for r in keep:
        if not r['meta'] and r['tier'] == 'T0':
            r['tier'] = 'T1'

    # ---- 对位信息（克制面/被克制面）
    for r in keep:
        atk, dfd = [], []
        for other in keep:
            m = type_mult(chart, r['attr'], other['attr'])
            if m >= 1.5:
                atk.append(other['name'])
            m2 = type_mult(chart, other['attr'], r['attr'])
            if m2 >= 1.5:
                dfd.append(other['name'])
        r['beats'] = atk[:12]
        r['weak_to'] = dfd[:12]

    keep.sort(key=lambda r: (TIER_ORDER.index(r['tier']), -r['score']))
    pool = {
        'meta': {'built_from': 'wiki.biligame.com/seer', 'min_id': MIN_ID,
                 'rules': ['无魂印记录待复核', '一代精灵王(有二代)剔除', '同名族上位替代合并'],
                 'voided_rules_F20261104': ['种族值<680剔除', '单条魂印无核心机制剔除'],
                 'inclusion_standard': 'references/catalog/creator_index.json 中两位 UP 主是否出过配置/攻略作品；见 scripts/apply_creator_filter.py'},
        'elves': keep,
        'dropped': dropped,
    }
    os.makedirs(DATA, exist_ok=True)
    json.dump(pool, open(os.path.join(DATA, 'bwiki/pool.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(chart, open(os.path.join(DATA, 'derived/typechart.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    from collections import Counter
    print('收录', len(keep), '剔除', len(dropped))
    print('分层', Counter(r['tier'] for r in keep))
    print('剔除原因', Counter(d['reason'].split('（')[0] for d in dropped))
    return pool


if __name__ == '__main__':
    build()

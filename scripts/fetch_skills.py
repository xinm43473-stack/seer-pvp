#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取指定精灵的技能详情，写入 data/seerapi/skills.json
用法: python fetch_skills.py [--tier T0 T1] [--limit N]
"""
import json, os, sys, time, re, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
API = 'https://wiki.biligame.com/seer/api.php'


def api(params, retry=4):
    params['format'] = 'json'
    url = API + '?' + urllib.parse.urlencode(params)
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research)'})
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception:
            if i == retry - 1:
                raise
            time.sleep(1.5 * (i + 1))


def parse_tpl(text):
    out = {}
    for m in re.finditer(r'\|([^=|{}\n]+)=([^|{}\n]*)', text):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def main():
    tiers = ['T0', 'T1']
    if '--tier' in sys.argv:
        i = sys.argv.index('--tier')
        tiers = sys.argv[i + 1:]
    pool = json.load(open(os.path.join(DATA, 'bwiki/pool.json'), encoding='utf-8'))
    if '--names' in sys.argv:
        i = sys.argv.index('--names')
        want = set(sys.argv[i + 1:])
        target = [e for e in pool['elves'] if e['name'] in want]
    else:
        target = [e for e in pool['elves'] if e['tier'] in tiers]
    if '--limit' in sys.argv:
        target = target[:int(sys.argv[sys.argv.index('--limit') + 1])]

    elf_skills = {}
    all_ids = []
    for e in target:
        ids = []
        for chunk in (e.get('skill_ids') or '').split(';'):
            chunk = chunk.strip()
            if not chunk:
                continue
            sid = chunk.split('-')[0]
            if sid.isdigit():
                ids.append(sid)
        elf_skills[e['id']] = ids
        all_ids += ids
    all_ids = sorted(set(all_ids), key=int)
    print(f'精灵 {len(target)} 只，技能 {len(all_ids)} 个', file=sys.stderr)

    skills = {}
    if os.path.exists(os.path.join(DATA, 'seerapi/skills.json')):
        skills = json.load(open(os.path.join(DATA, 'seerapi/skills.json'), encoding='utf-8'))
    todo = [i for i in all_ids if i not in skills]
    for i in range(0, len(todo), 10):
        titles = '|'.join(f'技能:{n}' for n in todo[i:i + 10])
        try:
            d = api({'action': 'query', 'prop': 'revisions', 'rvprop': 'content',
                     'rvslots': 'main', 'titles': titles, 'redirects': '1'})
        except Exception as ex:
            sys.stderr.write('\nFAIL %d: %s\n' % (i, ex))
            time.sleep(3)
            continue
        for p in d['query']['pages'].values():
            if 'revisions' not in p:
                continue
            d2 = parse_tpl(p['revisions'][0]['slots']['main']['*'])
            sid = d2.get('技能序号')
            if not sid:
                continue
            skills[sid] = {
                'name': d2.get('技能名称', ''),
                'type': d2.get('技能类型', ''),
                'attr': d2.get('技能属性', ''),
                'power': d2.get('威力', ''),
                'pp': d2.get('次数', ''),
                'priority': d2.get('先制', ''),
                'effect': d2.get('技能效果', ''),
            }
        sys.stderr.write('\r技能 %d/%d' % (min(i + 10, len(todo)), len(todo)))
        sys.stderr.flush()
        time.sleep(0.5)
        if i % 50 == 0:
            json.dump(skills, open(os.path.join(DATA, 'seerapi/skills.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)
    print()
    json.dump(skills, open(os.path.join(DATA, 'seerapi/skills.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    esp = os.path.join(DATA, 'seerapi/elf_skills.json')
    merged = {}
    if os.path.exists(esp):
        merged = json.load(open(esp, encoding='utf-8'))
    merged.update(elf_skills)
    json.dump(merged, open(esp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'技能总数 {len(skills)}')


if __name__ == '__main__':
    main()

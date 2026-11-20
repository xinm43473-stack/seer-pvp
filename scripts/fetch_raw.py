"""赛尔号 WIKI 批量抓取精灵与魂印原始数据

用法: python fetch_raw.py elves 4950 && python fetch_raw.py souls 4950
输出: data/bwiki/elves.json, data/bwiki/souls.json
"""
import urllib.request, urllib.parse, json, re, os, sys, time

API = 'https://wiki.biligame.com/seer/api.php'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'raw')
OUT = os.path.abspath(OUT)


def api(params, retry=3):
    params['format'] = 'json'
    url = API + '?' + urllib.parse.urlencode(params)
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research)'})
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception as e:
            if i == retry - 1:
                raise
            time.sleep(1.5 * (i + 1))


def fetch_batch(prefix, ids, chunk=25):
    """返回 {title: wikitext}"""
    out = {}
    for i in range(0, len(ids), chunk):
        titles = '|'.join(f'{prefix}:{n}' for n in ids[i:i + chunk])
        try:
            d = api({'action': 'query', 'prop': 'revisions', 'rvprop': 'content',
                     'rvslots': 'main', 'titles': titles, 'redirects': '1'}, retry=5)
        except Exception as e:
            sys.stderr.write(f'\nBATCH FAIL {i}: {e}\n')
            continue
        for p in d['query']['pages'].values():
            if 'missing' in p or 'revisions' not in p:
                continue
            try:
                out[p['title']] = p['revisions'][0]['slots']['main']['*']
            except Exception:
                pass
        sys.stderr.write(f'\r{prefix} {i + len(ids[i:i + chunk])}/{len(ids)}')
        sys.stderr.flush()
        time.sleep(0.35)
    print()
    return out


def parse_template(text):
    """把 {{模板|k=v|...}} 解析成 dict"""
    res = {}
    for m in re.finditer(r'\|([^=|{}\n]+)=([^|{}\n]*)', text):
        res[m.group(1).strip()] = m.group(2).strip()
    return res


def parse_elves(pages):
    data = []
    for title, text in pages.items():
        if '{{精灵' not in text:
            continue
        d = parse_template(text)
        try:
            eid = int(d.get('ID') or title.split(':')[1])
        except Exception:
            continue
        stats = {}
        for k in ('体力', '攻击', '防御', '特攻', '特防', '速度'):
            try:
                stats[k] = int(d.get(k) or 0)
            except Exception:
                stats[k] = 0
        data.append({
            'id': eid,
            'name': d.get('名称', ''),
            'attr': d.get('属性', ''),
            'gender': d.get('性别', ''),
            'series': d.get('系列名称', ''),
            'intro': d.get('介绍', ''),
            'stats': stats,
            'total': sum(stats.values()),
            'skills': d.get('技能', ''),
            'status': d.get('状态', ''),
        })
    data.sort(key=lambda x: x['id'])
    return data


def parse_souls(pages):
    data = []
    for title, text in pages.items():
        if '{{魂印' not in text:
            continue
        d = parse_template(text)
        try:
            sid = int(d.get('魂印ID') or title.split(':')[1])
        except Exception:
            continue
        rel = d.get('相关精灵', '')
        elf_ids = [int(x) for x in re.findall(r'\d+', rel)]
        data.append({
            'sid': sid,
            'elves': elf_ids,
            'effect': re.sub(r'\s+', ' ', d.get('魂印效果', '')),
            'kind': d.get('kind', ''),
        })
    data.sort(key=lambda x: x['sid'])
    return data


def main():
    mode = sys.argv[1]
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 4950
    os.makedirs(OUT, exist_ok=True)
    ids = list(range(1, hi + 1))
    pages = fetch_batch('精灵' if mode == 'elves' else '魂印', ids)
    data = parse_elves(pages) if mode == 'elves' else parse_souls(pages)
    name = 'elves.json' if mode == 'elves' else 'souls.json'
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f'{mode}: {len(data)} -> {path}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""热榜聚合:DailyHotApi(本机 6688)→ 去重合并 Top N

用法: python3 scripts/hotlist.py [--n 20] [--sources douyin,weibo,zhihu,baidu,toutiao]
"""
import argparse
import json
import urllib.request
from collections import defaultdict

BASE = 'http://127.0.0.1:6688'


def fetch(source, timeout=25):
    try:
        with urllib.request.urlopen(f'{BASE}/{source}', timeout=timeout) as r:
            d = json.loads(r.read())
            return [(source, item.get('title', ''), item.get('hot', '') or item.get('desc', ''))
                    for item in (d.get('data') or [])]
    except Exception as e:
        print(f'# {source} 拉取失败: {e}', flush=True)
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20)
    ap.add_argument('--sources', default='douyin,weibo,zhihu,baidu,toutiao')
    args = ap.parse_args()
    seen, rows = {}, []
    for src in args.sources.split(','):
        for source, title, hot in fetch(src.strip()):
            key = title[:18]
            if key in seen:
                seen[key][1] += 1          # 多平台同现,热度信号+
                continue
            seen[key] = [title, 1, source, hot]
            rows.append(seen[key])
    rows.sort(key=lambda x: -x[1])
    for title, hits, source, hot in rows[:args.n]:
        multi = f' ★{hits}平台同现' if hits > 1 else ''
        print(f'[{source}]{multi} {title}')


if __name__ == '__main__':
    main()

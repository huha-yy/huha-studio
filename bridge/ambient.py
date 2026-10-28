#!/usr/bin/env python3
"""闲逛导演:流水线空闲时,让小人们自由活动(串门/开会/表情)

空闲判定:所有任务没有 running 阶段。忙时退场,不和工作动画打架。
用法: python3 bridge/ambient.py [--min 40] [--max 90]
"""
import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
CFG = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['pixoffice']
BASE = CFG['base_url']
KEY = os.environ.get(CFG.get('api_key_env', 'PIXOFFICE_API_KEY'), 'pixoffice-demo-key')

ACTORS = {
    'studio-creative': ['office-lead', 'data-agent', 'app-agent', 'file-agent', 'code-agent'],
    'studio-post': ['office-lead', 'data-agent', 'code-agent', 'review-agent'],
}

VISIT_LINES = [
    ('今天热榜还有什么能蹭的?', '我这边盯着呢,一有新梗就喊你。'),
    ('那条片的BGM会不会太吵?', '有道理,我压到负18dB以下。'),
    ('选题会要不要提前?', '等策划那边三选一出来就开。'),
    ('你上次说的钩子妙啊', '嘿嘿,刷了两百条对标总结出来的。'),
    ('喝咖啡不?', '来一杯,顺便看看数据。'),
    ('下一条想试新风格', '库里有59种,随便挑。'),
    ('字幕字体再大点?', '收到,下次改成粗体大号。'),
    ('审片结论出来没?', '出了,三条改进建议,都挺专业。'),
    ('咱们一天能出几条?', '全速的话,一条一小时。'),
    ('有点想念生成式那条路线', '慢是慢,写实感确实没得比。'),
]
MEETING_LINES = [
    '碰个头,聊聊下一条选题',
    '复盘一下上一条的完播率',
    '对一下本週的产量目标',
    '讨论下新风格的尝试',
    '同步一下热榜的变化',
]
EMOTES = ['emotes/wave', 'emotes/thinking', 'emotes/surprised']


def post(data, timeout=15):
    req = urllib.request.Request(BASE.rstrip('/') + '/api/pixoffice/messages',
                                 data=json.dumps(data).encode(),
                                 headers={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'code': e.code, 'msg': e.read().decode()[:150]}


def idle():
    if not RUNS.exists():
        return True
    for d in RUNS.iterdir():
        f = d / 'state.json'
        if not f.exists() or not d.name[:1].isdigit():
            continue
        st = json.loads(f.read_text())
        if any(s['status'] == 'running' for s in st['stages'].values()):
            return False
    return True


def cmd(team, capability, participants, params):
    return post({'teamId': team, 'command': {
        'protocolVersion': '2.0', 'sceneId': team, 'commandId': f'ambient-{uuid.uuid4().hex[:8]}',
        'type': 'activity.start', 'capability': capability,
        'participants': participants, 'params': params}})


def act(team):
    actors = ACTORS[team]
    roll = random.random()
    if roll < 0.50:                                 # 串门
        visitor = random.choice(actors)
        hosts = [a for a in actors if a != visitor]
        random.shuffle(hosts)
        stops = []
        for h in hosts[:random.choice((1, 1, 2))]:
            msg, reply = random.choice(VISIT_LINES)
            stops.append({'hostId': h, 'message': msg, 'reply': reply})
        r = cmd(team, 'office.visit',
                [{'entityId': visitor, 'role': 'visitor'}] +
                [{'entityId': s['hostId'], 'role': 'host'} for s in stops],
                {'stops': stops, 'durationMs': 3000})
        return f'visit:{visitor[:12]}→{len(stops)}站 {r.get("code")}'
    if roll < 0.35:                                 # 围桌小会(坐着开)
        crowd = random.sample([a for a in actors if a != 'office-lead'],
                              k=random.choice((1, 2)))
        r = cmd(team, 'office.table-meeting',
                [{'entityId': 'office-lead', 'role': 'speaker'}] +
                [{'entityId': a, 'role': 'attendee'} for a in crowd],
                {'tableId': 'conference-table-1', 'text': random.choice(MEETING_LINES),
                 'durationMs': 15000})
        return f'table-meeting×{len(crowd) + 1} {r.get("code")}'
    if roll < 0.70:                                 # 白板小会(站着开)
        crowd = random.sample([a for a in actors if a != 'office-lead'],
                               k=min(2, len(actors) - 1))
        r = cmd(team, 'office.meeting',
                [{'entityId': 'office-lead', 'role': 'speaker'}] +
                [{'entityId': a, 'role': 'attendee'} for a in crowd],
                {'boardId': 'office.wall-whiteboard', 'text': random.choice(MEETING_LINES),
                 'durationMs': 12000})
        return f'meeting×{len(crowd) + 1} {r.get("code")}'
    # 表情
    who = random.choice(actors)
    r = cmd(team, 'office.emote', [{'entityId': who, 'role': 'actor'}],
            {'animation': random.choice(EMOTES), 'durationMs': 3500})
    return f'emote:{who[:12]} {r.get("code")}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min', type=int, default=40)
    ap.add_argument('--max', type=int, default=90)
    args = ap.parse_args()
    print(f'闲逛导演启动:空闲时每 {args.min}-{args.max}s 一幕', flush=True)
    while True:
        try:
            if idle():
                for team in ACTORS:
                    what = act(team)
                    print(f"[{time.strftime('%H:%M:%S')}] {team.split('-')[1]} {what}", flush=True)
                    time.sleep(random.uniform(3, 8))   # 两办公室错开
            else:
                time.sleep(10)                          # 忙时退场
        except Exception as e:
            print(f'异常:{e}', flush=True)
            time.sleep(15)
        time.sleep(random.uniform(args.min, args.max))


if __name__ == '__main__':
    main()

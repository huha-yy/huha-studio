#!/usr/bin/env python3
"""PixOffice 桥接 · watch:流水线状态 → 办公室画面

常驻进程,轮询 runs/*/state.json,变化即推送 office.snapshot;
阶段开始/完成/失败时给对应小人发 scene.say 气泡。
设计见 docs/pixoffice-bridge-design.md。

用法: python3 bridge/watch.py [--interval 3] [--dry]
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'
CFG = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['pixoffice']
BASE = CFG['base_url']
KEY = os.environ.get(CFG.get('api_key_env', 'PIXOFFICE_API_KEY'), 'pixoffice-demo-key')

# agent → (办公室, 人物);办公室定义见 docs/architecture.md
OFFICES = {
    'studio-creative': {'name': '创意中心', 'agents': {
        'planner': ('选题策划', 'data-agent'), 'screenwriter': ('编剧', 'app-agent'),
        'designer': ('设计师', 'file-agent'), 'videogen': ('视频制作', 'code-agent')}},
    'studio-post': {'name': '后期车间', 'agents': {
        'voice': ('配音', 'data-agent'), 'editor': ('剪辑', 'code-agent'),
        'reviewer': ('质控', 'review-agent')}},
}
STAGE_TO_AGENT = {'brief': 'planner', 'script': 'screenwriter', 'design': 'designer',
                  'video': 'videogen', 'voice': 'voice', 'edit': 'editor', 'review': 'reviewer'}
TASK_STATUS = {'pending': 'queued', 'running': 'running', 'failed': 'blocked', 'done': 'completed'}
OFFICE_OF = {a: oid for oid, o in OFFICES.items() for a in o['agents']}
QUOTES = {
    'running': {'planner': '在看选题库,找今天能爆的…', 'screenwriter': '写口播稿,先把钩子磨尖…',
                'designer': '出封面方案,定视觉基调…', 'videogen': '分镜生成中,一条条来…',
                'voice': '录音中,注意语速和情绪…', 'editor': '合成时间线,对齐字幕…',
                'reviewer': '逐项过检查清单…'},
    'done': {'planner': '选题定了!', 'screenwriter': '剧本交了!', 'designer': '封面和首帧齐了!',
             'videogen': '镜头全部产出!', 'voice': '配音完成!', 'editor': '成片出炉!',
             'reviewer': '审核完毕,等老板拍板。'},
    'failed': None,
}


def post(data, timeout=15):
    req = urllib.request.Request(BASE.rstrip('/') + '/api/pixoffice/messages',
                                 data=json.dumps(data).encode(),
                                 headers={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'code': e.code, 'msg': e.read().decode()[:200]}


def say(team, actor, text):
    import uuid
    r = post({'teamId': team, 'command': {
        'protocolVersion': '2.0', 'sceneId': team, 'commandId': str(uuid.uuid4()),
        'type': 'activity.start', 'capability': 'scene.say',
        'participants': [{'entityId': actor, 'role': 'actor'}],
        'params': {'text': text, 'durationMs': 6000}}})
    return r.get('code')


def collect():
    """runs/* → 两办公室快照数据 + 每任务阶段状态(事件用)。"""
    snapshots = {}
    events_seen = set()
    tasks_state = {}
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        f = d / 'state.json'
        if not f.exists():
            continue
        st = json.loads(f.read_text())
        tasks_state[st['task_id']] = st['stages']
        for oid, spec in OFFICES.items():
            snap = snapshots.setdefault(oid, {
                'employees': [{'id': a, 'name': n, 'role': n, 'sceneActorId': actor, 'online': True}
                              for a, (n, actor) in spec['agents'].items()],
                'tasks': [], 'events': []})
            done = sum(1 for s in st['stages'].values() if s['status'] == 'done')
            total = len(st['stages'])
            snap['tasks'].append({
                'id': f"{st['task_id']}-{oid}", 'title': st['topic'][:40],
                'assigneeId': 'planner' if oid == 'studio-creative' else 'voice',
                'status': 'running' if done < total else 'completed',
                'progress': int(done * 100 / total), 'summary': f"{done}/{total} 阶段完成",
                'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%S.000Z')})
            for sid, s in st['stages'].items():
                agent = STAGE_TO_AGENT.get(sid)
                if not agent or OFFICE_OF.get(agent) != oid:
                    continue
                snap['tasks'].append({
                    'id': f"{st['task_id']}-{sid}", 'title': sid, 'assigneeId': agent,
                    'status': TASK_STATUS.get(s['status'], 'queued'), 'progress': -1,
                    'summary': '', 'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%S.000Z')})
    return snapshots, tasks_state


def build(oid, snap, seq):
    spec = OFFICES[oid]
    total_done = sum(1 for t in snap['tasks'] if t['status'] == 'completed')
    return {
        'schemaVersion': '1.0', 'seq': seq,
        'workspace': {'id': oid, 'name': spec['name']},
        'conversations': [{
            'id': 'main', 'title': '内容流水线',
            'whiteboard': {'template': 'task-board-v1', 'title': '短视频流水线',
                           'status': 'running',
                           'description': '选题 → 剧本 → 视觉 → 视频 → 配音 → 合成 → 审核',
                           'steps': [
                               {'id': 'creative', 'title': '创意(选题/剧本)',
                                'progress': _stage_progress(snap, ('brief', 'script'))},
                               {'id': 'visual', 'title': '视觉/视频',
                                'progress': _stage_progress(snap, ('design', 'video'))},
                               {'id': 'post', 'title': '配音/合成/审核',
                                'progress': _stage_progress(snap, ('voice', 'edit', 'review'))}]},
            'employees': snap['employees'], 'tasks': snap['tasks'][:40], 'events': []}],
    }


def _stage_progress(snap, stages):
    ts = [t for t in snap['tasks'] for s in stages if t['id'].endswith(f'-{s}')]
    if not ts:
        return 0
    score = sum({'completed': 100, 'running': 50, 'blocked': 0, 'queued': 0}.get(t['status'], 0)
                for t in ts) / len(ts)
    return int(score)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=int, default=CFG.get('watch_interval', 3))
    ap.add_argument('--dry', action='store_true', help='只打印不推送')
    args = ap.parse_args()
    last_hash, seqs, last_stages = None, {}, {}
    print(f'watch 启动:轮询 {RUNS},推送 {BASE}')
    while True:
        try:
            snaps, tasks_state = collect()
            h = json.dumps(snaps, sort_keys=True, ensure_ascii=False).__hash__()
            # 事件:阶段状态变化 → 气泡
            for tid, stages in tasks_state.items():
                for sid, s in stages.items():
                    key = (tid, sid, s['status'])
                    if key in last_stages.get(tid, set()):
                        continue
                    last_stages.setdefault(tid, set()).add(key)
                    agent = STAGE_TO_AGENT.get(sid)
                    quote = (QUOTES.get(s['status']) or {}).get(agent)
                    if quote and agent in OFFICE_OF and not args.dry:
                        office, actor = OFFICE_OF[agent], OFFICES[OFFICE_OF[agent]]['agents'][agent][1]
                        say(office, actor, quote)
            if h != last_hash:
                for oid, snap in snaps.items():
                    seqs[oid] = seqs.get(oid, 0) + 1
                    if args.dry:
                        print(f'[dry] {oid} seq={seqs[oid]} 任务{len(snap["tasks"])}')
                        continue
                    first = seqs[oid] == 1
                    body = ({'type': 'offices.initialize', 'offices': [build(oid, snap, seqs[oid])]}
                            if first else
                            {'type': 'office.snapshot', 'teamId': oid, 'snapshot': build(oid, snap, seqs[oid])})
                    r = post(body)
                    print(f'[{time.strftime("%H:%M:%S")}] {oid} seq={seqs[oid]} → {r.get("code")} '
                          f'{r.get("msg", "")[:40]}')
                last_hash = h
        except Exception as e:
            print(f'[{time.strftime("%H:%M:%S")}] {e}', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()

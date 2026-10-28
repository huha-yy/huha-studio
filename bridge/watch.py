#!/usr/bin/env python3
"""PixOffice 桥接 · watch:流水线状态 → 办公室画面

核心模型:**每条视频 = 一个会话**(conversation),双办公室各挂同一会话;
白板=该片进度,完成时白板挂成片链接;review 完成自动把审片报告注入会话聊天。

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
RUNS_SERVER = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text()).get('runs_server',
                                                                                'http://192.168.10.247:8899')
CHAT_SERVER = 'http://127.0.0.1:8789'

OFFICES = {
    'studio-creative': {'name': '创意中心', 'agents': {
        'planner': ('选题策划', 'data-agent'), 'screenwriter': ('编剧', 'app-agent'),
        'designer': ('设计师', 'file-agent'), 'videogen': ('视频制作', 'code-agent'),
        'ops': ('运营负责人', 'office-lead')}},
    'studio-post': {'name': '后期车间', 'agents': {
        'voice': ('配音', 'data-agent'), 'editor': ('剪辑', 'code-agent'),
        'reviewer': ('质控', 'review-agent'), 'ops': ('运营负责人', 'office-lead')}},
}
STAGE_TO_AGENT = {'brief': 'planner', 'script': 'screenwriter', 'design': 'designer',
                  'video': 'videogen', 'voice': 'voice', 'edit': 'editor', 'review': 'reviewer'}
TASK_STATUS = {'pending': 'queued', 'running': 'running', 'failed': 'blocked', 'done': 'completed'}
OFFICE_OF = {a: oid for oid, o in OFFICES.items() for a in o['agents']}
QUOTES = {
    'running': {'planner': '在看选题库,找今天能爆的…', 'screenwriter': '写口播稿,先把钩子磨尖…',
                'designer': '出封面方案,定视觉基调…', 'videogen': '分镜渲染中,一条条来…',
                'voice': '录音中,注意语速和情绪…', 'editor': '合成时间线,对齐字幕…',
                'reviewer': '逐项过检查清单…'},
    'done': {'planner': '选题定了!', 'screenwriter': '剧本交了!', 'designer': '封面和首帧齐了!',
             'videogen': '镜头全部产出!', 'voice': '配音完成!', 'editor': '成片出炉!',
             'reviewer': '审核完毕,等老板拍板。'},
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


def _stable_time(f):
    import datetime
    return datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def collect():
    """runs/* → {task_id: {task_dir, topic, stages, final_url}} + 阶段状态表。"""
    tasks, tasks_state = {}, {}
    if not RUNS.exists():
        return tasks, tasks_state
    for d in sorted(RUNS.iterdir()):
        f = d / 'state.json'
        if not f.exists() or not d.name[:1].isdigit():
            continue
        st = json.loads(f.read_text())
        final = d / '06-edit' / 'final.mp4'
        tasks[st['task_id']] = {
            'dir': d, 'topic': st['topic'], 'stages': st['stages'],
            'final': str(final) if final.exists() else '',
            'mtime': _stable_time(f)}
        tasks_state[st['task_id']] = st['stages']
    return tasks, tasks_state


def _insights_for(agent, all_tasks):
    """从全部任务状态聚合该岗位的统计(完成数/成本/时长/近期活动)。"""
    import datetime
    sid = STAGE_TO_AGENT.get(agent)
    done_n = cost = dur = 0.0
    acts = []
    for tid, t in all_tasks.items():
        st = t['stages'].get(sid)
        if not st:
            continue
        if st['status'] == 'done':
            done_n += 1
            cost += st.get('cost_usd') or 0
            dur += st.get('duration') or 0
        acts.append({'label': f"{t['topic'][:16]}·{sid}",
                     'occurredAt': datetime.datetime.fromtimestamp(
                         (t['dir'] / 'state.json').stat().st_mtime).astimezone().isoformat(),
                     'status': {'done': 'completed', 'running': 'running',
                                'failed': 'blocked', 'pending': 'running'}.get(st['status'], 'running')})
    acts = acts[-5:]
    return {'scope': 'conversation',
            'updatedAt': datetime.datetime.now().astimezone().isoformat(),
            'periods': [{'id': 'last7Days', 'label': '近7天',
                         'metrics': [
                             {'id': 'stages', 'label': '完成阶段', 'value': done_n, 'unit': '个'},
                             {'id': 'cost', 'label': '累计成本', 'value': round(cost, 2), 'unit': '美元',
                              'sentiment': 'positive' if cost < 2 else 'neutral'},
                             {'id': 'mins', 'label': '累计工时', 'value': round(dur / 60, 1), 'unit': '分'}],
                         'blocks': ([{'id': 'recent', 'type': 'activity', 'title': '近期工作', 'items': acts}] if acts else [])}]}


def _lifecycle(stages):
    """completed=全部done;aborted=无pending/running但有failed;active=其余。"""
    vals = [v['status'] for v in stages.values()]
    if all(v == 'done' for v in vals):
        return 'completed'
    if any(v in ('running', 'pending') for v in vals):
        return 'active'
    return 'aborted'


class SystemMeter:
    """从 /proc 采样 CPU/内存/网络,供快照 system 字段。"""

    def __init__(self):
        self._cpu = None      # (idle_sum, total_sum, ts)
        self._net = None      # (rx_bytes, tx_bytes, ts)
        self._last = {'cpuPercent': -1, 'memoryPercent': -1, 'networkKbps': -1}

    def sample(self):
        try:
            parts = {}
            for line in open('/proc/stat'):
                if line.startswith('cpu '):
                    v = [int(x) for x in line.split()[1:8]]
                    parts['cpu'] = (sum(v), sum(v) - v[3] - v[4])   # total, busy
                    break
            mem = {}
            for line in open('/proc/meminfo'):
                k, v = line.split(':')[0], int(line.split()[1])
                mem[k] = v
            rx = tx = 0
            for line in open('/proc/net/dev'):
                if ':' in line and not line.strip().startswith(('lo', 'docker', 'br-', 'veth', 'virbr')):
                    cols = line.split()
                    rx += int(cols[1]); tx += int(cols[8])
            import time as _t
            now = _t.time()
            out = dict(self._last)
            if self._cpu and parts.get('cpu'):
                dt_cpu = parts['cpu'][0] - self._cpu[0]
                busy = parts['cpu'][1] - self._cpu[1]
                if dt_cpu > 0:
                    out['cpuPercent'] = round(min(100, busy * 100 / dt_cpu), 1)
            if self._net:
                dt = now - self._net[2]
                if dt > 0:
                    out['networkKbps'] = round((rx + tx - self._net[0] - self._net[1]) * 8 / 1000 / dt, 1)
            if mem.get('MemTotal'):
                used = mem['MemTotal'] - mem.get('MemAvailable', 0)
                out['memoryPercent'] = round(used * 100 / mem['MemTotal'], 1)
            self._cpu = (parts['cpu'][0], parts['cpu'][1], now) if parts.get('cpu') else self._cpu
            self._net = (rx, tx, now)
            self._last = out
            return out
        except Exception:
            return {'cpuPercent': -1, 'memoryPercent': -1, 'networkKbps': -1}


def conv_id(tid):
    """会话 id 须匹配 ^[a-zA-Z0-9_.:-]+$:取任务号前缀(日期-序号),唯一且合法。"""
    parts = tid.split('-')
    if len(parts) >= 2 and len(parts[1]) == 3 and parts[0].isdigit():
        return f'{parts[0]}-{parts[1]}'
    import hashlib
    return 't-' + hashlib.md5(tid.encode()).hexdigest()[:12]


def _progress(stages, names):
    score = sum({'done': 100, 'running': 50, 'failed': 0, 'pending': 0}.get(stages.get(n, {}).get('status'), 0)
                for n in names) / len(names)
    return int(score)


ALL_ROSTER = [('planner', '选题策划', 'data-agent'), ('screenwriter', '编剧', 'app-agent'),
              ('designer', '设计师', 'file-agent'), ('videogen', '视频制作', 'code-agent'),
              ('voice', '配音', 'data-agent'), ('editor', '剪辑', 'code-agent'),
              ('reviewer', '质控', 'review-agent'), ('ops', '运营负责人', 'office-lead')]


def build(oid, tasks, seq, all_tasks=None, sysd=None):
    spec = OFFICES[oid]
    all_tasks = all_tasks or tasks
    # 成员名单全编制 + 岗位统计
    employees = [{'id': a, 'name': n, 'role': n, 'sceneActorId': actor, 'online': True,
                  'insights': _insights_for(a, all_tasks)}
                 for a, n, actor in ALL_ROSTER]
    deleted = set()
    df = ROOT / 'bridge' / 'deleted_convs.txt'
    if df.exists():
        deleted = {l.strip() for l in df.read_text().splitlines() if l.strip()}
    convs = []
    for tid, t in reversed(tasks.items()):          # 新任务排前
        if conv_id(tid) in deleted:
            continue
        total = len(t['stages'])
        done = sum(1 for s in t['stages'].values() if s['status'] == 'done')
        life = _lifecycle(t['stages'])
        finished = life == 'completed'
        board = {'template': 'task-board-v1', 'title': t['topic'][:12],
                 'status': 'completed' if finished else ('failed' if life == 'aborted' else 'running'),
                 'tagline': f"{'完结' if finished else ('中止' if life == 'aborted' else '制作中')} {done}/{total}",
                 'description': '',
                 'steps': [
                     {'id': 'c', 'title': '创意', 'progress': _progress(t['stages'], ('brief', 'script'))},
                     {'id': 'v', 'title': '视觉/视频', 'progress': _progress(t['stages'], ('design', 'video'))},
                     {'id': 'p', 'title': '后期', 'progress': _progress(t['stages'], ('voice', 'edit', 'review'))}]}
        if t['final']:
            from urllib.parse import quote
            board['link'] = {'label': '▶ 看成片', 'url': f"{RUNS_SERVER}/{quote(tid)}/06-edit/final.mp4"}
        tasks_list = []
        if life == 'completed':
            # 完结任务:撤掉阶段任务牌,但保留一张交付卡(挂运营名下)——任务中心不空窗,桌面只占领导位一格
            cost = sum(c.get('cost_usd') or 0 for c in t['stages'].values())
            tasks_list.append({'id': f'{tid}-delivery', 'title': f'交付:{t["topic"][:10]}',
                               'assigneeId': 'ops', 'status': 'completed', 'progress': 100,
                               'summary': f'成片就绪·总成本${cost:.2f}', 'updatedAt': t['mtime']})
        for sid, s in ({} if life == 'completed' else t['stages']).items():
            agent = STAGE_TO_AGENT.get(sid)
            if not agent or OFFICE_OF.get(agent) != oid:
                continue
            tasks_list.append({'id': f'{tid}-{sid}', 'title': f'{spec["agents"][agent][0]}·{sid}',
                               'assigneeId': agent, 'status': TASK_STATUS.get(s['status'], 'queued'),
                               'progress': -1, 'summary': '', 'updatedAt': t['mtime']})
        convs.append({'id': conv_id(tid), 'title': t['topic'][:16], 'whiteboard': board,
                      'employees': employees, 'tasks': tasks_list, 'events': []})
    # 永久保留 main 总览会话:任何旧选中/默认会话永远合法
    items = list(tasks.values())
    lifes = [_lifecycle(t['stages']) for t in items]
    finished = lifes.count('completed')
    aborted = lifes.count('aborted')
    active = lifes.count('active')
    latest = list(tasks.values())[-1] if items else None
    overview_tasks = []
    if latest and _lifecycle(latest['stages']) != 'completed':   # 总览同样:完结任务撤牌
        for sid, sv in latest['stages'].items():
            agent = STAGE_TO_AGENT.get(sid)
            if not agent or OFFICE_OF.get(agent) != oid:
                continue
            overview_tasks.append({'id': f'main-{sid}', 'title': f'{spec["agents"][agent][0]}·{sid}',
                                   'assigneeId': agent, 'status': TASK_STATUS.get(sv['status'], 'queued'),
                                   'progress': -1, 'summary': '', 'updatedAt': latest['mtime']})
    convs.insert(0, {'id': 'main', 'title': '团队总览', 'employees': employees,
                     'tasks': overview_tasks, 'events': [],
                     'whiteboard': {'template': 'task-board-v1', 'title': 'huaha-studio 内容工厂',
                                    'status': 'running', 'tagline': f'今日 {len(items)} 条',
                                    'description': '选题 → 剧本 → 视觉 → 视频 → 配音 → 合成 → 审核',
                                    'steps': [
                                        {'id': 'done', 'title': f'已完成 {finished} 条', 'progress': 100 if finished else 0},
                                        {'id': 'doing', 'title': f'在制 {active} 条', 'progress': 50 if active else 100},
                                        {'id': 'latest', 'title': f'最新:{(latest or {}).get("topic", "无")[:12]}',
                                         'progress': _progress(latest['stages'], tuple(STAGE_TO_AGENT)) if latest else 0}]}})
    system = sysd or {'cpuPercent': -1, 'memoryPercent': -1, 'networkKbps': -1}
    return {'schemaVersion': '1.0', 'seq': seq,
            'workspace': {'id': oid, 'name': spec['name']},
            'system': system,
            'conversations': convs}


def review_notice(tid, t):
    """review 完成时:把审片报告注入该片会话的聊天(两办公室都发)。"""
    report, verdict = '', {'pass': True, 'suggestions': []}
    try:
        verdict = json.loads((t['dir'] / '07-review' / 'verdict.json').read_text())
        checklist = (t['dir'] / '07-review' / 'checklist.md').read_text()[:600]
        verdict_text = '✅ 通过' if verdict.get('pass') else '❌ 打回'
        sugs = '\n'.join(f'{i + 1}. {s}' for i, s in enumerate(verdict.get('suggestions', [])[:3]))
        from urllib.parse import quote
        link = f"{RUNS_SERVER}/{quote(tid)}/06-edit/final.mp4"
        report = (f'**成片出炉:{t["topic"][:30]}**\n\n'
                  f'[▶ 点击观看成片]({link})\n\n'
                  f'质控结论:{verdict_text}\n\n改进建议:\n{sugs or "无"}\n\n---\n{checklist}')
    except Exception as e:
        report = f'成片已产出:{t["topic"][:30]}(报告读取失败:{e})'
    body = json.dumps({'conversationId': conv_id(tid), 'user': '(审片报告)',
                       'assistant': report}, ensure_ascii=False).encode()
    for team in OFFICES:
        req = urllib.request.Request(f'{CHAT_SERVER}/internal/notice?team={team}',
                                     data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            urllib.request.urlopen(req, timeout=10)
            print(f'  审片报告已注入 {team}/{tid}')
        except Exception as e:
            print(f'  报告注入失败 {team}: {e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=int, default=CFG.get('watch_interval', 3))
    ap.add_argument('--dry', action='store_true', help='只打印不推送')
    args = ap.parse_args()
    last_hash, seqs, last_stages = None, {}, {}
    last_sys_bucket, last_push_ts = None, 0.0
    meter = SystemMeter()
    # 续接服务端已有 seq,避免重启后同 seq 不同快照被拒(409)
    try:
        directory = post({'type': 'office.read'})
        for o in directory.get('data', {}).get('state', {}).get('offices', []):
            oid = o['snapshot']['workspace']['id']
            seqs[oid] = o['snapshot']['seq']
        print(f'续接服务端 seq:{seqs or "无在线办公室"}')
    except Exception as e:
        print(f'seq 查询失败(忽略):{e}')
    print(f'watch 启动:轮询 {RUNS},推送 {BASE},成片服务 {RUNS_SERVER}')
    while True:
        try:
            tasks, tasks_state = collect()
            recent = dict(list(tasks.items())[-5:])
            sysd = meter.sample()
            # 内容与资源解耦:内容(任务)变化即时推;资源读数仅在分桶跨档且距上次推送≥30s 时刷新,
            # 否则流水线一跑 CPU 翻腾会造成每几秒一次快照轰炸(白板反复黑闪)
            bucket = (round(max(0, sysd['cpuPercent']) / 10) * 10,
                      round(sysd['memoryPercent']),
                      round(max(0, sysd['networkKbps']) / 500) * 500)
            now_ts = time.time()
            content_h = json.dumps({k: {'topic': v['topic'], 'stages': v['stages'], 'final': v['final']}
                                    for k, v in tasks.items()}, sort_keys=True, ensure_ascii=False).__hash__()
            h = content_h if content_h != last_hash else (
                bucket if (bucket != last_sys_bucket and now_ts - last_push_ts >= 30) else last_hash)
            first_round = not last_stages
            for tid, stages in tasks_state.items():
                for sid, s in stages.items():
                    key = (tid, sid, s['status'])
                    if key in last_stages.get(tid, set()):
                        continue
                    if first_round:
                        # 启动首轮:历史状态只登记不触发,避免重启重放整个历史(气泡轰炸)
                        last_stages.setdefault(tid, set()).add(key)
                        continue
                    last_stages.setdefault(tid, set()).add(key)
                    agent = STAGE_TO_AGENT.get(sid)
                    quote_ = (QUOTES.get(s['status']) or {}).get(agent)
                    if quote_ and agent in OFFICE_OF and not args.dry:
                        office, actor = OFFICE_OF[agent], OFFICES[OFFICE_OF[agent]]['agents'][agent][1]
                        say(office, actor, quote_)
                    if sid == 'review' and s['status'] == 'done' and tid in tasks and not args.dry:
                        review_notice(tid, tasks[tid])
            if h != last_hash:
                for oid in OFFICES:
                    seqs[oid] = seqs.get(oid, 0) + 1
                    if args.dry:
                        print(f'[dry] {oid} seq={seqs[oid]} 会话{len(tasks)}')
                        continue
                    first = seqs[oid] == 1
                    body = ({'type': 'offices.initialize', 'offices': [build(oid, recent, seqs[oid], tasks, sysd)],
                             'chat': {'url': f'{CHAT_SERVER}/chat'}}
                            if first else
                            {'type': 'office.snapshot', 'teamId': oid, 'snapshot': build(oid, recent, seqs[oid], tasks, sysd)})
                    r = post(body)
                    if r.get('code') == 404:      # 服务端重启丢态 → 下一轮重新初始化
                        seqs[oid] = 0
                        print(f'[{time.strftime("%H:%M:%S")}] {oid} 服务端无此办公室,转为重新初始化')
                        continue
                    print(f'[{time.strftime("%H:%M:%S")}] {oid} seq={seqs[oid]} → {r.get("code")} '
                          f'{r.get("msg", "")[:40]}')
                last_hash = content_h
                last_sys_bucket = bucket
                last_push_ts = now_ts
        except Exception as e:
            print(f'[{time.strftime("%H:%M:%S")}] {e}', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()

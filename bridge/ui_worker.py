#!/usr/bin/env python3
"""PixOffice 桥接 · ui_worker:领取页面点击,回弹窗(岗位名片/汇报/任务操作)

ui.next 长轮询领取用户动作 → ui.respond 返回 detail-v1 弹窗或结果。
用法: python3 bridge/ui_worker.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['pixoffice']
BASE = CFG['base_url']
KEY = os.environ.get(CFG.get('api_key_env', 'PIXOFFICE_API_KEY'), 'pixoffice-demo-key')
AGENTS = yaml.safe_load((ROOT / 'agents.yaml').read_text())['agents']
DELETED = ROOT / 'bridge' / 'deleted_convs.txt'

from watch import ALL_ROSTER   # 单一名单源:id/名/工位

ACTOR_TO_AGENT = {actor: aid for aid, _n, actor in ALL_ROSTER}
STAGE_OF = {'planner': 'brief', 'screenwriter': 'script', 'designer': 'design',
            'videogen': 'video', 'voice': 'voice', 'editor': 'edit', 'reviewer': 'review'}


def post(data, timeout=40):
    req = urllib.request.Request(BASE.rstrip('/') + '/api/pixoffice/messages',
                                 data=json.dumps(data).encode(),
                                 headers={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'code': e.code, 'msg': e.read().decode()[:200]}


def latest_state():
    """最近一个任务的状态与主题。"""
    runs = ROOT / 'runs'
    best = None
    for d in sorted(runs.iterdir()) if runs.exists() else []:
        f = d / 'state.json'
        if f.exists() and d.name[:1].isdigit():
            best = json.loads(f.read_text())
    return best


def agent_status(agent):
    st = latest_state()
    if not st:
        return '暂无任务'
    sid = STAGE_OF.get(agent)
    if not sid:
        return f"常驻岗(不跑具体阶段),当前任务《{st['topic'][:18]}》"
    s = st['stages'].get(sid, {})
    return f"任务《{st['topic'][:18]}》 {sid}:{s.get('status', '?')}"


def respond(interaction_id, presentation):
    r = post({'type': 'ui.respond', 'interactionId': interaction_id, 'presentation': presentation})
    return r.get('code')


def dialog_card(agent, team):
    a = AGENTS[agent]
    return {'target': 'dialog', 'content': {
        'template': 'detail-v1',
        'title': f"{a['name']}",
        'description': a['description'],
        'fields': [
            {'label': '装备技能', 'value': ', '.join(a.get('skills') or ['无'])},
            {'label': '大脑模型', 'value': f"{a['model']['provider']}/{a['model']['model']}"},
            {'label': '当前状态', 'value': agent_status(agent)},
            {'label': '怎么聊', 'value': '底部输入框可直接对话(团队主管代答)'},
        ],
        'actions': [{'id': f'report-{agent}', 'label': '让TA汇报进展'}],
    }}


def agent_report(agent, team):
    """glm 以该岗位第一人称做进展汇报。"""
    from chat_server import stream_model
    a = AGENTS[agent]
    st = latest_state()
    stages = json.dumps(st['stages'], ensure_ascii=False) if st else '{}'
    topic = st['topic'] if st else '无'
    sysp = (f"你是 huaha-studio 的{a['name']},{a['description']}。当前任务:《{topic}》阶段状态:{stages}。"
            '用第一人称、口语化向老板汇报你的工作进展,150 字以内,说清:干完了什么、质量如何、下一步。')
    out = []
    stream_model(team, [{'role': 'user', 'content': '汇报一下你的进展'}],
                 emit=lambda t: out.append(t), cancelled=lambda: False)
    text = ''.join(out)[:3800]
    return {'target': 'dialog', 'content': {
        'template': 'detail-v1', 'title': f'{a["name"]}的汇报',
        'description': text, 'fields': [], 'actions': []}}


def _find_run_stage(task_id):
    """'20261027-003-xxx-brief' → (run_dir, stage_id)。总览任务(main-*)返回 None。"""
    if not task_id or '-' not in task_id or task_id.startswith('main-'):
        return None, None
    stage = task_id.rsplit('-', 1)[1]
    stem = task_id.rsplit('-', 1)[0]
    runs = ROOT / 'runs'
    if runs.exists():
        for d in runs.iterdir():
            if d.name == stem or d.name.startswith(stem):
                return d, stage
    return None, None


def handle_task_op(action):
    """任务操作真连流水线:block=打回已完成阶段(resume 时重跑);complete=跳过未开始阶段。"""
    tid = action['taskId']
    run_dir, stage = _find_run_stage(tid)
    if not run_dir:
        return respond(action['id'], {'target': 'result', 'success': False,
                                      'message': '总览任务不可直接操作,请进入具体视频会话'})
    f = run_dir / 'state.json'
    st = json.loads(f.read_text())
    cell = st['stages'].get(stage)
    if not cell:
        return respond(action['id'], {'target': 'result', 'success': False, 'message': f'未知阶段:{stage}'})
    kind = action['action']
    if kind == 'task.block':
        if cell['status'] == 'running':
            return respond(action['id'], {'target': 'result', 'success': False,
                                          'message': '该阶段正在运行,等它结束后再打回(或先停掉流水线)'})
        cell['status'] = 'failed'
        cell['error'] = '人工打回(办公室页面)'
        f.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        return respond(action['id'], {'target': 'result', 'success': True,
                                      'message': f'已打回 {stage}。执行 resume 将重跑该阶段及其下游,打回理由可在聊天里补充给对应岗位'})
    if kind == 'task.complete':
        if cell['status'] == 'done':
            return respond(action['id'], {'target': 'result', 'success': True, 'message': '该阶段本来就是完成态'})
        cell['status'] = 'done'
        f.write_text(json.dumps(st, ensure_ascii=False, indent=1))
        return respond(action['id'], {'target': 'result', 'success': True,
                                      'message': f'已将 {stage} 标记完成(跳过)。流水线 resume 时不再执行它'})
    return respond(action['id'], {'target': 'result', 'success': True,
                                  'message': f'已收到 {kind}(启动/改派暂由终端 resume 控制)'})


def handle(action):
    kind = action['action']
    team, conv = action['teamId'], action['conversationId']
    if kind in ('actor.inspect', 'employee.inspect'):
        who = action.get('actorId') or action.get('employeeId')
        agent = ACTOR_TO_AGENT.get(who, who)
        if agent in AGENTS:
            return respond(action['id'], dialog_card(agent, team))
        return respond(action['id'], {'target': 'result', 'success': False, 'message': '未登记的成员'})
    if kind == 'dialog.action':
        opt = action['optionId']
        if opt.startswith('report-'):
            agent = opt.split('-', 1)[1]
            if agent in AGENTS:
                return respond(action['interactionId'], agent_report(agent, team))
        return respond(action['interactionId'], {'target': 'result', 'success': False, 'message': '未知操作'})
    if kind in ('task.start', 'task.block', 'task.complete', 'task.assign'):
        return handle_task_op(action)
    if kind == 'conversation.delete':
        with open(DELETED, 'a') as f:
            f.write(conv + '\n')
        return respond(action['id'], {'target': 'result', 'success': True, 'message': '会话已移出看板'})
    return respond(action['id'], {'target': 'result', 'success': False, 'message': f'未支持:{kind}'})


def main():
    print('ui_worker 启动:长轮询领取页面点击', flush=True)
    while True:
        try:
            r = post({'type': 'ui.next', 'timeoutMs': 25000}, timeout=35)
            for a in (r.get('data', {}).get('actions') or []):
                print(f"[{time.strftime('%H:%M:%S')}] 动作:{json.dumps(a, ensure_ascii=False)}")
                handle(a)
        except Exception as e:
            print(f'轮询异常:{e}', flush=True)
            time.sleep(3)


if __name__ == '__main__':
    main()

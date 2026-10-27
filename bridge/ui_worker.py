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

OFFICES = {
    'studio-creative': {'name': '创意中心', 'agents': {
        'planner': 'data-agent', 'screenwriter': 'app-agent',
        'designer': 'file-agent', 'videogen': 'code-agent'}},
    'studio-post': {'name': '后期车间', 'agents': {
        'voice': 'data-agent', 'editor': 'code-agent', 'reviewer': 'review-agent'}},
}
ACTOR_TO_AGENT = {actor: (agent, team) for team, o in OFFICES.items()
                  for agent, actor in o['agents'].items()}
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
    s = st['stages'].get(sid, {})
    return f"任务《{st['topic'][:18]}》 {sid}:{s.get('status', '?')}"


def respond(interaction_id, presentation):
    r = post({'type': 'ui.respond', 'interactionId': interaction_id, 'presentation': presentation})
    return r.get('code')


def dialog_card(agent, team):
    a = AGENTS[agent]
    return {'target': 'dialog', 'content': {
        'template': 'detail-v1',
        'title': f"{a['name']} · {OFFICES[team]['name']}",
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


def handle(action):
    kind = action['action']
    team, conv = action['teamId'], action['conversationId']
    if kind in ('actor.inspect', 'employee.inspect'):
        who = action.get('actorId') or action.get('employeeId')
        agent, t2 = ACTOR_TO_AGENT.get(who, (who, team))
        if agent in AGENTS:
            return respond(action['id'], dialog_card(agent, t2 if kind == 'actor.inspect' else team))
        return respond(action['id'], {'target': 'result', 'success': False, 'message': '未登记的成员'})
    if kind == 'dialog.action':
        opt = action['optionId']
        if opt.startswith('report-'):
            agent = opt.split('-', 1)[1]
            if agent in AGENTS:
                return respond(action['interactionId'], agent_report(agent, team))
        return respond(action['interactionId'], {'target': 'result', 'success': False, 'message': '未知操作'})
    if kind in ('task.start', 'task.block', 'task.complete', 'task.assign'):
        verb = {'task.start': '启动', 'task.block': '打回', 'task.complete': '完成', 'task.assign': '改派'}[kind]
        return respond(action['id'], {'target': 'result', 'success': True,
                                      'message': f'已记录:你想{verb}任务 {action["taskId"]}(暂不直接改动流水线,改稿请在聊天里说)'})
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
                print(f"[{time.strftime('%H:%M:%S')}] 动作:{json.dumps(a, ensure_ascii=False)[:120]}")
                handle(a)
        except Exception as e:
            print(f'轮询异常:{e}', flush=True)
            time.sleep(3)


if __name__ == '__main__':
    main()

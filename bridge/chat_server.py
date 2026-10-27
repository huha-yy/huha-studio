#!/usr/bin/env python3
"""PixOffice 聊天服务:办公室小人 ↔ 真·团队大脑(glm-5.3-flash)

实现 PixOffice chat 协议四种操作(send/history/resume/cancel),NDJSON 流式。
人格:创意中心=制片人,后期车间=后期主管;系统提示注入流水线实时状态。
历史持久化:bridge/chat_history/<team>__<conv>.json

用法: python3 bridge/chat_server.py [--port 8789]
"""
import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / 'bridge' / 'chat_history'
HIST.mkdir(exist_ok=True)
AGENTS = yaml.safe_load((ROOT / 'agents.yaml').read_text())['agents']
MODELS = yaml.safe_load((ROOT / 'config' / 'models.yaml').read_text())['providers']
MODEL = os.environ.get('STUDIO_CHAT_MODEL', 'glm-5.3-flash')

PERSONA = {
    'studio-creative': ('制片人', '创意中心负责人,统管选题策划/编剧/设计/视频制作四个岗位'),
    'studio-post': ('后期主管', '后期车间负责人,统管配音/剪辑/质控三个岗位'),
}


def load_env():
    f = ROOT / '.env'
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()


def pipeline_state_text():
    """汇总 runs/*/state.json → 给模型看的现状。"""
    lines = ['# 流水线现状']
    runs = ROOT / 'runs'
    if not runs.exists():
        return lines[0] + ':暂无任务'
    for d in sorted(runs.iterdir())[-3:]:
        f = d / 'state.json'
        if not f.exists() or not d.name[0].isdigit():
            continue
        st = json.loads(f.read_text())
        marks = ' '.join(f"{sid}:{s['status']}" for sid, s in st['stages'].items())
        lines.append(f"- 任务 {st['task_id']}《{st['topic'][:30]}》 {marks}")
    return '\n'.join(lines)


def system_prompt(team):
    name, role = PERSONA.get(team, ('团队助理', 'huaha-studio 成员'))
    roster = '\n'.join(f"- {a['name']}({k}):{a['description']}" for k, a in AGENTS.items())
    return (
        f'你是 huaha-studio(抖音内容工作室)的{name},{role}。'
        '工作室定位:紧跟当下热榜,用纯代码动效快速产出有价值、有意义的竖版短视频。\n\n'
        f'# 团队成员\n{roster}\n\n{pipeline_state_text()}\n\n'
        '回答要求:中文,口语化,像同事聊天;涉及任务进展以"流水线现状"为准;'
        '给建议要具体可执行;用户若提出新选题/改稿等需求,说明可以由哪个岗位执行、怎么触发;'
        '不知道就说不知道,不编造。')


# ---------- 轮次存储 ----------
LOCKS = {}
TURNS = {}   # (team, conv) -> [ {id,user,assistant,state,error,ts} ]


def store_key(team, conv):
    return f"{team}__{re.sub(r'[^\\w-]', '_', conv)}"


def turns_of(team, conv):
    key = store_key(team, conv)
    if key not in TURNS:
        f = HIST / f'{key}.json'
        TURNS[key] = json.loads(f.read_text()) if f.exists() else []
    return TURNS[key]


def save(team, conv):
    key = store_key(team, conv)
    (HIST / f'{key}.json').write_text(json.dumps(TURNS[key], ensure_ascii=False))


def lock_for(team, conv):
    return LOCKS.setdefault(store_key(team, conv), threading.Lock())


# ---------- 模型流式 ----------
def stream_model(team, messages, emit, cancelled):
    """调智谱 Anthropic 兼容流式接口;emit(text) 逐段吐出;返回完整文本。"""
    prov = MODELS['zhipu']
    body = json.dumps({
        'model': MODEL, 'max_tokens': 2048, 'stream': True,
        'system': system_prompt(team),
        'messages': [{'role': m['role'], 'content': m['content']} for m in messages],
    }).encode()
    req = urllib.request.Request(prov['base_url'].rstrip('/') + '/v1/messages', data=body,
                                 headers={'x-api-key': os.environ.get(prov['auth_env'], ''),
                                          'anthropic-version': '2023-06-01',
                                          'content-type': 'application/json'}, method='POST')
    full = []
    with urllib.request.urlopen(req, timeout=180) as r:
        for raw in r:
            if cancelled():
                break
            line = raw.decode().strip()
            if not line.startswith('data:'):
                continue
            try:
                ev = json.loads(line[5:])
            except json.JSONDecodeError:
                continue
            if ev.get('type') == 'content_block_delta':
                d = ev.get('delta', {})
                if d.get('type') == 'text_delta' and d.get('text'):
                    full.append(d['text'])
                    emit(d['text'])
    return ''.join(full)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'[chat] {time.strftime("%H:%M:%S")} {self.address_string()} {fmt % args}', flush=True)

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ndjson(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def _ev(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + '\n').encode())
        self.wfile.flush()

    def do_POST(self):
        if self.path != '/chat':
            return self._json(404, {'code': 404, 'msg': 'not found', 'data': {}})
        n = int(self.headers.get('Content-Length', 0))
        req = json.loads(self.rfile.read(n))
        team, conv, typ = req['teamId'], req['conversationId'], req['type']

        if typ == 'history':
            return self.history(team, conv, req)
        if typ == 'cancel':
            return self.cancel(team, conv, req)
        if typ == 'resume':
            return self.resume(team, conv, req)
        if typ == 'send':
            return self.send(team, conv, req)
        return self._json(400, {'code': 400, 'msg': 'bad type', 'data': {}})

    def history(self, team, conv, req):
        with lock_for(team, conv):
            ts = turns_of(team, conv)
            limit = max(1, min(50, req.get('limit', 20)))
            cursor = req.get('cursor', '')
            page = ts[-limit:] if not cursor else ts[:int(cursor)][-limit:]
            next_cursor = str(max(0, len(ts) - limit)) if len(ts) > limit and not cursor else ''
            has_more = len(ts) > limit
            if cursor:
                has_more = int(cursor) > limit
            active = next((t['id'] for t in reversed(ts) if t['state'] == 'pending'), '')
            return self._json(200, {'code': 200, 'msg': 'OK', 'data': {
                'turns': [{'id': t['id'], 'user': t['user'], 'assistant': t['assistant'],
                           'state': t['state'], 'error': t['error']} for t in page],
                'nextCursor': next_cursor, 'hasMore': has_more, 'activeTurnId': active}})

    def _turn(self, team, conv, turn_id):
        return next((t for t in turns_of(team, conv) if t['id'] == turn_id), None)

    def cancel(self, team, conv, req):
        with lock_for(team, conv):
            t = self._turn(team, conv, req['turnId'])
            if t and t['state'] == 'pending':
                t['state'] = 'stopped'
                save(team, conv)
        return self._json(200, {'code': 200, 'msg': 'OK', 'data': {'stopped': True}})

    def resume(self, team, conv, req):
        with lock_for(team, conv):
            t = self._turn(team, conv, req['turnId'])
        self._ndjson()
        if not t:
            return self._ev({'type': 'error', 'message': 'turn not found'})
        self._ev({'type': 'snapshot', 'text': t['assistant'], 'state': t['state'], 'message': t['error']})
        if t['state'] == 'pending':
            for _ in range(600):        # 等生成线程补完(v1 简化:轮询)
                time.sleep(0.3)
                if t['state'] != 'pending':
                    break
            self._ev({'type': 'snapshot', 'text': t['assistant'], 'state': t['state'], 'message': t['error']})
        self._ev({'type': 'done'})

    def send(self, team, conv, req):
        turn_id, msgs = req['turnId'], req['messages']
        user_text = msgs[-1]['content'] if msgs else ''
        with lock_for(team, conv):
            ts = turns_of(team, conv)
            exist = self._turn(team, conv, turn_id)
            if exist:
                if exist['user'] == user_text:      # 重复提交:按恢复处理
                    t = exist
                    fresh = False
                else:
                    return self._json(409, {'code': 409, 'msg': 'turn id conflict', 'data': {}})
            else:
                t = {'id': turn_id, 'user': user_text, 'assistant': '', 'state': 'pending', 'error': '', 'ts': time.time()}
                ts.append(t)
                save(team, conv)
                fresh = True
        self._ndjson()
        self._ev({'type': 'status', 'phase': 'thinking'})
        if fresh:
            try:
                stream_model(team, msgs, lambda txt: (t.__setitem__('assistant', t['assistant'] + txt),
                                                      t['state'] == 'pending' and self._ev({'type': 'delta', 'text': txt})),
                             cancelled=lambda: t['state'] != 'pending')
                t['state'] = 'stopped' if t['state'] == 'pending' else t['state']
            except Exception as e:
                t['state'], t['error'] = 'error', str(e)[:200]
            save(team, conv)
        self._ev({'type': 'done'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8789)
    args = ap.parse_args()
    print(f'聊天服务 :{args.port}/chat 模型={MODEL}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""PixOffice 桥接 · ask:人工决策一次性调用

发 decision.request 到办公室页面,阻塞等人选择;打印所选退出。
编排器在 human 阶段调用;办公室离线/超时时退出码 2(编排器降级终端问答)。

用法:
  python3 bridge/ask.py choice   --team studio-creative --title "选题拍板" \
      --desc "..." --options '{"A":"标题A","B":"标题B","C":"标题C"}' [--timeout 180]
  python3 bridge/ask.py confirm  --team studio-post --title "发布审核" --desc "..." \
      [--confirm-label 发布] [--reject-label 打回] [--timeout 120]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['pixoffice']
BASE = CFG['base_url']
KEY = os.environ.get(CFG.get('api_key_env', 'PIXOFFICE_API_KEY'), 'pixoffice-demo-key')

ACTORS = {'studio-creative': 'office-lead', 'studio-post': 'office-lead'}


def post(data, timeout):
    req = urllib.request.Request(BASE.rstrip('/') + '/api/pixoffice/messages',
                                 data=json.dumps(data).encode(),
                                 headers={'Authorization': f'Bearer {KEY}',
                                          'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'code': e.code, 'msg': e.read().decode()[:300]}
    except Exception as e:
        return {'code': -1, 'msg': str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=['choice', 'confirm'])
    ap.add_argument('--team', default='studio-creative')
    ap.add_argument('--title', required=True)
    ap.add_argument('--desc', default='')
    ap.add_argument('--options', help='choice 模式: {"A":"...","B":"..."}')
    ap.add_argument('--confirm-label', default='确认')
    ap.add_argument('--reject-label', default='拒绝')
    ap.add_argument('--timeout', type=int, default=180)
    args = ap.parse_args()

    decision = {'id': str(uuid.uuid4()), 'actorId': ACTORS.get(args.team, 'office-lead'),
                'title': args.title[:80], 'description': args.desc[:300]}
    if args.kind == 'choice':
        opts = json.loads(args.options or '{}')
        decision.update(kind='choice', options=[
            {'id': k, 'label': v[:40]} for k, v in opts.items()])
    else:
        decision.update(kind='confirmation',
                        confirmLabel=args.confirm_label[:20], rejectLabel=args.reject_label[:20])

    r = post({'type': 'decision.request', 'teamId': args.team, 'conversationId': 'main',
              'timeoutMs': args.timeout * 1000, 'decision': decision},
             timeout=args.timeout + 20)
    if r.get('code') == 200:
        choice = r['data'].get('choiceId', '')
        print(choice if args.kind == 'choice' else ('yes' if choice == 'confirm' else 'no'))
        return
    print(f'决策失败: {r.get("code")} {r.get("msg", "")[:120]}', file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""huha-studio 编排器

用法:
  python3 scripts/studio.py run   short-video --topic "xxx" [--auto] [--until <stage>]
  python3 scripts/studio.py resume <task-id>   [--auto] [--until <stage>]
  python3 scripts/studio.py status [<task-id>]
  python3 scripts/studio.py list

设计见 docs/pipeline-design.md。状态即文件:runs/<task>/state.json。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / 'runs'

STATUS_FLOW = 'pending running done failed'.split()


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env():
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_configs():
    agents = yaml.safe_load((ROOT / 'agents.yaml').read_text())['agents']
    models = yaml.safe_load((ROOT / 'config' / 'models.yaml').read_text())['providers']
    return agents, models


def load_pipeline(pid):
    p = yaml.safe_load((ROOT / 'pipeline' / f'{pid}.yaml').read_text())
    p['_index'] = {s['id']: i for i, s in enumerate(p['stages'])}
    for i, s in enumerate(p['stages']):
        s['dir'] = f"{i + 1:02d}-{s['id']}"
    return p


def read_state(task_dir):
    f = task_dir / 'state.json'
    return json.loads(f.read_text()) if f.exists() else None


def write_state(task_dir, state):
    (task_dir / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=1))


def new_task(pipeline, topic):
    RUNS.mkdir(exist_ok=True)
    today = time.strftime('%Y%m%d')
    n = 1
    while (RUNS / f'{today}-{n:03d}').exists():
        n += 1
    slug = re.sub(r'[^\w-]+', '-', topic)[:24].strip('-')
    task_id = f'{today}-{n:03d}' + (f'-{slug}' if slug else '')
    task_dir = RUNS / task_id
    task_dir.mkdir(parents=True)
    state = {
        'task_id': task_id, 'pipeline': pipeline['id'], 'topic': topic,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'stages': {s['id']: {'status': 'pending', 'attempts': 0} for s in pipeline['stages']},
    }
    write_state(task_dir, state)
    (task_dir / 'topic-input.md').write_text(f'# 主题\n\n{topic}\n')
    return task_id, task_dir


def agent_env(agent_cfg, models):
    """为 claude 子进程构造干净环境:清掉继承的 ANTHROPIC_*,再按 provider 注入。"""
    provider = models[agent_cfg['model']['provider']]
    key = os.environ.get(provider['auth_env'], '')
    env = {k: v for k, v in os.environ.items() if not k.startswith('ANTHROPIC_')}
    env['ANTHROPIC_BASE_URL'] = provider['base_url']
    env['ANTHROPIC_AUTH_TOKEN'] = key
    env['ANTHROPIC_API_KEY'] = key
    return env


def link_skills(stage_dir, agent_cfg, global_skills):
    """把 agent 声明的技能软链进阶段工作区(项目级技能)。注:用户级技能仍全局可见,靠 AGENT.md 约束使用范围(软隔离)。"""
    skills_dir = stage_dir / '.claude' / 'skills'
    skills_dir.mkdir(parents=True, exist_ok=True)
    for name in agent_cfg.get('skills') or []:
        src = global_skills / name
        dst = skills_dir / name
        if not dst.exists():
            dst.symlink_to(src.resolve())


def run_agent(task_dir, stage, agent_cfg, models, global_skills, prompt, timeout):
    stage_dir = task_dir / stage['dir']
    stage_dir.mkdir(exist_ok=True)
    link_skills(stage_dir, agent_cfg, global_skills)
    agent_md = ROOT / 'agents' / stage['agent'] / 'AGENT.md'
    (stage_dir / 'stage-prompt.md').write_text(prompt)
    cmd = [
        shutil.which('claude'), '-p',
        '--model', agent_cfg['model']['model'],
        '--append-system-prompt', agent_md.read_text(),
        '--output-format', 'json',
        '--dangerously-skip-permissions',
    ]
    log(f"  ↳ claude -p 模型={agent_cfg['model']['provider']}/{agent_cfg['model']['model']} "
        f"技能={agent_cfg.get('skills') or '无'} 工作区={stage['dir']}/")
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              cwd=stage_dir, env=agent_env(agent_cfg, models), timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'error': f'超时({timeout}s)'}
    dur = round(time.time() - t0, 1)
    out = {}
    try:
        payload = json.loads(proc.stdout)
        out = {'cost_usd': payload.get('total_cost_usd'),
               'tokens': payload.get('usage', {}).get('output_tokens'),
               'result': (payload.get('result') or '')[:400]}
    except (json.JSONDecodeError, AttributeError):
        out = {'raw': (proc.stdout or '')[:200]}
    if proc.returncode != 0:
        out.update({'status': 'failed', 'error': (proc.stderr or '')[:300], 'duration': dur})
        return out
    out.update({'status': 'ok', 'duration': dur})
    return out


def outputs_exist(task_dir, stage):
    missing = [o for o in stage.get('output', [])
               if not (task_dir / stage['dir'] / o).exists()]
    return missing


def ask_human(kind, task_dir, stage, auto):
    """两段式人工介入。auto=True 时自动选第一个/通过,便于无人值守冒烟。"""
    stage_dir = task_dir / stage['dir']
    if kind == 'brief':
        cands_file = stage_dir / 'candidates.json'
        if not cands_file.exists():
            log('  ! 未找到 candidates.json,跳过人工选择(以 brief 直接产出为准)')
            return
        cands = json.loads(cands_file.read_text()).get('candidates', [])
        if not cands:
            return
        if auto:
            choice = cands[0]['id']
            log(f"  [auto] 已自动选择候选 {choice}")
        else:
            print('\n===== 选题候选,请拍板 =====')
            for c in cands:
                print(f"  [{c['id']}] {c['title']} — {c.get('hook', '')}")
            choice = input('输入编号回车(默认A): ').strip().upper() or 'A'
        (stage_dir / 'decision.json').write_text(
            json.dumps({'choice': choice}, ensure_ascii=False, indent=1))
        log(f"  人选: {choice} → decision.json")
    elif kind == 'review':
        verdict_file = stage_dir / 'verdict.json'
        verdict = json.loads(verdict_file.read_text()) if verdict_file.exists() else {'pass': True}
        if auto:
            ok = verdict.get('pass', True)
            log(f"  [auto] 按 verdict.pass={ok} 自动处理")
        else:
            print('\n===== 人工终审 =====')
            print(json.dumps(verdict, ensure_ascii=False, indent=1)[:600])
            ok = input('通过发布?(y/n,默认y): ').strip().lower() != 'n'
        (stage_dir / 'final-decision.json').write_text(
            json.dumps({'approved': ok}, ensure_ascii=False))
        log(f"  终审: {'通过' if ok else '打回'}")


def run_stage(task_dir, pipeline, stage, agents, models, global_skills, auto):
    cfg = agents[stage['agent']]
    state = read_state(task_dir)
    st = state['stages'][stage['id']]
    st['status'], st['attempts'] = 'running', st.get('attempts', 0) + 1
    st['start'] = time.strftime('%H:%M:%S')
    write_state(task_dir, state)

    stage_dir = task_dir / stage['dir']
    stage_dir.mkdir(exist_ok=True)
    topic = read_state(task_dir)['topic']
    inputs = ', '.join(f'../{p}' for p in stage.get('input', []))
    outputs = ', '.join(stage.get('output', []))

    def run_once(goal):
        prompt = (f"# 任务\n主题:{topic}\n\n{goal}\n\n"
                  f"输入(只读,在上级目录):{inputs or '无,topic-input.md 在 runs 根目录'}\n"
                  f"本阶段必须产出的文件:{outputs}\n\n"
                  f"严格按你的岗位说明书(AGENT.md)执行;只读写当前工作目录。")
        return run_agent(task_dir, stage, cfg, models, global_skills, prompt,
                         stage.get('timeout', 1800))

    kind = stage.get('human')
    if kind == 'brief':
        r1 = run_once('第一阶段:产出 candidates.json(三个候选选题)。先不要写 brief.md。')
        if r1['status'] != 'ok':
            return fail(task_dir, stage, r1)
        ask_human('brief', task_dir, stage, auto)
        r2 = run_once('第二阶段:decision.json 已在工作目录,请据此产出 brief.md。')
        result = r2
    elif kind == 'review':
        result = run_once('按检查清单审片,产出 checklist.md 与 verdict.json。')
        if result['status'] == 'ok':
            ask_human('review', task_dir, stage, auto)
    else:
        result = run_once('完成你阶段的工作。')

    if result['status'] != 'ok':
        return fail(task_dir, stage, result)
    missing = outputs_exist(task_dir, stage)
    if missing:
        return fail(task_dir, stage, {'error': f'缺少产物: {missing}', **result})
    state = read_state(task_dir)
    s = state['stages'][stage['id']]
    s.update(status='done', end=time.strftime('%H:%M:%S'),
             cost_usd=result.get('cost_usd'), duration=result.get('duration'))
    write_state(task_dir, state)
    log(f"  ✓ {stage['id']} 完成 ({result.get('duration')}s, cost={result.get('cost_usd')})")
    return True


def fail(task_dir, stage, result):
    state = read_state(task_dir)
    state['stages'][stage['id']].update(status='failed', end=time.strftime('%H:%M:%S'),
                                        error=str(result.get('error'))[:300])
    write_state(task_dir, state)
    log(f"  ✗ {stage['id']} 失败: {str(result.get('error'))[:200]}")
    return False


def cmd_run(args):
    agents, models = load_configs()
    pipeline = load_pipeline(args.pipeline)
    global_skills = Path(os.path.expanduser(
        yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['paths']['skills_global']))
    task_id, task_dir = new_task(pipeline, args.topic)
    log(f"新任务 {task_id}: {args.topic}")
    state = read_state(task_dir)
    state.update(auto=args.auto)
    write_state(task_dir, state)
    execute(task_dir, pipeline, agents, models, global_skills, args)


def cmd_resume(args):
    agents, models = load_configs()
    pipeline = load_pipeline(read_state(RUNS / args.task_id)['pipeline'])
    global_skills = Path(os.path.expanduser(
        yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['paths']['skills_global']))
    task_dir = RUNS / args.task_id
    state = read_state(task_dir)
    # 失败阶段及其下游重置为 pending
    idx = pipeline['_index']
    failed_at = min((idx[sid] for sid, s in state['stages'].items() if s['status'] == 'failed'),
                    default=None)
    if failed_at is not None:
        for s in pipeline['stages'][failed_at:]:
            state['stages'][s['id']]['status'] = 'pending'
        write_state(task_dir, state)
    log(f"续跑 {args.task_id}")
    execute(task_dir, pipeline, agents, models, global_skills, args)


def execute(task_dir, pipeline, agents, models, global_skills, args):
    state = read_state(task_dir)
    for stage in pipeline['stages']:
        if state['stages'][stage['id']]['status'] == 'done':
            log(f"= {stage['id']} 已完成,跳过")
            state = read_state(task_dir)
            continue
        log(f"▶ {stage['id']} ({agents[stage['agent']]['name']})")
        if not run_stage(task_dir, pipeline, stage, agents, models, global_skills,
                         auto=getattr(args, 'auto', False)):
            log(f"任务中止。续跑: python3 scripts/studio.py resume {state['task_id']}")
            sys.exit(1)
        state = read_state(task_dir)
        if args.until == stage['id']:
            log(f"--until {stage['id']} 达成,停止")
            return
    log(f"★ 任务完成: {state['task_id']}")


def cmd_status(args):
    if args.task_id:
        s = read_state(RUNS / args.task_id)
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        st = read_state(d)
        if st:
            done = sum(1 for x in st['stages'].values() if x['status'] == 'done')
            print(f"{st['task_id']}  {done}/{len(st['stages'])}  {st['topic'][:30]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('pipeline')
    r.add_argument('--topic', required=True)
    r.add_argument('--auto', action='store_true', help='人工环节自动拍板(冒烟用)')
    r.add_argument('--until')
    r.set_defaults(fn=cmd_run)
    r2 = sub.add_parser('resume')
    r2.add_argument('task_id')
    r2.add_argument('--auto', action='store_true')
    r2.add_argument('--until')
    r2.set_defaults(fn=cmd_resume)
    s = sub.add_parser('status')
    s.add_argument('task_id', nargs='?')
    s.set_defaults(fn=cmd_status)
    sub.add_parser('list').set_defaults(fn=lambda a: cmd_status(a.__class__(task_id=None)))
    args = ap.parse_args()
    load_env()
    args.fn(args)


if __name__ == '__main__':
    main()

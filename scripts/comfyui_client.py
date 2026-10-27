#!/usr/bin/env python3
"""ComfyUI 客户端:工作流转换 / 参数注入 / 提交生成 / 收集产物

用法:
  python3 scripts/comfyui_client.py ping
  python3 scripts/comfyui_client.py convert                  # UI工作流 → pipeline/workflows/*.api.json
  python3 scripts/comfyui_client.py fields t2v-fast          # 列出模板可改字段
  python3 scripts/comfyui_client.py run t2v-fast \
      --set 35.text="一只猫在弹钢琴" --out /tmp/out

设计:不手搓节点图。读 ComfyUI 保存的 UI 工作流,用 /object_info 的节点输入定义
把 widgets_values 按序映射为 API 格式(一次转换,模板入库 pipeline/workflows/)。
"""
import argparse
import json
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / 'pipeline' / 'workflows'
SOURCE_DIR = Path.home() / 'ComfyUI' / 'user' / 'default' / 'workflows'
BASE = 'http://127.0.0.1:8188'

# 模板名 → 源工作流文件(职责缩写,给 agent 用)
TEMPLATE_MAP = {
    't2v-fast': '文生视频-快速4步.json',
    't2v-hq': '文生视频-高清8步.json',
    'flf2v': '首尾帧转视频-4步.json',
    'ref2v': '角色参考视频-4步.json',
    'video-enhance': '视频增强-修复版.json',
    'image-edit': 'image_qwen_image_edit_2511.json',
    'i2v-ltx': 'ltx23_hq_i2v_api.json',          # 源已是 API 格式
}


def http(path, data=None, method=None, timeout=30, raw=False, headers=None):
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return body if raw else json.loads(body)


def load_object_info():
    """class_type → (按序 widget 名, 字段类型/枚举规格)。"""
    info = http('/object_info')
    widget_order, field_spec = {}, {}
    for cls, spec in info.items():
        names, specs = [], {}
        for group in ('required', 'optional'):
            for name, val in (spec.get('input', {}).get(group) or {}).items():
                typ = val[0] if isinstance(val, list) and val else None
                extra = val[1] if isinstance(val, list) and len(val) > 1 and isinstance(val[1], dict) else {}
                if isinstance(typ, list) or (isinstance(typ, str) and typ in ('INT', 'FLOAT', 'STRING', 'BOOLEAN', 'COMBO')):
                    names.append(name)
                    specs[name] = typ if isinstance(typ, list) else typ
                    if extra.get('control_after_generate'):
                        names.append(('control_after_generate', name))  # 伪控件:占位消费一个 widgets_value
        widget_order[cls] = names
        field_spec[cls] = specs
    return widget_order, field_spec


def compatible(value, spec):
    """值是否与字段规格兼容。"""
    if isinstance(spec, list):                      # 枚举
        return value in spec
    if spec == 'INT':
        return isinstance(value, int) and not isinstance(value, bool)
    if spec == 'FLOAT':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if spec == 'BOOLEAN':
        return isinstance(value, bool)
    return isinstance(value, str)


def map_widgets(cls, wv, connected, widget_order, field_spec):
    """widgets_values → inputs。顺序不保证与 object_info 一致,用类型感知贪心匹配。"""
    inputs = {}
    if wv and isinstance(wv[0], list):
        wv = [x for sub in wv for x in (sub if isinstance(sub, list) else [sub])]
    wv = list(wv or [])
    specs = field_spec.get(cls, {})
    for name in widget_order.get(cls, []):
        pseudo = isinstance(name, tuple)
        field = name[1] if pseudo else name
        if pseudo:
            if wv:
                wv.pop(0)          # 伪控件只消费不写入
            continue
        if field in connected:
            if wv:
                wv.pop(0)          # 已连接的输入同样占位消费
            continue
        spec = specs.get(field)
        idx = next((i for i, v in enumerate(wv) if compatible(v, spec)), None) if spec is not None else (0 if wv else None)
        if idx is None:
            if isinstance(spec, list) and wv:
                idx = 0          # 枚举值已不在当前选项里(如历史文件名),按位置兜底
            else:
                continue
        inputs[field] = wv.pop(idx)
    return inputs


def convert_ui_workflow(ui, widget_order, field_spec):
    """UI → API,支持 ComfyUI 0.33 子图(subgraph)展开。"""
    subgraphs = {sg['id']: sg for sg in ui.get('definitions', {}).get('subgraphs', [])}
    links = {l[0]: l for l in ui.get('links', [])}
    api, outputs_to_patch = {}, []   # outputs_to_patch: (instance_id, slot) → 内部真实来源

    def register(node, prefix=''):
        nid = f"{prefix}{node['id']}"
        api[nid] = {'class_type': node['type'], 'inputs': {}, '_meta': {'title': node.get('title') or node['type']}}
        return nid

    for node in ui.get('nodes', []):
        sg_id = node.get('subgraph')
        if not sg_id and node['type'] in subgraphs:
            sg_id = node['type']
        if sg_id and sg_id in subgraphs:
            sg = subgraphs[sg_id]
            prefix = f"{node['id']}x"
            # 子图接口节点(inputNode/outputNode 是 dict:{id: -10/-20,...})
            in_node_id = (sg.get('inputNode') or {}).get('id')
            out_node_id = (sg.get('outputNode') or {}).get('id')
            slinks = {}
            for l in sg.get('links', []):
                slinks[l['id']] = {'src': l['origin_id'], 'src_slot': l['origin_slot'],
                                   'dst': l['target_id'], 'dst_slot': l['target_slot']}
            for inner in sg['nodes']:
                if inner['id'] in (in_node_id, out_node_id):
                    continue
                if inner['type'] not in widget_order and 'Note' in inner['type']:
                    continue
                register(inner, prefix)
                # 内部连线
                for inp in inner.get('inputs', []) or []:
                    if inp.get('link') is not None:
                        link = slinks.get(inp['link'])
                        if not link:
                            continue
                        src = link['src']
                        if src == in_node_id:
                            # 来自子图接口:IMAGE 等真输入 → 接到实例的外部连线;
                            # 提升的 widget(COMBO/STRING/INT/FLOAT/BOOLEAN)→ 不算连接,回落 widgets_values 取值
                            if inp.get('type') in ('IMAGE', 'LATENT', 'MODEL', 'CLIP', 'VAE', 'CONDITIONING', 'MASK'):
                                slot = link['src_slot']
                                iface_inputs = sg.get('inputs', [])
                                name = iface_inputs[slot]['name'] if slot < len(iface_inputs) else None
                                outer = next((i for i in (node.get('inputs') or []) if i.get('name') == name), None)
                                if outer and outer.get('link') is not None:
                                    ol = links.get(outer['link'])
                                    if ol:
                                        api[f"{prefix}{inner['id']}"]['inputs'][inp['name']] = [str(ol[1]), ol[2]]
                        else:
                            api[f"{prefix}{inner['id']}"]['inputs'][inp['name']] = [f"{prefix}{src}", link['src_slot']]
                # 输出到子图输出接口 → 记录:实例(出槽) 应改指内部真实节点
                for out in inner.get('outputs', []) or []:
                    for lid in out.get('links', []) or []:
                        link = slinks.get(lid)
                        if link and link['dst'] == out_node_id:
                            outputs_to_patch.append((str(node['id']), link['dst_slot'],
                                                     f"{prefix}{inner['id']}", link['src_slot']))
                # widgets(connected = 已有线连接的输入名)
                connected = set(api[f"{prefix}{inner['id']}"]['inputs'].keys())
                api[f"{prefix}{inner['id']}"]['inputs'].update(
                    map_widgets(inner["type"], inner.get("widgets_values"), connected, widget_order, field_spec))
        else:
            if node['type'] not in widget_order and ('Note' in node['type'] or 'MarkdownNote' in node['type']):
                continue
            nid = register(node)
            for inp in node.get('inputs', []) or []:
                if inp.get('link') is not None:
                    link = links.get(inp['link'])
                    if link:
                        src_id = str(link[1])
                        patch = next(((i, s, r, rs) for i, s, r, rs in outputs_to_patch if i == src_id and s == link[2]), None)
                        if patch:
                            api[nid]['inputs'][inp['name']] = [patch[2], patch[3]]
                        else:
                            api[nid]['inputs'][inp['name']] = [src_id, link[2]]
            connected = {i['name'] for i in (node.get('inputs') or []) if i.get('link') is not None}
            api[nid]['inputs'].update(map_widgets(node["type"], node.get("widgets_values"), connected, widget_order, field_spec))
    return api


def cmd_convert(_):
    widget_order, field_spec = load_object_info()
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for tname, fname in TEMPLATE_MAP.items():
        src = SOURCE_DIR / fname
        ui = json.loads(src.read_text())
        if 'nodes' in ui:
            api = convert_ui_workflow(ui, widget_order, field_spec)
        else:
            api = ui  # 已是 API 格式
        out = TEMPLATES / f'{tname}.api.json'
        out.write_text(json.dumps(api, ensure_ascii=False, indent=1))
        manifest[tname] = {'source': fname, 'nodes': len(api)}
        print(f'{tname:14s} ← {fname}  ({len(api)} nodes)')
    (TEMPLATES / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))


def load_template(name):
    f = TEMPLATES / f'{name}.api.json'
    if not f.exists():
        sys.exit(f'模板不存在:{name}(先跑 convert)')
    return json.loads(f.read_text())


def cmd_fields(args):
    api = load_template(args.template)
    for nid, node in sorted(api.items(), key=lambda x: [int(p) for p in re.findall(r'\d+', x[0])]):
        title = node['_meta'].get('title', '')
        for k, v in node['inputs'].items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                continue  # 连接线
            flag = '★' if any(w in k.lower() for w in ('text', 'prompt', 'image', 'video', 'seed', 'width', 'height', 'length')) else ' '
            print(f"{flag} {nid}.{k} = {str(v)[:60]}   [{node['class_type']}|{title}]")


def parse_set(pairs):
    out = {}
    for p in pairs:
        m = re.match(r'^(\d+(?:x\d+)*)\.([\w.]+)=(.*)$', p, re.S)
        if not m:
            sys.exit(f'--set 格式错:{p}(应为 node.field=value)')
        out[(m.group(1), m.group(2))] = m.group(3)
    return out


def upload_image(path):
    boundary = uuid.uuid4().hex
    data = Path(path).read_bytes()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
            f'filename="{Path(path).name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode() + data + f'\r\n--{boundary}--\r\n'.encode()
    r = http('/upload/image', data=body, method='POST',
             headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, raw=True)
    return json.loads(r)['name']


def cmd_run(args):
    api = load_template(args.template)
    overrides = parse_set(args.set or [])
    for (nid, field), value in overrides.items():
        if nid not in api:
            sys.exit(f'节点 {nid} 不在模板里(用 fields 查看)')
        if field not in api[nid]['inputs']:
            sys.exit(f'字段 {nid}.{field} 不存在')
        # 类型跟随原值
        orig = api[nid]['inputs'][field]
        if isinstance(orig, int) and re.match(r'^-?\d+$', value):
            value = int(value)
        elif isinstance(orig, float) and re.match(r'^-?\d+(\.\d+)?$', value):
            value = float(value)
        api[nid]['inputs'][field] = value
    for p in args.image or []:
        m = re.match(r'^(\d+(?:x\d+)*)\.([\w.]+)=(.*)$', p)
        nid, field, path = m.groups()
        if field not in api[nid]['inputs']:
            sys.exit(f'字段 {nid}.{field} 不存在')
        api[nid]['inputs'][field] = upload_image(path)
        print(f'已上传图片 → {nid}.{field}')

    prompt_id = http('/prompt', data=json.dumps({'prompt': api, 'client_id': 'huha-studio'}).encode(),
                     method='POST', headers={'Content-Type': 'application/json'})['prompt_id']
    print(f'已提交 {prompt_id},排队中…')
    t0 = time.time()
    while True:
        time.sleep(3)
        hist = http(f'/history/{prompt_id}')
        if prompt_id not in hist:
            print(f'  …排队/执行中 {time.time() - t0:.0f}s')
            continue
        entry = hist[prompt_id]
        if entry.get('status', {}).get('status_str') == 'error':
            sys.exit(f'执行失败: {json.dumps(entry["status"], ensure_ascii=False)[:400]}')
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for nid, outs in entry.get('outputs', {}).items():
            for img in outs.get('images', []):
                blob = http('/view?' + '&'.join(f'{k}={v}' for k, v in img.items() if k in ('filename', 'subfolder', 'type')), raw=True, timeout=120)
                (out_dir / img['filename']).write_bytes(blob)
                saved.append(img['filename'])
            for vid in outs.get('gifs', []):  # 视频输出在 gifs 槽位
                blob = http('/view?' + '&'.join(f'{k}={v}' for k, v in vid.items() if k in ('filename', 'subfolder', 'type')), raw=True, timeout=300)
                (out_dir / vid['filename']).write_bytes(blob)
                saved.append(vid['filename'])
        print(f'完成 {time.time() - t0:.0f}s,产物 {len(saved)} 个 → {out_dir}')
        for s in saved:
            print(f'  {s}')
        return


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('ping').set_defaults(fn=lambda a: print(http('/system_stats')['system']['comfyui_version']))
    sub.add_parser('convert').set_defaults(fn=cmd_convert)
    f = sub.add_parser('fields')
    f.add_argument('template')
    f.set_defaults(fn=cmd_fields)
    r = sub.add_parser('run')
    r.add_argument('template')
    r.add_argument('--set', nargs='*', help='node.field=value')
    r.add_argument('--image', nargs='*', help='node.field=/path/to/img(自动上传)')
    r.add_argument('--out', default='/tmp/comfyui-out')
    r.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()

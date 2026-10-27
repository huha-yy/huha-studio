import sys, json, time, re
sys.path.insert(0, '/home/huha-play/huha-studio/scripts')
import comfyui_client as cc

def run(tag, prompt, duration, out_base, codec='auto'):
    api = cc.load_template('ref2v')
    api['138']['inputs']['value'] = prompt
    api['132']['inputs']['value'] = float(duration)
    api['92']['inputs']['codec'] = codec
    api['115']['inputs']['aspect_ratio'] = '9:16 (Portrait Widescreen)'
    api['115']['inputs']['megapixels'] = 2.0
    img = '/home/huha-play/huha-studio/runs/20261027-001-用AI把老照片变会动的短视频-给家里老人一个惊喜/03-design/assets/%s.png' % tag
    name = cc.upload_image(img)
    api['137']['inputs']['image'] = name
    api['139']['inputs']['image'] = name
    pid = cc.http('/prompt', data=json.dumps({'prompt': api, 'client_id': 'huha-studio'}).encode(),
                  method='POST', headers={'Content-Type': 'application/json'})['prompt_id']
    print(f'[{tag}] submitted {pid}')
    t0 = time.time()
    while True:
        time.sleep(5)
        h = cc.http(f'/history/{pid}')
        if pid not in h:
            print(f'  …running {time.time()-t0:.0f}s'); continue
        st = h[pid]['status']
        if st['status_str'] == 'error' or not st['completed']:
            for m in st.get('messages', []):
                if m[0] == 'execution_error':
                    e = m[1]
                    print(f'[{tag}] FAILED at {e.get("node_id")} {e.get("node_type")}: {e.get("exception_message")}')
                    return False
        # fetch outputs
        outs = []
        for nid, node in (h[pid].get('outputs') or {}).items():
            for g in node.get('gifs', []) or node.get('videos', []) or node.get('images', []):
                outs.append((g['filename'], g.get('subfolder', ''), g.get('type', 'output')))
        if not outs:
            print(f'[{tag}] no outputs, status={st["status_str"]}'); return False
        fn, sub, typ = outs[0]
        q = f'/view?filename={fn}&subfolder={sub}&type={typ}'
        data = cc.http(q, raw=True)
        ext = '.mp4' if fn.endswith(('.mp4','.webm','.gif')) is False else ('.gif' if fn.endswith('.gif') else '.mp4')
        if fn.endswith('.webm'): ext = '.webm'
        path = out_base + ext
        open(path, 'wb').write(data)
        print(f'[{tag}] saved {path} ({len(data)} bytes)')
        return True

if __name__ == '__main__':
    base = '/home/huha-play/huha-studio/runs/20261027-001-用AI把老照片变会动的短视频-给家里老人一个惊喜/04-video/shots/'
    ok1 = run('S1',
        'A restored 1960s Chinese black-and-white family portrait filling the full vertical frame, '
        'young woman in front center, vintage photo grain, warm soft nostalgic light; '
        'first two seconds completely still like a frozen photo, then she blinks gently once and the corners '
        'of her mouth lift into a subtle smile, tiny slow zoom-in, cinematic micro-motion only',
        5, base + 'S1')
    ok2 = run('S6',
        'Cinematic vertical shot, Chinese grandmother in her 80s seen from behind and side, holding a phone '
        'below eye level watching a video, soft window daylight from upper right rim-lighting her silhouette '
        'and silver hair bun, authentic documentary style, gentle skin texture, warm intimate framing; '
        'she first freezes stunned, then slowly breaks into a warm tearful smile, slight handheld camera sway, '
        'subtle slow motion on the smile, warm color grading, film grain',
        10, base + 'S6')
    sys.exit(0 if (ok1 and ok2) else 1)

import sys, json, time
sys.path.insert(0, '/home/huha-play/huha-studio/scripts')
import comfyui_client as cc

PROMPT = (
    'Cinematic vertical shot, Chinese grandmother in her 80s seen from behind and side, holding a phone '
    'below eye level watching a video, soft window daylight from upper right rim-lighting her silhouette '
    'and silver hair bun, authentic documentary style, gentle skin texture, warm intimate framing; '
    'she first freezes stunned, then slowly breaks into a warm tearful smile, slight handheld camera sway, '
    'subtle slow motion on the smile, warm color grading, film grain'
)

def main():
    api = cc.load_template('ref2v')
    api['138']['inputs']['value'] = PROMPT
    api['132']['inputs']['value'] = 10.0
    api['115']['inputs']['aspect_ratio'] = '9:16 (Portrait Widescreen)'
    api['115']['inputs']['megapixels'] = 1.0  # 纪律:ref2v ≤1MP
    img = ('/home/huha-play/huha-studio/runs/20261027-001-用AI把老照片变会动的短视频'
           '-给家里老人一个惊喜/03-design/assets/S6.png')
    name = cc.upload_image(img)
    api['137']['inputs']['image'] = name
    api['139']['inputs']['image'] = name
    pid = cc.http('/prompt', data=json.dumps({'prompt': api, 'client_id': 'huaha-studio'}).encode(),
                  method='POST', headers={'Content-Type': 'application/json'})['prompt_id']
    print(f'[S6] submitted {pid}', flush=True)
    t0 = time.time()
    while True:
        time.sleep(10)
        h = cc.http(f'/history/{pid}')
        if pid not in h:
            print(f'  …running {time.time()-t0:.0f}s', flush=True)
            continue
        st = h[pid]['status']
        if st['status_str'] == 'error' or (st['completed'] and st['status_str'] != 'success'):
            for m in st.get('messages', []):
                if m[0] == 'execution_error':
                    e = m[1]
                    print(f'[S6] FAILED at {e.get("node_id")} {e.get("node_type")}: '
                          f'{e.get("exception_message")}', flush=True)
            return 1
        outs = []
        for nid, node in (h[pid].get('outputs') or {}).items():
            for g in node.get('gifs', []) or node.get('videos', []) or node.get('images', []):
                outs.append((g['filename'], g.get('subfolder', ''), g.get('type', 'output')))
        if not outs:
            print(f'[S6] no outputs, status={st["status_str"]}', flush=True)
            return 1
        fn, sub, typ = outs[0]
        data = cc.http(f'/view?filename={fn}&subfolder={sub}&type={typ}', raw=True)
        path = ('/home/huha-play/huha-studio/runs/20261027-001-用AI把老照片变会动的短视频'
                '-给家里老人一个惊喜/04-video/shots/S6.mp4')
        open(path, 'wb').write(data)
        print(f'[S6] saved {path} ({len(data)} bytes, {time.time()-t0:.0f}s)', flush=True)
        return 0

if __name__ == '__main__':
    sys.exit(main())

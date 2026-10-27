import sys, json, urllib.request, uuid, re
from pathlib import Path
sys.path.insert(0, '/home/huha-play/huha-studio/scripts')
import comfyui_client as cc

api = cc.load_template('ref2v')
api['138']['inputs']['value'] = ("A restored 1960s Chinese black-and-white family portrait, young woman in front center, "
    "vintage photo grain, warm soft nostalgic light; first two seconds completely still like a frozen photo, "
    "then she blinks gently once and smiles subtly, tiny slow zoom-in")
api['132']['inputs']['value'] = 5.0
# 图片已上传过一次,重新上传拿名字
name = cc.upload_image('/home/huha-play/huha-studio/runs/20261027-001-用AI把老照片变会动的短视频-给家里老人一个惊喜/03-design/assets/S1.png')
api['137']['inputs']['image'] = name

data = json.dumps({'prompt': api, 'client_id': 'huha-studio'}).encode()
req = urllib.request.Request(cc.BASE + '/prompt', data=data, method='POST',
                             headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print('HTTP', e.code)
    print(e.read().decode()[:3000])

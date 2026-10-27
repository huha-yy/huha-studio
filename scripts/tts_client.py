#!/usr/bin/env python3
"""Qwen3-TTS 薄封装:文本 → wav(并给出时长)

用法:
  python3 scripts/tts_client.py "要合成的文本" --out /tmp/voice.wav
  python3 scripts/tts_client.py --speakers
长文本按句切分合成后 ffmpeg 拼接(服务端单次上限 1200 字,这里更保守按 200 字切)。
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / 'config' / 'studio.yaml').read_text())['services']['tts']
BASE = CFG['base_url']


def speakers():
    with urllib.request.urlopen(f'{BASE}/healthz', timeout=10) as r:
        return json.loads(r.read())['speakers']


def synth_one(text, speaker, instruct, out):
    body = json.dumps({'text': text, 'language': 'Chinese',
                       'speaker': speaker, 'instruct': instruct}).encode()
    req = urllib.request.Request(f'{BASE}/synthesize', data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=600) as r:
        Path(out).write_bytes(r.read())


def split_text(text, limit=200):
    parts, buf = [], ''
    for seg in re.split(r'(?<=[。!?!?;;\n])', text):
        if len(buf) + len(seg) > limit and buf:
            parts.append(buf)
            buf = seg
        else:
            buf += seg
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('text', nargs='?')
    ap.add_argument('--out', default='/tmp/tts-out.wav')
    ap.add_argument('--speaker', default=CFG.get('default_speaker', 'Serena'))
    ap.add_argument('--instruct', default='', help='语气指令,如"温柔缓慢,带笑意"')
    ap.add_argument('--speakers', action='store_true')
    args = ap.parse_args()
    if args.speakers:
        print('\n'.join(speakers()))
        return
    if not args.text:
        sys.exit('需要文本或 --speakers')
    parts = split_text(args.text)
    tmp = Path(tempfile.mkdtemp())
    files = []
    for i, p in enumerate(parts):
        f = tmp / f'{i:03d}.wav'
        print(f'合成 {i + 1}/{len(parts)}:{p[:30]}…')
        synth_one(p, args.speaker, args.instruct, f)
        files.append(str(f))
    if len(files) == 1:
        subprocess.run(['cp', files[0], args.out], check=True)
    else:
        lst = tmp / 'list.txt'
        lst.write_text('\n'.join(f"file '{f}'" for f in files))
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0',
                        '-i', str(lst), '-c', 'copy', args.out], check=True)
    d = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', args.out], capture_output=True, text=True).stdout.strip()
    print(f'完成:{args.out} 时长 {d}s')


if __name__ == '__main__':
    main()

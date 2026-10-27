# Design Notes · 《老照片活了》(20261027-001)

方向:dir-2 暖棕纪实情感向(选择理由见 choice.md)。全片视觉关键词:**怀旧、温情、魔幻惊喜、暖调、忌冷色科技风**。

## 色板

| 用途 | 色值 | 说明 |
|---|---|---|
| 暖光高光 | `#fdf3dc` / `#f3cf8e` | 屏幕光、窗光、照片卡(全片唯一亮源语言) |
| 暖中调 | `#d8a468` / `#cbb392` | 老相纸、肤色剪影 |
| 暖暗部 | `#38281f` / `#241811` / `#160f0b` | 暗室、剪影、前景压角 |
| 点睛朱砂 | `#c2492b` | 标题强调字、进度条、STEP 编号(唯一高饱和色) |
| 米白纸底 | `#f5f2ea` | 文字区底、教程页(S2-S4) |
| 正文墨色 | `#2e2620` | 大标题 |

## 字体

- 标题:Noto Serif CJK SC 900(宋体大字,情感锚)
- 辅文/UI:Noto Sans CJK SC(细、疏字距)
- 竖排引言用细宋,字距 ≥4px

## 版式母题

- 「装裱」:照片卡片=被人珍藏的物件,不是素材;唯一亮源永远在照片/屏幕上
- 「暖暗房」:场景压暗,让发光照片自己讲故事(cover/S5/S6 同语言)
- 教程段(S2-S4)米白纸底+红蓝金 STEP 色条,与情感段形成"工具→亲情"的段落对比

## 首帧参考图(assets/,1080×1920,构图/光位锚定,成图由 ComfyUI 生成)

- `S1.png` — 三人黑白全家福剪影、地面分界、暗角、字幕「她朝我眨眼了」
- `S5.png` — 过肩、手机屏唯一亮源、轻微透视偏转、拇指压屏
- `S6.png` — 窗光右上、奶奶剪影轮廓光、手机低于视线、手臂交代持机

## ComfyUI 生成提示词(videogen 阶段直接取用)

- **S1(生图→生视频首帧)**:`A restored 1960s Chinese black-and-white family portrait filling the full vertical 9:16 frame, three family members standing formally, young woman in front center, vintage photo grain, slightly faded edges, warm soft key light, nostalgic film texture, gentle vignette` — 负面:`modern clothing, color, cartoon, deformed hands, text watermark`
- **S5(生图)**:`Over-the-shoulder shot, hands holding a smartphone showing an animated vintage portrait, phone screen as the only bright glowing element in a dim warm living room, shallow depth of field, cinematic warm amber tones, cozy evening atmosphere` — 负面:`cold blue tones, harsh flash, face close-up, cluttered background`
- **S6(生视频首帧)**:`Cinematic vertical shot, Chinese grandmother in her 80s seen from behind and side, holding a phone below eye level, soft window daylight from upper right rim-lighting her silhouette and silver hair bun, authentic documentary style, gentle skin texture, warm intimate framing` — 负面:`frontal face, studio lighting, cold tones, oversaturated`
- 统一后缀:`warm color grading, film grain, 9:16 vertical, photorealistic`

## 给下游的统一纪律

- 情感段(S1/S5/S6):暗调+暖光,唯一亮源=照片/屏幕;景深浅;手持微晃
- 教程段(S2/S4 motion-code):米白纸底、朱砂点睛、Noto Sans;STEP 标签左侧色条 01红/02蓝/03金
- 字幕统一:宋体、米白字、底部安全区 ≥150px,避开平台 UI
- 封面文字已按缩略图可读校验:主标 92px、对比度足够、底部边距 150px

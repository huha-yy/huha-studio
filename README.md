# huha-studio

> 呼哈工作室 —— 跑在 DGX Spark 上的 AI 内容生产团队,抖音起家,平台无关。

一句话:**选题进,成片出。** 一群 AI(生图/生视频/配音/动画/剪辑)在虚拟办公室里分工协作,人只做两件事:拍板和发布。

## 架构

```
选题策划(LLM) → 编剧/分镜(LLM) → 设计(huashu-design · 84风格)
     → 生图(Qwen-Image 2512/Edit 2511) → 生视频(LTX-2 22B / MiniMax H3 / Wan 2.2)
     → 配音(Qwen3-TTS) → 合成(huashu-motion / huashu-art-motion)
     → 人工审核(PixOffice 决策菜单) → 发布 → 数据复盘
```

## 目录

| 路径 | 用途 |
| --- | --- |
| `pipeline/` | 流水线各环节的脚本与 prompt 模板 |
| `scripts/` | ComfyUI workflow 调用、TTS/ASR 服务封装 |
| `docs/` | 架构文档、运行手册 |

## 硬件与依赖(都在 192.168.10.247 / DGX Spark GB10)

- ComfyUI 0.33(`127.0.0.1:8188`),7 个现成 workflow(文生图/图编辑/首尾帧/角色参考/LTX-2 高清/视频增强)
- Qwen3-TTS(自定义音色,`~/qwen3-tts-service`)
- 技能:huashu-motion、huashu-design、huashu-art-motion
- PixOffice(`../pixoffice`,指挥中心与人工审核)
- ffmpeg 8 / ASR / OCR

## 状态

- [x] 能力盘点完成(2026-10-26)
- [ ] 第一条端到端成片
- [ ] PixOffice 指挥中心接入
- [ ] 发布与数据回流

## License

TBD

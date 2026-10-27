# huaha-studio

> 呼哈工作室 —— 跑在 DGX Spark 上的 AI 内容生产团队,抖音起家,平台无关。

一句话:**今天热榜进,成片出。** 一群 AI(选题/编剧/设计/动画/配音/剪辑/质控)盯着当下热点,用纯代码动效快速产出有价值、有意义的短视频;人在虚拟办公室里只做两件事:拍板和发布。

## 架构

```
当日热榜(DailyHotApi 自托管) → 选题策划(锚定热点+价值筛选,三候选供人拍板)
  → 编剧/分镜(全 motion-code) → 设计(huashu-design · 84风格)
  → 视频制作(纯代码动效:huashu-art-motion 36风格 / huashu-motion / lemo-opuscar 59风格)
  → 配音(Qwen3-TTS) → 剪辑合成(ffmpeg + huashu-motion)
  → 质控 → 人工终审(PixOffice 决策菜单) → 发布
```

全部 agent 由 **Claude Code headless** 驱动,默认模型 **glm-5.3-flash**(智谱,agents.yaml 一行可换)。视频渲染走 CPU(分钟级、零 GPU);生成式图/视频模型已弃用,ComfyUI 配置保留备用。

## 目录

| 路径 | 用途 |
| --- | --- |
| `agents/` + `agents.yaml` | 7 个智能体的岗位说明书与注册表(模型/技能/工位) |
| `pipeline/` | 流水线定义(short-video)与 ComfyUI 模板(备用) |
| `scripts/` | `studio.py` 编排器 / `hotlist.py` 热榜 / `tts_client.py` / `comfyui_client.py` |
| `bridge/` | PixOffice 桥接(watch 状态同步 / ask 人工决策) |
| `docs/` | 架构、流水线、桥接设计文档与参考项目追踪 |
| `runs/` | 每条片子的产物与状态(gitignore) |

## 依赖(192.168.10.247 / DGX Spark GB10)

- DailyHotApi 自托管(`:6688`,`~/DailyHotApi`,聚合抖音/微博/知乎/百度/头条)
- Qwen3-TTS(`:8001`,`systemd --user start qwen3-tts`)
- 技能:huashu-motion、huashu-design、huashu-art-motion、lemo-opuscar
- PixOffice(`../pixoffice`,指挥中心与人工审核,服务器模式 :8767)
- ffmpeg 8 / ComfyUI(已停用,备用)

## 快速开始

```bash
cd /home/huha-play/studio
python3 scripts/studio.py run short-video --topic "今日热榜热点,由策划自行选题"   # 人工拍板版
python3 scripts/studio.py run short-video --topic "..." --auto                  # 无人值守冒烟
python3 scripts/studio.py status / list / resume <task-id>
```

## 状态

- [x] 能力盘点完成(2026-10-26)
- [x] 编排器/桥接/热点情报全链路打通(2026-10-27)
- [x] 纯代码动效路线定型(弃用生成式模型)
- [ ] 第一条热点驱动端到端成片
- [ ] 发布与数据回流

## License

TBD

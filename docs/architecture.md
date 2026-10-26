# huha-studio 架构(已定稿决策)

> 规划日期:2026-10-26。原则:**站在巨人的肩膀上,少重复造轮子**。

## 已定决策

| 决策点 | 结论 |
|---|---|
| 智能体运行时 | **Claude Code headless**(`claude -p` 子进程,每 agent 独立模型环境) |
| PixOffice 集成 | **桥接模式**:PixOffice 原样运行,huha-studio 通过其 HTTP 协议(offices.initialize / office.snapshot / decision.request)同步状态与人工审核 |
| 模型配置 | **agents.yaml 统一声明**,模型端点注册在 config/models.yaml |
| 素材生成 | ComfyUI API / Qwen3-TTS / ffmpeg 现成服务,scripts/ 只做薄封装 |
| 技能 | 标准 skills 格式(huashu-design / huashu-art-motion / huashu-motion 已装,lemo-opuscar 待装) |

## 分层

```
指挥/展示   PixOffice(桥接集成)
智能体运行时  claude -p 子进程 × 7
技能层      标准 skills
模型路由    models.yaml 注册的 provider(智谱/DeepSeek/本地)
素材生成    ComfyUI / TTS / ffmpeg(服务化,脚本封装)
编排/状态    pipeline runner(薄编排器,读 pipeline/*.yaml 逐阶段调度)
```

## 智能体分工表(7 个)

| Agent | 职责 | 技能 | 默认模型 | PixOffice |
|---|---|---|---|---|
| planner 选题策划 | 热点/选题库选题,产出 brief | (待装:热点采集类) | deepseek-chat | 办公室A·data-agent |
| screenwriter 编剧 | 脚本/分镜/口播稿 | — | glm-4.7(智谱) | 办公室A·app-agent |
| designer 设计 | 封面/视觉包装/信息图 | huashu-design | glm-4.7(智谱) | 办公室A·file-agent |
| videogen 视频制作 | 生图(分镜帧)+生视频 | huashu-art-motion, huashu-motion | 本地 llm_proxy | 办公室A·code-agent |
| voice 配音 | TTS 配音/音色管理 | — | 本地 llm_proxy | 办公室B·data-agent |
| editor 剪辑 | 合成/字幕/BGM/成片 | — | 本地 llm_proxy | 办公室B·code-agent |
| reviewer 质控 | 发布前检查清单,触发人工审核 | — | deepseek-chat | 办公室B·review-agent |

> PixOffice 双办公室:**A 创意中心**(策划/编剧/设计/视频)、**B 后期车间**(配音/剪辑/质控)。每个办公室各自有 6 个固定人物位,审批决策菜单由 lead 位承载。

## 模型注册表(config/models.yaml 设计)

```yaml
providers:
  zhipu-coding:                    # 智谱 coding plan(Anthropic 兼容)
    base_url: https://open.bigmodel.cn/api/anthropic
    auth_env: ZHIPU_API_KEY
  deepseek:                        # DeepSeek 官方(Anthropic 兼容)
    base_url: https://api.deepseek.com/anthropic
    auth_env: DEEPSEEK_API_KEY
  llm_proxy:                       # 本地代理(247,dato 栈,路由 DeepSeek 等)
    base_url: http://127.0.0.1:8080
    auth_env: DL_INTERNAL_TOKEN

asset_services:                    # 非 LLM,素材服务(studio.yaml)
  comfyui: http://127.0.0.1:8188   # 生图/生视频(Qwen-Image/LTX-2/MiniMax H3/Wan2.2)
  tts: qwen3-tts                   # 本地 ~/qwen3-tts-service(按需启动)
  asr: dl-asr                      # 字幕
```

> 换模型 = 改 agents.yaml 一行;加模型商 = models.yaml 加一段。不动代码。

## 仓库结构(定稿)

```
huha-studio/
├── agents.yaml              # 智能体注册表(角色/技能/模型/办公室映射)
├── config/{models,studio}.yaml
├── agents/<name>/AGENT.md   # 7 份岗位说明书(系统提示+工作规范)
├── skills/                  # 仓库私有技能(可选)
├── pipeline/*.yaml          # 流水线定义(阶段串)
├── bridge/                  # PixOffice 桥接
├── scripts/                 # comfyui/tts/ffmpeg 薄封装
├── runs/<task-id>/          # 每条片子的产物与状态(gitignore)
└── docs/
```

## 待办规划(顺序)

1. ✅ 架构决策与分工表(本文档)
2. ✅ 流水线与编排引擎设计(docs/pipeline-design.md)
3. ✅ PixOffice 桥接设计(docs/pixoffice-bridge-design.md)
4. ⬜ 动工实施

# huha-studio 架构(已定稿决策)

> 规划日期:2026-10-26,2026-10-27 修订(纯代码路线 + 热点驱动 + glm-5.3-flash)。原则:**站在巨人的肩膀上,少重复造轮子**。

## 已定决策

| 决策点 | 结论 |
|---|---|
| 内容定位 | **热点驱动**:选题锚定当日真实热榜(DailyHotApi 自托管 :6688),产出有价值、有意义的大众向短视频;不做纯标题党 |
| 智能体运行时 | **Claude Code headless**(`claude -p` 子进程,每 agent 独立模型环境) |
| 视频生产路线 | **纯代码动效**(motion-code:huashu-motion / huashu-art-motion / lemo-opuscar,CPU 分钟级渲染);生成式图/视频模型弃用,ComfyUI 与 7 个工作流模板保留备用 |
| PixOffice 集成 | **桥接模式**:PixOffice 原样运行,huha-studio 经其 HTTP 协议(offices.initialize / office.snapshot / decision.request)同步状态与人工审核 |
| 模型配置 | **agents.yaml 统一声明**,全部 agent 默认 **glm-5.3-flash**(智谱);换模型=改一行 |

## 分层

```
指挥/展示    PixOffice(桥接:bridge/watch.py 状态同步 + bridge/ask.py 人工决策)
智能体运行时  claude -p 子进程 × 7
技能层      标准 skills(huashu-design / art-motion / motion / lemo-opuscar 已装)
模型路由    models.yaml(zhipu / deepseek / llm_proxy)
热点情报    DailyHotApi 自托管(:6688,scripts/hotlist.py 聚合去重)
音频        Qwen3-TTS(:8001,systemd --user start qwen3-tts)/ ffmpeg 8
编排/状态    scripts/studio.py(文件即状态:runs/<task>/state.json)
```

## 智能体分工表(7 个)

| Agent | 职责 | 技能/工具 | 默认模型 | PixOffice |
|---|---|---|---|---|
| planner 选题策划 | 拉当日热榜 → 筛"有流量+有价值+做得出来" → 三候选供人拍板 | hotlist.py | glm-5.3-flash | 办公室A·data-agent |
| screenwriter 编剧 | 脚本/分镜/口播稿(分镜全部 motion-code) | — | glm-5.3-flash | 办公室A·app-agent |
| designer 设计 | 封面/视觉包装/信息图 | huashu-design | glm-5.3-flash | 办公室A·file-agent |
| videogen 视频制作 | 纯代码动效渲染镜头 | huashu-art-motion, huashu-motion, lemo-opuscar | glm-5.3-flash | 办公室A·code-agent |
| voice 配音 | TTS 配音/音色/时间轴 | tts_client.py | glm-5.3-flash | 办公室B·data-agent |
| editor 剪辑 | 合成/字幕/BGM/成片 | huashu-motion | glm-5.3-flash | 办公室B·code-agent |
| reviewer 质控 | 发布前检查清单,触发人工终审 | — | glm-5.3-flash | 办公室B·review-agent |

> PixOffice 双办公室:**A 创意中心**(策划/编剧/设计/视频)、**B 后期车间**(配音/剪辑/质控)。审批决策菜单由 lead 位承载。

## 模型注册表(config/models.yaml)

```yaml
providers:
  zhipu:                          # 智谱 coding plan(Anthropic 兼容),glm-5.3-flash
    base_url: https://open.bigmodel.cn/api/anthropic
    auth_env: ZHIPU_API_KEY
  deepseek:                       # DeepSeek 官方(Anthropic 兼容),key 到位即用
    base_url: https://api.deepseek.com/anthropic
    auth_env: DEEPSEEK_API_KEY
  llm_proxy:                      # 本地代理(247 dato 栈),备用
    base_url: http://127.0.0.1:8080
    auth_env: DL_INTERNAL_TOKEN

services(config/studio.yaml):
  hotlist: http://127.0.0.1:6688  # DailyHotApi(抖音/微博/知乎/百度/头条)
  tts: http://127.0.0.1:8001      # Qwen3-TTS
  comfyui: http://127.0.0.1:8188  # 已停用,保留备用(生成式图/视频)
```

## 仓库结构(定稿)

```
huha-studio/(可经 /home/huha-play/huha-studio 软链访问)
├── agents.yaml              # 智能体注册表(角色/技能/模型/办公室映射)
├── config/{models,studio}.yaml
├── agents/<name>/AGENT.md   # 7 份岗位说明书(系统提示+工作规范)
├── pipeline/*.yaml          # 流水线定义 + workflows/(ComfyUI 模板备用)
├── bridge/                  # PixOffice 桥接(watch.py / ask.py)
├── scripts/                 # studio.py 编排器 / hotlist / tts_client / comfyui_client
├── runs/<task-id>/          # 每条片子的产物与状态(gitignore)
└── docs/
```

## 待办规划(顺序)

1. ✅ 架构决策与分工表(本文档)
2. ✅ 流水线与编排引擎设计(docs/pipeline-design.md)
3. ✅ PixOffice 桥接设计(docs/pixoffice-bridge-design.md)
4. 🔄 动工实施(brief→script→design 已通;2026-10-27 转纯代码+热点驱动后重跑全链路)

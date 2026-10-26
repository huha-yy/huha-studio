# 流水线与编排引擎设计

> 规划任务 #5。原则:编排器只做"胶水",不引入框架、不建数据库——状态就是文件。

## 核心决策:薄 Python 编排器(仅标准库)

调研过的轮子:Airflow/Prefect/Temporal(太重,为7个阶段引入一套基础设施不值)、Make(依赖追踪很妙,但组装提示词/注入模型环境变量/上报状态会跟它搏斗)。

**结论:一个 ~300 行的 `studio.py`**,职责只有三件事:读配置、起 `claude -p` 子进程、记录状态。流水线状态不用数据库——`runs/<task>/state.json` 一个文件,PixOffice 桥接直接读它。这不算造轮子,是 Unix 传统的薄胶水。

## 流水线定义(pipeline/short-video.yaml)

```yaml
id: short-video
name: 竖版短视频 30s
stages:
  - id: brief
    agent: planner
    human: true            # 选题要人拍板(PixOffice 决策菜单)
    output: [brief.md]
  - id: script
    agent: screenwriter
    input: [01-brief/brief.md]
    output: [script.md, storyboard.json]
  - id: design
    agent: designer
    input: [02-script/storyboard.json]
    output: [cover.png, assets/]
  - id: video
    agent: videogen
    input: [02-script/storyboard.json, 03-design/assets]
    output: [shots/]
  - id: voice
    agent: voice
    input: [02-script/script.md]
    output: [voiceover.wav, timeline.json]
  - id: edit
    agent: editor
    input: [04-video/shots/, 05-voice/, 03-design/]
    output: [final.mp4]
  - id: review
    agent: reviewer
    human: true            # 发布前人工审核(PixOffice 决策菜单)
    input: [06-edit/final.mp4]
    output: [checklist.md, verdict.json]
```

> 线性流水,v1 不做 DAG。design 和 video/voice 理论可并行,v2 再说。

## 产物与状态规范(runs/)

```
runs/20261027-001-<slug>/
├── task.yaml        # 元信息:主题/目标平台/时长/流水线id
├── state.json       # 各阶段: pending|running|done|failed + 起止时间 + token用量
├── 01-brief/        # 每阶段一个目录,agent 的工作区就是这里
├── 02-script/
├── ...
└── 06-edit/final.mp4
```

**断点续跑 = 天然免费**:阶段产物在磁盘上,`resume` 只重跑 `failed` 阶段及其下游。agent 跑完的标志:`state.json` 里标 `done`。

## claude -p 调用模板(编排器的核心逻辑)

```bash
# 编排器按 agents.yaml 为每个阶段构造:
cd runs/<task>/01-brief/
mkdir -p .claude/skills && ln -sf <该agent声明的技能> .claude/skills/   # 技能隔离
ANTHROPIC_BASE_URL=<models.yaml 里的端点> \
ANTHROPIC_AUTH_TOKEN=<对应 key> \
claude -p --model <agents.yaml 里的模型> \
  --append-system-prompt "<agents/planner/AGENT.md>" \
  --output-format json < stage-prompt.md
```

- **cwd = 阶段目录**:agent 的所有读写天然限定在自己阶段内,防串台
- **.claude/skills 软链**:每个 agent 只见自己声明的技能(满足"不同 agent 装不同技能")
- `--output-format json` 拿 token 用量,记进 state.json(成本可见)

## 人工介入(human: true 的阶段)

编排器遇到 `human: true` 阶段:agent 先产出候选(如选题 brief 三选一/审核清单),编排器调 bridge → PixOffice `decision.request` 弹菜单,人点选后结果写回文件,流水线继续。**PixOffice 不在线时降级为终端交互问答**,流水线不卡死。

## CLI 设计

```
python scripts/studio.py run   short-video --topic "xxx"   # 起新任务
python scripts/studio.py resume <task-id>                  # 断点续跑
python scripts/studio.py status [<task-id>]                # 状态(桥接也用它)
python scripts/studio.py list                              # 任务列表
```

## 与 PixOffice 的分工(为任务#6铺垫)

- 编排器只管执行,**不直接懂 PixOffice**;每阶段状态变化时调用 bridge 的回调
- bridge 读 state.json → 换算成 office.snapshot 推送(哪个小人 working/thinking、白板进度)
- 审核阶段 → decision.request(上次已验证的协议)

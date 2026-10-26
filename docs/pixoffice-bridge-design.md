# PixOffice 桥接设计

> 规划任务 #6。PixOffice 原样运行(247 `/home/huha-play/pixoffice`,服务器模式 8767),桥接进程把 runs/ 的流水线状态"翻译"成办公室画面。

## 桥接 = 两个独立小工具(不是一个常驻大服务)

| 工具 | 形态 | 职责 |
|---|---|---|
| `bridge/watch.py` | 常驻进程,轮询 `runs/*/state.json`(每3秒) | 状态变化 → `office.snapshot` 推送(小人动画/白板进度);重要事件 → `scene.say` 气泡 |
| `bridge/ask.py` | 一次性命令,阻塞至人回答 | 编排器在 human 阶段调用:发 `decision.request`,拿回选择写入文件 |

> 松耦合原则:编排器对 PixOffice 零依赖(不在线照样跑,降级终端问答);watch 挂了也不影响生产,重启后从 state.json 全量对齐。

## 映射规则

### 办公室与人物(agents.yaml 的 actor 字段声明)

| 办公室 | workspace id | 成员→人物 |
|---|---|---|
| A 创意中心 | `studio-creative` | planner→data-agent, screenwriter→app-agent, designer→file-agent, videogen→code-agent |
| B 后期车间 | `studio-post` | voice→data-agent, editor→code-agent, reviewer→review-agent |

### 阶段状态 → 任务/动画

- 流水线阶段 = PixOffice 任务:`task-<任务id>-<阶段>`,assignee=该阶段 agent,status 映射(pending→queued, running→running, failed→blocked, done→completed)
- 小人动画由 PixOffice 根据任务状态自动驱动(working/idle),桥接不用管动画细节

### 白板(注意协议限制:steps ≤ 3)

- 办公室A 白板「创意流水线」:选题 → 剧本 → 视觉&视频(3步,取各阶段完成度)
- 办公室B 白板「后期流水线」:配音 → 合成 → 审核(3步)

### 气泡(scene.say,点缀用)

- 阶段开始:该 agent 小人冒一句角色台词(如设计:"开始出封面方案…")
- 阶段失败:lead 冒错误提示
- 全部完成:lead 汇报"成片就绪,请审核"

## 人工决策时序(brief 三选一 & review 发布审核)

```
编排器: 写 01-brief/candidates.json, state→human_pending
  └─ 调 bridge/ask.py --options candidates.json --timeout 180
       └─ decision.request(kind:choice/confirmation) → PixOffice 页面弹菜单
            人点选 → ask.py 打印所选 → 编排器写 decision.json,继续流水线
       └─ 超时/办公室离线 → ask.py 退出码2 → 编排器降级终端问答
```

## 部署与访问

- PixOffice 服务器模式常驻 247(8767,HOST=0.0.0.0;8765/8766 被别的服务占用)
- 办公室页面:`http://192.168.10.247:5173/office/`(局域网任意设备可看)
- 后续若做自己的总控界面:直接 iframe 嵌办公室页面即可(v2,不急)

## 已验证的协议要点(上次实测)

- 认证:`Bearer pixoffice-demo-key`(公网部署前必须换 PIXOFFICE_API_KEY)
- 初始化:`offices.initialize`(seq 从 office.read 查询后 +1)
- 增量:`office.snapshot`(seq 递增,STALE_SEQ 会被忽略)
- 决策:`decision.request` 408=超时无人选;菜单在页面**会话面板**显示(非人物头顶)
- 白板 steps 上限 3;任务 status 枚举:queued/running/blocked/completed/failed
- 202=快照已缓存(页面离线,上线自动应用)

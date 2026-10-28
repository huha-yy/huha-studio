# AI 视频参考项目追踪

> huha-studio 的外部弹药库。用于学习打法、拆解风格、复用提示词与代码。
> 状态:⬜未研究 / 📥已克隆 / 🔍拆解中 / ✅已复用 / ❌放弃
> 星数为 2026-10-26 核实值,均已验证真实存在。

## 项目清单

| # | 项目 | 地址 | 星数 | 许可 | 是什么 | 对我们的用途 | 状态 |
|---|------|------|------|------|--------|------------|------|
| 1 | awesome-opus5-5-videos | https://github.com/yihui-dev/awesome-opus5-5-videos | 11243 | MIT | 最大的爆款视频合集,每条附背后提示词(703条) | **选题与打法的灵感库**;找爆款模式反推我们做同款 | 📥已克隆(2026-10-28) |
| 2 | lemo-opuscar | https://github.com/lemomo-ai/lemo-opuscar | 7708 | MIT | Claude Code skill,59 种纯代码短片电影风格 | **直接装成 skill 用**;风格库比 art-motion 更偏电影感,互补 | ✅已装(2026-10-26) |
| 3 | pdoom-video | https://github.com/mexicat/pdoom-video | 3476 | MIT | 歌词卡拉 OK MV 完整工程,本地渲 4K60 | **音乐类内容模板**;卡拉OK字幕、节拍同步的工程参考 | 📥已克隆 |
| 4 | PDoomVideo | https://github.com/JohnHeibel/PDoomVideo | 2602 | ⚠️无许可 | 同一首歌的另一支 MV 源码 | **与 #3 对照拆解**:同一题材两种实现,学风格差异 | ⬜ |
| 5 | mg-styles-15 | https://github.com/Vincentwei1021/mg-styles-15 | 2155 | MIT | 15 种 MG 动效风格,成片+提示词+源码全给 | **MG 风格模板库**;商业口播/产品片的动效直接套 | 📥已克隆 |
| 6 | ClaudeAnimationBase | https://github.com/JohnHeibel/ClaudeAnimationBase | 1843 | MIT | 手绘卡通角色动画起步包,p5.js,31 种表情 | **IP 形象动画底座**;做品牌吉祥物/个人 IP 内容 | ⬜ |
| 7 | awesome-claude-5-5-videos | https://github.com/athemeroy/awesome-claude-5-5-videos | 783 | CC-BY-4.0 | 视频工作流合集,每个案例标出处,Opus 案例 301 个 | **工作流索引**;按案例找现成做法 | ⬜ |
| 8 | opus-video-prompts | https://github.com/joeseesun/opus-video-prompts | 759 | ⚠️无许可 | 中文案例合集,可直接复制的提示词 | **中文提示词模板**;直接复用的 prompt 起点 | 📥已克隆(2026-10-28) |

## 已装备的本机能力(对照)

| 能力 | 来源 | 状态 |
|------|------|------|
| 商业动画/发布片 | huashu-motion(本地 skill) | ✅已装 |
| 设计/封面/信息图(84 风格) | https://github.com/alchaincyf/huashu-design | ✅已装 |
| 艺术动画解说(36 风格) | https://github.com/alchaincyf/huashu-art-motion | ✅已装 |
| 精剪时间线 | https://github.com/JimLiu/baocut | ❌无 Linux 版,弃用 |

## 行动建议(优先级)

1. ✅ 装 lemo-opuscar(#2)——已装,videogen 技能池在用
2. ✅ **过一遍 opus-video-prompts(#8)和 awesome 合集(#1)**——已提炼 20 条打法入库(docs/viral-patterns.md),planner 升级"热点×打法"选题
3. ✅ 克隆 mg-styles-15(#5)和 pdoom-video(#3)——已在 references/,拆解待需
4. ⬜ ClaudeAnimationBase(#6)——等确定做 IP 形象内容时再启用

## 注意

- #4、#8 **无开源许可**(默认版权保留):本地克隆/运行/学习均可(个人自用无实际风险),但**不要把其代码复制进本仓库再分发**(本仓库是 public);提示词参考后重写最稳妥
- #7 是 CC-BY-4.0:引用案例需署名
- 其余 MIT:可自由复用,保留版权声明即可

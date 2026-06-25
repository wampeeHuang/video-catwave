# HANDOFF · 猫波信号站

> 新会话开始读此文件。

## 当前状态

**2026-06-25** — 飞书选题库大清理完成。Kevin Weil + Dan Shipper 两期已发布。

## 飞书选题库（本次会话操作）

**字段变更：**
- 删除「字幕可用」（已从评分维度移除）
- 「来源」→「来源频道名」（更明确）
- 「播放量」→「YouTube播放量」，「点赞」→「YouTube点赞」（区分原平台/B站）
- 新增「中文摘要」字段 — 每条记录一句中文概括
- Slug 字段加了备注说明

**数据修复：**
- 7 条排除记录：来源频道名从「B站已有XX」恢复为真实频道名（Andrej Karpathy、Y Combinator、Stanford Online、Lex Fridman），废弃原因挪入废弃原因字段
- 4 条候选 slug 从中文日期格式改为英文：`fiona-fung-claude-code-lenny` 等
- 全部 15 条标题翻译为中文
- 12 条有 URL 的记录填入 YouTube 播放量和点赞
- 删除 Cat Wu 记录（内容太差无 URL）
- Boris Cherny 视频已下架，YouTube 数据为空

**当前 4 条候选：**

| 选题 | 分 | YouTube播放 | 发布天数 | Slug |
|------|------|------|------|------|
| Fiona Fung | 28 | 3.0万 | 4天 | fiona-fung-claude-code-lenny |
| Google DeepMind | 24 | 4.2万 | 2天 | deepmind-ai-agents-millions |
| Databricks | 28 | 1310 | 1天 | databricks-agent-cloud-latentspace |
| Dan Shipper/Every | 24 | 618 | 1天 | dan-shipper-ai-humanity-every |

**推荐优先级**：Fiona Fung > DeepMind > Databricks > Dan Shipper/Every

## 下一步

1. **跑新选题扫描** — 触发 OpenClaw cron job（工具架定时器 `猫波信号站选题巡检`），或直接 `lark-cli base` 写入
2. **或直接做 Fiona Fung** — 分数最高、势头最好、与已做的 Boris+Dan 形成 Claude Code 系列视角互补
3. 做新一期时从 AGENT_GUIDE.md §1 管线流程 ② 开始

## 飞书

- Base token: `F7E8bJie5aX3BvsZz1Xc9KiznNb`
- Table: `tblIs359fHfIapwd`
- 操作命令: `lark-cli base +<subcommand> --base-token F7E8bJie5aX3BvsZz1Xc9KiznNb --table-id tblIs359fHfIapwd --as bot`
- JSON 需用文件传递: `--json "@_runtime/tmp.json"`（相对路径，无BOM）

## 评分体系

四维：总分 = 时效性×3 + 独占性×3 + 人物权威×2 + 长期价值×2 (满分 30)

## 路由

- **Lab 项目:** `D:\workspace\lab\2026-06-16-猫波信号站\`
- **产出根目录:** `D:\workspace\_output\猫波信号站\视频\`
- **飞书选题库:** `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **硬件:** RTX 5060 Ti 16GB, NVENC 默认编码

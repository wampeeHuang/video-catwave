# HANDOFF · 猫波信号站

> 新会话开始读此文件。覆盖式更新。

## 当前状态

**2026-06-28** — 文档收束完成，prompt 语言审计完成。生产手册合并已撤销，恢复双文件独立导航。

## 本会话完成

### 1. Prompt 语言审计（6 处修复）
Agent 面 prompt 中禁止人类交互假设（"人工判断""手动操作""需人工确认"）：
- `_archive/选题方法论.md:17` — "手动巡检"→"cron agent 自动执行"
- `_archive/选题方法论.md:32` — "1-2% 人工判断"→">= 1% 通过"
- `_ref/生产参数.md:44` — "人工判断后填入"→"按 §2 标题公式自动生成"
- `AGENT_GUIDE.md:252` — CDP "手动操作清单"→"agent 执行，不依赖人工"
- `stage_01_topic_onboard.py:18+223` — docstring + WARN 去 "manual review"
- Tips 条目：`~/.agentboard/tips/agent-prompt-no-human-assumptions.md`

### 2. 文档收束
- 删除 `_archive/` 3 个历史方法论 HTML 快照 (v1/v2/v3)
- `生产操作手册.html` + `生产方法论.html` 合并→已撤销，恢复独立文件
  - 生产方法论.html：方案/概念设计 (116 KB, 8 章节, 独立 sticky nav + scrollspy)
  - 生产操作手册.html：施工图/操作流程 (79 KB, 4 章节, 独立 sticky nav + scrollspy)
  - 合并版丢失各自内页导航栏，回退为双文件

### 3. 阈值收束尝试（已回退）
尝试建 `_ref/thresholds.json` → 判定为过早抽象 → 已完全回退。阈值保持在各文件硬编码。

### 4. 状态面板
- `gen_status_board.py` — 飞书×本地交叉引用，生成 `状态面板.html`
- 状态分类颜色（待发布=黄/已发布=绿/排除=红），`file:///` 链接直开文件夹
- cron job 6f5191da 阶段 C 已含 `python tools/gen_status_board.py`
- 点赞/播放比门禁 `< 1% 排除` 已写入 cron prompt（硬编码，非 JSON 引用）

## 文档维护面

| 文件 | 角色 | 维护频率 |
|------|------|---------|
| `生产方法论.html` | 人读：方案/概念设计 + 案例 | 参数/流程变化时 |
| `生产操作手册.html` | 人读：施工图/操作流程 | 参数/流程变化时 |
| `AGENT_GUIDE.md` | Agent 操作手册 | 管线调整时 |
| `_ref/生产参数.md` | 工程参数唯一真相源 | 封面/标题/字幕参数变化时 |
| `_ref/pitfalls.md` | 踩坑沉淀 | 新坑出现时 |
| `_archive/选题方法论.md` | 过程文件（选题系统设计稿） | 不维护 |
| `PROJECT_CONTEXT.md` | 架构总览 | 极少 |
| `CLAUDE.md` | 入口重定向 → AGENT_GUIDE | 不维护 |

## 管线进度

| # | Slug | 状态 | 产出 |
|---|------|------|------|
| 1 | tony-fadell-taste-ai-lenny | 待发布 | 完整 |
| 2 | ethan-he-xai-video-agents-latentspace | 待发布 | 完整 |
| 3 | greg-brockman-human-attention-sequoia | 待发布 | 完整 |
| 4 | satya-nadella-microsoft-build-latentspace | 待发布 | 完整 |
| 5 | joon-sung-park-simile-sequoia | 待发布 | 完整 |
| 6 | dan-biderman-jessy-lin-aiR7F4jqjXY-training-data-(sequoia-capital) | 待发布 | 完整 |
| 7 | mark-chen-fpAthTtha8c-latentspace | 已发布 | 完整 |
| 8 | gray-swan-ai-security-latentspace | 待发布 | 完整 |
| 9 | noam-brown-benchmarks-nopriors | 待发布 | 完整 |

## 待做

- ⑯ B站上传（管道就绪）
- 下一次 cron 触发验证巡检正常

## 路由

- **项目根:** `D:\workspace\猫波信号站\`
- **生产方法论:** `D:\workspace\猫波信号站\生产方法论.html`
- **生产操作手册:** `D:\workspace\猫波信号站\生产操作手册.html`
- **产出根:** `D:\workspace\_output\猫波信号站\视频\`
- **状态面板:** `D:\workspace\_output\猫波信号站\视频\状态面板.html`
- **飞书选题库:** `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **Cron 面板:** http://localhost:3100/cron
- **Main cron job:** `6f5191da-728c-4330-9eac-2717de3ff8c1` (Mon/Wed/Fri 9am, 选题+生产)
- **GPU:** h264_nvenc (RTX 5060 Ti 16GB)

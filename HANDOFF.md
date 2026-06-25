# HANDOFF · 猫波信号站

> 新会话开始读此文件。

## 当前状态

**2026-06-25** — Boris Cherny 发布面板和封面完成。Feishu 选题库大清理完成。Kevin Weil + Dan Shipper 两期已发布。

## 本次会话操作

### Boris Cherny 发布面板 + 封面重制

**发布面板** (`发布面板.html`)：
- 标题：`Claude Code 之父：我不写代码了，开着几十个 Loop 让 AI 7×24 帮我干活`
- 章节：10 章，全部 ≤16 字，首章起始 00:00:00
  ```
  00:00:00 开场与嘉宾介绍
  00:02:40 Claude Code 意外诞生
  00:04:30 前六个月完全不好用
  00:06:21 一年没写代码了
  00:07:11 手机管理几十个 Loop
  00:10:04 全员写代码的时代
  00:10:42 AI 如何摧毁 SaaS
  00:13:47 YC：做人们爱用的产品
  00:15:55 编程的印刷术时刻
  00:18:30 Anthropic 零手写代码
  ```
- 简介突出 Loop 概念，核心论点第一条即 Loop 工程

**封面** (`cover.jpg`)：
- 帧源：`_runtime/frames_loop/loop_03.jpg`（00:07:50 Loop 讨论段落）
- 标题双行：「设个 Loop」「AI 7×24 自己跑」
- 副标题：Claude Code 创建者 · 红杉资本 AI Ascent
- 1920×1080，201 KB，165px 无缩放

**`/loop` 概念**：Claude Code 内置 slash 命令，类似 cron 定时任务但执行 AI agent。设好间隔后 Claude 自动循环执行（修 CI、管 PR、聚合反馈）。Boris 开了几十个 loop 7×24 运行。与 `/schedule`（Routines）的区别：`/loop` 在本地 session 跑（最长 3 天），`/schedule` 在云端跑（合上笔记本也不停）。

### Feishu 选题库（上周操作，已记录）

详见上期 HANDOFF。当前 4 条候选：Fiona Fung (28分) > Google DeepMind (24分) > Databricks (28分) > Dan Shipper/Every (24分)。

## 待办

1. **Cursor Team 标题优化** — 当前标题太泛（"AI编程的未来"），需换具体标题。已做竞品调研，用户尚未选定方向
2. **跑新选题扫描** — 触发 OpenClaw cron job 或直接 `lark-cli base` 写入
3. **Boris Cherny 更新到 B站** — 需手动操作（CDP 限制）：更新标题、添加章节、上传新封面
4. **或直接做 Fiona Fung** — 分数最高、势头最好、与 Boris+Dan 形成 Claude Code 系列视角互补

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

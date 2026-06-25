# HANDOFF · 猫波信号站

> 新会话开始读此文件。

## 当前状态

**2026-06-25** — Fiona Fung 视频管线 ②~⑮ 已完成，⑯ CDP 上传进行中。

## 本次会话操作

### Fiona Fung — Claude Code PM on Lenny's Podcast

**管线状态**：②③④⑤⑥⑦⑧ ✅ | ⑨⑩⑪⑫⑬⑭⑮ ✅ | ⑯ 待执行

**产出目录**：`D:\workspace\_output\猫波信号站\视频\20260625_fiona-fung-claude-code-lenny\`

**关键产出**：
- 视频：`成片\编程解决之后？Claude Code PM Fiona Fung 谈软件开发者的未来.mp4` (1799 MB, NVENC, bord=1 alpha=128)
- 封面：`cover.jpg`
- 电子书：`电子书\编程解决之后？Claude Code PM 谈软件开发的未来.epub` (286 KB, 1124条, 20章)
- 发布面板：`发布面板.html`
- 元数据：`_runtime\metadata.json`

### 管线修复

- **`_lib.py:80`** — `parse_srt()` BOM bug：UTF-8 BOM `﻿` 粘在第一条索引号上，`int('﻿1')` 抛 ValueError 被静默丢弃，导致前 5 秒字幕丢失。修复：`lstrip('﻿')`
- **`stage_07_ass.py`** — 新增 `--outline-alpha` 参数（0-255），支持半透明白边。默认 255=不透明。128=50% 透明
- **`stage_07_ass.py`** — `run()` 和 `_generate_ass()` 签名增加 `outline_alpha` 参数
- **`stage_09_baidu_upload.py`**：修复 GBK 编码 print 崩溃
- **`stage_16_cdp_upload.py`**：添加 `sys.stdout.reconfigure(encoding='utf-8')` 修复 GBK 控制台输出

## 待办

1. **Fiona Fung CDP 后手动步骤** — 见桌面操作清单
2. **Boris Cherny 更新到 B站** — 需手动：更新标题、添加章节、上传新封面
3. **跑新选题扫描** — 触发 OpenClaw cron job 或直接 `lark-cli base` 写入

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

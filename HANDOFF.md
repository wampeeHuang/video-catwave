# HANDOFF · 猫波信号站

> 新会话开始读此文件。覆盖式更新。

## 当前状态

**2026-07-30** — 三视频生产完成，四个管线缺陷修复。生产面板待发布。

## 本会话完成

### 视频生产 (3/3)

| 视频 | 飞书 ID | 封面 | 成片 | 状态 |
|------|---------|------|------|------|
| Boris Cherny | recvqRsF12bdFV | 143px "砍掉80%系统提示词" | 308MB, 720p, 35min | 待发布 |
| Sam Altman | recvqRLTD7GdTh | 132px "现在是最好的创业时机" frame_03m54s | 699MB, 1080p, 39min | 待发布 |
| Elon Musk | recvqRLWn773N9 | 145px "AI即将脱离人类控制" | 270MB, 1080p, 10:36 | 待发布 |

三条 B站合规检查全部通过。

### 管线缺陷修复 (4/4)

| 问题 | 修复 | 文件 |
|------|------|------|
| pipeline.py 缺少 B站合规检查 | ⑥-split 后加合规门禁，exit 1阻断/2警告 | `tools/pipeline.py` |
| 封面副标题自动加"猫波信号站" | `gen_cover.py` 硬拦截，含频道名→exit 1 | `tools/gen_cover.py` |
| sync_feishu_to_curation `--help`当日期 | `sys.argv[1]`→argparse，--help正常显示帮助 | `tools/sync_feishu_to_curation.py` |
| 侵权风险字段不写入飞书 | `_feishu.py` 自动评估→`pipeline.py` 回写 | `tools/_feishu.py` + `tools/pipeline.py` |

### 其他修复

- orchestrator 调 pipeline 传 `--feishu-rid` + `--source` 参数
- tips 入库: `dual-entry-gate-drift.md` (多入口门禁不同步)
- 复盘: `D:\workspace\_output\retrospectives\2026-07-30-猫波信号站-管线缺陷修复.md`

## 发布面板标准 (2026-07-30 标准)

| 标准 | 内容 |
|------|------|
| 标题 | 身份+反常识钩子+具体数字, ≤80字 |
| 创作声明 | 内容为转载, 单行来源注明 "转自 URL (频道), 日期" |
| 标签 | 不用"播客翻译""猫波信号站", 8个以内 |
| 简介 | 结构化要点(■), 含来源声明, 不写 hashtag |
| 金句候选 | **已删除** — 自动提取质量太差, 不展示 |
| 合集 | 猫波译站 (写死) |
| 面板顺序 | 1标题→2创作声明→3分区→4标签→5合集→6简介→7章节 |

## 未完成

- EPUB 百度云盘上传 (stage_09)
- B站 CDP 上传 (实验性, 未测通)
- 调度器进程频繁死亡根因排查 (低优先级)

## 约定 (增量)

- gen_publish_panel 是发布面板真相源, agent 不手动编辑 HTML
- metadata.json 必须包含 author/publish_date/source_url 三字段
- 标签不含"播客翻译""猫波信号站"
- 金句候选永久移除, 不恢复
- 微信文章提取: WorkBuddy CodeBuddy CLI, `node "C:\Program Files\WorkBuddy\..."` (coze-wx-extract 已废弃)
- 封面副标题只写人名，不加频道名 — `gen_cover.py` 已硬拦截
- 侵权风险根据来源频道自动评估回写飞书 — `_feishu.py` `assess_copyright_risk()`
- 任何新增门禁步骤，grep 所有入口脚本确认覆盖（pipeline.py / orchestrator.py / cron jobs）

## 路由

- **Sam Altman**: `D:\workspace\_output\猫波信号站\视频\20260730_sam-altman-ZIaOBAjvc38-yc\`
- **Elon Musk**: `D:\workspace\_output\猫波信号站\视频\20260730_elon-musk-1X-rr1DKSbY-the-economist\`
- **Boris Cherny**: `D:\workspace\_output\猫波信号站\视频\20260730_boris-cherny-qyPCVqFUyDo-yc\`
- **飞书**: `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **curation**: `D:\workspace\_output\猫波信号站\视频\_curation\2026-07-30.json`
- **复盘**: `D:\workspace\_output\retrospectives\2026-07-30-猫波信号站-管线缺陷修复.md`

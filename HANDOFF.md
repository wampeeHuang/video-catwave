# HANDOFF · 猫波信号站

> 新会话开始读此文件。覆盖式更新。

## 当前状态

**2026-07-30** — 三视频生产完成。Sam Altman + Elon Musk 新增，Boris Cherny 前序完成。

## 本会话完成

### Sam Altman 视频全流程生产
- 入库 Feishu: `recvqRLTD7GdTh`, 状态 候选→待发布
- 管线 ②→⑧ 全部通过: 下载→Whisper→赞助→翻译→拆分(591→617)→ASS→渲染
- 封面: 132px 字号, 标题 "现在是最好的创业时机", frame_07m11s.jpg
- 成片: 699MB, 1080p, 39min
- 产出: `D:\workspace\_output\猫波信号站\视频\20260730_sam-altman-ZIaOBAjvc38-yc\`

### Elon Musk 视频全流程生产
- 入库 Feishu: `recvqRLWn773N9`, 状态 排除→候选→待发布
- 管线 ②→⑧ 全部通过: 下载→Whisper→赞助→翻译→ASS→渲染
- 封面: 145px 字号, 标题 "AI即将脱离人类控制", frame_09m32s.jpg
- 成片: 270MB, 1080p, 10:36
- 产出: `D:\workspace\_output\猫波信号站\视频\20260730_elon-musk-1X-rr1DKSbY-the-economist\`

### Boris Cherny 视频 (前序会话)
- 入库 Feishu: `recvqRsF12bdFV`, 状态 待发布
- 成片: 308MB, 720p, 35min
- 产出: `D:\workspace\_output\猫波信号站\视频\20260730_boris-cherny-qyPCVqFUyDo-yc\`

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

## 管线改动

| 文件 | 改动 |
|------|------|
| `tools/gen_publish_panel.py` | -金句候选 +创作声明(内容为转载+来源注明) +读author/publish_date/source_url +重排1-7编号 |
| `tools/gen_metadata.py` | +--author +--publish-date +--source-url 参数 → 写入metadata.json |
| `tools/orchestrator.py` | 传author/publish_date/source_url给gen_metadata |
| `tools/validate_panel.py` | 必填字段9→8(-金句+创作声明) |

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
- 两视频直接用 pipeline.py 跑, 绕过 orchestrator (curation 有 MAX_CANDIDATES=5 硬上限)

## 路由

- **Sam Altman**: `D:\workspace\_output\猫波信号站\视频\20260730_sam-altman-ZIaOBAjvc38-yc\`
- **Elon Musk**: `D:\workspace\_output\猫波信号站\视频\20260730_elon-musk-1X-rr1DKSbY-the-economist\`
- **Boris Cherny**: `D:\workspace\_output\猫波信号站\视频\20260730_boris-cherny-qyPCVqFUyDo-yc\`
- **飞书**: `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **curation**: `D:\workspace\_output\猫波信号站\视频\_curation\2026-07-30.json`

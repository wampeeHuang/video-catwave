# HANDOFF · 猫波信号站

> 打开新会话时读此文件，了解当前状态和下一步。

## 当前状态

**2026-06-23 重构**：
- 项目从 skill 模式重构为完整项目结构（参照 OpenMontage）
- 所有工具脚本迁入 `tools/`，skill 改为薄指针
- CLAUDE.md(短) → AGENT_GUIDE.md(全部指令) → PROJECT_CONTEXT.md(架构)
- Cursor 期已完成（待发布），Kevin Weil 期进行中

## Cursor 期进度

| # | 阶段 | 状态 | 产出 |
|---|------|------|------|
| ②-⑧ | 机械段 | ✅ | 全片 Cursor创始人团队：AI编程的未来.mp4 |
| ⑨-⑭ | AI段 | ✅ | 封面/标题/电子书/元数据/专栏/发布面板 |
| ⑯ | 发布 | ❌ | 待发布 |

## Kevin Weil 期进度

| # | 阶段 | 状态 | 文件 |
|---|------|------|------|
| ②-⑦ | 机械段 | ✅ | _runtime/字幕/05.ass（3250条） |
| ⑧ | 测试片 | ✅ | KevinWeil_test90s_v2.mp4（90s） |
| ⑧ | 全片 | ❌ | 未渲染 |
| ⑨ | 金句 | ❌ | |
| ⑩ | 封面 | ⚠️ | cover.jpg 已生成，待人工审核 |
| ⑮ | 发布面板 | ⚠️ | 缺少标签逐个复制/章节/金句字段 |

## 待做

- [ ] Kevin Weil 发布面板对齐 Cursor 标准（标签逐个复制 + 章节 ≤10 + 金句候选）
- [ ] 封面人工审核
- [ ] Kevin Weil 全片渲染
- [ ] Cursor 期发布到 B站
- [ ] Kevin Weil 期发布到 B站

## 架构

```
D:\workspace\lab\2026-06-16-猫波信号站\    ← 项目根目录（唯一真相源）
├── CLAUDE.md              ← 入口 → AGENT_GUIDE.md
├── AGENT_GUIDE.md         ← 全部操作指令
├── PROJECT_CONTEXT.md     ← 架构总览
├── HANDOFF.md             ← 会话交接
├── tools/                 ← 所有阶段脚本 + gen_cover + gen_epub
├── _ref/
│   ├── 生产参数.md         ← 工程参数
│   └── pitfalls.md        ← 11条踩坑记录
└── _runtime/              ← 开发测试临时文件

产出目录：D:\workspace\_output\猫波信号站\
```

## 关键约束

- 工作目录：`cd D:\workspace\lab\2026-06-16-猫波信号站`
- 封面字体 SimHei（不是 msyhbd），2px 黑边填充
- ASS：Outline=0，MarginL/R=200
- 视频文件名 = B站标题，≤80 字
- 标签逐个复制，章节 ≤10 段 HH:MM:SS
- EPUB 全中文，百度云盘分发

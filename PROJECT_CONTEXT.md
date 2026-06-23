# 猫波信号站 · Project Context

YouTube → B站 搬运管线。单一管线项目，非平台。

## 架构

```
Agent 读 AGENT_GUIDE.md → 判断任务 → 执行 tools/*.py
→ 检查 _ref/生产参数.md 参数 → 参考 _ref/pitfalls.md 避坑
→ 产出物落 D:\workspace\_output\猫波信号站\
```

没有 Python 编排器、没有 Python reviewer。Agent 自己驱动管线。

## 真相源

| 层级 | 文件 | 内容 |
|------|------|------|
| 入口 | `CLAUDE.md` | 重定向到 AGENT_GUIDE.md |
| 指令 | `AGENT_GUIDE.md` | 管线流程、阶段索引、门禁、发布模板 |
| 参数 | `_ref/生产参数.md` | 封面/标题/字幕全部工程参数 |
| 坑 | `_ref/pitfalls.md` | 11条踩坑记录，生产前必读 |
| 交接 | `HANDOFF.md` | 会话交接，覆盖更新 |
| 工具 | `tools/` | ③~⑧ + gen_cover + gen_epub + publish |

## 产出目录

```
D:\workspace\_output\猫波信号站\
├── CLAUDE.md              ← 产出目录宪法
├── 频道资产/               ← 头像/签名，频道身份根基
├── 选题库/                 ← 内容源 + 候选池
└── 视频/
    ├── CLAUDE.md           ← 视频目录规范 + 生命周期
    └── <YYYYMMDD_slug>/    ← 每期全周期
```

## 关键约束

- 工具在 `tools/` 下，每个阶段独立脚本，阶段间通过文件通信
- 产出物不在本项目目录——在 `D:\workspace\_output\`
- 每期视频目录结构严格遵循 `视频/CLAUDE.md`
- 封面字体 SimHei，不是 msyhbd
- EPUB 全中文，百度云盘分发

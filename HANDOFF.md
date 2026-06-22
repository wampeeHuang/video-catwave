# HANDOFF · 猫波信号站

> 打开新会话时读此文件，了解当前状态和下一步。

## 当前状态

**2026-06-22 终态**：
- 全片已渲染：`Cursor创始人团队：AI编程的未来.mp4` (1311MB, 2:29:04, H.264+AAC)
- 赞助段已翻译（未裁），无背景框，纯白双语字幕。`_sponsor_cuts.json` = `[]`
- 背景框代码在 stage_07_ass.py 中默认关闭（--bg-opacity 0），色块与文字相对位置不对，暂时搁置
- stage_04 已加 `--min-sponsor-duration` 参数（默认 10s）
- 技能已迁移至 C 盘 `C:\Users\Administrator\.claude\skills\video-catwave\`（全局可用），D 盘副本已归档至 `_archive/`
- ⑫⑬⑭ 全部完成，pitfalls #9-#11 写入 _ref/pitfalls.md，CLAUDE.md 已知坑改为索引表

## 管道进度

| # | 阶段 | 状态 | 产出 |
|---|------|------|------|
| ② | 下载 | ✅ | source.mp4 + 01_raw.srt |
| ③ | 去重叠+标点 | ✅ | 3917碎片→2014短句 |
| ④ | 赞助检测 | ✅ | 0条赞助 cut（唯一赞助段 49.6-54.1s < 10s，已保留翻译） |
| ⑤ | 翻译 | ✅ | 2014条双语字幕 |
| ⑥ | 字宽拆分 | ✅ | 2014→2356行 |
| ⑦ | ASS | ✅ | SimHei 42px + YaHei，Outline=0，MarginL/R=200 |
| ⑧ | 测试片 | ✅ | test_95s.mp4 (95s) |
| ⑧ | 全片 | ✅ | Cursor创始人团队：AI编程的未来.mp4 (1311MB, 2:29:04, H.264+AAC) |
| ⑨ | 金句 | ✅ | "快就是乐趣" + "人类掌控方向盘" |
| ⑩ | 封面 | ✅ | cover.jpg（标题黄上白下，#FFC82D） |
| ⑪ | 标题 | ✅ | Cursor创始团队·LexFridman AI编程：快就是好玩 |
| EPUB | 电子书 | ✅ | 30章双语EPUB (370KB)，百度云盘分发 |
| ⑫ | 元数据 | ✅ | metadata.json（10章节/10标签/554字简介，含百度云盘链接） |
| ⑬ | 专栏 | ✅ | draft.md（引言+10节核心论点+结尾） |
| ⑭ | 发布面板 | ✅ | 发布面板.html（含标题/标签/简介/封面/章节/金句） |

## 踩坑日志（_ref/pitfalls.md）

已收录 11 条，最近 3 条（2026-06-22）：
- #9 B站章节上限 10 段 + HH:MM:SS 格式
- #10 B站标签只能逐个输入
- #11 B站封面 4:3 裁剪安全区

`CLAUDE.md` 已知坑已改为索引表 + 踩坑日志写入标准。

## 已知问题

1. **背景框位置偏差**：色块与文字相对位置不对。代码保留在 stage_07_ass.py（`--bg-opacity` 参数），默认关闭。
2. **EPUB 双语格式**：当前为中英双语对照，考虑调整为全中文输出以更适合 B站 观众。

## 待做

- [ ] EPUB 输出格式调整为全中文
- [ ] 修复背景框位置
- [ ] 发布到 B站（打开发布面板.html → 逐项复制到创作者中心）

## 架构

```
D:\workspace\lab\2026-06-16-猫波信号站\                   ← Lab 根目录（管线 SDK 开发）
│
├── _tools/                             ← 辅助脚本（封面/头像生成等）
├── _ref/                               ← 参考素材 + 生产参数 + 踩坑日志
│   ├── pitfalls.md                     ← 踩坑日志（唯一真相源，生产前必读）
│   └── 生产参数.md                     ← 封面/标题/字幕工程参数
├── _archive/                           ← 历史归档（含旧 skills-video-catwave D 盘副本）
├── CLAUDE.md                           ← 项目硬约束 + 已知坑索引
└── HANDOFF.md                          ← 本文档（会话交接）

技能唯一真相源（C 盘，全局可用）：
C:\Users\Administrator\.claude\skills\video-catwave\
├── SKILL.md                            ← 全流程 14 站定义 + 门禁 + 调用方式
└── tools/
    ├── _lib.py                         ← 共享库
    ├── stage_02_download.py            ← ② 下载
    ├── stage_03_segment.py             ← ③ 去重叠+LLM标点
    ├── stage_04_sponsor.py             ← ④ 赞助检测
    ├── stage_05_translate.py           ← ⑤ 翻译+专名修复
    ├── stage_06_split.py               ← ⑥ 字宽拆分
    ├── stage_07_ass.py                 ← ⑦ ASS+transcript
    ├── stage_08_render.py              ← ⑧ 渲染
    └── gen_cover.py                    ← ⑩ 封面合成

D:\workspace\_output\猫波信号站\视频\20260620_cursor-team-lex-fridman\
│   _runtime/字幕/  ← 01_raw → 02_seg → 02_seg_clean → 03_zh → 04_split → 05.ass
│   _runtime/_sponsor_cuts.json  ← 赞助时间戳
│   _runtime/测试片/  ← test_95s.mp4
│   _runtime/发布面板过程/  ← 发布面板_v1.html（旧版）+ 发布面板.html（新版）
│   _runtime/metadata.json  ← ⑫ B站元数据
│   _runtime/draft.md       ← ⑬ 专栏文章
│   成片/           ← Cursor创始人团队：AI编程的未来.mp4
│   电子书/         ← Cursor创始团队：AI编程的快就是乐趣.epub
│   cover.jpg
│   发布面板.html   ← ⑭ 发布面板（根目录快捷访问）
```

## 关键约束

- yt-dlp 必须 H.264+AAC
- YouTube 需代理 VORTEX_PROXY 127.0.0.1:7897
- DEEPSEEK_API_KEY 用于 ③④⑤
- ffmpeg 渲染 ASS：必须 chdir 到字幕目录用相对路径
- 文件名禁止全角冒号 U+FF1A
- 封面：msyhbd.ttc 纯色无描边，亮度 0.80，#FFC82D，≤4.8MB
- 视频文件名 = B站标题，标题 ≤80 字
- 成片只保留最终交付物，测试片放 _runtime/测试片/
- EPUB 通过百度云盘分发（pan.baidu.com/s/1liyKvWdgW9HbG_exAVUiWg?pwd=1234），B站评论区置顶回复链接
- 所有产物统一落在当期视频输出目录（`视频/YYYYMMDD_slug/`），含电子书/

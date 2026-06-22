# HANDOFF · 猫波信号站

> 打开新会话时读此文件，了解当前状态和下一步。

## 当前状态

**全片已重新渲染（2026-06-22 22:44）**：赞助段已翻译（未裁），无背景框，纯白双语字幕。
`_sponsor_cuts.json` = `[]`，全片走简单烧录路径，无 concat。
背景框功能代码在 stage_07_ass.py 中但**默认关闭**（--bg-opacity 0），因色块与文字相对位置不对，暂时搁置。
stage_04 已加 `--min-sponsor-duration` 参数（默认 10s），短赞助段保留翻译不裁。

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
| EPUB | 电子书 | ✅ | 30章双语EPUB (370KB)，GitHub Releases分发 |
| ⑫ | 元数据 | ✅ | metadata.json（15章节/10标签/475字简介） |
| ⑬ | 专栏 | ✅ | draft.md（引言+10节核心论点+结尾） |
| ⑭ | 发布面板 | ✅ | 发布面板.html（含标题/标签/简介/封面/章节/金句） |

## 已知问题

1. **背景框位置偏差**：色块与文字相对位置不对。代码保留在 stage_07_ass.py（`--bg-opacity` 参数），默认关闭。

## 待做

- [ ] 修复背景框位置
- [ ] 发布到 B站（打开发布面板.html → 逐项复制到创作者中心）

## 架构

```
D:\workspace\lab\2026-06-16-猫波信号站\                   ← Lab 根目录
│
├── .claude/skills/video-catwave/              ← 唯一真相源
│   ├── SKILL.md                         ← 全流程定义 + 门禁标准 + 调用方式
│   └── tools/
│       ├── _lib.py                      ← 共享：SubEntry / SRT读写 / 时间工具 / 路径
│       ├── stage_02_download.py         ← ② yt-dlp 下载
│       ├── stage_03_segment.py          ← ③ 去重叠（30s cap）+ LLM补标点（per-segment）
│       ├── stage_04_sponsor.py          ← ④ 赞助检测 → cuts.json
│       ├── stage_05_translate.py        ← ⑤ DeepSeek 翻译 + 专名修复
│       ├── stage_06_split.py            ← ⑥ 标点优先拆分 + PIL 像素宽度
│       ├── stage_07_ass.py              ← ⑦ ASS + transcript（背景框默认关闭）
│       ├── stage_08_render.py           ← ⑧ ffmpeg（测试片简单烧录/全片concat裁赞助）
│       └── gen_cover.py                 ← ⑩ 封面合成
│
├── _archive/_tools_old/                 ← 旧 _tools/ 归档
└── HANDOFF.md                           ← 本文档

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

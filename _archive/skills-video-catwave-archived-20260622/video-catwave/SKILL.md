---
name: video-catwave
description: |
  YouTube → B站 完整搬运管线，14 阶段流水线。
  
  用法：cd D:\workspace\lab\2026-06-16-猫波信号站；设置 $env:VORTEX_PROXY="127.0.0.1:7897"；$env:DEEPSEEK_API_KEY。
  
  机械段②-⑧（每阶段独立脚本，可单独重跑）：
  ② 下载：python .claude/skills/video-catwave/tools/stage_02_download.py --url "<URL>" --slug <slug>
  ③ 去重叠+LLM标点：python .claude/skills/video-catwave/tools/stage_03_segment.py --slug <slug>
  ④ 赞助检测：python .claude/skills/video-catwave/tools/stage_04_sponsor.py --slug <slug>
  ⑤ 翻译+专名修复：python .claude/skills/video-catwave/tools/stage_05_translate.py --slug <slug>
  ⑥ 字宽拆分：python .claude/skills/video-catwave/tools/stage_06_split.py --slug <slug>
  ⑦ ASS+transcript：python .claude/skills/video-catwave/tools/stage_07_ass.py --slug <slug>
  ⑧ 渲染：python .claude/skills/video-catwave/tools/stage_08_render.py --slug <slug> --title "标题" [--duration 60]
  
  每阶段跑完后人工检查输出文件，不通过→修改脚本→从该阶段重跑。
  
  AI决策段⑨-⑭：金句提取→封面合成→标题→元数据→专栏→发布面板。逐项AI生成+人工确认。
  
  门禁标准：③每段5-15词/④cuts.json有效时间戳/⑤专有名词留英文/⑥中文像素宽≤1520px/⑦Outline=0,MarginL/R=200/⑧音画同步+赞助已裁。
  
  触发：做下一期、做视频、做 <嘉宾> 那期、跑管线、video-catwave、猫波信号站。
  禁止触发：只是下载 YouTube 视频、只是翻译英文、和猫波信号站无关。
---

# 猫波信号站 · 全流程管线

> **唯一真相源**：本文档定义所有阶段的输入/输出/门禁/调用方式。
> 工具脚本在 `tools/` 下，每个阶段一个独立脚本，阶段之间通过 SRT/JSON 文件通信，不传 Python 对象。

## 目录约定

```
Lab（管道代码）:  D:\workspace\lab\2026-06-16-猫波信号站\
  .claude/skills/video-catwave/tools/   ← 所有阶段脚本 + _lib.py
  _runtime/<slug>_process/        ← 下载缓存（source.mp4 + 01_raw.srt）

Output（产出物）: D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\
  _runtime/字幕/                   ← 01_raw → 02_seg → 03_zh → 04_split → 05.ass
  _runtime/_sponsor_cuts.json     ← 赞助时间戳（给 ⑧ 裁视频用）
  _runtime/测试片/                 ← 测试片
  _runtime/发布面板过程/           ← 发布面板旧版归档
  成片/<标题>.mp4
  电子书/<标题>.epub              ← 双语EPUB，百度云盘分发，B站评论区置顶链接
  电子书/百度云盘位置.txt         ← 分享链接+提取码
  cover.jpg
```

## 全流程 14 站

```
① 选题 ──→ ② 下载 ──→ ③ 去重叠+标点 ──→ ④ 赞助检测 ──→ ⑤ 翻译 ──→ ⑥ 字宽检查 ──→ ⑦ ASS ──→ ⑧ 渲染
                 pipeline 机械段（②-⑧，每个阶段一个独立脚本）

⑨ 金句提取 ──→ ⑩ 封面 ──→ ⑪ 标题 ──→ ⑫ 元数据 ──→ ⑬ 专栏 ──→ ⑭ 发布面板
                 Claude AI 决策段（每步需读 transcript 判断）
```

## 机械段 ②-⑧

所有脚本在 `tools/` 下。从 Lab 根目录运行。

```powershell
cd D:\workspace\lab\2026-06-16-猫波信号站
$env:VORTEX_PROXY = "127.0.0.1:7897"
$env:DEEPSEEK_API_KEY = "<key>"

# ② 下载
python .claude/skills/video-catwave/tools/stage_02_download.py --url "<YouTube URL>" --slug <slug>

# ③ 去重叠 + LLM 补标点（→ 短句模式）
python .claude/skills/video-catwave/tools/stage_03_segment.py --slug <slug>

# ④ 赞助检测（→ 02_seg_clean.srt + _sponsor_cuts.json）
python .claude/skills/video-catwave/tools/stage_04_sponsor.py --slug <slug>

# ⑤ 翻译 + 专名修复
python .claude/skills/video-catwave/tools/stage_05_translate.py --slug <slug>

# ⑥ 标点优先拆分 + 像素宽度检查
python .claude/skills/video-catwave/tools/stage_06_split.py --slug <slug>

# ⑦ ASS + transcript（背景框实验性功能，默认关闭）
python .claude/skills/video-catwave/tools/stage_07_ass.py --slug <slug> [--bg-opacity 0.5] [--bg-padding 15]

# ⑧ 渲染（--duration 60 做测试片，不传 = 全片；测试片用 --output-subdir "_runtime/测试片"）
python .claude/skills/video-catwave/tools/stage_08_render.py --slug <slug> --title "output" [--duration 60] [--output-subdir "_runtime/测试片"]
```

## 各阶段门禁

| # | 阶段 | 输入 | 输出 | 门禁检查 |
|---|------|------|------|----------|
| ② | 下载 | YouTube URL | `source.mp4` + `01_raw.srt` | MP4 存在且 H.264+AAC；SRT 有 5000-15000 条碎片 |
| ③ | 去重叠+标点 | `01_raw.srt` | `02_seg.srt` | 每段 5-15 词；时间戳来自源碎片（不重新计算）；跨非重叠碎片不合并 |
| ④ | 赞助检测 | `02_seg.srt` | `02_seg_clean.srt` + `_sponsor_cuts.json` | 行数 ≤ ③；抽检被剔段落确为赞助；cuts.json 有有效时间戳 |
| ⑤ | 翻译 | `02_seg_clean.srt` | `03_zh.srt` | 行数 = ④；专有名词留英文；中文语义通顺 |
| ⑥ | 字宽 | `03_zh.srt` | `04_split.srt` | 中文像素宽 ≤1520px（SimHei 42px）；拆分点在标点处 |
| ⑦ | ASS | `04_split.srt` | `05.ass` + `transcript.txt` | Outline=0；MarginL/R=200；无重叠字幕 |
| ⑧ | 渲染 | `05.ass` + `source.mp4` + `_sponsor_cuts.json` | `成片/<title>.mp4` | 帧数=时长×fps；音画同步；赞助片段已裁 |

### 门禁检查方式

每阶段跑完后，人工检查输出文件。不通过 → 修改对应阶段脚本 → 从该阶段重跑。

| 要改什么 | 从哪个阶段重跑 | 花费 |
|----------|---------------|------|
| 断句粒度 | ③ → ④ → ⑤ → ⑥ → ⑦ → ⑧ | ~$0.20 + 30min |
| 翻译质量/专名 | ⑤ → ⑥ → ⑦ → ⑧ | ~$0.15 + 30min |
| 字宽阈值 | ⑥ → ⑦ → ⑧ | 免费 + 30min |
| ASS 样式 | ⑦ → ⑧ | 免费 + 30min |
| 赞助检测策略 | ④ → ⑤ → ⑥ → ⑦ → ⑧ | ~$0.17 + 30min |

## AI 决策段 ⑨-⑭

> 工作目录：先 cd 到当期视频输出目录。以下相对路径以此为基准。

```powershell
cd D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>
```

### ⑨ 金句提取
- 读 `_runtime/字幕/transcript.txt`
- 提取 5 条候选金句（4-12 字、有反差/数字、来自嘉宾）
- 选最优 1-2 句

### ⑩ 封面
- 从 ⑨ 金句取最优 3 句 → 在 transcript 中定位时间戳 → ffmpeg 截图 → 肉眼评分
- `python D:\workspace\lab\2026-06-16-猫波信号站\.claude\skills\video-catwave\tools\gen_cover.py <frame.jpg> cover.jpg --title "<金句>" --sub "<嘉宾·来源>" --source "YouTube · <频道>" --brightness 0.80 --color "#FFC82D"`
- 约束：msyhbd.ttc 纯色无描边、#FFC82D、0.80 亮度、≤4.8MB、1920×1080
- **4:3 安全区**：B站首页推荐裁剪 16:9→4:3（1440×1080），左右各裁 240px。标题超过 1320px（SAFE_W 1440 - SAFE_PAD 60×2）自动缩字。gen_cover.py 已内置 auto-shrink 逻辑

### ⑪ 标题
- 格式：`嘉宾身份 + 嘉宾名：核心论断`
- ≤80 字，生成 3-5 候选

### ⑫ 元数据
- 标签 ≤10 个、每个 ≤12 字、简介 ≤2000 字
- 章节 ≥2 个且 ≤10 个（B站硬上限），格式 `HH:MM:SS 章节标题`（必须带小时位）
- 章节间隔 ≥5 秒，时间戳不重叠，按时间递增
- 生成 `_runtime/metadata.json`（chapters/tags/description）和 `_runtime/chapters_bilibili.json`（B站导入格式：`start_time` 秒 + `title`）

### ⑬ 专栏
- 写 `_runtime/draft.md`：引言 → 10 节核心论点 → 结尾

### ⑭ 发布面板
- 生成 `发布面板.html`（标题/标签/简介/封面/分区/合集/章节/金句），落盘到视频根目录和 `_runtime/发布面板过程/`
- 每个标签旁带独立「复制」按钮（B站标签只能逐个输入，不能批量粘贴）
- 章节用 `HH:MM:SS 章节标题` 格式，全量复制后一键贴入 B站章节文本编辑器
- B站章节入口：创作中心 → 稿件管理 → 视频右侧「···」→ 个性化配置 → 分段章节
- 人工去 B站创作者中心逐项复制发布

## 首版质量检查（自动触发）

| # | 检查项 | 方法 | 标准 |
|---|--------|------|------|
| 1 | 字幕样式 | 读 `05.ass` Style 行 | Outline=0, MarginL=200, MarginR=200 |
| 2 | 字幕重叠 | 渲染后拖进度条 | 全程无两条字幕同时显示 |
| 3 | 专有名词 | 随机抽 10 条翻译 | Cursor/Claude/GPT 等留英文 10/10 |
| 4 | 字幕长度 | 读 `04_split.srt` 检查中文像素宽 | 全行 ≤1520px |
| 5 | 封面字体 | 打开 cover.jpg | 纯色粗体无黑边 |

## 关键约束

- yt-dlp 必须 H.264+AAC
- YouTube 需代理 VORTEX_PROXY 127.0.0.1:7897
- DEEPSEEK_API_KEY 用于 ③④⑤ 三个阶段
- ffmpeg 渲染 ASS 用相对路径（Windows 盘符冒号被当 filter 分隔符）
- 文件名禁止全角冒号 U+FF1A
- EPUB 通过百度云盘分发（链接 + 提取码写入 `电子书/百度云盘位置.txt`），B站评论区置顶回复
- 视频文件名 = B站标题，标题 ≤80 字
- 封面：msyhbd.ttc 纯色无描边，亮度 0.80，#FFC82D，≤4.8MB
- ASS：SimHei 42px + Microsoft YaHei 底栏，纯白无描边
- B站发布格式清单：

| 字段 | 格式 | 限制 |
|------|------|------|
| 标题 | 纯文本 | ≤80 字 |
| 标签 | 逐个输入 | ≤10 个，每个 ≤12 字 |
| 章节 | `HH:MM:SS 标题` | ≤10 段，间隔 ≥5s，必须带小时位 |
| 简介 | 纯文本 | ≤2000 字 |
| 封面 | 16:9 JPG | ≤4.8MB，首页推荐裁为 4:3 |
| 分区 | 知识 → 科技 → 人工智能 | — |
| 合集 | 猫波译站 | — |

## 文件指针

```
.claude/skills/video-catwave/SKILL.md              ← 本文档：唯一真相源
.claude/skills/video-catwave/tools/_lib.py          ← 共享库
.claude/skills/video-catwave/tools/stage_02_*.py    ← ② 下载
.claude/skills/video-catwave/tools/stage_03_*.py    ← ③ 去重叠+标点
.claude/skills/video-catwave/tools/stage_04_*.py    ← ④ 赞助检测
.claude/skills/video-catwave/tools/stage_05_*.py    ← ⑤ 翻译
.claude/skills/video-catwave/tools/stage_06_*.py    ← ⑥ 字宽检查
.claude/skills/video-catwave/tools/stage_07_*.py    ← ⑦ ASS
.claude/skills/video-catwave/tools/stage_08_*.py    ← ⑧ 渲染
.claude/skills/video-catwave/tools/gen_cover.py     ← ⑩ 封面合成
D:\workspace\_output\猫波信号站\选题库\飞书选题库.md  ← 选题库
D:\workspace\lab\2026-06-16-猫波信号站\生产方法论.html ← 完整方法论
```

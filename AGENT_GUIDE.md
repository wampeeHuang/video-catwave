# 猫波信号站 · Agent Guide

YouTube → B站 搬运管线。本文件每次对话自动加载，是所有操作的唯一指令源。

## 0. 先判断任务

收到用户消息后，先判断属于哪类，再执行：

| 用户意图 | 动作 |
|---------|------|
| 做新一期视频 | 读 §1 管线流程，从 ② 开始 |
| 重跑某个阶段 | 读 §2 阶段索引，找到对应脚本 |
| 生成封面 | 读 §3 封面工作流 + `_ref/生产参数.md` §1 |
| 做发布面板 | 读 §4 发布面板模板 |
| 发布到B站 | 读 §5 B站发布 |
| 修bug/改参数 | 读对应工具源码 + `_ref/pitfalls.md` |

## 1. 管线流程

```
② 下载 ──→ ③ 去重叠+标点 ──→ ④ 赞助检测 ──→ ⑤ 翻译 ──→ ⑥ 字宽检查 ──→ ⑦ ASS ──→ ⑧ 渲染
               机械段（每阶段独立脚本，可单独重跑）

⑨ 金句提取 ──→ ⑩ 封面 ──→ ⑪ 标题 ──→ ⑫ 电子书 ──→ ⑬ 元数据 ──→ ⑭ 专栏 ──→ ⑮ 发布面板 ──→ ⑯ B站发布
                AI 决策段（每步需读 transcript 判断）
```

### 环境

```powershell
cd D:\workspace\lab\2026-06-16-猫波信号站
$env:VORTEX_PROXY = "127.0.0.1:7897"
$env:DEEPSEEK_API_KEY = "<key>"
```

### 产出目录

```
D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\
├── cover.jpg              ← 封面 1920×1080（SimHei 165px + 2px黑边）
├── 发布面板.html           ← 标题/标签/简介/章节/金句
├── 成片/<B站标题>.mp4       ← 最终视频
├── _runtime/
│   ├── 素材/source.mp4     ← yt-dlp 下载
│   ├── 字幕/01~05          ← 管线中间产物
│   ├── frames/             ← 截图（封面素材）
│   ├── draft.md            ← 专栏草稿
│   └── run.log
└── .published              ← 发布后创建
```

## 2. 阶段索引

所有脚本在 `tools/` 下。从项目根目录运行。

```powershell
# ② 下载
python tools/stage_02_download.py --url "<YouTube URL>" --slug <slug>

# ③ 去重叠 + LLM 补标点
python tools/stage_03_segment.py --slug <slug>

# ④ 赞助检测
python tools/stage_04_sponsor.py --slug <slug>

# ⑤ 翻译 + 专名修复
python tools/stage_05_translate.py --slug <slug>

# ⑥ 标点优先拆分 + 像素宽度检查
python tools/stage_06_split.py --slug <slug>

# ⑦ ASS + transcript
python tools/stage_07_ass.py --slug <slug>

# ⑧ 渲染（--duration 60 做测试片）
python tools/stage_08_render.py --slug <slug> --title "标题" [--duration 60]
```

### 重跑规则

| 要改什么 | 从哪个阶段重跑 |
|----------|---------------|
| 断句粒度 | ③ → ④ → ⑤ → ⑥ → ⑦ → ⑧ |
| 翻译质量/专名 | ⑤ → ⑥ → ⑦ → ⑧ |
| 字宽阈值 | ⑥ → ⑦ → ⑧ |
| ASS 样式 | ⑦ → ⑧ |
| 赞助检测策略 | ④ → ⑤ → ⑥ → ⑦ → ⑧ |

### 门禁

| 阶段 | 检查项 | 标准 |
|------|--------|------|
| ③ | 断句粒度 | 每段 5-15 词 |
| ④ | 赞助检测 | 抽检被剔段落确为赞助 |
| ⑤ | 翻译 | 行数=④，专名留英文 |
| ⑥ | 字宽 | 中文像素宽 ≤1520px（SimHei 42px） |
| ⑦ | ASS | Outline=0，MarginL/R=200 |
| ⑧ | 渲染 | 音画同步，赞助已裁 |

## 3. 封面工作流

**必须按此顺序：**

```
1. 从 transcript.txt 提取 5 条候选金句（4-12 字、有反差/数字、来自嘉宾）
2. 定位金句时间戳 → ffmpeg 截图至少 5 帧 → 选主讲人正脸最清晰的一张
3. 读 draft.md 确认标题文案
4. python tools/gen_cover.py <frame.jpg> <cover.jpg> \
     --title "<金句>" --sub "<嘉宾身份> · <来源>" --source "<YouTube频道>"
5. 落盘到产出目录根目录 cover.jpg
```

**关键参数**（来源 `_ref/生产参数.md` §1）：
- 画布 1920×1080，亮度 0.80
- 主标题 SimHei 165px 暖黄 #FFC82D，≤15 字
- 副标题 SimHei 62px 暖白 #FCFAF5
- 出处行 SimHei 28px 暖白
- 文字 2px 黑色 8 方向填充模拟超粗
- 装饰线 120×4px 暖黄
- 4:3 安全区 SAFE_W=1440，文字超宽自动缩字
- JPG ≤4.8MB

## 4. 发布面板模板

**文件位置**：`D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\发布面板.html`

**必须包含以下字段，每个字段独立复制按钮**：

```html
1. 标题（≤80字）— 嘉宾身份 + 嘉宾名：核心论断
2. 标签（≤10个）— 每个标签旁独立「复制」按钮，逐个复制粘贴
3. 分区 — 知识 > 科技 > 人工智能
4. 合集 — 猫波译站
5. 简介（≤2000字）— 含字数统计、EPUB百度云盘链接
6. 章节（≤10个）— 格式 HH:MM:SS 标题，全量复制一键粘贴
7. 金句候选 — 5条候选金句
8. 封面信息 — 文件大小、尺寸、设计参数
9. 视频文件 — 文件名、大小、编码
```

**标签规则**：
- B站标签只能逐个输入，不能批量粘贴
- 每个标签用独立 `<button>` 调用 `navigator.clipboard.writeText()`

**章节规则**：
- ≤10 段（B站硬上限）
- 格式 `HH:MM:SS 标题`（必须带小时位）
- 间隔 ≥5 秒，按时间递增
- 入口：创作中心 → 稿件管理 → 视频右侧「···」→ 个性化配置 → 分段章节

## 5. B站发布

Chrome DevTools MCP 浏览器自动化。详见 `_ref/pitfalls.md` §8-11。

**前置条件**：Chrome DevTools MCP 已连接，浏览器已登录 B站。

**流程**：
1. 上传视频 → 2. 填标题 → 3. 选分区 → 4. 逐个加标签 → 5. 填简介（Quill编辑器）→ 6. 上传封面 → 7. 存草稿

## 6. 文件纪律

- 所有产出物落 `D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\`
- 封面固定 `cover.jpg`，不保留多版本
- 成片只放最终交付物，测试片放 `_runtime/`
- `_runtime/` 保留溯源，发布后不删
- 视频文件名 = B站标题（≤80 字）
- 文件名禁止全角冒号 U+FF1A
- 每会话结束写 HANDOFF.md

## 7. 决策日志

每期视频的决策（选帧、标题候选、布局选择）写入当期 `_runtime/draft.md` 或 HANDOFF.md。不在本文件追加。

## 8. 参考文件

| 文件 | 内容 |
|------|------|
| `_ref/生产参数.md` | 封面/标题/字幕全部工程参数 |
| `_ref/pitfalls.md` | 11条踩坑记录（生产前必读） |
| `PROJECT_CONTEXT.md` | 项目架构总览 |
| `生产方法论.html` | 统一方法论入口（人类可读） |

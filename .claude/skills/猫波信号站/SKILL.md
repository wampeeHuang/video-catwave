---
name: 猫波信号站
description: |
  YouTube → B站 完整搬运管线。全流程 ①-⑭：选题→下载→断句→赞助检测→翻译→判定→ASS→渲染→金句→封面→标题→元数据→专栏→发布。

  触发：做下一期、做视频、做 <嘉宾> 那期、跑管线、做 Cursor Team、做 Kevin Weil、新一期、pipeline 跑完了接下来怎么办。
  Do NOT trigger when: 只是下载一个 YouTube 视频、只是翻译一段英文、和猫波信号站项目无关的对话。
---

# 猫波信号站 · 全流程管线

> pipeline.py 做机械段（②-⑦），Claude 做 AI 决策段（⑧-⑬）。本 skill 是总指挥。

## 触发后第一步：确定目标

用户说"做下一期"→ 查飞书选题库取最高分候选；说"做 <嘉宾>"→ 查飞书取对应行。

飞书 API：`D:\workspace\_output\猫波信号站\选题库\飞书选题库.md`

## 全流程 14 站

```
① 选题 ──→ ② 下载 ──→ ③ 断句 ──→ ④ 赞助检测 ──→ ⑤ 翻译 ──→ ⑥ 判定 ──→ ⑦ ASS ──→ ⑧ 渲染
                  pipeline.py 机械段（②-⑧，一键跑完）
                  
⑨ 金句提取 ──→ ⑩ 封面 ──→ ⑪ 标题 ──→ ⑫ 元数据 ──→ ⑬ 专栏 ──→ ⑭ 发布
                  Claude AI 决策段（每步需读 transcript 判断）
```

## 机械段 ②-⑧：pipeline.py

```powershell
cd D:\workspace\lab\2026-06-16-猫波信号站
$env:VORTEX_PROXY="127.0.0.1:7897"

# 阶段门禁（推荐迭代方式）
python pipeline.py segment --slug <slug>                  # ② LLM断句
python pipeline.py translate --slug <slug>               # ④⑤ 翻译+字宽限制
python pipeline.py ass --slug <slug>                     # ⑥⑦ 生成ASS+transcript
python pipeline.py render --slug <slug> [--duration 120] # ⑧ 渲染（--duration 做测试片）
python pipeline.py render --slug <slug> --output-title "<B站标题>"  # 正式成片

# 一键全流程
python pipeline.py all <YouTube URL> --slug <slug> --output-title "<B站标题>"
```

可选：`--skip-download` `--skip-sponsor-check` `--max-chars 36`（默认36）

目录布局：
- **Lab（管道代码+源视频）**: `D:\workspace\lab\2026-06-16-猫波信号站\_runtime\<slug>_process\`
- **Output（产出物）**: `D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\`
  - `_runtime/字幕/` 01_raw.srt → 02_seg.srt → 02_seg_clean.srt → 03_zh.srt → 04_split.srt → 05.ass
  - `成片/<标题>.mp4`

## AI 决策段 ⑨-⑭：Claude 逐步执行

> **工作目录：** 先 `cd` 到当期视频输出目录（如 `D:\workspace\_output\猫波信号站\视频\20260620_cursor-team-lex-fridman`）。
> 以下所有相对路径（`_runtime/`、`成片/`、`cover.jpg`）均以此为基准。

### ⑨ 金句提取
读 `_runtime/字幕/transcript.txt`，提取 5 条候选金句（4-12字、有反差/数字、来自嘉宾）。选最优 1-2 句。

### ⑩ 封面

封面是 B站信息流中 50% 的点击驱动。遵循生产方法论 §2 的完整设计链。

**10.1 截图选帧（方法论 §2 选帧 v2）**
1. 从 ⑨ 金句结果中取最优 3 句
2. 在 transcript.txt 中定位每句对应的时间戳
3. 用 ffmpeg 精确定位取帧（已 cd 到视频输出目录）：
   ```powershell
   ffmpeg -ss <timestamp> -i "_runtime\素材\source.mp4" -vframes 1 "_runtime\frames\candidate_N.jpg"
   ```
4. 肉眼评分选最优帧。评分维度：**清晰度 > 表情 > 构图（留白）> 光照**
5. 排除：纯代码/文档页、人物模糊、背景杂乱、无留白放文字

**10.2 布局选择**
根据选中的帧内容特征，选一种布局：

| 布局 | 条件 | 特征 |
|------|------|------|
| **A（首选）** | 人物偏左/右，另一侧有均匀背景 | 人物半身 40% + 文字 60% |
| **B** | 底图信息丰富、无大面积留白 | 全幅底图 + 半透明黑底衬文字 |
| **C** | 单人正脸居中、头顶有空间 | 文字居顶/底，不挡脸 |
| **D** | 底图不够大或构图偏下 | 上 35% 纯色区放文字 + 下 65% 图 |

**10.3 多方案择优**
生成至少 3 个候选方案（不同金句 × 不同帧 × 不同布局），在浏览器中对比，选视觉冲击力最强的。

**10.4 合成（gen_cover.py）**
```powershell
python D:\workspace\lab\2026-06-16-猫波信号站\_tools\gen_cover.py `
  "_runtime\frames\<best>.jpg" "cover.jpg" `
  --title "<4-8字金句>" --sub "<嘉宾·来源>" `
  --source "YouTube · <频道>" `
  --brightness 0.80 --color "#FFC82D"
```

**10.5 协同检查（封面+标题互补）**
- 封面用 4-8 字金句制造好奇心
- 标题用完整句式（嘉宾身份+嘉宾名：核心论断）提供权威背书
- 两者不重复——封面抛钩、标题展开

约束：msyhbd.ttc（微软雅黑 Bold，纯色无描边）、#FFC82D、0.80 亮度、≤4.8MB、1920×1080。
详见 `生产方法论.html §2`。

### ⑪ 标题
格式：`嘉宾身份 + 嘉宾名：核心论断`。≤80字。生成 3-5 候选，选最优。

### ⑫ 元数据
标签 ≤10个×12字、简介 ≤2000字（核心论点+嘉宾+出处）、章节时间戳 mm:ss。

### ⑬ 专栏
从 transcript 写 `_runtime/draft.md`：引言→核心论点分节→结尾。

### ⑭ 发布面板
生成 `发布面板.html`（标题/标签/简介/封面预览/分区/合集）。人工去 B站 创作者中心发布。

## 首版完成后质量检查（自动触发）

首版完成后逐项检查，不等用户提意见：

| # | 检查项 | 方法 | 通过标准 |
|---|--------|------|----------|
| 1 | **字幕样式** | 读 `_runtime/字幕/05.ass` → 检查 Style 行 | `Outline=0, MarginL=200, MarginR=200` |
| 2 | **字幕重叠** | 渲染后拖进度条检查 | 全程无两段字幕同时显示 |
| 3 | **专有名词** | 随机抽 10 条翻译，检查 Cursor/Claude/GPT 等是否留英文 | 10/10 正确 |
| 4 | **封面字体** | 打开 cover.jpg → 检查字体粗细和边缘 | 纯色粗体无黑边 |
| 5 | **封面底图** | 检查是否有视觉吸引力 | 有人脸/非纯代码页 |

**发现问题处理路径：**
- **系统性问题**（多期复现）→ 修 pipeline.py / gen_cover.py → 更新生产方法论 §5.5 → 重跑当前期
- **本期个案** → 手动修复 → 记录到 `_runtime/pitfalls.md`
- **方向性问题**（需新方案）→ 标注待定案 → 下期迭代

详见 `生产方法论.html §5.5 改期问题处理`。

## 关键文件指针

```
D:\workspace\lab\2026-06-16-猫波信号站\pipeline.py          ← 机械管线
D:\workspace\lab\2026-06-16-猫波信号站\_tools\gen_cover.py  ← 封面合成脚本
D:\workspace\lab\2026-06-16-猫波信号站\生产方法论.html       ← 完整方法论
D:\workspace\_output\猫波信号站\选题库\飞书选题库.md         ← 选题库 API
D:\workspace\_output\猫波信号站\视频\CLAUDE.md              ← 视频规范
~/.agentboard/tools/catwave-pipeline/manifest.json         ← 工具架
```

## 关键约束

- yt-dlp 必须 H.264+AAC
- ffmpeg 渲染 ASS 用相对路径（盘符 `:` 被当成 filter 分隔符）
- 文件名禁止全角冒号 U+FF1A
- 赞助商检测在翻译前自动执行
- **封面字体 msyhbd.ttc（微软雅黑 Bold），纯色无描边**，亮度 0.80，#FFC82D
- **翻译专有名词白名单**（Cursor/Claude/Copilot 等 ~50 词留英文），在 pipeline.py `_translate_batch()` 维护
- **ASS 字幕纯白无描边**（Outline=0, Shadow=0, MarginL/R=200），重叠裁剪
- 视频文件名 = B站标题，标题 ≤80 字
- DEEPSEEK_API_KEY 用于翻译+赞助检测
- YouTube 需代理 VORTEX_PROXY 127.0.0.1:7897

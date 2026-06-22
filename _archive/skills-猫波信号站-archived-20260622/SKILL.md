---
name: 猫波信号站
description: YouTube → B站 完整搬运管线——下载、断句、翻译、双语字幕压制、封面生成、B站元数据。覆盖 yt-dlp、DeepSeek 翻译、ASS 双语字幕、PIL 封面、B站上传全套。
argument-hint: <command> [url] [--skip-download] [--skip-translate]
allowed-tools: Bash, Read, Write, Edit, PowerPoint, WebFetch
---

# 猫波信号站

把 YouTube 英文视频搬运到 B站，加上双语字幕 + 封面 + 元数据，全流程。

## 前置：读取项目知识库

**每次生产前必须读：**

| 文件 | 做什么用 |
|------|---------|
| `CLAUDE.md` | 硬约束（命名红线、管线步骤、已知坑） |
| `选题方法论.md` | 选什么视频、评分标准、排除项、内容发现策略 |
| `_ref/生产参数.md` | 封面/标题/字幕全部工程参数（唯一真相源） |
| `_ref/pitfalls.md` | 完整踩坑日志、错误签名→修复方案 |
| `生产方法论.html` | 统一方法论入口—人类可读视图，参数细节以 `_ref/生产参数.md` 为准 |

项目根: `D:\workspace\lab\2026-06-16-猫波信号站\`
产出目录: `D:\workspace\_output\猫波信号站\`
选题库: `D:\workspace\_output\猫波信号站\选题库\`（内容源 + 候选池 + 已发布 + 已废弃）

## 角色人设路由

**进入每个阶段前，必须先 Read 对应人设文件，以该视角做判断：**

| 阶段 | 负责人 | 人设文件 | 核心判断 |
|------|--------|---------|---------|
| §0 任务书/选题 | Zara Zhang | `~/.claude/skills/perspective-router/references/perspective-zara-zhang.md` | 这期内容 B站 AI 观众需要知道吗？ |
| §1 案例分析 | 潘乱 | `~/.claude/skills/perspective-router/references/perspective-panluan.md` | 底层结构是什么？哪段是肉哪段是骨架？ |
| §2 封面&标题 | 李晨阳 (LKs) | `~/.claude/skills/perspective-router/references/perspective-lks.md` | B站信息流刷到，手指会停吗？ |
| §3 管线&制作 | Karpathy | `~/.claude/skills/perspective-router/references/perspective-andrej-karpathy.md` | 换人换机器，照着文档能跑出一样结果吗？ |
| §4 发布&复盘 | Karpathy | `~/.claude/skills/perspective-router/references/perspective-andrej-karpathy.md` | 发布完整吗？复盘有可操作教训吗？ |

**规则**：不跳过。阶段开始 → 读人设 → 以该视角判断 → 产出。

## 核心流程

```
选题评估 → 下载 → 提取文稿 → 断句 → 翻译 → 字数控制 → 生成ASS → 压制
                                                               ↓
                                          B站发布：标题 → 封面 → 发布面板HTML → 搬产出目录
```

## 输出结构

**管线过程文件**在项目 `_runtime/<video_slug>/`：

```
_runtime/<video_slug>/
  _process/              ← 管线中间产物（支持断点续跑）
    01_raw.srt ~ 05.ass + transcript.txt
  frames/                ← 视频截图（封面素材）
  output/                ← 临时输出（mp4 + cover）
```

**最终成品**搬至产出目录 `D:\workspace\_output\猫波信号站\视频/YYYYMMDD_标题/`（详见该目录 CLAUDE.md）:

```
视频/YYYYMMDD_标题/
├── 成片/<标题>.mp4
├── cover.jpg
├── 发布面板.html
└── _runtime/字幕/  frames/  draft.md  run.log
```

## 命令

```bash
cd D:\workspace\lab\2026-06-16-猫波信号站

# 全流程
python pipeline.py all <youtube_url>

# 跳过下载
python pipeline.py all <url> --skip-download

# 跳过翻译
python pipeline.py all <url> --skip-translate
```

## 技术步骤（pipeline.py）

### 1. 下载
yt-dlp ≤1080p H.264+AAC（B站兼容），英文自动字幕转 SRT。

### 2. 断句
合并逐词碎片为完整句子，按句尾标点断句，carryover 裁剪（只裁文本，不移时间戳）。目标 ~18 英文词/句。

### 3. 翻译
DeepSeek API 批量翻译 EN→ZH，双语 SRT（中文在上，`\N` 分隔）。并行每批 10 条。Key 从 `DEEPSEEK_API_KEY` 环境变量读取。

### 4. 字数控制
`enforce_max_chars(srt_path, max_chars=28)` — 中文超 28 字在中文标点处拆分，按字数比例分配时间戳。

### 5. ASS 生成
`srt_to_ass(srt_path)` — 单事件双语：`{\fnSimHei\fs42}中文\N{\fnSegoe UI\fs32\b1}English`。中上英下，1920×1080，MarginV=45。

### 6. 压制
FFmpeg 烧录 ASS，H.264 CRF 23，AAC 128k。输出文件名 = B站标题。

## B站 发布步骤

### 7. 标题
≤80 字。从 transcript 提取最独特/反直觉的论断，不是通用描述。不含「双语字幕」后缀（占字数）。
格式：`Claude Code 之父 Boris Cherny：{核心论断}`

### 8. 封面（_tools/gen_cover.py）
- 底图：视频截图（主讲人正脸），亮度 0.80（黑色透明度 80%）
- 字体：SimHei（系统最粗中文），四周 2px 填充模拟超粗
- 主色：暖黄 #FFC82D，辅色：暖白 #FCFAF5
- 布局：全部居中，3 行文字 + 1 条装饰线 + 底部信息条
- 不加频道水印
- 截图至少 5 个时间点，选正脸最清晰的一张，其余删除

### 9. 简介 & 标签
- 简介 ≤2000 字：核心论点 + 嘉宾信息 + 出处 + hashtag
- 标签 ≤10 个，每个 ≤12 字
- 分区：知识 > 科技 > 人工智能

### 10. 专栏文章
从翻译 transcript 提取结构：引言 → 核心论点分节展开 → 结尾。B站专栏 markdown。

### 11. B站 上传
- 视频文件命名 = 标题（B站自动识别填入）
- 合集：猫波译站
- 转载出处：原作者、原平台、原链接

## B站 频道资产

| 项目 | 值 |
|------|-----|
| 昵称 | 猫波信号站 |
| UID | `bili51931896575` |
| 签名 | 猫波雷达滴滴响——又有好信号来了！ |
| 合集 | 猫波译站 |
| 头像 | avatar_catwave_v3.png（1024×1024，浅暖白，脉冲雷达图形） |
| 昵称检测 | WebFetch 搜 `search.bilibili.com/upuser?keyword=xxx`，"用户0"=可用 |

## 已知坑

- **全角冒号 U+FF1A** 在文件名中导致 shell 编码错误，用 Python Path 对象绕过
- **yt-dlp**：必须指定 H.264(`avc1`)+AAC(`m4a`)，否则拿 webm/vp9（B站不兼容）
- **enforce_max_chars** 签名：`(srt_path, max_chars=28)`，不是 `(srt_path, output_path)`
- **srt_to_ass** 不接受 `video_size` 参数
- **B站 API 反爬**：API 直接调用返回 HTML 错误页，检查昵称用 WebFetch
- **封面透明度**："透明度 80%"= 透明度高= 原图几乎全透，不是 80% 不透明。亮度 0.80
- **封面字体**：Windows 上 SimHei 是唯一粗体中文字体，NotoSansSC-VF 是可变字体但 PIL 不支持轴参数
- **gpt-image-2** 走 aigoapi（key 在 memory），`b64_json` 可能空，用 `response_format="url"` + curl 下载
- **ASS 单事件 > 双事件**：用 `\N` 分隔中英文，双 Dialogue 事件会被 libass 碰撞检测吞掉
- **ASS 颜色编码**：`&HAABBGGRR&`，Alignment=2 底部居中
- **carryover 裁剪**：只裁文本不裁时间戳，避免字幕闪烁

## 待扩展

- **掐头去尾自动化**：基于语音稿自动检测低密度段
- **内容评估自动化**：信息密度评分（语音占比、观点密度、演示占比）
- **术语表/上下文翻译**：技术名词一致性，上下文窗口传递
- **字幕同步修正**：全局时间偏移，解决 YouTube 字幕固有延迟
- **多 API 翻译**：支持切换翻译后端

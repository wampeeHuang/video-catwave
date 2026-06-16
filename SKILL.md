---
name: youtube-content-pipeline
description: YouTube → B站 完整搬运管线——下载、断句、翻译、双语字幕压制、封面生成、B站元数据。覆盖 yt-dlp、DeepSeek 翻译、ASS 双语字幕、PIL 封面、B站上传全套。
argument-hint: <command> [url] [--skip-download] [--skip-translate]
allowed-tools: Bash, Read, Write, Edit, PowerPoint, WebFetch
---

# YouTube Content Pipeline · 猫波信号站

把 YouTube 英文视频搬运到 B站，加上双语字幕 + 封面 + 元数据，全流程。

## 核心流程

```
下载 → 提取文稿 → 内容评估 → [通过] 掐头去尾 → 断句 → 翻译 → 字数控制 → 生成ASS → 压制
                                                                                    ↓
                                                                          B站发布：标题 → 封面 → 简介 → 标签 → 专栏
```

## 输出结构

每期视频独立文件夹，位于项目 `_runtime/<video_slug>/`（英文下划线命名，如 `boris_sequoia_2026`）：

```
_runtime/<video_slug>/
  _process/                     # 管线中间产物（支持断点续跑）
    01_raw.srt                  # yt-dlp 原始英字
    02_seg.srt                  # 断句后
    03_zh.srt                   # 翻译后（双语）
    04_split.srt                # 字数控制后（≤28字）
    05.ass                      # ASS 字幕
    transcript.txt              # 提取的纯文本
  frames/                       # 视频截图（封面素材）
    frame_0900s.jpg             # 截到主讲人正脸，其余删除
  output/                       # 最终交付物
    <B站标题>.mp4               # 渲染成品，文件名 = B站标题
    cover.jpg                   # 封面 1920×1080 JPG ≤5MB
    B站上传信息.txt              # 标题/标签/简介/出处
    B站专栏文章.md               # 可发布专栏
```

`_process/` 和 `output/` 彻底分离。`_process/` 按 step 编号，`output/` 只放上传 B站 需要的 4 个文件。yt-dlp 原始 mp4 下载到 `_process/`，渲染后手动清理（不入 git）。

## 命令

```bash
cd D:\Claude code_workspace\2026-06-16-youtube-content-pipeline

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
| 签名 | 猫波雷达滴滴响——又有好信号来了！🐾 |
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

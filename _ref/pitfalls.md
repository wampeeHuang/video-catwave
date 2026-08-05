# 踩坑日志 · YouTube Content Pipeline

> 项目专用的踩坑记录。格式：现象 → 根因 → 修复 → 预防。
> 跨项目通用坑写入 `~/.agentboard/tips/`。

---

## 1. 全角冒号 U+FF1A 导致 Windows 文件名编码错误

type: diagnosis
date: 2026-06-16
source: 视频标题含中文冒号，渲染输出文件名炸 shell

### 现象

B站标题含全角冒号 `：`（U+FF1A），FFmpeg 输出文件时 PowerShell/Bash 报编码错误，文件创建失败。尝试在命令行中手动创建含 `：` 的文件同样失败。

### 根因

Windows 文件系统（NTFS）内部用 UTF-16，但 shell 层面（cmd/PowerShell/bash on Windows）在处理文件名时经过多层编码转换。全角冒号 U+FF1A 在部分代码页转换路径被误解释为半角冒号 U+003A（NTFS 的流分隔符），导致路径解析失败。

不是 NTFS 不支持——`CreateFileW` API 可以创建——而是 shell 工具链在 ANSI/UTF-8 转换时丢了信息。

### 修复

- 所有文件写入用 Python `Path` 对象，绕过 shell 字符串传递
- 标题中含全角标点：渲染时用英文 slug 做临时文件名，最后用 `Path.rename()` 改回中文名
- B站上传时标题可以含全角冒号（网页端直接填），只是文件名不能

### 预防

`_process/` 内固定英文文件名（`01_raw.srt` ~ `05.ass`），`output/` 内 `cover.jpg` 固定。只有最终 mp4 用中文标题命名——如果标题含 U+FF1A，替换为半角冒号或 `-`。

---

## 2. yt-dlp 默认格式拿到 webm/vp9 → B站不兼容

type: diagnosis
date: 2026-06-16
source: 首次下载 Cat Wu 视频，渲染后上传 B站失败

### 现象

`yt-dlp <url>` 默认下载 webm 容器 + vp9 编码。FFmpeg 能烧录字幕，但上传 B站 后转码失败（B站服务端不支持 vp9 输入）。

### 根因

YouTube 高清视频默认提供 vp9 + opus 编码（压缩率更高）。yt-dlp 默认选最佳质量 = vp9。B站上传后台只接受 H.264 视频流和 AAC 音频流。

### 修复

强制指定格式选择器：

```bash
yt-dlp -f "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=1080]" <url>
```

`vcodec^=avc1` = 视频编码以 avc1 开头（H.264），`ext=m4a` = 音频用 AAC 容器。fallback 到 1080p 以下的 best。

### 预防

pipeline.py 的 `download_video()` 已内置此格式选择器。如果未来 B站 支持更多编码，只改这一处。

---

## 3. "透明度 80%" = 亮度 0.80，不是 0.20

type: diagnosis
date: 2026-06-16
source: 封面生成迭代 v3→v6，用户纠正

### 现象

用户说"黑色遮罩透明度 80%"。我用 `enhancer.enhance(0.15)` 把底图压到极暗（85% 不透明）。用户说"太黑了，我说的是透明度 80% 到 90%"。

### 根因

中文设计语境中"透明度 80%"指**透过程度** 80%——底图保留 80% 可见度，压暗程度只有 20%。对应代码 `enhancer.enhance(0.80)`。

英文 "80% transparency" 同样有歧义（CSS `opacity: 0.8` = 80% 不透明 = 20% 透明）。但中文设计沟通中，"透明度"几乎总是指透过程度。

### 修复

封面亮度固定为 0.80，对应 80% 透明度（微微压暗，主讲人面部仍然清晰）。

### 预防

听到"透明度 X%"→ 先确认是透过程度还是不透明程度。代码中 brightness 参数注释写明"0.80 = 80% 透明，底图保留 80% 亮度"。

---

## 4. ASS 双 Dialogue 事件被 libass 碰撞检测吞掉

type: diagnosis
date: 2026-06-16
source: 字幕渲染后中英文交替消失

### 现象

初版 ASS 用两条相邻 Dialogue 分别放中文和英文（同一时间段）。渲染后某些字幕只显示中文或只显示英文，同一条字幕的中英随机消失一个。

### 根因

libass 有碰撞检测（collision detection）：当两条 Dialogue 时间重叠且位置接近时，自动隐藏其中一条以避免"字幕重叠"。两条相邻双语字幕的 `MarginV` 差只有 10px，碰撞检测认为它们重叠，随机吞掉一条。

这不是 bug——libass 设计假设一个字幕事件 = 一行文字。双语字幕的正确做法是在一条 Dialogue 内用 `\N` 换行。

### 修复

单事件双语格式：

```ass
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,45,,{\fnSimHei\fs42}中文\N{\fnSegoe UI\fs32\b1}English
```

`\N` = ASS 硬换行。中上（42px SimHei），英下（32px Segoe UI 加粗）。

### 预防

所有 ASS 字幕生成用单事件模式。如需不同样式的中英文，用 `\fn` `\fs` `\b` 标签在 `\N` 前后切换，不拆 Dialogue。

---

## 5. Windows PIL 中文字体：只有 SimHei 够粗

type: diagnosis [HISTORICAL — 2026-06-23 已回退 msyhbd.ttc]
date: 2026-06-16
source: 封面字体加粗迭代

### 现象

封面标题需要超粗中文字体。尝试 NotoSansSC-VF（可变字体，理论上可调 weight 轴），但 PIL 渲染出来是 Regular 粗细。尝试描边模拟加粗但边缘模糊。用户多次说"还不够粗"。

### 根因

- PIL/Pillow 不支持 OpenType 可变字体（variable fonts）的轴参数——`ImageFont.truetype('NotoSansSC-VF.ttf', 165)` 只拿默认 instance，通常是 Regular
- Windows 10/11 系统自带中文字体中，SimHei（黑体）是唯一原生粗体中文字体
- 用 `stroke_width` 描边在 165px 字号时最多做到 2-3px，再多就糊

### 修复

用 SimHei（`C:\Windows\Fonts\simhei.ttf`）+ 四周 2px 填充：

```python
for dx, dy in [(-2,-2), (-2,0), (-2,2), (0,-2), (0,2), (2,-2), (2,0), (2,2)]:
    draw.text((x+dx, y+dy), text, font=font, fill=(0,0,0))
draw.text((x, y), text, font=font, fill=accent)
```

8 个偏移方向画黑字 + 1 次正中画彩色字 = 模拟 2px 外轮廓超粗效果。

### 预防

- ~~中文封面/海报 → SimHei，不碰 NotoSansSC~~ **[2026-06-23 已废弃]** gen_cover.py 已回退 msyhbd.ttc 纯色无描边。当前真相源: `gen_cover.py`（生产）+ `validate_cover.py`（验证）。SimHei 作为 gen_cover.py 的 fallback (#3 in chain)。
- 需要更粗 → 考虑 ImageMagick 预处理或换用 HTML→截图 方案
- `gen_cover.py` 已内置字体查找逻辑（`_find_font()`），自动搜 `C:\Windows\Fonts\`

---

## 6. DeepSeek API 批量翻译：行数对齐和并行稳定性

type: method
date: 2026-06-16
source: 翻译 Boris Cherny 40 分钟演讲，~300 条字幕

### 现象

批量翻译时，API 返回的行数和输入行数不一致（多出空行、少返回、或合并两行为一行）。单线程处理 300 条需要 5+ 分钟。网络抖动导致个别批次丢失。

### 根因

- DeepSeek 翻译 prompt 要求"每行对应输出一行"，但大模型对行数对齐不严格——有时在译文后加注释，有时跳过空行
- 串行请求 30 批，每批 ~10s = 5 分钟，视频越长越慢
- 网络超时无重试，一整批 10 条丢失

### 修复

```python
# 并行：ThreadPoolExecutor，最多 5 并发
# 行数对齐：截断多余行 / 补齐空行
while len(lines) < len(batch):
    lines.append("")
return lines[:len(batch)]

# 重试：3 次，指数退避 1s/2s/4s
for attempt in range(3):
    try: ...
    except Exception:
        if attempt < 2: time.sleep(2 ** attempt)
```

### 预防

- `pipeline.py` `_translate_batch()` 已内置行数对齐和重试
- 并发数上限 5（DeepSeek API 免费版限流约 5 QPS）
- 如果未来换翻译后端，行数对齐逻辑必须保留

---

## 7. enforce_max_chars：无标点长文本永远不会拆分

type: diagnosis
date: 2026-06-16
source: 单元测试发现

### 现象

字幕中有一句中文无标点长句（演讲者连续输出没有停顿），超过 28 字但没有被拆分。`_split_cn_text()` 返回原文本作为单一段落。

### 根因

原始拆分逻辑只在遇到中文标点（，。！？；、）且累计字数超过 max_chars 时才切割。如果整段没有标点，buf 从头累积到尾，永远不会触发切割条件。

### 修复

增加 hard split fallback：如果累积超过 `max_chars * 2` 仍无标点，强制切割。

```python
if _cn_char_count(buf) >= max_chars:
    if ch in punct:
        result.append(buf); buf = ""
    elif _cn_char_count(buf) >= max_chars * 2:
        result.append(buf); buf = ""  # hard split
```

### 预防

任何"检测到分隔符才切割"的逻辑，必须有"超长无分隔符"的兜底。`pipeline.py` `_split_cn_text()` 已含此逻辑。

---

## 8. B站 API 直接调用返回 HTML 错误页

type: diagnosis
date: 2026-06-16
source: 测试昵称是否可用时 API 返回乱码 HTML

### 现象

用 `requests.get('https://api.bilibili.com/x/web-interface/search/type?...')` 查昵称，返回的不是 JSON 而是 HTML 错误页（反爬验证码页）。HTTP 200 但 body 是 `<html>...</html>`。

### 根因

B站 API 有反爬机制：检测到非浏览器 User-Agent 或缺少 Cookie/Referer 时，不返回错误状态码（保持 200），直接返回人机验证 HTML 页面。

### 修复

不用直接 API 调用。用 WebFetch 工具搜 B站 用户搜索页：

```
https://search.bilibili.com/upuser?keyword=猫波信号站
```

WebFetch 渲染页面后返回搜索结果。"用户0" 表示该昵称未被注册。

### 预防

对 B站 的任何自动化查询，优先走 WebFetch（浏览器渲染）而不是直接调 API。API 的反爬策略随时变化，WebFetch 更稳定。

---

## 9. B站章节上限 10 段 + 格式必须 HH:MM:SS

type: diagnosis
date: 2026-06-22
source: ⑫ 元数据生成 15 章节，发布时发现上限 10 段，格式缺少小时位

### 现象

从 transcript 提取了 15 个章节，格式为 `mm:ss 标题`。粘贴到 B站章节编辑器后报错，且发现超过 10 段无法全部添加。

### 根因

- B站分段章节硬上限为 **10 段**（含首章 00:00）
- 章节时间格式必须为 **`HH:MM:SS 标题`**（三段时间，带小时位），`MM:SS` 格式不被识别
- 章节间隔必须 ≥5 秒，时间戳不可重叠
- 章节入口不在上传页：创作中心 → 稿件管理 → 视频右侧「···」→ 个性化配置 → 分段章节

### 修复

- 章节从 15 段合并精简到 10 段
- 时间格式统一改为 `HH:MM:SS`（00:00:00 / 01:05:43 / 02:19:20）
- 生成 `chapters_bilibili.json` 供 JSON 导入（`start_time` 秒 + `title`）
- 发布面板章节栏直接输出 `HH:MM:SS 标题` 格式，全量复制一键粘贴

### 预防

- ⑫ 元数据阶段就按 10 段上限规划章节（合并相邻话题），不等到发布才发现
- SKILL.md ⑫ 已写死上限 10 段 + HH:MM:SS 格式
- 每期自动生成 `chapters_bilibili.json` 备 JSON 导入方案

---

## 10. B站标签只能逐个输入

type: diagnosis
date: 2026-06-22
source: 发布面板复制逗号分隔的 10 个标签，粘贴到 B站无效

### 现象

发布面板标签栏输出 `标签1,标签2,标签3...`（逗号分隔），复制后粘贴到 B站标签输入框，只识别为 1 个含逗号的长标签。

### 根因

B站标签输入框是逐个添加的交互模式：每输入一个标签后按回车确认，不支持逗号分隔的批量粘贴。

### 修复

发布面板标签栏改为每个标签旁带独立的「复制」按钮，逐个点击复制 → 粘贴 → 回车。

```html
<div class=tag-row><span>AI编程</span><button onclick="navigator.clipboard.writeText('AI编程')">复制</button></div>
```

### 预防

- SKILL.md ⑭ 和发布面板模板已固定此交互模式
- 不再尝试批量粘贴标签，只提供逐条复制按钮

---

## 11. B站封面首页推荐 4:3 裁剪

type: diagnosis
date: 2026-06-22
source: 封面标题"AI编程：快就是好玩"在首页推荐 4:3 视图出界

### 现象

上传 1920×1080 (16:9) 封面后，B站首页推荐展示为 4:3 裁剪（1440×1080，左右各裁 240px）。标题 165px 字宽 1499px 超出 1320px 安全区（1440 - 60×2 内边距），文字被裁。

### 根因

B站封面上传接受 16:9，但首页推荐流和搜索结果是 4:3 裁剪显示。标题文字如果靠近左右边缘，必然被裁。16:9 居中放置的文字在 4:3 视图中不一定安全。

### 修复

gen_cover.py 增加 auto-shrink 逻辑：
- `SAFE_W = 1440`（4:3 裁剪区宽度）
- `SAFE_PAD = 60`（安全区内边距）
- 有效文字宽度上限 1320px
- 标题超过 1320px 时自动缩小字号：`title_size = int(165 * safe_max / tw)`

### 预防

- gen_cover.py 已内置 4:3 安全区检测和自动缩字
- 封面生成后检查日志中的 `Title shrunk` 行，确认调整幅度是否合理

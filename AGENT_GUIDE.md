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
| CDP浏览器上传 | 读 §5.1 CDP上传，`python tools/stage_16_cdp_upload.py --help` |
| 上传百度云盘 | 读 §6 百度云盘上传 |
| 修bug/改参数 | 读对应工具源码 + `_ref/pitfalls.md` |

## 1. 管线流程

```
② 下载 ──→ ③ Whisper转录 ──→ ④ 赞助检测 ──→ ⑤ 翻译 ──→ ⑥ 字宽检查 ──→ ⑦ ASS ──→ ⑧ 渲染
               机械段（每阶段独立脚本，可单独重跑）

⑨ 百度云上传 ──→ ⑩ 元数据 JSON ──→ ⑪ 金句提取 ──→ ⑫ 封面 ──→ ⑬ 标题 ──→ ⑭ 电子书 ──→ ⑮ 发布面板 ──→ ⑯ B站上传
                AI 决策段（每步需读 transcript 判断）

⑯ 分两路:
  - API 直连: stage_15_publish.py (小文件, <500MB)
  - CDP 浏览器: stage_16_cdp_upload.py (大文件, 1GB+)
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
├── 电子书/<书名>.epub       ← gen_epub.py 生成
├── _runtime/
│   ├── 素材/source.mp4     ← yt-dlp 下载
│   ├── 字幕/01~05          ← 管线中间产物
│   ├── frames/             ← 截图（封面素材）
│   ├── metadata.json       ← B站投稿元数据（gen_metadata.py 生成）
│   ├── draft.md            ← 专栏草稿
│   └── run.log
└── .published              ← 发布后创建
```

## 2. 阶段索引

所有脚本在 `tools/` 下。从项目根目录运行。

```powershell
# ② 下载
python tools/stage_02_download.py --url "<YouTube URL>" --slug <slug>

# ③ Whisper 转录（时间锚点，不可用 segment 替代）
python tools/stage_03_whisper.py --slug <slug>

# ④ 赞助检测
python tools/stage_04_sponsor.py --slug <slug>

# ⑤ 翻译 + 专名修复
python tools/stage_05_translate.py --slug <slug>

# ⑥ 标点优先拆分 + 像素宽度检查
python tools/stage_06_split.py --slug <slug>

# ⑦ ASS + transcript（--bord 3 白字黑边，Netflix 标准）
python tools/stage_07_ass.py --slug <slug> --bord 3

# ⑧ 渲染（--duration 60 做测试片）
python tools/stage_08_render.py --slug <slug> --title "标题" [--duration 60]

# ⑨ 百度云盘上传 EPUB
python tools/stage_09_baidu_upload.py --slug <slug>

# ⑩ 生成 B站投稿元数据
python tools/gen_metadata.py --slug <slug> --title "标题" --source "YouTube @频道名" \
    --tags "tag1,tag2,..." [--baidu-link "<百度盘链接>"]

# ⑯ B站草稿箱上传 (API)
python tools/stage_15_publish.py --video <mp4> --metadata <metadata.json> \
    --cookie "<cookie>" --cover <cover.jpg> --draft

# ⑯ B站上传 (CDP 浏览器，大文件)
python tools/stage_16_cdp_upload.py --slug <slug> --page-id <CDP_PAGE_ID>
```

### 重跑规则

| 要改什么 | 从哪个阶段重跑 |
|----------|---------------|
| Whisper 转录 | ③ → ④ → ⑤ → ⑥ → ⑦ → ⑧ |
| 翻译质量/专名 | ⑤ → ⑥ → ⑦ → ⑧ |
| 字宽阈值 | ⑥ → ⑦ → ⑧ |
| ASS 样式 | ⑦ → ⑧ |
| 赞助检测策略 | ④ → ⑤ → ⑥ → ⑦ → ⑧ |

### 门禁

| 阶段 | 检查项 | 标准 |
|------|--------|------|
| ③ | Whisper 转录 | 输出 02_seg.srt，时间戳无重叠，直接绑定音频波形 |
| ④ | 赞助检测 | 抽检被剔段落确为赞助 |
| ⑤ | 翻译 | 行数=④，专名留英文 |
| ⑥ | 字宽 | 中文像素宽 ≤1520px（SimHei 42px） |
| ⑦ | ASS | Outline=3, OutlineColour=opaque black, MarginL/R=200 |
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
- **标题 ≤16 字**（B站硬上限，超长截断）
- 间隔 ≥5 秒，按时间递增
- 入口：创作中心 → 稿件管理 → 视频右侧「···」→ 个性化配置 → 分段章节

## 5. B站发布

三种方式：

### A. API 直连（小文件首选）
```powershell
python tools/stage_15_publish.py --video "<成片/视频.mp4>" \
    --metadata "_runtime/metadata.json" --cover "cover.jpg" \
    --cookie "<浏览器Cookie>" --draft
```
- `--draft`：存入草稿箱，不直接发布
- 需要 Cookie 含 `bili_jct`、`SESSDATA`、`DedeUserID`
- metadata.json 由 `gen_metadata.py` 生成
- **限制**: 大文件 (>500MB) 可能超时，B站 API 上传限速

### B. CDP 浏览器自动化（大文件推荐，1GB+）
Bit Browser CDP port 55054，浏览器已登录 B站。
详细文档：`生产操作手册.html` §3.4 CDP 上传。

**连接**：
```python
import websocket
ws = websocket.create_connection(
    "ws://127.0.0.1:55054/devtools/page/<PAGE_ID>",
    timeout=30, suppress_origin=True
)
# 必须用 msg_id 匹配过滤 CDP 事件
```

**上传流程**：
1. `Page.navigate` → `https://member.bilibili.com/platform/upload/video/frame`
2. `DOM.querySelectorAll` → 找到隐藏的 `input[type=file]`（class 含 `bcc-upload`）
3. `DOM.setFileInputFiles` → 设置视频文件，触发上传
4. 循环 `Runtime.evaluate` 读取进度（body.innerText 正则匹配百分比）
5. 上传中即可填写表单（标题、简介、标签推荐点击）
6. 上传完成后页面会跳转到 `/platform/home`，重新导航回 upload 页
7. 页面显示「共1个未提交视频」→ 点击「继续编辑」恢复草稿

**表单填写（有效的方法）**：
```python
# 标题 — Vue 输入框
expression = '''
(() => {
    const inp = document.querySelector('input[placeholder*="标题"]');
    const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    s.call(inp, "标题内容");
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    return inp.value.length;
})()
'''

# 简介 — Quill contenteditable div
expression = '''
(() => {
    const div = document.querySelector('div[contenteditable="true"]');
    div.focus();
    div.innerText = "简介内容";
    div.dispatchEvent(new Event('input', { bubbles: true }));
    return div.innerText.length;
})()
'''

# 标签 — 点击推荐标签（仅限 hot-tag-item）
# 自定义标签输入：Vue 不响应 CDP 键盘事件，无法通过 CDP 添加
# 标签删除：CDP Input.dispatchMouseEvent 点击 SVG.close 按钮有效
```

**CDP 限制（B站 Vue SPA 无法突破）**：
- Vue 下拉选择（创作声明、分区）：CDP mouse click 无效，li 元素 h=0
- 标签输入框：Vue 不响应 CDP key events 和 JS KeyboardEvent
- 封面上传：点击封面触发 OS 文件对话框，CDP 无法控制
- 页面跳转后表单数据可能丢失
- **总结**: 视频上传 + 标题 + 简介 + 标签推荐点击 + 分区（自动检测）可通过 CDP 完成；创作声明、自定义标签、封面、存草稿需手动

### C. 手动操作清单（CDP 后必做）
1. 验证创作声明 → 含AI内容生成（脚本已自动设置，确认即可）
2. 验证封面上传是否生效
3. 点击「存草稿」（如脚本未能点击）
4. 在稿件管理页确认草稿存在

### D. stage_16_cdp_upload.py 管线脚本

```powershell
# 自动发现 slug 目录下的 cover/video/metadata
python tools/stage_16_cdp_upload.py --slug <slug> --page-id <PAGE_ID>

# 手动指定参数
python tools/stage_16_cdp_upload.py --video <mp4> --cover <jpg> \
    --title "标题" --tags "tag1,tag2" --description "简介..." \
    --page-id <ID>

# 只填表单不传视频（视频已在页面中）
python tools/stage_16_cdp_upload.py --slug <slug> --page-id <ID> --no-upload

# 只检查状态
python tools/stage_16_cdp_upload.py --slug <slug> --page-id <ID> --check-only
```

脚本执行流程:
1. 连接 Bit Browser CDP (port 55054)
2. 导航到 B站上传页
3. 上传视频 (DOM.setFileInputFiles + 进度监控)
4. 填写标题 (native setter + Vue input event)
5. 填写简介 (contenteditable div)
6. 点击推荐标签
7. 设置创作声明 → 含AI内容生成 (Vue $data)
8. 上传封面 (click → editor → setFile → 完成)
9. 点击存草稿

## 6. 百度云盘上传

```powershell
python tools/stage_09_baidu_upload.py --slug <slug>
```
- 依赖 `bypy`（已安装），需先授权：`bypy info`
- 上传到「猫波信号站电子书」共享文件夹
- 永久链接：`https://pan.baidu.com/s/1huGTuQdCWXS0JFERhEf-8g?pwd=1234`

## 7. 文件纪律

- 所有产出物落 `D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\`
- **目录命名宪法**: 格式 `YYYYMMDD_slug`，日期 = 处理当天（不是视频发布日期）。`_lib.py` 的 `slug_dir()` 自动强制此规则，裸 slug 自动补当天日期前缀
- 封面固定 `cover.jpg`，不保留多版本
- 成片只放最终交付物，测试片放 `_runtime/`
- `_runtime/` 保留溯源，发布后不删
- 视频文件名 = B站标题（≤80 字）
- 文件名禁止全角冒号 U+FF1A
- 每会话结束写 HANDOFF.md

## 8. 决策日志

每期视频的决策（选帧、标题候选、布局选择）写入当期 `_runtime/draft.md` 或 HANDOFF.md。不在本文件追加。

## 9. 参考文件

| 文件 | 内容 |
|------|------|
| `_ref/生产参数.md` | 封面/标题/字幕全部工程参数 |
| `_ref/pitfalls.md` | 11条踩坑记录（生产前必读） |
| `PROJECT_CONTEXT.md` | 项目架构总览 |
| `生产方法论.html` | 统一方法论入口（人类可读） |

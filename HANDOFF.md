# HANDOFF · 猫波信号站

> 新会话开始读此文件。本文件是交接唯一真相源，覆盖式更新。

## 当前状态

**2026-06-26** — 项目已从 lab 搬入 `D:\workspace\猫波信号站\`。`.project` 身份证已创建（id: `catwave-signal-station`）。生产操作手册 & 生产方法论管线表已对齐（①-⑯），飞书为唯一真相源。6 个新选题待跑 ②→⑮，管线未启动。

## 本轮已完成

| 事项 | 状态 |
|------|------|
| Qwen3.7-Max 选型分析 → 结论：不推荐，Flash 最优 | ✅ |
| 管线 API+算力成本测算 → 6 选题 $0.31（¥2.5） | ✅ |
| `生产操作手册.html` +1.8 飞书记录入库（工具用法+字段清单+教训） | ✅ |
| `生产操作手册.html` +4.5 管线成本测算（公式+单视频参考+定价表） | ✅ |
| 6 选题管线 **未执行** | ⬜ 待跑 |

---

## 📋 核心任务：跑完 6 个候选的 ②→⑮

按分数从高到低。每个选题跑通后再开下一个（GPU 独占编码，不能并行）。

### 候选清单

| # | Slug | 嘉宾 | YT ID | 分数 | 来源 | 飞书标题 |
|---|------|------|-------|------|------|---------|
| 1 | `tony-fadell-taste-ai-lenny` | Tony Fadell | RJjl1TwyfWM | 28 | Lenny's Podcast | iPod之父Tony Fadell：AI时代真正的稀缺是品味与判断力 |
| 2 | `ethan-he-xai-video-agents-latentspace` | Ethan He | jPtQlILfkhA | 27 | Latent Space | xAI视频生成负责人Ethan He：视频Agent是下一个前沿 |
| 3 | `satya-nadella-microsoft-build-latentspace` | Satya Nadella | cFNI2FORAc0 | 26 | Latent Space | 微软CEO纳德拉：全栈构建者崛起与AI平台战略 |
| 4 | `kyle-daigle-github-agents-latentspace` | Kyle Daigle | LEWlSyR0cXA | 23 | Latent Space | GitHub COO Kyle Daigle：Agent时代14倍提交与2亿开发者 |
| 5 | `logan-kilpatrick-model-eats-sequoia` | Logan Kilpatrick | cMAs8z2dehs | 23 | Training Data | DeepMind Logan Kilpatrick：为什么模型终将吃掉脚手架 |
| 6 | `greg-brockman-human-attention-sequoia` | Greg Brockman | bBS93A0BeNI | 22 | Training Data | OpenAI联创Greg Brockman：人类注意力是AI时代最稀缺资源 |

### 视频时长

| # | 时长 | 备注 |
|---|------|------|
| 1 | 95min | 标准长片 |
| 2 | 105min | 最长 |
| 3 | 41min | ⚠️ 仅 38 分钟，跑前确认内容密度 |
| 4 | 85min | 标准长片 |
| 5 | 51min | 中等长度 |
| 6 | 28min | 最短 |

### 飞书链接

`https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`

查看视图 `vewHaNJhlQ`（候选队列，按总分降序）。

---

## 💰 成本参考

**单视频（~90min）：API $0.05 + 电费 $0.02 = ~$0.07**
**6 选题整轮：API $0.22 + 电费 $0.09 = ~$0.31（¥2.5）**

模型用 `deepseek-chat`（V4-Flash，$0.14/$0.28 per 1M tokens）。**2026-07-24 前需迁移到 `deepseek-v4-flash`**（同价，改 3 个脚本各一行）。

详见 `生产方法论.html` §5.6。

---

## 🔧 管线跑法（每个选题通用）

### 环境

```powershell
cd D:\workspace\猫波信号站
$env:VORTEX_PROXY = "127.0.0.1:7897"
$env:DEEPSEEK_API_KEY = "<key>"
```

### 固定参数（所有视频统一）

- ASS: `--bord 1`（1px，outline-alpha=128 即 50%透明黑边）
- 编码: NVENC GPU (`h264_nvenc`), 720p
- 封面底图: `frame_0010.jpg`（从视频每分钟抽一帧，选构图最好的）
- 封面参数: 1920×1080, 主标题 SimHei 165px 暖黄 #FFC82D, 副标题 SimHei 62px 暖白 #FCFAF5, 亮度 0.80, 自动缩字至安全区 ≤1440px
- EPUB: 从 `03_zh.srt` 提取中文翻译
- 百度盘链接（所有视频共用）: `https://pan.baidu.com/s/1huGTuQdCWXS0JFERhEf-8g?pwd=1234`

### ② 下载

```powershell
python tools/stage_02_download.py --url "https://youtube.com/watch?v=<YT_ID>" --slug <slug>
```
产出: `<output>/_runtime/素材/source.mp4` + `01_raw.srt`

### ③ Whisper 转录

```powershell
python tools/stage_03_whisper.py --slug <slug>
```
产出: `<output>/_runtime/字幕/02_whisper.srt`（时间锚点）

### ④ 赞助检测 + 裁剪

```powershell
python tools/stage_04_sponsor.py --slug <slug>
```
产出: `source_clean.mp4`（切掉赞助片段）

### ⑤ 翻译

```powershell
python tools/stage_05_translate.py --slug <slug>
```
产出: `<output>/_runtime/字幕/03_zh.srt`

### ⑥ 拆分（标点优先 + 像素宽度检查）

```powershell
python tools/stage_06_split.py --slug <slug>
```
产出: `<output>/_runtime/字幕/04_split.srt`

### ⑦ ASS

```powershell
python tools/stage_07_ass.py --slug <slug> --bord 1
```
产出: `<output>/_runtime/字幕/05.ass`

### ⑧ 渲染

```powershell
# 先 60s 测试片，确认字幕位置/颜色/边框 OK
python tools/stage_08_render.py --slug <slug> --title "测试片" --duration 60

# 确认无误后全片渲染（GPU 独占，>20min 视频约 15-30min）
python tools/stage_08_render.py --slug <slug> --title "<B站显示标题>"
```
产出: `<output>/成片/<title>.mp4`

### ⑨ 百度云上传 EPUB（可选）

```powershell
python tools/stage_09_baidu_upload.py --slug <slug>
```

### ⑩→⑮ AI 决策段

以下阶段需要先读 `transcript.txt`（`_runtime/字幕/transcript.txt`）理解内容后再执行：

**⑩ 元数据** — 生成 metadata.json（章节/标签/简介）

```powershell
python tools/gen_metadata.py --slug <slug> --title "<B站标题>" --source "YouTube @<频道名>" --tags "tag1,tag2,..."
```

**⑪ 金句** — 从 transcript 提取 5 条金句候选（手动，用于封面/标题/推广）

**⑫ 封面** — 从 frames 中选构图最好的帧

```powershell
# 先抽帧（每分钟一帧）
ffmpeg -i "<视频路径>" -vf "fps=1/60" -q:v 3 <output>/_runtime/frames/frame_%04d.jpg

# 生成封面（标题需 ≤1440px 安全区，gen_cover.py 会自动缩字）
python tools/gen_cover.py <选中的frame.jpg> <output>/cover.jpg \
    --title "<封面主标题>" --sub "<副标题（姓名 · 头衔）>" \
    --brightness 0.80 --color "#FFC82D"
```

**⑭ EPUB**

```powershell
python tools/gen_epub.py --slug <slug> --title "<书名>" --author "<嘉宾>" --source "<来源频道>"
```

**⑮ 发布面板** — HTML 文件，参照 `_ref/发布面板模板.html` 或已有面板（`D:\workspace\_output\猫波信号站\视频\20260625_databricks-agent-cloud-latentspace\发布面板.html`）。包含：标题(带字数)、标签(逐个复制按钮)、分区/合集、简介(含百度盘链接)、章节(≤16字标题, HH:MM:SS 格式)、金句候选(5条)、封面信息、视频文件信息。

**⑯ 发布** — 用户要求暂不执行。全部 ⑮ 完成后待用户指令。

---

## 执行策略

1. **按分数顺序跑**。跑完 #1 的 ②→⑮ 再开 #2，依此类推
2. **机械段 (②→⑧) 可连续跑**，每个阶段脚本独立，产出落盘后即可进入下一阶段
3. **AI 决策段 (⑩→⑮) 需读 transcript** — `_runtime/字幕/transcript.txt`
4. 封面标题 = 飞书"标题"字段中的冒号后面部分（如 "AI时代真正的稀缺是品味与判断力"），副标题 = 嘉宾名 + 头衔 + 来源频道
5. B站标题在 ⑩ 阶段根据 transcript 内容最终确定，**≤80 字**
6. ⚠️ 第 3 号 Satya Nadella 仅 38 分钟，确认内容密度足够后再跑

---

## 产出目录

每个选题: `D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\`

slug 格式: `YYYYMMDD_<slug>`（脚本 `_lib.py` 的 `_normalize_slug` 自动补日期前缀）

---

## 飞书

- Base token: `F7E8bJie5aX3BvsZz1Xc9KiznNb`
- Table: `tblIs359fHfIapwd`
- 操作命令: `lark-cli base +<subcommand> --base-token F7E8bJie5aX3BvsZz1Xc9KiznNb --table-id tblIs359fHfIapwd --as bot`
- JSON 需用文件传递: `--json "@_runtime/tmp.json"`（相对路径，无BOM，文件放 `C:\Users\Administrator\_runtime\`）
- **选题入库优先用 `stage_01_topic_onboard.py`，禁止手工拼 JSON**（详见 `生产操作手册.html` §1.8）

## 新工具: stage_01_topic_onboard.py

选题入库用，不要手工拼 JSON：

```powershell
python tools/stage_01_topic_onboard.py \
    --url "https://youtube.com/watch?v=XXX" \
    --title "中文标题（身份：主题）" \
    --guest "Guest Name" --source "Channel Name" \
    --summary "一句话中文摘要" \
    --timeliness N --exclusivity N --authority N --longevity N \
    --create
```

自动拉 YouTube 元数据、校验中文标题、计算总分、写入飞书。

## 评分体系

总分 = 时效性×3 + 独占性×3 + 人物权威×2 + 长期价值×2 (满分 30)

## 模型选型结论

**保持 DeepSeek V4-Flash（当前 `deepseek-chat`）。** 管线 3 个 LLM 调用点（③断句/④赞助检测/⑤翻译）均为小批量短上下文任务（每批 10-20 条字幕行，无跨批依赖），Flash 在该模式上效率最优。Pro 的 12× 价格买不到质量提升。Qwen3.7-Max 贵 18-27× 且迁移成本不低，不推荐。

⚠️ `deepseek-chat` 将于 2026-07-24 退役。届时将 3 个脚本各改一行 `model: "deepseek-v4-flash"`。

## 路由

- **Lab 项目:** `D:\workspace\猫波信号站\`
- **产出根目录:** `D:\workspace\_output\猫波信号站\视频\`
- **飞书选题库:** `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **硬件:** RTX 5060 Ti 16GB, NVENC 默认编码
- **Agent guide:** `D:\workspace\猫波信号站\AGENT_GUIDE.md`
- **Agentboard tip:** `C:\Users\Administrator\.agentboard\tips\feishu-record-incomplete-fields.md`
- **生产操作手册:** `D:\workspace\猫波信号站\生产操作手册.html`
- **生产方法论:** `D:\workspace\猫波信号站\生产方法论.html`（§5.6 管线成本测算）


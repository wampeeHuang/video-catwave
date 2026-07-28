# HANDOFF · 猫波信号站

> 新会话开始读此文件。覆盖式更新。

## 当前状态

**2026-07-28** — validate_curation.py 上线。Stage A 产出现在有独立验证器，15项硬约束逐条检查。

## 本会话完成

### 1. validate_curation.py — curation 可执行验证器

新建 `tools/validate_curation.py`（~370行），覆盖 curation-prompt.txt 中所有硬性约束：

| 规则 | 检查 |
|------|------|
| 3.5 | 时长≥600秒（读 JSON duration字段）；Shorts/clip/trailer关键词命中 |
| 5 | 仅 youtube.com/youtu.be 域名 |
| 5.5 | likes/views ≥ 1% |
| 5.6 | 加权播放/天 ≥ 500（vpd空则从views+date推算） |
| 5.7 | 来源频道名 ≠ 空 ≠ "YouTube Search" |
| 5.8 | 嘉宾 ≠ 空 ≠ TBD ≠ 节目名/期号；TBD+权威>2 |
| 6 | URL 去重（调飞书 API `fetch_records()` 查已有记录） |
| 7 | 标题含中文 + ≤80字 |
| 7.5 | cover_title 存在 + ≤MAX_COVER_CHARS |
| 8 | 摘要 100-200字 |
| 9 | candidates ≤ 5 |
| 10 | 总分 ≥ 2.0 + 最高维度 ≥ 1.5 |
| 公式 | total = 时效×0.3+独占×0.3+权威×0.2+长期×0.2 |

**调用分工**：
- **curator (Stage A)**：`python tools/validate_curation.py file.json` → 含飞书去重
- **orchestrator (Stage B+C)**：`python tools/validate_curation.py file.json --skip-feishu` → 只验JSON结构

### 2. cover_design.py — 封面设计单源契约

新建 `tools/cover_design.py`，集中管理所有封面设计参数。`gen_cover.py`、`validate_cover.py`、`orchestrator.py` 都 import 同一份常量。

关键参数：MIN_TITLE_FS=130px, MAX_TITLE_FS=165px, CANVAS=1920×1080, SAFE_W=1440

自动检测函数：`detect_position(skin_ratio)` → center/bottom，`detect_overlay(avg_luminance)` → 10/15%黑遮罩

### 3. curation-prompt.txt 更新

- 规则 3.5：要求写 `duration` 字段（秒数），供验证器校验
- 规则 7.5：封面标题写作原则 + MAX_COVER_CHARS 约束
- 规则 12：写完 JSON 立即跑 `validate_curation.py`，FAIL → 修 → 重跑 → PASS

### 4. orchestrator.py — 前置验证门禁

读 curation JSON 后第一件事跑 `validate_curation.py --skip-feishu`，不通过 exit 1。

## 架构决策

- **不建 `_contracts/` 目录**。选了可执行验证器而非文档契约。Karpathy 原则：给成功标准让它自循环，不靠枚举规则。
- **duration 字段暂为 WARN**（过渡期，历史 curation 没有），几个周期后升级 FAIL
- **删了 yt-dlp 实测时长**。curator 已获取 duration 写入 JSON，验证器只需读字段。单一数据源。

## 关键变更文件

| 文件 | 改动 |
|------|------|
| `tools/validate_curation.py` | **新建** — Stage A 产出验证器 |
| `tools/cover_design.py` | **新建** — 封面设计参数唯一真相源 |
| `tools/curation-prompt.txt` | 规则 3.5/7.5/12 更新 |
| `tools/orchestrator.py` | 前置 validate_curation 门禁 |
| `tools/gen_cover.py` | import cover_design，删本地常量 |
| `tools/validate_cover.py` | import cover_design，字号验证 |

## 约定

- `加权播放/天` = views/sqrt(days)，sqrt修正时间衰减。agent硬门禁 <500 排除
- `视频发布日期` = YouTube 视频发布日期（yt-dlp 抓取）
- 策展 agent 只做决策（评分/选候选），不碰日期/slug
- Slug 不匹配是正常状态：AI agent 生成 clean slug，飞书存 YouTube-ID slug
- 飞书 API 日期字段返回字符串格式 `"YYYY-MM-DD HH:MM:SS"`
- `duration` 字段单位是**秒**，curator 写入，validator 读
- 封面标题 ≤ MAX_COVER_CHARS（≈12 CJK），min 字号 130px

## 定时任务

| 时间 | Job | Cron | 启用 |
|------|-----|------|------|
| 9:00 | 猫波选题 (run-curation.ps1) | `0 9 * * 1,3,5` | ✓ |
| 10:30 | 猫波生产 (sync+orchestrator) | `30 10 * * 1,3,5` | ✓ |

## 路由

- **项目根**: `D:\workspace\猫波信号站\`
- **产出根**: `D:\workspace\_output\猫波信号站\视频\`
- **状态面板**: `D:\workspace\_output\猫波信号站\视频\状态面板.html`
- **curation**: `D:\workspace\_output\猫波信号站\视频\_curation\YYYY-MM-DD.json`
- **复盘**: `D:\workspace\_output\retrospectives\`
- **飞书选题库**: `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **网站**: `https://data.evopearl.com/`
- **调度器**: `http://localhost:3100/cron`

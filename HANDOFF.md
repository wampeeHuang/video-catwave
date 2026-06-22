# HANDOFF · 猫波信号站

> 打开新会话时读此文件，了解当前状态和下一步。

## 当前状态

Cursor Team 期（Lex Fridman #447）全流程 ②-⑭ 已完成（2026-06-22）。待发布至 B站。

## 架构（最终版）

```
D:\workspace\lab\2026-06-16-猫波信号站\                   ← Lab：管线 SDK + 源视频
│   pipeline.py          ← 机械管线 ②-⑧（阶段门禁）
│   _tools/gen_cover.py  ← 封面合成
│   _runtime/<slug>_process/  ← 下载缓存（source.mp4 + 01_raw.srt）
│
D:\workspace\_output\猫波信号站\视频\<YYYYMMDD_slug>\      ← Output：所有产出物
│   _runtime/字幕/  ← 01_raw → 02_seg → 03_zh → 04_split → 05.ass + transcript.txt
│   成片/           ← <标题>.mp4
│   cover.jpg       ← 封面
│   发布面板.html
```

**核心原则：** skill（`.claude/skills/猫波信号站/SKILL.md`）是总指挥；pipeline.py / gen_cover.py / yt-dlp / ffmpeg 是它调的工具。

## 已做

- [x] 阶段门禁模块化（segment / translate / ass / render 四个阶段独立可跑）
- [x] 目录分离：RUNTIME → `D:\workspace\_output\猫波信号站\视频\`，PROCESS_ROOT → lab `_runtime\`
- [x] max_chars 默认值 28 → 36
- [x] 专有名词后处理 `_fix_proper_nouns()`：光标→Cursor
- [x] Cursor Team 期机械段已跑通一次（全流程 ②-⑧，1.35GB 成片）
- [x] 封面已确认 → cover.jpg（布局 C，"AI编程：快就是好玩"，"Cursor创始团队·Lex Fridman"）
- [x] Kevin Weil + Boris Cherny 两期已发布
- [x] 字幕样式修复（Outline=0, MarginL/R=80, 重叠裁剪）
- [x] **Bug 1 修复**（2026-06-22）— 字幕时间戳用 batch 实际时间替代全局字符比例
- [x] **Bug 2 修复**（2026-06-22）— 单遍 ffmpeg 替代两遍 -c copy
- [x] **Bug 3 修复**（2026-06-22）— SKILL.md AI 决策段加 `cd` 工作目录指令
- [x] `download_video()` 重命名 FileExistsError 修复 + `frames_dir` 未定义修复
- [x] ⑨ 金句提取 → 5 条候选，"快速就是好玩"定案
- [x] ⑩ 封面已确认（布局 C，无需重做）
- [x] ⑪ 标题 → "Cursor创始团队：快速就是好玩，AI编程的未来才刚刚开始"
- [x] ⑫ 元数据 → 标签×10、简介、章节×14
- [x] ⑬ 专栏 → `_runtime/draft.md`（引言→10节核心论点→结尾）
- [x] ⑭ 发布面板 → `发布面板.html`（含金句区块）
- [x] 测试片 → 60s (5.3MB) + 120s (14.4MB)，单遍 ffmpeg 验证通过

## Bug 修复记录（全部已修复）

### ✅ Bug 1 — 字幕大段空白 + 时间戳塌缩（已修复 2026-06-22）

**根因：** `_llm_restore_punctuation()` 全文字符扫描 + `_split_sentences_with_time()` 全局比例时间分配

**修复：**
1. `_llm_restore_punctuation()` (line 179) — 返回 `list[tuple[str, int, int, int]]` (text, batch_start_ms, batch_end_ms, batch_index)，直接从 merged entry 时间戳获取 batch 边界
2. `_split_sentences_with_time()` (line 301) — 按 batch_index 分组，每组内均匀分配时间
3. 删除了全文字符位置扫描逻辑

**验证：** 760 句字幕时间戳均匀递增，无重复、无 >10s 空白。batch 边界有小幅重叠（~1s），可接受。

---

### ✅ Bug 2 — 测试片音画不同步（已修复 2026-06-22）

**根因：** `-c copy` 流拷贝裁剪 MP4 导致 keyframe 对齐偏移

**修复：** `_run_stage_render()` (line 1061) — 单遍 ffmpeg 同时裁剪+烧字幕，删除 `_trimmed_src.mp4` 中间文件

**验证：** 60s 测试片 5.3MB，单遍渲染无报错，1800 frames @ 30fps 精确

---

### ✅ Bug 3 — SKILL.md 部分路径引用未同步（已修复 2026-06-22）

**根因：** AI 决策段相对路径 `_runtime/` 在 lab 和 output 之间歧义

**修复：** SKILL.md 第 57 行 AI 决策段开头加 `cd` 工作目录指令："先 cd 到当期视频输出目录，以下所有相对路径以此为基准"

**验证：** 金句提取、封面、发布面板生成均使用正确的 output 相对路径

---

## 验证结果（2026-06-22）

全流程输出在 `D:\workspace\_output\猫波信号站\视频\20260620_cursor-team-lex-fridman\`：

| 文件 | 状态 |
|------|------|
| `_runtime/字幕/02_seg.srt` | 760 句，时间戳均匀递增 ✓ |
| `_runtime/字幕/05.ass` | ASS 字幕 ✓ |
| `_runtime/字幕/transcript.txt` | 全文转录 ✓ |
| `成片/cursor-team-lex-fridman.mp4` | 全片 1.4GB ✓ |
| `成片/test_1min.mp4` | 60s 测试片 5.3MB ✓ |
| `成片/test_2min_v2.mp4` | 120s 测试片 14.4MB ✓ |
| `_runtime/draft.md` | 专栏文章 ✓ |
| `发布面板.html` | 含金句区块 ✓ |
| `cover.jpg` | 布局 C 已确认 ✓ |

## 下一步：发布到 B站

全流程 ①-⑭ 已完成。人工操作：
1. 打开 `发布面板.html`，逐项复制到 B站创作者中心
2. 上传视频 `成片/cursor-team-lex-fridman.mp4`（1.4GB）
3. 上传封面 `cover.jpg`
4. 发布专栏 `_runtime/draft.md`

## 已确认决策（跨会话不变）

参见 memory：`project_catwave_cursor_team.md`
- 封面：布局 C，"AI编程：快就是好玩"，"Cursor创始团队·Lex Fridman"
- 翻译：max_chars=36，专名后处理"光标"→"Cursor"
- 管线：阶段门禁已模块化，RUNTIME → output 目录

## 关键文件指针

```
D:\workspace\lab\2026-06-16-猫波信号站\pipeline.py                         ← 机械管线（Bug 1+2 在此）
D:\workspace\lab\2026-06-16-猫波信号站\.claude\skills\猫波信号站\SKILL.md  ← 全流程 skill（Bug 3 在此）
D:\workspace\lab\2026-06-16-猫波信号站\_tools\gen_cover.py                 ← 封面合成
D:\workspace\lab\2026-06-16-猫波信号站\生产方法论.html                      ← 完整方法论
D:\workspace\_output\猫波信号站\视频\20260620_cursor-team-lex-fridman\      ← Cursor Team 产出
D:\workspace\_output\猫波信号站\选题库\飞书选题库.md                        ← 选题库
~/.agentboard/tools/catwave-pipeline/manifest.json                        ← 工具架
```

## 关键约束速查

- yt-dlp 必须 H.264+AAC
- 飞书 API：更新记录用字段名（中文），不用 field_id
- 视频目录命名：YYYYMMDD_slug/
- 封面：msyhbd.ttc 纯色无描边，亮度 0.80，#FFC82D，≤4.8MB
- 视频文件名 = B站标题，标题 ≤80 字
- 赞助商检测在翻译前自动执行
- **ffmpeg 渲染 ASS：必须 chdir 到字幕目录用相对路径**（盘符冒号被当 filter 分隔符）
- YouTube 需代理 VORTEX_PROXY 127.0.0.1:7897
- DEEPSEEK_API_KEY 用于翻译+赞助检测+断句

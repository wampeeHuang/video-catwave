# HANDOFF · 猫波信号站

> 新会话开始读此文件。覆盖式更新。

## 当前状态

**2026-08-05** — 管线重构完成。选题阶段 agent 只出 JSON，Feishu 写入移交脚本。验证闸门就位。

## 本会话完成

### 管线重构

| 变更 | 说明 |
|------|------|
| `tools/onboard_to_feishu.py` | **新建** — 读 curation JSON → yt-dlp 获取元数据 → 创建飞书记录(状态=候选) → 写回 record_id + 侵权风险 |
| `tools/verify_chain.ps1` | **新建** — 三段闸门：数量一致/record_id存在/面板时间，失败飞书通知 + exit 1 |
| `tools/curation-prompt.txt` | 删除飞书写入指令，agent 只产出 JSON；去重改为扫描 30 天 JSON |
| `tools/run-curation.ps1` | 插入 onboard 步骤 (Step 2/4)，流程从 3 步扩为 4 步 |
| `tools/gen_cover.py` | `_fit_size()` 强制钳位到 MIN_TITLE_FS，注释里的硬地板变真的硬 |
| `tools/_feishu.py` | 新增 `create_record()` 函数 |

### 流程变更

```
旧: agent → JSON + 飞书(agent写) → sync → 网站
新: agent → JSON → onboard_to_feishu.py(脚本写飞书) → sync → verify_chain.ps1(终端闸门)
```

### tips 入库

- `design-constants-not-enforced.md` — 注释里的约束不是约束，代码里的才是
- `pipeline-terminal-verification-gate.md` — 多段管线末端接验证闸门模板

### 已有约定 (继续有效)

- gen_publish_panel 是发布面板真相源
- 封面副标题只写人名，不加频道名
- 侵权风险根据来源频道自动评估回写飞书 — `_feishu.py` `assess_copyright_risk()`
- 标签不含"播客翻译""猫波信号站"

## 待发布视频

上次生产 (2026-07-30) 的三条视频已全部完成、状态待发布。

## 路由

- **飞书**: `https://fcn7dgp1xcm8.feishu.cn/base/F7E8bJie5aX3BvsZz1Xc9KiznNb?table=tblIs359fHfIapwd`
- **curation**: `D:\workspace\_output\猫波信号站\视频\_curation\`
- **catwave 数据**: `D:\workspace\evopearl-data\data\catwave\`
- **复盘**: `D:\workspace\_output\retrospectives\entries\2026-08-05-猫波信号站-管线重构.md`

## 未完成

- EPUB 百度云盘上传 (stage_09)
- B站 CDP 上传 (实验性)

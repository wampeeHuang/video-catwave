# YouTube Content Pipeline · 猫波信号站

YouTube → B站 完整管线：下载 → 翻译 → 字幕渲染 → 封面 → 元数据 → 上传。

## 项目定位

一句话：把 YouTube 英文视频搬运到 B站，加双语字幕 + 封面 + 元数据。

遵守 [FOLDER-CONSTITUTION.md](../FOLDER-CONSTITUTION.md) 工作区宪法。

## 文件管理规则

### 目录职责

| 目录 | 职责 | 谁看 | 规则 |
|------|------|------|------|
| `pipeline.py` | 核心 CLI 入口 | Agent | 唯一真相源，所有管线逻辑在这里 |
| `CLAUDE.md` | 项目约定+坑+流程 | Agent | 只放规则和硬约束，不放历史叙事 |
| `_tools/` | 辅助脚本 | Agent | 封面/头像生成、转录处理、测试。每个脚本只做一件事 |
| `_ref/` | 参考素材 | 人类 | B站规范截图、设计参考、设计哲学。不参与管线运行 |
| `_runtime/` | 运行时产出 | 人类 | 按视频分子文件夹；`downloads/` 和 `output/` 已 gitignore |

### 每期视频文件夹约定

```
_runtime/<video_slug>/          # 英文下划线命名，如 boris_sequoia_2026
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

`_process/` 和 `output/` 彻底分离。`_process/` 里的文件按 step 编号，`output/` 里只有上传 B站 需要的 4 个文件。

### 文件命名红线

- **禁止全角冒号（：U+FF1A）** 在文件名中，shell 编码必然炸
- 视频成品 = B站标题（≤80字），上传时自动识别
- `_process/` 内文件名固定（`01_raw.srt` ~ `05.ass`），pipeline.py 需对齐
- `output/` 内封面固定为 `cover.jpg`，不保留多版本
- 不使用 `_final` `_v2` `_old` 后缀——旧版直接删，git 能找回

### 新增视频 checklist

1. `mkdir _runtime/<video_slug>/` + 三个子目录 `_process/` `frames/` `output/`
2. yt-dlp 下载到 `_process/` → 跑完整管线 → 中间产物逐一写入 `_process/`
3. 截图至少 5 个时间点到 `frames/`，选主讲人正脸最清晰的一张，其余删除
4. 封面 `_tools/gen_cover.py` 生成 → `output/cover.jpg`
5. `output/B站上传信息.txt` 全部字段填完
6. `output/B站专栏文章.md` 写完
7. 渲染视频落 `output/<B站标题>.mp4`
8. 清理 yt-dlp 原始 mp4（185MB+，不入 git）

## 管线流程

### 1. 下载
```bash
yt-dlp --write-auto-subs --sub-langs en --convert-subs srt \
  -f "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/..." <url>
```
H.264+AAC（B站兼容），最高 1080p。

### 2. 断句（pipeline.py §1.5）
切句子级片段（目标 ~18 英文词/句），携带词裁剪。输出 `*_seg.srt`。

### 3. 翻译（pipeline.py §2）
DeepSeek API EN→ZH 双语，并行每批 10 条。输出 `*_zh.srt`。

### 4. 中文字符限制（pipeline.py §3）
`enforce_max_chars(srt_path, max_chars=28)` — 中文超 28 字拆为两条。

### 5. ASS 生成（pipeline.py §4）
`srt_to_ass(srt_path)` — 中文 SimHei 42px 中上，英文 Segoe UI 32px 中下。

### 6. 渲染（pipeline.py §5）
```bash
ffmpeg -i video.mp4 -vf "ass=subs.ass" -c:v libx264 -crf 20 -c:a copy output.mp4
```

### 7. B站元数据
- **标题**：≤80 字。从 transcript 提取最独特/反直觉的论断。不啰嗦，不堆砌关键词
- **标签**：≤10 个，每个 ≤12 字
- **简介**：≤2000 字。核心论点 + 嘉宾 + 出处
- **合集**：猫波译站
- **分区**：知识 > 科技 > 人工智能

### 8. 封面（_tools/gen_cover.py）
- 底图：视频截图，亮度 0.80（黑色透明度 80%），微微压暗
- 字体：SimHei（系统最粗中文），四周 2px 填充模拟超粗
- 主色：暖黄 #FFC82D，辅色：暖白 #FCFAF5
- 布局：全部居中，最多 3 行 + 1 条装饰线 + 底部信息条
- 不加频道水印

### 9. 专栏文章
从翻译 transcript 提取：引言 → 核心论点分节 → 结尾。B站专栏 markdown。

## B站 频道资产

| 项目 | 值 |
|------|-----|
| 昵称 | 猫波信号站 |
| 签名 | 猫波雷达滴滴响——又有好信号来了！🐾 |
| 合集 | 猫波译站 |
| 头像 | avatar_catwave_v3.png（1024×1024，浅暖白底，脉冲雷达图形） |

## 已知坑

- **全角冒号 U+FF1A** 在文件名→shell 编码错误，用 Python Path 对象绕过
- **B站 API 反爬**：查昵称用 WebFetch 搜 `search.bilibili.com/upuser?keyword=xxx`，"用户0"=可用
- **yt-dlp**：必须指定 H.264(`avc1`)+AAC(`m4a`)，否则拿 webm/vp9（B站不兼容）
- **enforce_max_chars** 签名：`(srt_path, max_chars=28)`，不是 `(srt_path, output_path)`
- **srt_to_ass** 不接受 `video_size` 参数
- **gpt-image-2** 走 aigoapi（key 在 memory），`b64_json` 可能空，用 `response_format="url"` + curl 下载
- **封面透明度**：用户说"透明度 80%"=透明度高=原图几乎全透，不是 80% 不透明。亮度 0.80 对应 80% 透明度

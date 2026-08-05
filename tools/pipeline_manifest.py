"""Pipeline contract manifest — single source of truth for stage I/O requirements.

Every stage declares:
  - required_inputs: files that MUST exist (relative to slug_dir)
  - required_outputs: files the stage MUST produce
  - validators: postflight validators to run (function names in validate_outputs.py)

Preflight reads this to gate before production. Postflight reads this to verify after.
"""

from pathlib import Path

# ── Stage contracts ──────────────────────────────────────────────────────────

STAGES = {
    "pipeline": {
        "label": "视频下载+字幕+翻译+渲染",
        "required_inputs": [],  # url/title passed as args, not files
        "required_outputs": [
            "_runtime/字幕/04_split.srt",
            "_runtime/字幕/03_zh.srt",
            "_runtime/字幕/05.ass",
            "_runtime/字幕/transcript.txt",
        ],
        "validators": ["validate_transcript"],
    },
    "bilibili_compliance": {
        "label": "B站合规检查",
        "required_inputs": [
            "_runtime/字幕/03_zh.srt",
            "_runtime/字幕/transcript.txt",
        ],
        "required_outputs": [],
        "validators": [],
    },
    "gen_metadata": {
        "label": "元数据+章节",
        "required_inputs": [
            "_runtime/字幕/04_split.srt",
            "_runtime/字幕/transcript.txt",
        ],
        "required_outputs": [
            "_runtime/metadata.json",
        ],
        "validators": ["validate_metadata", "validate_chapters"],
    },
    "gen_cover": {
        "label": "封面生成",
        "required_inputs": [],
        "required_outputs": ["cover.jpg"],
        "validators": ["validate_cover"],
    },
    "gen_epub": {
        "label": "EPUB电子书",
        "required_inputs": ["_runtime/字幕/03_zh.srt"],
        "required_outputs": [],  # EPUB goes into 电子书/ dir
        "validators": ["validate_epub"],
    },
    "gen_publish_panel": {
        "label": "发布面板",
        "required_inputs": ["_runtime/metadata.json"],
        "required_outputs": ["发布面板.html"],
        "validators": ["validate_panel"],
    },
    "final_assembly": {
        "label": "最终产出",
        "required_inputs": [
            "cover.jpg",
            "发布面板.html",
            "_runtime/metadata.json",
            "_runtime/字幕/05.ass",
            "_runtime/字幕/transcript.txt",
        ],
        "required_outputs": [],
        "validators": ["validate_video"],
    },
}

# ── Validator registry ───────────────────────────────────────────────────────
# Maps validator names → (module, function) for import-time resolution.
# Missing entries → postflight hard-fails (no silent skip).

VALIDATORS = {
    "validate_transcript":  ("validate_outputs", "_validate_transcript"),
    "validate_metadata":    ("validate_outputs", "_validate_metadata"),
    "validate_chapters":    ("validate_outputs", "_validate_chapters"),
    "validate_cover":       ("validate_cover",   "validate_cover"),
    "validate_epub":        ("validate_epub",    "validate_epub"),
    "validate_panel":       ("validate_panel",   "validate_panel"),
    "validate_video":       ("validate_video",   "validate_video"),
}

# ── Duration profile — single source of truth ────────────────────────────────

def duration_profile(duration_sec: int) -> dict:
    """所有时长相关参数的单一起源。入参：视频秒数。无分支，纯公式。

    所有模块从这里读取参数，禁止各自硬编码。
    """
    mins = duration_sec / 60

    return {
        # 章节
        "min_chapters":        max(2,  min(10, int(mins / 8 + 0.5))),
        "max_chapters":        10,                          # B站硬上限
        "max_chapter_title":   16,                          # B站硬上限
        "min_chapter_gap_sec": max(5,  int(duration_sec / 20)),
        "auto_chunk_sec":      max(10, int(duration_sec / 12)),

        # EPUB 分块
        "epub_chunk_sec":      max(60, int(duration_sec / 8)),

        # 视频文件大小
        "min_video_size_mb":   max(2,  int(mins * 0.3)),

        # 截图帧数
        "frame_count":         max(3,  min(20, int(mins / 2 + 0.5))),
        "min_frames":          max(2,  min(10, int(mins / 6 + 0.5))),  # 不超过 frame_count 下限

        # AI 功能最低时长
        "min_duration_for_ai": 180,                        # 3 分钟

        # 选题最低时长
        "min_duration_for_curation": 600,                  # 10 分钟
    }


def chapter_min_for_duration(duration_sec: int) -> int:
    """向后兼容 — 委托给 duration_profile。"""
    return duration_profile(duration_sec)["min_chapters"]

def quality_threshold(duration_sec: int = 3600) -> tuple[float, float]:
    """Returns (min_total_score, min_dim_score) for quality gate.

    Longer videos have higher bar — more production cost at stake.
    """
    if duration_sec < 1800:
        return (2.0, 1.0)
    return (2.0, 1.5)

"""Postflight validator — manifest-driven, no silent skip.

Usage:
  python tools/validate_outputs.py --slug <slug> [--title "B站标题"] [--frame <frame.jpg>]

Exit 0 = all deliverables present and valid, all registered validators ran.
Exit 1 = one or more failures.

Architecture:
  - File existence: checked against pipeline_manifest.STAGES required_outputs
  - Quality gates: each validator registered in pipeline_manifest.VALIDATORS
  - Missing validator module → hard FAIL (not WARN — no silent skip)
"""

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir, sanitize_filename
from pipeline_manifest import STAGES, VALIDATORS, duration_profile

REQUIRED = [
    ("cover.jpg", "封面", True),
    ("发布面板.html", "发布面板", True),
    ("成片", "成片目录", False),
    ("电子书", "电子书目录", False),
    ("_runtime/metadata.json", "元数据", True),
    ("_runtime/字幕/05.ass", "ASS字幕", True),
    ("_runtime/字幕/transcript.txt", "全文转录", True),
]

BILI_CHAPTER_LIMIT = 10
BILI_CHAPTER_TITLE_MAX = 16
BILI_CHAPTER_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def _check_metadata(sdir: Path) -> list[str]:
    results = []
    md_path = sdir / "_runtime" / "metadata.json"
    if not md_path.exists():
        return ["[FAIL] metadata.json 缺失"]
    try:
        md = json.loads(md_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"[FAIL] metadata.json 不是合法JSON: {e}"]

    for field in ["title", "source", "chapters", "tags"]:
        if field not in md:
            results.append(f"[FAIL] metadata.json 缺少字段: {field}")

    # ── Chapter validation ──
    chapters = md.get("chapters", [])
    if not chapters:
        results.append("[FAIL] 章节为空")
    elif len(chapters) > BILI_CHAPTER_LIMIT:
        results.append(f"[FAIL] 章节 {len(chapters)} 段 > B站上限 {BILI_CHAPTER_LIMIT}")
    else:
        # Adaptive minimum from manifest
        dur_sec = _video_duration_from_md(md)
        profile = duration_profile(dur_sec)
        min_ch = profile["min_chapters"]
        if len(chapters) < min_ch:
            results.append(f"[FAIL] 章节 {len(chapters)} 段 < {min_ch}（{dur_sec//60}分钟视频要求 ≥{min_ch}章）")
        else:
            results.append(f"[OK] 章节 {len(chapters)} 段 (上限{BILI_CHAPTER_LIMIT})")

    min_gap = profile["min_chapter_gap_sec"]
    prev_sec = -min_gap
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            ts, title = ch.get("start_time", ch.get("timestamp", "")), ch.get("title", "")
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            ts, title = ch[0], ch[1]
        else:
            results.append(f"[FAIL] 章节 {i+1} 格式无法解析")
            continue

        if not BILI_CHAPTER_TIME_RE.match(ts):
            results.append(f"[FAIL] 章节 {i+1} 时间格式错误: {ts} (应为 HH:MM:SS)")
        else:
            h, m, s = [int(x) for x in ts.split(":")]
            cur_sec = h * 3600 + m * 60 + s
            if cur_sec - prev_sec < min_gap and i > 0:
                results.append(f"[WARN] 章节 {i+1} 间距 {cur_sec - prev_sec}s < {min_gap}s")

        n = len(title)
        if n > BILI_CHAPTER_TITLE_MAX:
            results.append(f"[FAIL] 章节 {i+1} 标题 {n} 字 > {BILI_CHAPTER_TITLE_MAX} 上限: {title[:30]}")
        elif n == 0:
            results.append(f"[FAIL] 章节 {i+1} 标题为空")
        else:
            if i < 3 or any(title.endswith("..") for title in [chapters[j][1] for j in range(min(3, len(chapters)))]):
                # Show first 3 titles for audit
                results.append(f"[OK] 章节 {i+1}: {ts} {title} ({n}字)")

    return results


def _check_frames(sdir: Path) -> list[str]:
    frames_dir = sdir / "_runtime" / "frames"
    if not frames_dir.exists():
        return ["[WARN] _runtime/frames/ 不存在 — 选帧流程未执行（见 select_frame.py）"]
    jpgs = list(frames_dir.glob("*.jpg")) + list(frames_dir.glob("*.png"))
    n = len(jpgs)
    if n == 0:
        return ["[WARN] _runtime/frames/ 为空 — 未截图"]
    # Read video duration from selection.json or default
    sel_json = frames_dir / "selection.json"
    dur_sec = 3600
    if sel_json.exists():
        try:
            sel = json.loads(sel_json.read_text(encoding="utf-8"))
            dur_sec = int(sel.get("duration_s", 3600))
        except (json.JSONDecodeError, ValueError):
            pass
    min_frames = duration_profile(dur_sec)["min_frames"]
    if n < min_frames:
        return [f"[WARN] 仅 {n} 帧截图（{dur_sec//60}分钟视频要求 ≥{min_frames} 帧，见 AGENT_GUIDE.md §3）"]
    return [f"[OK] 截图 {n} 帧"]


def _run_validator(vname: str, slug: str, **kwargs):
    """Resolve and run a registered validator. Missing module = hard FAIL."""
    if vname not in VALIDATORS:
        return False, [f"[FAIL] Validator '{vname}' 未在 pipeline_manifest.VALIDATORS 注册"]

    module_name, func_name = VALIDATORS[vname]
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        return False, [f"[FAIL] Validator 模块缺失: {module_name}.py（manifest 已注册但文件不存在）"]

    func = getattr(mod, func_name, None)
    if func is None:
        return False, [f"[FAIL] {module_name}.{func_name}() 不存在（manifest 注册的函数名与文件不一致）"]

    try:
        return func(slug, **kwargs)
    except TypeError:
        # Retry without extra kwargs
        return func(slug)


def _video_duration_from_md(md: dict) -> int:
    """Estimate video duration from metadata chapters (last timestamp)."""
    chapters = md.get("chapters", [])
    if chapters:
        last = chapters[-1]
        if isinstance(last, dict):
            ts = last.get("timestamp", last.get("start_time", "01:00:00"))
        elif isinstance(last, (list, tuple)) and len(last) >= 1:
            ts = last[0]
        else:
            return 3600
        try:
            h, m, s = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + int(s)
        except (ValueError, AttributeError):
            return 3600
    return 3600


def _validate_transcript(slug: str, **kwargs) -> tuple[bool, list[str]]:
    """Manifest-registered: transcript.txt exists with content."""
    sdir = slug_dir(slug)
    tp = sdir / "_runtime" / "字幕" / "transcript.txt"
    if not tp.exists():
        return False, ["[FAIL] transcript.txt 缺失"]
    if tp.stat().st_size < 100:
        return False, [f"[FAIL] transcript.txt 过小 ({tp.stat().st_size} bytes)"]
    return True, [f"[OK] transcript.txt ({tp.stat().st_size} bytes)"]


def _validate_metadata(slug: str, **kwargs) -> tuple[bool, list[str]]:
    """Manifest-registered: metadata.json valid JSON with required fields."""
    sdir = slug_dir(slug)
    mp = sdir / "_runtime" / "metadata.json"
    if not mp.exists():
        return False, ["[FAIL] metadata.json 缺失"]
    try:
        md = json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"[FAIL] metadata.json 非合法JSON: {e}"]
    missing = [f for f in ["title", "source", "chapters", "tags"] if f not in md]
    if missing:
        return False, [f"[FAIL] metadata.json 缺字段: {missing}"]
    return True, [f"[OK] metadata.json 字段完整"]


def _validate_chapters(slug: str, **kwargs) -> tuple[bool, list[str]]:
    """Manifest-registered: chapter count, format, spacing."""
    sdir = slug_dir(slug)
    mp = sdir / "_runtime" / "metadata.json"
    if not mp.exists():
        return False, ["[FAIL] metadata.json 缺失，无法验证章节"]
    md = json.loads(mp.read_text(encoding="utf-8"))
    chapters = md.get("chapters", [])
    if not chapters:
        return False, ["[FAIL] 章节为空"]
    dur_sec = _video_duration_from_md(md)
    profile = duration_profile(dur_sec)
    if len(chapters) > profile["max_chapters"]:
        return False, [f"[FAIL] 章节 {len(chapters)} > B站上限 {profile['max_chapters']}"]
    min_ch = profile["min_chapters"]
    if len(chapters) < min_ch:
        return False, [f"[FAIL] 章节 {len(chapters)} < {min_ch}（{dur_sec//60}分钟视频要求 ≥{min_ch}章）"]
    return True, [f"[OK] 章节 {len(chapters)} 段（{dur_sec//60}分钟视频，下限{min_ch}章）"]


def _check_ass(sdir: Path) -> list[str]:
    """Check ASS subtitle border style."""
    ass_file = sdir / "_runtime" / "字幕" / "05.ass"
    if not ass_file.exists():
        return ["[WARN] 05.ass 不存在"]
    ass_text = ass_file.read_text(encoding="utf-8")
    m = re.search(r"Style:(?:[^,]*,){16}([^,]+)", ass_text)
    if m:
        outline = m.group(1).strip()
        try:
            outline_val = int(outline)
            if outline_val == 1:
                return ["[OK] ASS 字幕描边 1px"]
            elif outline_val == 0:
                return ["[WARN] ASS 字幕无描边（bord=0）"]
            else:
                return [f"[WARN] ASS 字幕描边 {outline_val}px，期望 1px"]
        except ValueError:
            return ["[WARN] 无法解析 ASS 描边值"]
    return ["[WARN] 无法解析 ASS Style 行"]


def validate(slug: str, title: str | None = None, frame: str | None = None) -> tuple[bool, list[str]]:
    sdir = slug_dir(slug)
    ok = True
    details: list[str] = []

    for rel, label, is_file in REQUIRED:
        p = sdir / rel
        if is_file:
            if not p.exists():
                details.append(f"[FAIL] {label}: {rel} — 缺失")
                ok = False
            elif p.stat().st_size == 0:
                details.append(f"[FAIL] {label}: {rel} — 空文件")
                ok = False
            else:
                size = p.stat().st_size
                size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
                details.append(f"[OK] {label}: {rel} ({size_str})")
        else:
            if not p.exists() or not p.is_dir():
                details.append(f"[FAIL] {label}: {rel} — 目录缺失")
                ok = False
            else:
                contents = list(p.iterdir())
                details.append(f"[OK] {label}: {rel} ({len(contents)} files)")

    # Video file
    if title:
        safe_title = sanitize_filename(title)
        video = sdir / "成片" / f"{safe_title}.mp4"
        if video.exists() and video.stat().st_size > 0:
            size_mb = video.stat().st_size / 1024 / 1024
            details.append(f"[OK] video: {safe_title}.mp4 ({size_mb:.0f} MB)")
        else:
            details.append(f"[FAIL] video: {safe_title}.mp4 — 缺失或空文件")
            ok = False

    # ── Manifest-driven quality gates ──
    details.append("\n── 元数据质量 ──")
    for r in _check_metadata(sdir):
        details.append(r)
        if r.startswith("[FAIL]"):
            ok = False

    details.append("\n── 截图质量 ──")
    for r in _check_frames(sdir):
        details.append(r)

    # All registered validators — manifest-driven, missing = hard fail
    validators_to_run = [
        ("validate_cover", "封面质量", lambda: _run_validator("validate_cover", slug, frame=frame)),
        ("validate_panel", "发布面板质量", lambda: _run_validator("validate_panel", slug)),
        ("validate_epub", "电子书质量", lambda: _run_validator("validate_epub", slug)),
        ("validate_video", "成片质量", lambda: _run_validator("validate_video", slug, title=title)),
    ]

    for vname, label, runner in validators_to_run:
        details.append(f"\n── {label} ──")
        vok, vresults = runner()
        for r in vresults:
            details.append(r)
        if not vok:
            ok = False

    # ── ASS subtitle border ──
    details.append("\n── 字幕样式 ──")
    for r in _check_ass(sdir):
        details.append(r)

    return ok, details


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="验证猫波信号站产出完整性 + 质量门禁")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", default=None, help="B站视频标题（检查成片文件名）")
    p.add_argument("--frame", default=None, help="源截图路径（封面亮度检查）")
    args = p.parse_args()

    ok, details = validate(args.slug, args.title, args.frame)
    for d in details:
        print(d)
    print(f"\n{'ALL PASS' if ok else 'MISSING / INVALID FILES OR QUALITY GATES'}")
    sys.exit(0 if ok else 1)

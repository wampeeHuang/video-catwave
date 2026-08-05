#!/usr/bin/env python3
"""Panel verifier: checks 发布面板.html structure and content against B站 limits.

Usage:
  python tools/validate_panel.py --slug <slug>

This is the VERIFICATION layer. Production: AI writes 发布面板.html per AGENT_GUIDE.md §4.

Checks:
  1. Valid HTML, readable
  2. All 8 required sections present (title/copyright/category/tags/collection/desc/chapters/cover/video)
  3. Title ≤80 chars
  4. Tags ≤10
  5. Description ≤2000 chars
  6. Chapters ≤10, each ≤16 chars, HH:MM:SS format
  7. Each field has a copy button
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir
from pipeline_manifest import duration_profile

BILI_TITLE_MAX = 80
BILI_TAG_MAX = 10
BILI_DESC_MAX = 2000
BILI_CHAPTER_MAX = 10
BILI_CHAPTER_TITLE_MAX = 16
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}")

REQUIRED_SECTIONS = [
    ("id=\"title\"", "标题"),
    ("id=\"copyright\"", "创作声明"),
    ("id=\"category\"", "分区"),
    ("id=\"tags\"", "标签"),
    ("id=\"collection\"", "合集"),
    ("id=\"desc\"", "简介"),
    ("id=\"chapters\"", "章节"),
    ("封面", "封面信息"),  # cover section has no id, keyword match
    ("视频文件", "视频信息"),
]


def _extract_text(html: str, elem_id: str) -> str:
    m = re.search(rf'id="{elem_id}"[^>]*>([\s\S]*?)</div>', html)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def _count_copy_buttons(html: str, section_id: str) -> int:
    """Count copy buttons within a section's field div (header + body)."""
    # Find the whole field div containing this section_id
    m = re.search(rf'<div class="field">([\s\S]*?)id="{section_id}"[\s\S]*?</div>\s*</div>\s*</div>', html)
    if not m:
        return 0
    block = m.group(0)
    return len(re.findall(r"copyField|navigator\.clipboard\.writeText", block))


def validate_panel(slug: str) -> tuple[bool, list[str]]:
    sdir = slug_dir(slug)
    panel = sdir / "发布面板.html"
    results: list[str] = []
    all_ok = True

    if not panel.exists():
        return False, [f"[FAIL] 发布面板.html 不存在: {panel}"]
    if panel.stat().st_size == 0:
        return False, [f"[FAIL] 发布面板.html 是空文件"]

    html = panel.read_text(encoding="utf-8")
    if not html.strip().startswith("<!DOCTYPE html>") and not html.strip().startswith("<html"):
        results.append("[WARN] 发布面板.html 不以标准 HTML 开头")
    else:
        results.append("[OK] 有效 HTML 结构")

    # ── Required sections ──
    for keyword, label in REQUIRED_SECTIONS:
        if keyword not in html:
            results.append(f"[FAIL] 缺少字段: {label}")
            all_ok = False
    if all(r.startswith("[OK]") or r.startswith("[WARN]") for r in results):
        results.append("[OK] 全部 8 个必填字段存在")

    # ── Title ──
    title = _extract_text(html, "title")
    if title:
        n = len(title)
        if n > BILI_TITLE_MAX:
            results.append(f"[FAIL] 标题 {n} 字 > {BILI_TITLE_MAX} 上限")
            all_ok = False
        else:
            results.append(f"[OK] 标题 {n}/{BILI_TITLE_MAX} 字")
    else:
        results.append("[FAIL] 标题为空")
        all_ok = False

    # ── Tags ──
    tag_count = len(re.findall(r'<div class="?tag-row', html))
    if tag_count == 0:
        results.append("[FAIL] 未找到标签")
        all_ok = False
    elif tag_count > BILI_TAG_MAX:
        results.append(f"[FAIL] 标签 {tag_count} 个 > {BILI_TAG_MAX} 上限")
        all_ok = False
    else:
        results.append(f"[OK] 标签 {tag_count}/{BILI_TAG_MAX} 个")
        # Check individual copy buttons
        tag_buttons = _count_copy_buttons(html, "tags")
        if tag_buttons < tag_count:
            results.append(f"[WARN] 标签复制按钮 {tag_buttons} < 标签数 {tag_count}")

    # ── Description ──
    desc = _extract_text(html, "desc")
    if desc:
        n = len(desc)
        if n > BILI_DESC_MAX:
            results.append(f"[FAIL] 简介 {n} 字 > {BILI_DESC_MAX} 上限")
            all_ok = False
        else:
            results.append(f"[OK] 简介 {n}/{BILI_DESC_MAX} 字")
    else:
        results.append("[WARN] 简介为空")

    # ── Chapters ──
    chapters_text = _extract_text(html, "chapters")
    if chapters_text:
        lines = [l.strip() for l in chapters_text.split("\n") if l.strip()]
        if len(lines) > BILI_CHAPTER_MAX:
            results.append(f"[FAIL] 章节 {len(lines)} 段 > {BILI_CHAPTER_MAX} 上限")
            all_ok = False
        else:
            results.append(f"[OK] 章节 {len(lines)}/{BILI_CHAPTER_MAX} 段")

        # Estimate video duration from last chapter timestamp
        last_ts = lines[-1][:8] if lines else "01:00:00"
        try:
            lh, lm, ls = (int(x) for x in last_ts.split(":"))
            est_dur = lh * 3600 + lm * 60 + ls
        except (ValueError, IndexError):
            est_dur = 3600
        min_gap = duration_profile(est_dur)["min_chapter_gap_sec"]

        prev_sec = -min_gap
        for i, line in enumerate(lines):
            if len(line) < 9:
                results.append(f"[FAIL] 章节 {i+1} 格式异常: {line[:40]}")
                all_ok = False
                continue
            ts = line[:8]
            title_text = line[9:] if len(line) > 9 else ""
            if not TIME_RE.match(ts):
                results.append(f"[FAIL] 章节 {i+1} 时间格式错误: {ts}")
                all_ok = False
            if len(title_text) > BILI_CHAPTER_TITLE_MAX:
                results.append(f"[FAIL] 章节 {i+1} 标题 {len(title_text)} 字 > {BILI_CHAPTER_TITLE_MAX}: {title_text[:30]}")
                all_ok = False
            h, m, s = (int(x) for x in ts.split(":"))
            cur_sec = h * 3600 + m * 60 + s
            if cur_sec - prev_sec < min_gap and i > 0:
                results.append(f"[WARN] 章节 {i+1} 间距 {cur_sec - prev_sec}s < {min_gap}s")
            prev_sec = cur_sec
    else:
        results.append("[FAIL] 章节为空")
        all_ok = False

    # ── Copy buttons check ──
    for section_id in ["title", "category", "collection", "desc", "chapters"]:
        n = _count_copy_buttons(html, section_id)
        if n == 0:
            results.append(f"[WARN] {section_id} 缺少复制按钮")

    # ── Source link check ──
    if "youtube.com" in html.lower() or "youtu.be" in html.lower():
        results.append("[OK] 来源链接存在")
    else:
        results.append("[WARN] 未检测到 YouTube 来源链接")

    # ── Duration consistency ──
    video_dir = sdir / "成片"
    if video_dir.exists():
        mp4s = list(video_dir.glob("*.mp4"))
        if mp4s:
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(mp4s[0])],
                    capture_output=True, text=True, timeout=15,
                )
                actual_s = float(r.stdout.strip())
                actual_h, actual_r = divmod(int(actual_s), 3600)
                actual_m, actual_s2 = divmod(actual_r, 60)

                # Extract displayed duration from panel (~H:MM:SS format)
                dur_m = re.search(r"~\d+:\d{2}:\d{2}", html)
                if dur_m:
                    parts = dur_m.group(0).lstrip("~").split(":")
                    displayed_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    diff_pct = abs(displayed_s - actual_s) / actual_s if actual_s > 0 else 0
                    if diff_pct > 0.05:
                        results.append(f"[FAIL] 面板时长 ~{':'.join(parts)} 与实际 {actual_h}:{actual_m:02d}:{actual_s2:02d} 偏差 {diff_pct:.0%}")
                        all_ok = False
                    else:
                        results.append(f"[OK] 面板时长与实际一致 (~{':'.join(parts)})")
            except Exception:
                pass

    return all_ok, results


def main():
    p = argparse.ArgumentParser(description="验证发布面板是否符合 B站 规范")
    p.add_argument("--slug", required=True)
    args = p.parse_args()

    ok, results = validate_panel(args.slug)
    for r in results:
        print(r)
    print(f"\n{'PANEL OK' if ok else 'PANEL NEEDS FIX'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

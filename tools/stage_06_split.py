"""Stage ⑥: Punctuation-first line splitting + PIL pixel width check.

Usage: python stage_06_split.py --slug <slug>
Input:  <output>/_runtime/字幕/03_zh.srt
Output: <output>/_runtime/字幕/04_split.srt

Logic:
  1. For each bilingual entry, check if Chinese pixel width exceeds max_px.
  2. If over: split at the punctuation point closest to the midpoint,
     iterating until all segments fit.
  3. English text is sync-split at the same character ratio.
  4. max_px defaults to 1520 (1920 - 200*2 margins) for SimHei @ 42px.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import SubEntry, ms_to_time, read_srt, srt_path, time_to_ms, write_srt

# ── Config ───────────────────────────────────────────────────────────────────

CN_FONT_SIZE = 42
EN_FONT_SIZE = 36  # Microsoft YaHei in ASS \fn override
VIDEO_W = 1920
MARGIN_LR = 200
MAX_PX = VIDEO_W - MARGIN_LR * 2  # 1520px


def run(slug: str, max_px: int = MAX_PX):
    src = srt_path(slug, "03_zh.srt")
    if not src.exists():
        print(f"ERROR: {src} not found. Run stage_05 first.")
        sys.exit(1)

    entries = read_srt(src)
    print(f"[⑥] Checking {len(entries)} lines (max {max_px}px)...")

    result = []
    over_count = 0
    for e in entries:
        parts = e.text.split("\\N", 1)
        zh = parts[0].strip()
        en = parts[1].strip() if len(parts) > 1 else ""

        if _cn_pixel_width(zh) <= max_px:
            result.append(e)
            continue

        # Need split
        over_count += 1
        segments_zh = _split_at_punctuation(zh, max_px)
        segments_en = _sync_split_en(en, zh, [len(s) for s in segments_zh])

        start_ms = time_to_ms(e.start)
        end_ms = time_to_ms(e.end)
        total_dur = end_ms - start_ms
        seg_widths = [_cn_pixel_width(s) for s in segments_zh]
        total_w = sum(seg_widths)

        # Merge segments whose estimated duration < 2s into the previous segment
        MIN_SEG_MS = 2000
        merged_zh = []
        merged_en = []
        for i, seg_zh in enumerate(segments_zh):
            seg_en = segments_en[i] if i < len(segments_en) else ""
            est_dur = int(total_dur * seg_widths[i] / total_w) if total_w > 0 else 0
            if est_dur < MIN_SEG_MS and merged_zh:
                merged_zh[-1] += seg_zh
                if merged_en[-1] and seg_en:
                    merged_en[-1] += " " + seg_en
            else:
                merged_zh.append(seg_zh)
                merged_en.append(seg_en)

        merged_widths = [_cn_pixel_width(s) for s in merged_zh]
        merged_total_w = sum(merged_widths)

        cursor = start_ms
        for i, seg_zh in enumerate(merged_zh):
            ratio = merged_widths[i] / merged_total_w if merged_total_w > 0 else 1 / len(merged_zh)
            seg_dur = max(int(total_dur * ratio), 400)
            seg_end = end_ms if i == len(merged_zh) - 1 else cursor + seg_dur
            seg_en = merged_en[i]
            text = f"{seg_zh}\\N{seg_en}" if seg_en else seg_zh
            result.append(SubEntry(len(result) + 1, ms_to_time(cursor), ms_to_time(seg_end), text))
            cursor = seg_end

    out = srt_path(slug, "04_split.srt")
    write_srt(result, out)
    print(f"  {over_count} entries split → {len(result)} total lines")
    print(f"  → {out.name}")


# ── Pixel width measurement ──────────────────────────────────────────────────


def _cn_pixel_width(text: str) -> int:
    """Estimate pixel width of text rendered in SimHei @ CN_FONT_SIZE.
    Uses character-type heuristics: CJK char ≈ font_size px, Latin ≈ 0.55x.
    """
    w = 0
    for ch in text:
        cp = ord(ch)
        if cp < 128:
            w += int(CN_FONT_SIZE * 0.55)  # Latin
        elif 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
            w += CN_FONT_SIZE  # CJK
        else:
            w += CN_FONT_SIZE  # Fullwidth punct, etc.
    return w


# ── Punctuation-first splitting ──────────────────────────────────────────────


def _split_at_punctuation(text: str, max_px: int, depth: int = 0) -> list[str]:
    """Split text at punctuation points, preferring the split closest to midpoint.
    Iterates: splits, checks each part, re-splits if any part still too wide.
    """
    if depth > 50 or len(text) <= 1 or _cn_pixel_width(text) <= max_px:
        return [text]

    punct = "，。！？；、"
    # Find all punctuation positions
    positions = [i for i, ch in enumerate(text) if ch in punct]
    if not positions:
        # No punctuation — hard split at midpoint, then check each half
        mid = len(text) // 2
        if mid == 0:
            return [text]
        result = []
        for part in [text[:mid], text[mid:]]:
            if _cn_pixel_width(part) > max_px:
                result.extend(_split_at_punctuation(part, max_px, depth + 1))
            elif part.strip():
                result.append(part)
        return result

    # Find the punctuation closest to half the pixel width
    target_w = _cn_pixel_width(text) / 2
    best_pos = positions[0]
    best_diff = abs(_cn_pixel_width(text[:best_pos + 1]) - target_w)
    for pos in positions[1:]:
        w = _cn_pixel_width(text[:pos + 1])
        diff = abs(w - target_w)
        if diff < best_diff:
            best_diff = diff
            best_pos = pos

    left = text[:best_pos + 1]
    right = text[best_pos + 1:]

    # Recurse: if either half still too wide, split it further
    result = []
    for part in [left, right]:
        if _cn_pixel_width(part) > max_px:
            result.extend(_split_at_punctuation(part, max_px, depth + 1))
        else:
            if part.strip():
                result.append(part)
    return result


# ── English sync-split ───────────────────────────────────────────────────────


def _sync_split_en(en: str, zh_original: str, zh_seg_lengths: list[int]) -> list[str]:
    """Split English text at position proportional to Chinese split points."""
    if not en or len(zh_seg_lengths) <= 1:
        return [en]
    total_zh = sum(zh_seg_lengths)
    en_words = en.split()
    if not en_words:
        return [en] * len(zh_seg_lengths)

    result = []
    cursor = 0
    for seg_len in zh_seg_lengths[:-1]:
        ratio = (cursor + seg_len) / total_zh
        split_at = min(int(len(en_words) * ratio), len(en_words) - 1)
        split_at = max(split_at, 1)  # At least 1 word
        result.append(" ".join(en_words[:split_at]))
        en_words = en_words[split_at:]
        cursor += seg_len
    result.append(" ".join(en_words))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑥ Punctuation-first line splitting")
    p.add_argument("--slug", required=True)
    p.add_argument("--max-px", type=int, default=MAX_PX)
    args = p.parse_args()
    run(args.slug, max_px=args.max_px)

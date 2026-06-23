"""Stage ③: Merge time-overlapping YouTube fragments, then LLM adds punctuation.

Usage: python stage_03_segment.py --slug <slug>
Input:  <lab>/_runtime/<slug>_process/01_raw.srt
Output: <output>/_runtime/字幕/02_seg.srt

Logic:
  1. Scan 01_raw.srt fragments. Consecutive fragments whose time ranges overlap
     are merged into one segment. Max 30s per segment to avoid infinite chains.
  2. Non-overlapping fragments stay independent.
  3. Segments are sent to DeepSeek in batches. LLM adds punctuation and
     splits at EVERY major punctuation mark with <S>. One line per segment.
  4. Each <S> clause gets a proportional slice of the segment's time range.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    PROCESS_ROOT, SubEntry, ms_to_time, read_srt, srt_path, time_to_ms, write_srt,
)

MAX_SEGMENT_MS = 30_000  # Max duration per merged segment
OVERLAP_TOLERANCE_MS = 200  # Gap tolerance for merging


def run(slug: str, *, api_key: str | None = None):
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    lab_srt = PROCESS_ROOT / slug / "_process" / "01_raw.srt"
    if not lab_srt.exists():
        hits = sorted(PROCESS_ROOT.glob(f"*_{slug}"))
        lab_srt = hits[0] / "_process" / "01_raw.srt" if hits else lab_srt
    if not lab_srt.exists():
        print(f"ERROR: {lab_srt} not found. Run stage_02_download first.")
        sys.exit(1)

    raw = read_srt(lab_srt)
    print(f"[③] {len(raw)} raw fragments → merging overlapping...")

    merged = _merge_overlapping(raw)
    print(f"  {len(merged)} segments after time-overlap merge (max {MAX_SEGMENT_MS // 1000}s each)")

    if not api_key:
        print("  WARNING: No DEEPSEEK_API_KEY, writing merged text as-is")
        out = srt_path(slug, "02_seg.srt")
        write_srt(merged, out)
        print(f"  → {out}")
        return

    print(f"  Adding punctuation via DeepSeek...")
    segmented = _llm_add_punctuation(merged, api_key)
    print(f"  {len(segmented)} clauses after punctuation split")

    out = srt_path(slug, "02_seg.srt")
    write_srt(segmented, out)
    print(f"  → {out}")


# ── Mechanical de-overlap ────────────────────────────────────────────────────


def _merge_overlapping(entries: list[SubEntry]) -> list[SubEntry]:
    """Merge consecutive fragments whose time ranges overlap, capped at MAX_SEGMENT_MS."""
    if not entries:
        return []
    result = []
    i = 0
    seq = 0
    while i < len(entries):
        buf = [entries[i].text]
        buf_start = entries[i].start
        buf_start_ms = time_to_ms(buf_start)
        buf_end = entries[i].end
        buf_end_ms = time_to_ms(buf_end)
        j = i + 1
        while j < len(entries):
            next_start_ms = time_to_ms(entries[j].start)
            # Break if gap too large
            if next_start_ms > buf_end_ms + OVERLAP_TOLERANCE_MS:
                break
            # If cap would trigger, clip current end to avoid overlap with next segment
            if next_start_ms - buf_start_ms > MAX_SEGMENT_MS:
                buf_end_ms = max(buf_start_ms + 800, next_start_ms - 20)
                buf_end = ms_to_time(buf_end_ms)
                break
            buf.append(entries[j].text)
            buf_end = entries[j].end
            buf_end_ms = time_to_ms(buf_end)
            j += 1
        text = " ".join(buf)
        seq += 1
        result.append(SubEntry(seq, buf_start, buf_end, text.strip()))
        i = j
    return result


# ── LLM punctuation (short-clause mode) ──────────────────────────────────────


def _llm_add_punctuation(segments: list[SubEntry], api_key: str) -> list[SubEntry]:
    """Send segments to DeepSeek. Returns clauses split at every punctuation mark."""
    if len(segments) < 2:
        return segments

    batch_size = 15  # Segments per LLM call
    all_clauses = []
    seq = 1

    for bi in range(0, len(segments), batch_size):
        batch = segments[bi:bi + batch_size]

        # Build numbered input
        lines = [f"{j+1}. {seg.text.strip()}" for j, seg in enumerate(batch)]
        prompt_lines = "\n".join(lines)

        prompt = (
            "Add punctuation (periods, commas, question marks, semicolons, colons) "
            "to these English transcript fragments. CRITICAL: do NOT change ANY words. Only add punctuation.\n\n"
            "Split at EVERY punctuation mark with <S>. Do NOT merge fragments together.\n"
            "Output ONE LINE per input fragment, with its <S>-split clauses all on that one line.\n"
            "Goal: each <S> clause should be short — one breath, ~5-15 words.\n\n"
            f"{prompt_lines}"
        )

        result = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    "https://api.deepseek.com/v1/chat/completions",
                    data=json.dumps({
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": (
                                "You restore punctuation to ASR transcripts. "
                                "Split at EVERY punctuation mark (. , ; : ! ?) with <S>. "
                                "Output ONE LINE per input fragment. Never change any word."
                            )},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 8192,
                    }).encode(),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    body = json.loads(resp.read())
                    result = body["choices"][0]["message"]["content"].strip()
                    break
            except Exception as e:
                if attempt == 1:
                    print(f"    Batch {bi // batch_size} failed: {e}")
                time.sleep(2)

        if result:
            seq = _parse_batch_result(result, batch, all_clauses, seq)
        else:
            # Fallback: keep original segments
            for seg in batch:
                all_clauses.append(SubEntry(seq, seg.start, seg.end, seg.text))
                seq += 1

    if not all_clauses:
        return segments
    return all_clauses


def _parse_batch_result(result: str, batch: list[SubEntry], out: list[SubEntry], seq: int) -> int:
    """Parse LLM output: one line per segment, <S>-split into clauses."""
    lines = [l.strip() for l in result.split("\n") if l.strip()]
    # Remove any leading numbers like "1. " that LLM might add
    import re

    def strip_leading_num(line: str) -> str:
        return re.sub(r'^\d+\.\s*', '', line.strip())

    for j, seg in enumerate(batch):
        if j >= len(lines):
            # LLM didn't return enough lines — use original
            out.append(SubEntry(seq, seg.start, seg.end, seg.text))
            seq += 1
            continue

        line = strip_leading_num(lines[j])
        clauses = [c.strip() for c in line.split("<S>") if c.strip()]
        if not clauses:
            out.append(SubEntry(seq, seg.start, seg.end, seg.text))
            seq += 1
            continue

        seg_start_ms = time_to_ms(seg.start)
        seg_end_ms = time_to_ms(seg.end)
        seg_dur = seg_end_ms - seg_start_ms

        # Distribute time proportionally by character count
        total_chars = sum(len(c) for c in clauses)
        cursor = seg_start_ms
        for ci, clause in enumerate(clauses):
            ratio = len(clause) / total_chars if total_chars > 0 else 1.0 / len(clauses)
            dur = max(int(seg_dur * ratio), 800)
            if ci == len(clauses) - 1:
                end_ms = seg_end_ms
            else:
                end_ms = min(cursor + dur, seg_end_ms)
            out.append(SubEntry(seq, ms_to_time(cursor), ms_to_time(end_ms), clause))
            cursor = end_ms
            seq += 1
    return seq


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="③ De-overlap + LLM punctuation")
    p.add_argument("--slug", required=True)
    args = p.parse_args()
    run(args.slug)

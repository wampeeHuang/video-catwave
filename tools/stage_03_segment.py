"""DEPRECATED — Use stage_03_whisper.py instead.

YouTube auto-caption timestamps are sliding windows with inherent overlaps
(see _ref/pitfalls.md §时序漂移). This script is kept as emergency fallback
only — it requires --force to run and prints a warning.

Usage: python stage_03_segment.py --slug <slug> --force
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    SubEntry, find_video, ms_to_time, read_srt, srt_path, time_to_ms, write_srt,
)

MIN_DURATION_MS = 100


def run(slug: str, *, api_key: str | None = None, force: bool = False):
    if not force:
        print("=" * 60)
        print("  DEPRECATED — Use stage_03_whisper.py instead.")
        print("  YouTube auto-caption timestamps are sliding windows with")
        print("  inherent overlaps. Whisper timestamps are audio-aligned.")
        print("  Add --force to run this script anyway.")
        print("=" * 60)
        sys.exit(1)

    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    video = find_video(slug)
    if not video or not video.exists():
        print(f"ERROR: No video found for slug '{slug}'. Run stage_02_download first.")
        sys.exit(1)
    raw_srt = video.parent / "01_raw.srt"
    if not raw_srt.exists():
        print(f"ERROR: {raw_srt} not found. Run stage_02_download first.")
        sys.exit(1)

    raw = read_srt(raw_srt)
    print(f"[③] {len(raw)} raw fragments → extracting deltas...")

    deltas = _extract_deltas(raw)
    print(f"  {len(deltas)} deltas (filtered stubs)")

    if not api_key:
        print("  WARNING: No DEEPSEEK_API_KEY, writing deltas as-is")
        write_srt(deltas, srt_path(slug, "02_seg.srt"))
        return

    print(f"  Adding punctuation via DeepSeek...")
    punctuated = _llm_add_punctuation(deltas, api_key)
    print(f"  {len(punctuated)} deltas with punctuation")

    merged = _merge_to_sentences(punctuated)
    print(f"  {len(merged)} sentences after merging")

    split = _split_long_sentences(merged)
    print(f"  → {len(split)} entries after splitting long sentences")

    out = srt_path(slug, "02_seg.srt")
    write_srt(split, out)
    print(f"  → {out}")


def _extract_deltas(entries: list[SubEntry]) -> list[SubEntry]:
    """Extract new-text delta from YouTube sliding-window fragments.

    Keeps fragments with duration >= MIN_DURATION_MS. For each, finds the
    new words that weren't in the previous fragment. Preserves original timing.
    """
    meaningful = [e for e in entries
                  if time_to_ms(e.end) - time_to_ms(e.start) >= MIN_DURATION_MS]
    if not meaningful:
        return []

    result = []
    prev = ""
    seq = 0
    for e in meaningful:
        cur = e.text.strip()
        if not cur:
            prev = cur
            continue
        delta = _delta(prev, cur)
        if delta:
            seq += 1
            result.append(SubEntry(seq, e.start, e.end, delta))
        prev = cur
    return result


def _delta(prev: str, cur: str) -> str:
    """Return the new words in cur that weren't in prev."""
    if not prev:
        return cur
    if prev == cur:
        return ""
    pw = prev.split()
    cw = cur.split()
    for n in range(min(len(pw), len(cw) - 1), 0, -1):
        if pw[-n:] == cw[:n]:
            d = cw[n:]
            return " ".join(d) if d else ""
    return cur


SENTENCE_ENDS = {'.', '!', '?'}


def _merge_to_sentences(deltas: list[SubEntry]) -> list[SubEntry]:
    """Merge consecutive deltas into sentences at period/?! boundaries.

    A delta ending with . ! ? closes a sentence. Others continue.
    Merged sentence takes the start of its first delta and the end of its last.
    """
    if not deltas:
        return []

    result = []
    buf_texts = []
    buf_start = None
    seq = 0

    for e in deltas:
        text = e.text.strip()
        if not text:
            continue

        if buf_start is None:
            buf_start = e.start

        buf_texts.append(text)

        if text[-1] in SENTENCE_ENDS:
            seq += 1
            result.append(SubEntry(seq, buf_start, e.end, " ".join(buf_texts)))
            buf_texts = []
            buf_start = None

    # Flush remaining (trailing incomplete sentence)
    if buf_texts:
        seq += 1
        result.append(SubEntry(seq, buf_start or deltas[0].start,
                               deltas[-1].end, " ".join(buf_texts)))

    return result


MAX_SENTENCE_MS = 12_000  # Split sentences longer than this at comma boundaries


def _split_long_sentences(entries: list[SubEntry]) -> list[SubEntry]:
    """Split overlong sentences at comma boundaries for readable subtitle duration."""
    result = []
    seq = 0
    for e in entries:
        dur = time_to_ms(e.end) - time_to_ms(e.start)
        if dur <= MAX_SENTENCE_MS:
            seq += 1
            e.index = seq
            result.append(e)
            continue

        text = e.text
        splits = [m.end() for m in re.finditer(r'[,;]', text)]

        if not splits:
            # No punctuation — split by words into ~equal chunks
            words = text.split()
            if len(words) < 2:
                seq += 1
                e.index = seq
                result.append(e)
                continue
            num_chunks = max(2, dur // MAX_SENTENCE_MS + 1)
            words_per = max(1, len(words) // num_chunks)
            start_ms = time_to_ms(e.start)
            end_ms = time_to_ms(e.end)
            chunk_dur = (end_ms - start_ms) / min(num_chunks, len(words))
            for ci in range(0, len(words), words_per):
                chunk_words = words[ci:ci + words_per]
                if not chunk_words:
                    continue
                seq += 1
                chunk_start = start_ms + int(ci / len(words) * (end_ms - start_ms))
                chunk_end = min(start_ms + int((ci + len(chunk_words)) / len(words) * (end_ms - start_ms)), end_ms)
                if ci + words_per >= len(words):
                    chunk_end = end_ms
                result.append(SubEntry(seq, ms_to_time(chunk_start), ms_to_time(chunk_end), " ".join(chunk_words)))
            continue

        # 1+ commas: build split points and distribute time
        num_chunks = max(2, dur // MAX_SENTENCE_MS + 1)
        if len(splits) == 1:
            chunk_starts = [0, splits[0]]
        else:
            chunk_size = max(1, len(splits) // num_chunks)
            chunk_starts = [0]
            for ci in range(1, num_chunks):
                idx = min(ci * chunk_size, len(splits) - 1)
                chunk_starts.append(splits[idx])

        total_chars = len(text)
        start_ms = time_to_ms(e.start)
        end_ms = time_to_ms(e.end)
        for ci in range(len(chunk_starts)):
            seq += 1
            cs = chunk_starts[ci]
            ce = chunk_starts[ci + 1] if ci + 1 < len(chunk_starts) else len(text)
            chunk_text = text[cs:ce].strip().lstrip(',').lstrip(';').strip()
            if ci == 0:
                chunk_start = start_ms
            else:
                chunk_start = start_ms + int((end_ms - start_ms) * (chunk_starts[ci - 1] / total_chars))
            if ci == len(chunk_starts) - 1:
                chunk_end = end_ms
            else:
                chunk_end = start_ms + int((end_ms - start_ms) * (ce / total_chars))
            result.append(SubEntry(seq, ms_to_time(chunk_start), ms_to_time(chunk_end), chunk_text))

    return result


# ── LLM punctuation (preserve timing, only add punctuation) ───────────────────

BATCH_SIZE = 20  # Deltas per LLM call


def _llm_add_punctuation(deltas: list[SubEntry], api_key: str) -> list[SubEntry]:
    """Batch deltas, send to LLM for punctuation only. Returns deltas with punctuation added."""
    if len(deltas) < 2:
        return deltas

    result = [None] * len(deltas)

    for bi in range(0, len(deltas), BATCH_SIZE):
        batch = deltas[bi:bi + BATCH_SIZE]
        texts = [e.text.strip() for e in batch]

        numbered = "\n".join(f"{j+1}. {t}" for j, t in enumerate(texts))
        prompt = (
            "Add proper punctuation (periods, commas, question marks, semicolons) "
            "to each line below. CRITICAL: do NOT change, add, remove, reorder, "
            "or merge ANY words. ONLY add punctuation marks. "
            "Output exactly the same number of lines, one per input line.\n\n"
            f"{numbered}"
        )

        response = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    "https://api.deepseek.com/v1/chat/completions",
                    data=json.dumps({
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": (
                                "You add punctuation to ASR transcript fragments. "
                                "NEVER change, add, or remove any words. Only insert "
                                "punctuation marks (. , ; : ! ?) at appropriate positions. "
                                "Output exactly one line per input line, same order."
                            )},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 4096,
                    }).encode(),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read())
                    response = body["choices"][0]["message"]["content"].strip()
                    break
            except Exception as e:
                if attempt == 1:
                    print(f"    Batch {bi // BATCH_SIZE} failed: {e}")
                time.sleep(2)

        parsed = _parse_punctuation(response, batch) if response else batch
        for j, entry in enumerate(parsed):
            idx = bi + j
            if idx < len(result):
                result[idx] = entry

    # Fallback for any missed entries
    for i, r in enumerate(result):
        if r is None:
            result[i] = deltas[i]

    return result


def _parse_punctuation(response: str, batch: list[SubEntry]) -> list[SubEntry]:
    """Parse LLM punctuation output back to SubEntry with original timing."""
    lines = [l.strip() for l in response.split("\n") if l.strip()]
    result = []
    for j, seg in enumerate(batch):
        if j < len(lines):
            text = re.sub(r'^\d+\.\s*', '', lines[j]).strip()
            if text:
                result.append(SubEntry(seg.index, seg.start, seg.end, text))
                continue
        result.append(seg)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="③ [DEPRECATED] Delta extraction + punctuation")
    p.add_argument("--slug", required=True)
    p.add_argument("--force", action="store_true", help="Suppress deprecation warning")
    args = p.parse_args()
    run(args.slug, force=args.force)

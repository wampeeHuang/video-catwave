"""Stage ④: Sponsor detection + timeline anchoring.

Usage: python stage_04_sponsor.py --slug <slug>
Input:  <output>/_runtime/字幕/02_seg.srt + source.mp4
Output: <output>/_runtime/字幕/02_seg_clean.srt (corrected timeline)
        <output>/_runtime/素材/source_clean.mp4 (cut video, if sponsor ≥10s)
        <output>/_runtime/字幕/_sponsor_cuts.json (reference only)

Architecture: this stage is the TIMELINE ANCHOR. After sponsor cuts,
both SRT and video share ONE timeline. Downstream stages ⑤-⑧ never touch
timecodes again — no shifting, no concat, just pure processing.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    SubEntry, get_deepseek_key, ms_to_time, read_srt, srt_path, time_to_ms, write_srt,
)


def run(slug: str, *, api_key: str | None = None, batch_size: int = 20,
        min_duration: float = 10.0):
    api_key = api_key or get_deepseek_key()
    srt = srt_path(slug, "02_seg.srt")
    if not srt.exists():
        print(f"ERROR: {srt} not found. Run stage_03 first.")
        sys.exit(1)

    entries = read_srt(srt)
    if not api_key:
        print("[④] No DEEPSEEK_API_KEY, copying as-is")
        write_srt(entries, srt_path(slug, "02_seg_clean.srt"))
        return

    print(f"[④] Detecting sponsors in {len(entries)} segments...")

    # ── Keyword pre-mark: deterministic lock on hard sponsor signals ─────────
    # LLM classification alone is unreliable — same prompt can return different
    # results across runs. Keywords like "sponsor" are absolute, never miss them.
    SPONSOR_KEYWORDS = [
        "sponsor", "sponsored", "brought to you by",
        "use code ", "promo code ", "discount code ",
    ]
    keyword_labels = ["no"] * len(entries)
    keyword_hits = 0
    for i, e in enumerate(entries):
        text_lower = e.text.lower()
        if any(kw in text_lower for kw in SPONSOR_KEYWORDS):
            keyword_labels[i] = "yes"
            keyword_hits += 1
    if keyword_hits:
        print(f"  Keyword pre-mark: {keyword_hits} segments locked as sponsor")

    batches = [entries[i:i + batch_size] for i in range(0, len(entries), batch_size)]
    all_labels = [None] * len(entries)

    with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
        futures = {}
        for bi, batch in enumerate(batches):
            futures[executor.submit(_classify_batch, batch, api_key)] = bi * batch_size

        for f in as_completed(futures):
            offset = futures[f]
            try:
                for j, label in enumerate(f.result()):
                    all_labels[offset + j] = label
            except Exception as exc:
                print(f"  Batch at offset {offset} failed: {exc}")
                for j in range(len(batches[offset // batch_size])):
                    all_labels[offset + j] = "no"

    # Merge keyword pre-marks into LLM results (keyword wins)
    for i in range(len(all_labels)):
        if keyword_labels[i] == "yes":
            all_labels[i] = "yes"

    clean_entries = []
    sponsor_entries = []
    for i, e in enumerate(entries):
        label = (all_labels[i] or "no").strip().lower()
        if label == "yes" or label.startswith("y"):
            sponsor_entries.append(e)
        else:
            clean_entries.append(e)

    # ── Post-classification: fill gaps between nearby sponsor segments ──────
    # Individual subtitle lines in a sponsor conversation often lack explicit
    # sponsor keywords (e.g. "Yes, thank you for having me"). When two sponsor
    # segments are separated by ≤5 non-sponsor lines, mark the gap as sponsor.
    _fill_sponsor_gaps(all_labels, entries, max_gap=5)

    # Rebuild sponsor/clean lists after gap filling
    sponsor_entries = []
    clean_entries = []
    for i, e in enumerate(entries):
        if all_labels[i] == "yes":
            sponsor_entries.append(e)
        else:
            clean_entries.append(e)

    # ── Expand sponsor ranges using named-entity anchors ─────────────────────
    # When a sponsor segment mentions a company/person name, adjacent segments
    # mentioning the same entity are likely part of the same sponsor read.
    # This catches sponsor interviews where only the intro contains "sponsor".
    cuts = _merge_ranges(sponsor_entries)
    cuts = _expand_by_key_terms(entries, cuts, max_lookahead=30)

    # Rebuild clean entries after expansion
    cut_starts = {time_to_ms(c["start"]) for c in cuts}
    sponsor_entries = []
    clean_entries = []
    for e in entries:
        is_sponsor = any(
            time_to_ms(c["start"]) <= time_to_ms(e.start)
            and time_to_ms(e.end) <= time_to_ms(c["end"])
            for c in cuts
        )
        if is_sponsor:
            sponsor_entries.append(e)
        else:
            clean_entries.append(e)
    for idx, e in enumerate(clean_entries):
        e.index = idx + 1

    # Restore short sponsor segments (<10s) — too short to cut
    short_cuts = []
    kept_cuts = []
    for c in cuts:
        dur = (time_to_ms(c["end"]) - time_to_ms(c["start"])) / 1000
        if dur < min_duration:
            short_cuts.append(c)
        else:
            kept_cuts.append(c)

    if short_cuts:
        restored = 0
        for c in short_cuts:
            for e in sponsor_entries:
                if c["start"] <= e.start <= c["end"]:
                    clean_entries.append(e)
                    restored += 1
        clean_entries.sort(key=lambda e: time_to_ms(e.start))
        for i, e in enumerate(clean_entries):
            e.index = i + 1
        print(f"  Restored {restored} entries from {len(short_cuts)} short sponsor segment(s) "
              f"(< {min_duration:.0f}s)")

    # ── Timeline anchoring ──────────────────────────────────────────────────
    # Shift SRT timestamps so they match the cut video timeline.
    # After this, clean SRT and cut video share ONE canonical timeline.
    if kept_cuts:
        _shift_timestamps(clean_entries, kept_cuts)
        print(f"  Shifted {len(clean_entries)} entries to cut timeline "
              f"({len(kept_cuts)} cuts)")

    # Write corrected clean SRT
    clean_path = srt_path(slug, "02_seg_clean.srt")
    write_srt(clean_entries, clean_path)

    # Write cut ranges (reference only — stage_08 no longer consumes this)
    cuts_path = srt_path(slug, "_sponsor_cuts.json")
    cuts_path.write_text(json.dumps(kept_cuts, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Video cutting ───────────────────────────────────────────────────────
    if kept_cuts:
        video_path = _find_source_video(slug)
        if video_path and video_path.exists():
            print(f"[④] Cutting video: {len(kept_cuts)} sponsor ranges → source_clean.mp4")
            clean_video = video_path.parent / "source_clean.mp4"
            _cut_video(video_path, kept_cuts, clean_video)
            print(f"  → {clean_video.name}")
        else:
            print(f"  WARNING: source video not found, skipping video cut")

    print(f"  Sponsored: {len(sponsor_entries)}/{len(entries)} → {len(kept_cuts)} cut ranges "
          f"(filtered {len(short_cuts)} short)")
    print(f"  → {clean_path.name}")
    print(f"  → {cuts_path.name}")


def _fill_sponsor_gaps(labels: list[str], entries: list[SubEntry], max_gap: int = 3):
    """Fill small gaps between sponsor segments — isolated non-sponsor lines
    sandwiched between two sponsor segments are likely part of the same ad read.
    Mutates labels in place."""
    n = len(labels)
    for i in range(n):
        if labels[i] == "yes":
            continue
        prev_yes = next((j for j in range(i - 1, max(i - max_gap - 1, -1), -1) if labels[j] == "yes"), None)
        next_yes = next((j for j in range(i + 1, min(i + max_gap + 1, n)) if labels[j] == "yes"), None)
        if prev_yes is not None and next_yes is not None:
            labels[i] = "yes"


def _expand_by_key_terms(entries: list[SubEntry], cuts: list[dict],
                         max_lookahead: int = 60,
                         max_gap: int = 5) -> list[dict]:
    """Expand sponsor ranges to include adjacent segments that share named entities
    (company/person names) with the sponsor anchor. This catches sponsor interviews
    where only the intro contains explicit sponsor keywords."""
    if not cuts:
        return cuts
    import re

    expanded = []
    for cut in cuts:
        start_ms = time_to_ms(cut["start"])
        end_ms = time_to_ms(cut["end"])
        range_entries = [e for e in entries
                         if time_to_ms(e.start) >= start_ms
                         and time_to_ms(e.end) <= end_ms]
        range_text = " ".join(e.text for e in range_entries)
        key_terms = set(re.findall(
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', range_text
        ))
        if not key_terms:
            expanded.append(cut)
            continue

        # Add spaceless variants so "One Schema" also matches "oneschema.co"
        extra = {t.replace(" ", "") for t in key_terms}
        key_terms |= extra

        first_idx = next(i for i, e in enumerate(entries)
                         if time_to_ms(e.start) >= start_ms)
        last_idx = next(i for i in range(len(entries) - 1, -1, -1)
                        if time_to_ms(entries[i].start) <= end_ms
                        and time_to_ms(entries[i].end) >= start_ms)

        def _term_match(text: str) -> bool:
            t = text.lower()
            return any(term.lower() in t for term in key_terms)

        # Expand forward while adjacent segments share key terms
        new_last = last_idx
        for i in range(last_idx + 1, min(last_idx + 1 + max_lookahead, len(entries))):
            if _term_match(entries[i].text):
                new_last = i
            elif i - new_last > max_gap:
                break

        # Expand backward
        new_first = first_idx
        for i in range(first_idx - 1, max(first_idx - 1 - max_lookahead, -1), -1):
            if _term_match(entries[i].text):
                new_first = i
            elif new_first - i > max_gap:
                break

        expanded.append({
            "start": entries[new_first].start,
            "end": entries[new_last].end,
        })

    return _merge_ranges([
        SubEntry(index=0, start=c["start"], end=c["end"], text="")
        for c in expanded
    ])


def _classify_batch(batch: list[SubEntry], api_key: str) -> list[str]:
    texts = [e.text.strip() for e in batch]
    system_prompt = (
        "You are a content classifier. For each subtitle segment below, "
        'answer ONLY "yes" or "no" — is this segment part of a sponsor/ad read? '
        "Sponsor indicators: brand names repeated, discount codes, 'thanks to our sponsors', "
        "'check out', 'use code', fast speech artifacts. "
        "Answer one word per line, exactly matching the input line count."
    )
    prompt = "Classify each line as sponsor/ad (yes/no):\n\n" + "\n".join(texts)

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                }).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"].strip()
                raw = [l.strip().lower() for l in content.split("\n") if l.strip()]
                labels = []
                for l in raw:
                    labels.append("yes" if (l.startswith("yes") or l.startswith("y")) else "no")
                while len(labels) < len(batch):
                    labels.append("no")
                return labels[:len(batch)]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise e


def _merge_ranges(entries: list[SubEntry]) -> list[dict]:
    """Merge consecutive sponsor segments into cut ranges."""
    if not entries:
        return []
    merged = []
    cur_start, cur_end = entries[0].start, entries[0].end
    for i in range(1, len(entries)):
        gap = time_to_ms(entries[i].start) - time_to_ms(cur_end)
        if gap <= 500:
            cur_end = entries[i].end
        else:
            merged.append({"start": cur_start, "end": cur_end})
            cur_start, cur_end = entries[i].start, entries[i].end
    merged.append({"start": cur_start, "end": cur_end})
    return merged


def _shift_timestamps(entries: list[SubEntry], cuts: list[dict]) -> None:
    """Shift SRT timestamps to match cut video timeline. Mutates entries in place.

    For each entry, subtract the total duration of all cuts that end
    before this entry starts. Result: SRT and concat video share ONE timeline.
    """
    if not cuts:
        return
    sorted_cuts = sorted(cuts, key=lambda c: time_to_ms(c["start"]))

    for e in entries:
        entry_start = time_to_ms(e.start)
        shift_ms = 0
        for c in sorted_cuts:
            cut_end = time_to_ms(c["end"])
            if cut_end <= entry_start:
                shift_ms += cut_end - time_to_ms(c["start"])
        if shift_ms > 0:
            e.start = ms_to_time(time_to_ms(e.start) - shift_ms)
            e.end = ms_to_time(time_to_ms(e.end) - shift_ms)


def _find_source_video(slug: str) -> Path | None:
    """Find source.mp4 for this slug in the output directory."""
    from _lib import slug_dir
    out = slug_dir(slug) / "_runtime" / "素材"
    if out.exists():
        for mp4 in sorted(out.glob("*.mp4")):
            if mp4.name == "source.mp4":
                return mp4
        mp4s = sorted(out.glob("*.mp4"))
        if mp4s:
            return mp4s[0]
    return None


def _cut_video(video: Path, cuts: list[dict], output: Path) -> None:
    """Cut sponsor segments from video via ffmpeg concat. Uses stream copy (no re-encode)."""
    cut_pairs = [(_to_seconds(c["start"]), _to_seconds(c["end"])) for c in cuts]

    segments = []
    last_end = 0.0
    for cs, ce in cut_pairs:
        if cs > last_end:
            segments.append((last_end, cs))
        last_end = ce
    segments.append((last_end, None))

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        seg_files = []
        for i, (seg_start, seg_end) in enumerate(segments):
            seg_path = tmp_dir / f"seg_{i:03d}.ts"
            cmd = ["ffmpeg", "-y", "-i", str(video)]
            if seg_start > 0:
                cmd += ["-ss", str(seg_start)]
            if seg_end is not None:
                cmd += ["-to", str(seg_end)]
            cmd += ["-c", "copy", str(seg_path)]
            subprocess.run(cmd, check=True, capture_output=True)
            seg_files.append(seg_path)

        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{f}'" for f in seg_files), encoding="utf-8")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            str(output),
        ]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _to_seconds(srt_time: str) -> float:
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="④ Sponsor detection + timeline anchoring")
    p.add_argument("--slug", required=True)
    p.add_argument("--min-sponsor-duration", type=float, default=10.0,
                   help="Minimum seconds for a sponsor segment to be cut (default 10)")
    args = p.parse_args()
    run(args.slug, min_duration=args.min_sponsor_duration)

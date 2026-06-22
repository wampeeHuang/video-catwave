"""Stage ④: Sponsor detection via DeepSeek.

Usage: python stage_04_sponsor.py --slug <slug>
Input:  <output>/_runtime/字幕/02_seg.srt
Output: <output>/_runtime/字幕/02_seg_clean.srt + _sponsor_cuts.json

_sponsor_cuts.json is consumed by stage_08_render to skip sponsor segments in video.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    SubEntry, read_srt, srt_path, time_to_ms, write_srt,
)


def run(slug: str, *, api_key: str | None = None, batch_size: int = 20,
        min_duration: float = 10.0):
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
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

    clean_entries = []
    sponsor_entries = []
    for i, e in enumerate(entries):
        label = (all_labels[i] or "no").strip().lower()
        if label == "yes" or label.startswith("y"):
            sponsor_entries.append(e)
        else:
            clean_entries.append(e)

    cuts = _merge_ranges(sponsor_entries)

    # Filter short sponsor segments back into clean (worth translating)
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
        # Re-index
        for i, e in enumerate(clean_entries):
            e.index = i + 1
        print(f"  Restored {restored} entries from {len(short_cuts)} short sponsor segment(s) "
              f"(< {min_duration:.0f}s)")

    # Write clean SRT
    clean_path = srt_path(slug, "02_seg_clean.srt")
    write_srt(clean_entries, clean_path)

    # Write cut ranges for stage_08 (only long cuts)
    cuts_path = srt_path(slug, "_sponsor_cuts.json")
    cuts_path.write_text(json.dumps(kept_cuts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  Sponsored: {len(sponsor_entries)}/{len(entries)} → {len(kept_cuts)} cut ranges "
          f"(filtered {len(short_cuts)} short)")
    print(f"  → {clean_path.name}")
    print(f"  → {cuts_path.name}")


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


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="④ Sponsor detection")
    p.add_argument("--slug", required=True)
    p.add_argument("--min-sponsor-duration", type=float, default=10.0,
                   help="Minimum seconds for a sponsor segment to be cut (default 10)")
    args = p.parse_args()
    run(args.slug, min_duration=args.min_sponsor_duration)

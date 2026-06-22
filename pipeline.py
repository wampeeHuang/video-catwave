#!/usr/bin/env python3
"""YouTube → B站 content pipeline. Single source of truth for all pipeline logic."""

import argparse
import dataclasses
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

# ── Project root ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME = Path("D:/workspace/_output/猫波信号站/视频")  # 产出物落盘目录
PROCESS_ROOT = PROJECT_ROOT / "_runtime"                # 管道工作目录（source video 等）

# ── Data model ────────────────────────────────────────────────────────────


@dataclasses.dataclass
class SubEntry:
    index: int
    start: str  # "HH:MM:SS,mmm"
    end: str
    text: str


# ── SRT parser / serializer ───────────────────────────────────────────────


def parse_srt(text: str) -> list[SubEntry]:
    entries = []
    blocks = text.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        idx = int(lines[0].strip())
        timing = lines[1].strip()
        start, end = timing.split(" --> ")
        content = "\n".join(lines[2:]).strip()
        entries.append(SubEntry(idx, start.strip(), end.strip(), content))
    return entries


def format_srt(entries: list[SubEntry]) -> str:
    out = []
    for e in entries:
        out.append(f"{e.index}\n{e.start} --> {e.end}\n{e.text}\n")
    return "\n".join(out)


def read_srt(path: Path) -> list[SubEntry]:
    return parse_srt(path.read_text(encoding="utf-8"))


def write_srt(entries: list[SubEntry], path: Path):
    path.write_text(format_srt(entries), encoding="utf-8")


def extract_transcript(entries: list[SubEntry]) -> str:
    """Extract plain text from SRT entries, deduplicating consecutive repeats."""
    lines = []
    prev = ""
    for e in entries:
        t = e.text.strip()
        if t and t != prev:
            lines.append(t)
        prev = t
    return "\n".join(lines)


# ── SRT time helpers ──────────────────────────────────────────────────────


def time_to_ms(t: str) -> int:
    """HH:MM:SS,mmm → milliseconds"""
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def ms_to_time(ms: int) -> str:
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── Step 1: Download ──────────────────────────────────────────────────────


def download_video(url: str, process_dir: Path) -> Path:
    """Download YouTube video + English auto-subs. Return path to video file."""
    process_dir.mkdir(parents=True, exist_ok=True)

    srt_template = str(process_dir / "01_raw")
    cmd = [
        "yt-dlp",
        "--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt",
        "-f", "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=1080]",
        "--output", str(process_dir / "%(title)s.%(ext)s"),
        "--write-sub", "--sub-format", "srt",
        url,
    ]

    print(f"[1/6] Downloading: {url}")
    subprocess.run(cmd, check=True, cwd=str(process_dir))

    # Rename English SRT to 01_raw.srt
    srt_files = sorted(process_dir.glob("*.en.srt"))
    if not srt_files:
        srt_files = sorted(process_dir.glob("*.srt"))
    if srt_files:
        target = process_dir / "01_raw.srt"
        target.unlink(missing_ok=True)
        srt_files[0].rename(target)
        print(f"  SRT saved: {target.name}")

    mp4_files = sorted(process_dir.glob("*.mp4"))
    return mp4_files[0] if mp4_files else None


# ── Step 1.5: Sentence segmentation ───────────────────────────────────────


def segment_sentences(srt_path: Path, target_words: int = 18) -> list[SubEntry]:
    """Merge YouTube word-level fragments, then use LLM to restore punctuation
    and split into proper sentence-level segments."""
    raw = read_srt(srt_path)
    merged = _merge_fragments(raw)

    if not merged:
        return []

    # Concatenate all merged text (already chunked by _merge_fragments at ~30 words)
    # Send to DeepSeek for punctuation restoration + sentence boundary marking
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("  WARNING: No DEEPSEEK_API_KEY, falling back to word-count segmentation")
        return _word_count_segment(merged, target_words)

    print("  Restoring punctuation via DeepSeek...")
    try:
        punctuated = _llm_restore_punctuation(merged, api_key)
        sentences = _split_sentences_with_time(merged, punctuated)
        print(f"  {len(merged)} fragments → {len(sentences)} sentences")
        return sentences
    except Exception as e:
        print(f"  LLM segmentation failed ({e}), falling back to word-count")
        return _word_count_segment(merged, target_words)


def _word_count_segment(merged: list[SubEntry], target_words: int) -> list[SubEntry]:
    """Fallback: segment by word count when LLM is unavailable."""
    sentences = []
    buf, buf_start, buf_end = [], None, None
    for e in merged:
        if buf_start is None:
            buf_start = e.start
        buf.append(e.text)
        buf_end = e.end
        text = " ".join(buf)
        word_count = len(text.split())
        ends_with_terminal = re.search(r"[.!?]$", text.strip())
        if ends_with_terminal or word_count >= target_words * 1.5:
            sentences.append(_make_entry(sentences, buf_start, buf_end, text))
            buf, buf_start, buf_end = [], None, None
    if buf:
        sentences.append(_make_entry(sentences, buf_start, buf_end, " ".join(buf)))
    return _carryover_trim(sentences, target_words)


def _llm_restore_punctuation(merged: list[SubEntry], api_key: str) -> list[tuple[str, int, int, int]]:
    """Send merged text batches to DeepSeek. Returns list of (sentence_text, batch_time_start_ms, batch_time_end_ms, batch_index)
    for time reconstruction using actual entry timestamps instead of global character-position heuristics."""
    import json
    import urllib.request

    if len(merged) < 5:
        first_ms = time_to_ms(merged[0].start)
        last_ms = time_to_ms(merged[-1].end)
        text = " ".join(e.text for e in merged)
        return [(text, first_ms, last_ms, 0)]

    batch_size = 20
    batches = [merged[i:i+batch_size] for i in range(0, len(merged), batch_size)]

    all_sentences = []
    entry_offset = 0

    for bi, batch in enumerate(batches):
        # Compute batch time boundaries from actual entry timestamps
        batch_start_ms = time_to_ms(merged[entry_offset].start)
        batch_end_ms = time_to_ms(merged[entry_offset + len(batch) - 1].end)

        # Build prompt with numbered lines
        numbered_lines = []
        for li, e in enumerate(batch):
            numbered_lines.append(f"{li+1}. {e.text.strip()}")
        prompt_lines = "\n".join(numbered_lines)

        prompt = (
            "Restore punctuation (periods, commas, question marks) to these English transcript lines. "
            "CRITICAL: do NOT change, add, remove, or rephrase ANY words. Only add punctuation. "
            "Mark sentence boundaries with <S>. A sentence may span multiple lines. "
            "Output the full punctuated text with <S> markers only, no line numbers, no explanations.\n\n"
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
                            {"role": "system", "content": "You restore punctuation to ASR transcripts. Output ONLY the segmented text with <S> between sentences. Never change any word."},
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
                    raise
                print(f"    Batch {bi} attempt {attempt+1} failed: {e}")
                time.sleep(2)

        if not result:
            entry_offset += len(batch)
            continue

        # Parse <S> markers → list of sentence texts
        raw_sentences = [s.strip() for s in result.split("<S>") if s.strip()]

        if raw_sentences:
            for sent in raw_sentences:
                all_sentences.append((sent, batch_start_ms, batch_end_ms, bi))

        entry_offset += len(batch)

    if not all_sentences:
        text = " ".join(e.text for e in merged)
        first_ms = time_to_ms(merged[0].start)
        last_ms = time_to_ms(merged[-1].end)
        return [(text, first_ms, last_ms, 0)]

    return all_sentences


def _split_sentences_with_time(merged: list[SubEntry], sentences: list[tuple[str, int, int, int]]) -> list[SubEntry]:
    """Map sentences to time ranges. Sentences are grouped by batch_index and distributed
    evenly within each batch's actual time window (from entry timestamps)."""
    from collections import defaultdict
    groups = defaultdict(list)
    for item in sentences:
        text, batch_start_ms, batch_end_ms, bi = item
        groups[bi].append((text, batch_start_ms, batch_end_ms))

    result = []
    seq = 1
    for bi in sorted(groups.keys()):
        group = groups[bi]
        _, batch_start_ms, batch_end_ms = group[0]
        n = len(group)
        segment_ms = max((batch_end_ms - batch_start_ms) // n, 800)

        for j, (text, _, _) in enumerate(group):
            start_ms = batch_start_ms + j * segment_ms
            end_ms = min(start_ms + segment_ms, batch_end_ms)
            result.append(SubEntry(seq, ms_to_time(start_ms), ms_to_time(end_ms), text))
            seq += 1

    return result


def _merge_fragments(entries: list[SubEntry], max_words: int = 30) -> list[SubEntry]:
    """Merge entries that don't end with sentence-ending punctuation.

    Also forces a split when the buffer exceeds *max_words*, so that subtitle
    files without any punctuation (common with YouTube auto-captions) don't
    collapse into a single entry.
    """
    result = []
    buf, buf_start, buf_end = [], None, None
    for e in entries:
        if buf_start is None:
            buf_start = e.start
        buf.append(e.text)
        buf_end = e.end
        text = " ".join(buf)
        if re.search(r"[.!?]$", e.text.strip()) or len(text.split()) >= max_words:
            result.append(_make_entry(result, buf_start, buf_end, text))
            buf, buf_start, buf_end = [], None, None
    if buf:
        result.append(_make_entry(result, buf_start, buf_end, " ".join(buf)))
    return result


def _make_entry(existing: list, start: str, end: str, text: str) -> SubEntry:
    return SubEntry(len(existing) + 1, start, end, text.strip())


def _carryover_trim(entries: list[SubEntry], target: int) -> list[SubEntry]:
    """Move words from head of next entry to tail of current entry.
    Only trims text; timestamps stay anchored to sentence boundaries."""
    result = []
    for i, e in enumerate(entries):
        words = e.text.split()
        if len(words) <= target or i == len(entries) - 1:
            result.append(e)
            continue

        next_entry = entries[i + 1]
        next_words = next_entry.text.split()
        carry = min(len(words) - target, len(next_words) - 1) if len(next_words) > 1 else 0
        carry = max(carry, 0)

        if carry > 0:
            to_carry = words[-carry:]
            new_current = SubEntry(e.index, e.start, e.end, " ".join(words[:-carry]))
            entries[i + 1] = SubEntry(
                next_entry.index, next_entry.start, next_entry.end,
                " ".join(to_carry + next_words),
            )
            result.append(new_current)
        else:
            result.append(e)
    return result


# ── Step 1.6: Sponsor detection ───────────────────────────────────────────


def detect_sponsors(srt_path: Path, api_key: Optional[str] = None, batch_size: int = 20) -> tuple[list[SubEntry], list[dict]]:
    """Classify each segment as sponsor/ad via DeepSeek. Returns (clean_entries, cut_list)."""
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[1.6/6] No DEEPSEEK_API_KEY set, skipping sponsor detection")
        return read_srt(srt_path), []

    entries = read_srt(srt_path)
    print(f"[1.6/6] Detecting sponsors in {len(entries)} segments via DeepSeek...")

    batches = [entries[i:i + batch_size] for i in range(0, len(entries), batch_size)]
    all_labels = [None] * len(entries)

    with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
        futures = {}
        for bi, batch in enumerate(batches):
            f = executor.submit(_classify_batch, batch, api_key)
            futures[f] = bi * batch_size

        for f in as_completed(futures):
            offset = futures[f]
            try:
                labels = f.result()
                for j, label in enumerate(labels):
                    all_labels[offset + j] = label
            except Exception as exc:
                print(f"  Sponsor batch at offset {offset} failed: {exc}")
                for j in range(len(batches[(offset // batch_size)])):
                    all_labels[offset + j] = "no"

    clean_entries = []
    sponsor_entries = []
    cuts = []
    for i, e in enumerate(entries):
        label = (all_labels[i] or "no").strip().lower()
        if label == "yes" or label.startswith("y"):
            sponsor_entries.append(e)
        else:
            clean_entries.append(e)

    # Build cut list: merge consecutive sponsor segments
    if sponsor_entries:
        merged = _merge_adjacent_sponsors(sponsor_entries)
        cuts = [{"start": s, "end": e} for s, e in merged]

    # Write outputs
    clean_path = srt_path.with_name("02_seg_clean.srt")
    write_srt(clean_entries, clean_path)

    cuts_path = srt_path.parent / "_sponsor_cuts.json"
    import json
    cuts_path.write_text(json.dumps(cuts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  Sponsored: {len(sponsor_entries)}/{len(entries)} segments → {len(cuts)} cut ranges")
    print(f"  Clean SRT: {clean_path.name} ({len(clean_entries)} segments)")
    print(f"  Cuts JSON: {cuts_path.name}")

    return clean_entries, cuts


def _classify_batch(batch: list[SubEntry], api_key: str) -> list[str]:
    import json
    import urllib.request

    texts = [e.text.strip() for e in batch]
    system_prompt = (
        "You are a content classifier. For each subtitle segment below, "
        'answer ONLY "yes" or "no" — is this segment part of a sponsor/ad read? '
        "Sponsor indicators: brand names repeated, discount codes, 'thanks to our sponsors', "
        "'check out', 'use code', fast speech artifacts (word repetition in ASR). "
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
                    if l.startswith("yes") or l.startswith("y"):
                        labels.append("yes")
                    else:
                        labels.append("no")
                while len(labels) < len(batch):
                    labels.append("no")
                return labels[: len(batch)]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise e


def _merge_adjacent_sponsors(entries: list[SubEntry]) -> list[tuple[str, str]]:
    """Merge consecutive sponsor segments into cut ranges."""
    if not entries:
        return []
    merged = []
    cur_start = entries[0].start
    cur_end = entries[0].end
    for i in range(1, len(entries)):
        gap = time_to_ms(entries[i].start) - time_to_ms(cur_end)
        if gap <= 500:  # ≤0.5s gap → same cut range
            cur_end = entries[i].end
        else:
            merged.append((cur_start, cur_end))
            cur_start = entries[i].start
            cur_end = entries[i].end
    merged.append((cur_start, cur_end))
    return merged


# ── Step 2: Translation ───────────────────────────────────────────────────


def translate_srt(srt_path: Path, api_key: Optional[str] = None, batch_size: int = 10):
    """DeepSeek API batch translation EN→ZH, bilingual output."""
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("[2/6] No DEEPSEEK_API_KEY set, skipping translation")
        return

    entries = read_srt(srt_path)
    print(f"[2/6] Translating {len(entries)} entries via DeepSeek API...")

    batches = [entries[i:i + batch_size] for i in range(0, len(entries), batch_size)]
    translated = [None] * len(entries)

    with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
        futures = {}
        for bi, batch in enumerate(batches):
            f = executor.submit(_translate_batch, batch, api_key)
            futures[f] = bi * batch_size

        for f in as_completed(futures):
            offset = futures[f]
            try:
                results = f.result()
                for j, zh_text in enumerate(results):
                    if zh_text:
                        idx = offset + j
                        en_text = entries[idx].text.strip()
                        translated[idx] = SubEntry(
                            entries[idx].index,
                            entries[idx].start,
                            entries[idx].end,
                            f"{zh_text}\\N{en_text}",
                        )
            except Exception as exc:
                print(f"  Batch at offset {offset} failed: {exc}")

    for i, e in enumerate(entries):
        if translated[i] is None:
            translated[i] = SubEntry(e.index, e.start, e.end, f"[未翻译]\\N{e.text.strip()}")

    zh_path = srt_path.with_name("03_zh.srt")
    write_srt(translated, zh_path)
    print(f"  Saved: {zh_path.name}")

    # Post-process proper nouns
    _fix_proper_nouns(zh_path)


def _translate_batch(batch: list[SubEntry], api_key: str) -> list[str]:
    import json
    import urllib.request

    texts = [e.text.strip() for e in batch]
    n = len(batch)

    system_prompt = (
        "You are a professional EN→ZH subtitle translator. "
        f"Translate EXACTLY {n} lines below. Output {n} numbered lines (1. 2. ... {n}.). "
        "One Chinese translation per line. No explanations, no extra text. "
        "CRITICAL: translate EVERY line — even garbled ASR artifacts and fast speech. "
        "If the English is unreadable, give your best guess based on surrounding words. "
        f"Your output MUST contain exactly {n} non-empty numbered lines. "
        "IMPORTANT — keep these names UNTRANSLATED (留英文): "
        "Cursor, Copilot, GitHub Copilot, Claude, Sonnet, GPT, GPT-4, OpenAI, "
        "Anthropic, VS Code, Visual Studio Code, Vim, Neovim, JetBrains, "
        "IntelliJ, macOS, Windows, Linux, AWS, GCP, Azure, "
        "JavaScript, TypeScript, Python, Rust, Go, React, Node.js, "
        "API, GPU, CPU, SSD, CUDA, PyTorch, TensorFlow, "
        "Stripe, Slack, Discord, Zoom, Google, Microsoft, Apple, Meta, "
        "DeepSeek, Llama, Gemini, o1, ChatGPT, "
        "Lex Fridman, Elon Musk, Sam Altman."
    )

    prompt = f"Translate these {n} English subtitle lines to Chinese:\n\n"
    for i, t in enumerate(texts, 1):
        prompt += f"{i}. {t}\n"

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
                    "temperature": 0.3,
                }).encode(),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
                content = body["choices"][0]["message"]["content"].strip()
                raw = [l.strip() for l in content.split("\n") if l.strip()]

                # Parse numbered lines: "1. 中文" or "1 中文" or "1、中文"
                lines = []
                for l in raw:
                    m = re.match(r"^\d+[\.\)\s、\)]\s*(.*)", l)
                    if m:
                        t = m.group(1).strip()
                        if t:
                            lines.append(t)
                    elif not re.match(r"^\d+$", l):  # Skip bare numbers
                        lines.append(l)

                # Line count check
                if len(lines) == n:
                    return lines
                if len(lines) > n:
                    return lines[:n]

                # Mismatch: retry with warning
                if attempt < 2:
                    print(f"  Line mismatch (got {len(lines)}, expected {n}), retry {attempt+2}...")
                    time.sleep(2 ** attempt)
                    continue

                # Last resort: pad with best-effort marker
                while len(lines) < n:
                    lines.append(f"[模型跳过:{texts[len(lines)][:30]}]")
                return lines[:n]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise e


# ── Step 2.5: Proper noun post-processing ──────────────────────────────────

PROPER_NOUN_FIXES: list[tuple[str, str]] = [
    # (pattern, replacement) — applied to Chinese text after translation
    # Order matters: longer patterns first to avoid partial matches
    ("光标", "Cursor"),
    ("黄金 Cursor 选项卡", "黄金 Cursor Tab"),
]


def _fix_proper_nouns(srt_path: Path):
    """Post-process Chinese translations to restore proper nouns.

    Reads 03_zh.srt, applies PROPER_NOUN_FIXES to the Chinese portion
    of each bilingual entry, writes back.
    """
    entries = read_srt(srt_path)
    fixed_count = 0

    for e in entries:
        parts = e.text.split("\\N", 1)
        zh = parts[0]
        en = parts[1] if len(parts) > 1 else ""

        for pattern, replacement in PROPER_NOUN_FIXES:
            if pattern in zh:
                zh = zh.replace(pattern, replacement)
                fixed_count += 1

        if len(parts) > 1:
            e.text = f"{zh}\\N{en}"
        else:
            e.text = zh

    write_srt(entries, srt_path)
    if fixed_count:
        print(f"  Proper noun fixes applied: {fixed_count} replacements")


# ── Step 3: Chinese char limit ────────────────────────────────────────────


def enforce_max_chars(srt_path: Path, max_chars: int = 36) -> list[SubEntry]:
    """Split entries where Chinese text exceeds max_chars. Splits at Chinese punctuation."""
    entries = read_srt(srt_path)
    result = []

    for e in entries:
        parts = e.text.split("\\N", 1)
        zh = parts[0].strip()
        en = parts[1].strip() if len(parts) > 1 else ""

        if _cn_char_count(zh) <= max_chars:
            result.append(e)
            continue

        segments = _split_cn_text(zh, max_chars)
        start_ms = time_to_ms(e.start)
        end_ms = time_to_ms(e.end)
        total_dur = end_ms - start_ms
        total_len = sum(_cn_char_count(s) for s in segments)

        cursor = start_ms
        for seg in segments:
            seg_len = _cn_char_count(seg)
            ratio = seg_len / total_len if total_len > 0 else 1 / len(segments)
            seg_dur = int(total_dur * ratio)
            seg_end = min(cursor + seg_dur, end_ms)
            text = f"{seg}\\N{en}" if en else seg
            result.append(SubEntry(len(result) + 1, ms_to_time(cursor), ms_to_time(seg_end), text))
            cursor = seg_end

    return result


def _cn_char_count(text: str) -> int:
    return len(re.sub(r"[a-zA-Z0-9\s\d\-\\/\\.]+", "", text))


def _split_cn_text(text: str, max_chars: int) -> list[str]:
    """Split Chinese text at punctuation when exceeding max_chars.
    Falls back to hard split at max_chars if no punctuation found."""
    punct = "，。！？；、"
    result = []
    buf = ""
    for ch in text:
        buf += ch
        if _cn_char_count(buf) >= max_chars:
            if ch in punct:
                result.append(buf)
                buf = ""
            elif _cn_char_count(buf) >= max_chars * 2:
                # Hard split if no punctuation within 2x limit
                result.append(buf)
                buf = ""
    if buf.strip():
        result.append(buf)
    return result if result else [text]


# ── Step 4: ASS generation ────────────────────────────────────────────────


def srt_to_ass(srt_path: Path) -> str:
    """Generate bilingual ASS file. 纯白无描边，SimHei 42px 中文 + 英文底栏。"""
    entries = read_srt(srt_path)

    # Fix overlapping segments: clip end time so no two segments share screen time
    fixed = []
    for i, e in enumerate(entries):
        end_ms = time_to_ms(e.end)
        if i + 1 < len(entries):
            next_start_ms = time_to_ms(entries[i + 1].start)
            if end_ms > next_start_ms:
                # Clip: end at next start minus 20ms gap
                end_ms = max(next_start_ms - 20, time_to_ms(e.start) + 500)
        e_fixed = SubEntry(e.index, e.start, ms_to_time(end_ms), e.text)
        fixed.append(e_fixed)
    entries = fixed

    # Pure white, no outline: Outline=0 Shadow=0, BorderStyle=1 (invisible with 0 width)
    # Alignment=2 (bottom-center), larger margins to prevent English overflow
    header = """[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Style: Default,SimHei,42,&H00FFFFFF&,&H00000000&,&H00FFFFFF&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,2,200,200,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for e in entries:
        start = _ass_time(e.start)
        end = _ass_time(e.end)
        text = e.text.replace("\\N", "\\N{\\fnMicrosoft YaHei}")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,45,,{text}")

    return "\n".join(lines)


def _ass_time(srt_time: str) -> str:
    """HH:MM:SS,mmm → H:MM:SS.mm (ASS format)"""
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return f"{int(h)}:{m}:{s}.{ms[:2]}"


# ── Step 5: Render ────────────────────────────────────────────────────────


def render_video(video_path: Path, ass_path: Path, output_path: Path):
    """FFmpeg burn ASS subtitles, H.264 CRF 23, AAC 128k.

    Uses relative ASS path to avoid ffmpeg parsing Windows drive-letter colon
    as a filter option separator.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import os as _os
    _prev = _os.getcwd()
    try:
        _os.chdir(str(ass_path.parent))
        ass_rel = ass_path.name
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{ass_rel}'",
            "-c:v", "libx264", "-crf", "23", "-threads", "4",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        print(f"[5/6] Rendering: {output_path.name}")
        subprocess.run(cmd, check=True)
    finally:
        _os.chdir(_prev)


# ── Step 6: Extract transcript ────────────────────────────────────────────


def save_transcript(srt_path: Path, output_path: Path):
    entries = read_srt(srt_path)
    text = extract_transcript(entries)
    output_path.write_text(text, encoding="utf-8")
    print(f"  Transcript saved: {output_path.name}")


# ── Slug extraction ───────────────────────────────────────────────────────


def extract_slug(url: str) -> str:
    """Derive video slug from YouTube URL."""
    import re
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
    return m.group(1)[:20] if m else "video"


# ── CLI ────────────────────────────────────────────────────────────────────


def _slug_dir(slug: str) -> Path:
    """Resolve slug to output directory. Supports both exact match and date-prefix match (YYYYMMDD_slug)."""
    d = RUNTIME / slug
    if d.exists():
        return d
    # Try date-prefix match: 20260620_cursor-team-lex-fridman
    hits = sorted(RUNTIME.glob(f"*_{slug}"))
    if hits:
        return hits[0]
    # Create new with exact slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_dirs(slug: str):
    video_dir = _slug_dir(slug)
    for d in [video_dir / "_runtime" / "字幕", video_dir / "成片"]:
        d.mkdir(parents=True, exist_ok=True)
    return video_dir, video_dir / "_runtime" / "字幕", video_dir / "成片"


def _find_video(slug: str) -> Path | None:
    """Find source video in lab _runtime/<slug>_process/."""
    # Strip date prefix if present in slug dir name for lab lookup
    clean_slug = slug
    process_dir = PROCESS_ROOT / clean_slug / "_process"
    if not process_dir.exists():
        # Try date-prefix match
        hits = sorted(PROCESS_ROOT.glob(f"*_{clean_slug}"))
        if hits:
            process_dir = hits[0] / "_process"
    if process_dir.exists():
        mp4s = sorted(process_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[0]
    return None


def _add_common_args(p):
    p.add_argument("--slug", required=True, help="Video folder slug (e.g. cursor-team-lex-fridman)")


def _add_translate_args(p):
    p.add_argument("--max-chars", type=int, default=36, help="Max Chinese chars per line (default: 36)")


def _add_render_args(p):
    p.add_argument("--duration", type=int, default=0, help="Clip duration in seconds (0=full)")
    p.add_argument("--output-title", default="output", help="Output filename")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube → B站 content pipeline (stage-gated)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py segment --slug my-video          # ② LLM断句
  python pipeline.py translate --slug my-video        # ④⑤ 翻译+字宽限制
  python pipeline.py ass --slug my-video              # ⑥⑦ 生成ASS+transcript
  python pipeline.py render --slug my-video           # ⑧ 渲染视频
  python pipeline.py render --slug my-video --duration 120  # 2min测试片
  python pipeline.py all <url> --slug my-video        # 一键全流程
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # segment
    cmd_seg = sub.add_parser("segment", help="② LLM断句 → 02_seg.srt")
    _add_common_args(cmd_seg)

    # translate
    cmd_tr = sub.add_parser("translate", help="④⑤ 翻译+字宽限制 → 03_zh.srt, 04_split.srt")
    _add_common_args(cmd_tr)
    _add_translate_args(cmd_tr)
    cmd_tr.add_argument("--skip-sponsor-check", action="store_true")

    # ass
    cmd_ass = sub.add_parser("ass", help="⑥⑦ 生成ASS+transcript → 05.ass, transcript.txt")
    _add_common_args(cmd_ass)

    # render
    cmd_render = sub.add_parser("render", help="⑧ 渲染视频 → output/*.mp4")
    _add_common_args(cmd_render)
    _add_render_args(cmd_render)

    # all (legacy)
    cmd_all = sub.add_parser("all", help="Run full pipeline ②-⑧")
    cmd_all.add_argument("url", help="YouTube video URL")
    cmd_all.add_argument("--skip-download", action="store_true")
    cmd_all.add_argument("--skip-sponsor-check", action="store_true")
    cmd_all.add_argument("--skip-translate", action="store_true")
    cmd_all.add_argument("--slug", help="Video folder slug (auto-detected if omitted)")
    cmd_all.add_argument("--output-title", help="B站 title for output filename")
    _add_translate_args(cmd_all)

    args = parser.parse_args()

    if args.command == "all":
        _run_pipeline_all(args)
    elif args.command == "segment":
        _run_stage_segment(args)
    elif args.command == "translate":
        _run_stage_translate(args)
    elif args.command == "ass":
        _run_stage_ass(args)
    elif args.command == "render":
        _run_stage_render(args)


# ── Stage functions ──────────────────────────────────────────────────────────


def _run_stage_segment(args):
    """② LLM断句: 01_raw.srt → 02_seg.srt"""
    video_dir, subtitle_dir, _ = _ensure_dirs(args.slug)
    raw_srt = subtitle_dir / "01_raw.srt"
    seg_srt = subtitle_dir / "02_seg.srt"

    if not raw_srt.exists():
        print(f"ERROR: {raw_srt} not found. Download first or copy 01_raw.srt to {subtitle_dir}")
        sys.exit(1)

    print(f"=== Stage: Segment ===\n  Source: {raw_srt}\n  Target: {seg_srt}")
    segmented = segment_sentences(raw_srt)
    write_srt(segmented, seg_srt)
    print(f"  {len(segmented)} sentences → {seg_srt.name}")


def _run_stage_translate(args):
    """④⑤ 翻译+字宽限制: 02_seg.srt → 03_zh.srt → 04_split.srt"""
    video_dir, subtitle_dir, _ = _ensure_dirs(args.slug)

    # Source: clean if available, else segmented
    clean_srt = subtitle_dir / "02_seg_clean.srt"
    seg_srt = subtitle_dir / "02_seg.srt"
    src = clean_srt if clean_srt.exists() else seg_srt

    if not src.exists():
        print(f"ERROR: Neither {clean_srt} nor {seg_srt} found. Run segment stage first.")
        sys.exit(1)

    # Detect sponsors if clean doesn't exist and not skipped
    if not clean_srt.exists() and not args.skip_sponsor_check:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            print("=== Stage: Sponsor Detection ===")
            _, _ = detect_sponsors(seg_srt, api_key)
            src = clean_srt if clean_srt.exists() else seg_srt

    # Translate
    zh_srt = subtitle_dir / "03_zh.srt"
    if not zh_srt.exists():
        print(f"=== Stage: Translate ===\n  Source: {src}\n  Target: {zh_srt}")
        translate_srt(src)
    else:
        print(f"=== Stage: Translate (skipped, {zh_srt.name} exists) ===")

    # Char limit
    split_srt = subtitle_dir / "04_split.srt"
    print(f"=== Stage: Char Limit (max {args.max_chars}) ===\n  Source: {zh_srt}\n  Target: {split_srt}")
    split_entries = enforce_max_chars(zh_srt, max_chars=args.max_chars)
    write_srt(split_entries, split_srt)
    print(f"  {len(split_entries)} entries → {split_srt.name}")


def _run_stage_ass(args):
    """⑥⑦ ASS+transcript: 04_split.srt → 05.ass, transcript.txt"""
    video_dir, subtitle_dir, _ = _ensure_dirs(args.slug)

    # Source: 04_split if exists, else 03_zh
    split_srt = subtitle_dir / "04_split.srt"
    zh_srt = subtitle_dir / "03_zh.srt"
    src = split_srt if split_srt.exists() else zh_srt

    if not src.exists():
        print(f"ERROR: Neither {split_srt} nor {zh_srt} found. Run translate stage first.")
        sys.exit(1)

    ass_file = subtitle_dir / "05.ass"
    print(f"=== Stage: ASS ===\n  Source: {src}\n  Target: {ass_file}")
    ass_content = srt_to_ass(src)
    ass_file.write_text(ass_content, encoding="utf-8")
    print(f"  ASS → {ass_file.name}")

    # Transcript
    transcript_file = subtitle_dir / "transcript.txt"
    print(f"=== Stage: Transcript ===\n  Target: {transcript_file}")
    save_transcript(src, transcript_file)


def _run_stage_render(args):
    """⑧ 渲染: 05.ass + video → 成片/*.mp4"""
    video_dir, subtitle_dir, output_dir = _ensure_dirs(args.slug)

    video_file = _find_video(args.slug)
    if video_file is None:
        print(f"ERROR: No video file found. Download first to lab _runtime/<slug>_process/")
        sys.exit(1)

    ass_file = subtitle_dir / "05.ass"
    if not ass_file.exists():
        print(f"ERROR: {ass_file} not found. Run ass stage first.")
        sys.exit(1)

    output_title = args.output_title or "output"
    output_mp4 = output_dir / f"{output_title}.mp4"

    print(f"=== Stage: Render ===\n  Video: {video_file.name}\n  ASS: {ass_file.name}\n  Output: {output_mp4}")

    if args.duration > 0:
        print(f"  Duration limit: {args.duration}s")
        # Single-pass: trim + burn ASS, avoids -c copy keyframe desync
        import os as _os
        _prev = _os.getcwd()
        try:
            _os.chdir(str(ass_file.parent))
            ass_rel = ass_file.name
            cmd = [
                "ffmpeg", "-y",
                "-ss", "0",
                "-i", str(video_file),
                "-t", str(args.duration),
                "-vf", f"ass='{ass_rel}'",
                "-c:v", "libx264", "-crf", "23", "-threads", "4",
                "-c:a", "aac", "-b:a", "128k",
                str(output_mp4),
            ]
            subprocess.run(cmd, check=True)
        finally:
            _os.chdir(_prev)
        print(f"  Rendered {args.duration}s clip")
    else:
        render_video(video_file, ass_file, output_mp4)

    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    print(f"  Done: {output_mp4.name} ({size_mb:.1f} MB)")


def _run_pipeline_all(args):
    slug = args.slug or extract_slug(args.url)
    video_dir, subtitle_dir, output_dir = _ensure_dirs(slug)

    # Download goes to lab _runtime (large video file stays there)
    lab_process = PROCESS_ROOT / slug / "_process"
    lab_process.mkdir(parents=True, exist_ok=True)

    print(f"Video slug: {slug}")
    print(f"Output dir:  {video_dir}")
    print(f"Lab dir:     {lab_process}\n")

    # 1. Download
    video_file = None
    if not args.skip_download:
        video_file = download_video(args.url, lab_process)
        # Copy raw SRT from lab to output subtitle dir
        raw_srt_lab = lab_process / "01_raw.srt"
        if raw_srt_lab.exists():
            import shutil
            shutil.copy2(raw_srt_lab, subtitle_dir / "01_raw.srt")
            print(f"  Raw SRT synced to output: {subtitle_dir / '01_raw.srt'}")
    else:
        mp4s = sorted(lab_process.glob("*.mp4"))
        video_file = mp4s[0] if mp4s else None
        print("[1/6] Skipped download")

    if video_file is None:
        print("WARNING: No video file found. Rendering will be skipped.")

    step_num = 2

    # 2. Segment
    raw_srt = subtitle_dir / "01_raw.srt"
    seg_srt = subtitle_dir / "02_seg.srt"
    if not seg_srt.exists() or not args.skip_download:
        print(f"[{step_num}/6] Segmenting sentences...")
        if not raw_srt.exists():
            print(f"  ERROR: {raw_srt} not found. Run without --skip-download first.")
            sys.exit(1)
        segmented = segment_sentences(raw_srt)
        write_srt(segmented, seg_srt)
        print(f"  {len(segmented)} segments → {seg_srt.name}")
    else:
        print(f"[{step_num}/6] Skipped (already exists)")

    # 3. Sponsor detection
    clean_srt = subtitle_dir / "02_seg_clean.srt"
    if not args.skip_sponsor_check:
        if not clean_srt.exists():
            _, cuts = detect_sponsors(seg_srt)
        else:
            print("[3/6] Sponsor detection skipped (02_seg_clean.srt already exists)")
    else:
        print("[3/6] Sponsor detection skipped (--skip-sponsor-check)")

    # Use clean SRT for translation if available
    translate_src = clean_srt if clean_srt.exists() else seg_srt

    # 4. Translate
    zh_srt = subtitle_dir / "03_zh.srt"
    if not zh_srt.exists() or not args.skip_translate:
        if not args.skip_translate:
            translate_srt(translate_src)
    else:
        print("[4/6] Skipped translation (already exists)")

    # 5. Char limit
    split_srt = subtitle_dir / "04_split.srt"
    max_chars = getattr(args, 'max_chars', 36)
    if zh_srt.exists():
        print(f"[5/6] Enforcing {max_chars}-char limit...")
        split_entries = enforce_max_chars(zh_srt, max_chars=max_chars)
        write_srt(split_entries, split_srt)
        print(f"  {len(split_entries)} entries → {split_srt.name}")
    else:
        print(f"[5/6] No translation, using segmented for char limit ({max_chars})...")
        split_entries = enforce_max_chars(translate_src, max_chars=max_chars)
        write_srt(split_entries, split_srt)

    # 6. ASS
    ass_file = subtitle_dir / "05.ass"
    src_for_ass = zh_srt if zh_srt.exists() else translate_src
    print("[6/6] Generating ASS...")
    ass_content = srt_to_ass(src_for_ass)
    ass_file.write_text(ass_content, encoding="utf-8")
    print(f"  ASS → {ass_file.name}")

    # Transcript
    transcript_file = subtitle_dir / "transcript.txt"
    save_transcript(src_for_ass, transcript_file)

    # 7. Render
    output_title = args.output_title or slug
    output_mp4 = output_dir / f"{output_title}.mp4"
    if video_file and video_file.exists() and ass_file.exists():
        print("[7/6] Rendering video...")
        render_video(video_file, ass_file, output_mp4)
        print(f"\nDone: {output_mp4}")
    else:
        print("[7/6] Skipped rendering (missing inputs)")

    print(f"\nNext steps:")
    print(f"  1. Cover    → {output_dir / 'cover.jpg'}")
    print(f"  2. Metadata → {output_dir / 'B站上传信息.txt'}")
    print(f"  3. Article  → {output_dir / 'B站专栏文章.md'}")


if __name__ == "__main__":
    main()

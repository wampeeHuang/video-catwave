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
RUNTIME = PROJECT_ROOT / "_runtime"

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
        srt_files[0].rename(target)
        print(f"  SRT saved: {target.name}")

    mp4_files = sorted(process_dir.glob("*.mp4"))
    return mp4_files[0] if mp4_files else None


# ── Step 1.5: Sentence segmentation ───────────────────────────────────────


def segment_sentences(srt_path: Path, target_words: int = 18) -> list[SubEntry]:
    """Merge YouTube word-level fragments into sentence-level segments."""
    raw = read_srt(srt_path)
    merged = _merge_fragments(raw)

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

    # Carryover trim: only trim text, keep timestamps
    return _carryover_trim(sentences, target_words)


def _merge_fragments(entries: list[SubEntry]) -> list[SubEntry]:
    """Merge entries that don't end with sentence-ending punctuation."""
    result = []
    buf, buf_start, buf_end = [], None, None
    for e in entries:
        if buf_start is None:
            buf_start = e.start
        buf.append(e.text)
        buf_end = e.end
        if re.search(r"[.!?]$", e.text.strip()):
            result.append(_make_entry(result, buf_start, buf_end, " ".join(buf)))
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


def _translate_batch(batch: list[SubEntry], api_key: str) -> list[str]:
    import json
    import urllib.request

    texts = [e.text.strip() for e in batch]
    prompt = (
        "Translate these English subtitles to Chinese (Simplified). "
        "For each input line, output ONLY the Chinese translation on a single line. "
        "Keep it concise and natural. Preserve technical terms where appropriate.\n\n"
        + "\n".join(texts)
    )

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional EN→ZH subtitle translator. Output ONLY the Chinese translation for each line, one per line. No explanations."},
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
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                # Ensure line count matches batch size
                while len(lines) < len(batch):
                    lines.append("")
                return lines[: len(batch)]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                raise e


# ── Step 3: Chinese char limit ────────────────────────────────────────────


def enforce_max_chars(srt_path: Path, max_chars: int = 28) -> list[SubEntry]:
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
    """Generate bilingual ASS file. SimHei 42px Chinese top, Segoe UI 32px English bottom."""
    entries = read_srt(srt_path)

    header = """[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Style: Default,SimHei,42,&H00FFFFFF&,&H00000000&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,2,0,2,10,10,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for e in entries:
        start = _ass_time(e.start)
        end = _ass_time(e.end)
        text = e.text.replace("\\N", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,45,,{text}")

    return "\n".join(lines)


def _ass_time(srt_time: str) -> str:
    """HH:MM:SS,mmm → H:MM:SS.mm (ASS format)"""
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return f"{int(h)}:{m}:{s}.{ms[:2]}"


# ── Step 5: Render ────────────────────────────────────────────────────────


def render_video(video_path: Path, ass_path: Path, output_path: Path):
    """FFmpeg burn ASS subtitles, H.264 CRF 23, AAC 128k."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    print(f"[5/6] Rendering: {output_path.name}")
    subprocess.run(cmd, check=True)


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


def main():
    parser = argparse.ArgumentParser(
        description="YouTube → B站 content pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline.py all https://youtube.com/watch?v=XXXXX
  python pipeline.py all <url> --skip-download
  python pipeline.py all <url> --skip-translate
  python pipeline.py all <url> --slug my_video --output-title "My Title"
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    cmd_all = sub.add_parser("all", help="Run full pipeline")
    cmd_all.add_argument("url", help="YouTube video URL")
    cmd_all.add_argument("--skip-download", action="store_true")
    cmd_all.add_argument("--skip-translate", action="store_true")
    cmd_all.add_argument("--slug", help="Video folder slug (auto-detected if omitted)")
    cmd_all.add_argument("--output-title", help="B站 title for output filename")

    args = parser.parse_args()

    if args.command != "all":
        parser.print_help()
        return

    _run_pipeline(args)


def _run_pipeline(args):
    slug = args.slug or extract_slug(args.url)
    video_dir = RUNTIME / slug
    process_dir = video_dir / "_process"
    frames_dir = video_dir / "frames"
    output_dir = video_dir / "output"

    for d in [process_dir, frames_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    print(f"Video slug: {slug}")
    print(f"Project dir: {video_dir}\n")

    # 1. Download
    raw_srt = process_dir / "01_raw.srt"
    video_file = None
    if not args.skip_download:
        video_file = download_video(args.url, process_dir)
        # Find mp4 in process_dir
        if video_file is None:
            mp4s = sorted(process_dir.glob("*.mp4"))
            video_file = mp4s[0] if mp4s else None
    else:
        mp4s = sorted(process_dir.glob("*.mp4"))
        video_file = mp4s[0] if mp4s else None
        print("[1/6] Skipped download")

    if video_file is None:
        print("WARNING: No video file found. Rendering will be skipped.")

    # 2. Segment
    seg_srt = process_dir / "02_seg.srt"
    if not seg_srt.exists() or not args.skip_download:
        print("[2/6] Segmenting sentences...")
        if not raw_srt.exists():
            print(f"  ERROR: {raw_srt} not found. Run without --skip-download first.")
            sys.exit(1)
        segmented = segment_sentences(raw_srt)
        write_srt(segmented, seg_srt)
        print(f"  {len(segmented)} segments → {seg_srt.name}")
    else:
        print("[2/6] Skipped (already exists)")

    # 3. Translate
    zh_srt = process_dir / "03_zh.srt"
    if not zh_srt.exists() or not args.skip_translate:
        if not args.skip_translate:
            translate_srt(seg_srt)
    else:
        print("[3/6] Skipped translation (already exists)")

    # 4. Char limit
    split_srt = process_dir / "04_split.srt"
    if zh_srt.exists():
        print("[4/6] Enforcing 28-char limit...")
        split_entries = enforce_max_chars(zh_srt)
        write_srt(split_entries, split_srt)
        print(f"  {len(split_entries)} entries → {split_srt.name}")
    else:
        # No translation available, use segmented
        print("[4/6] No translation, using segmented for char limit...")
        split_entries = enforce_max_chars(seg_srt)
        write_srt(split_entries, split_srt)

    # 5. ASS
    ass_file = process_dir / "05.ass"
    src_for_ass = zh_srt if zh_srt.exists() else seg_srt
    print("[5/6] Generating ASS...")
    ass_content = srt_to_ass(src_for_ass)
    ass_file.write_text(ass_content, encoding="utf-8")
    print(f"  ASS → {ass_file.name}")

    # Transcript
    transcript_file = process_dir / "transcript.txt"
    save_transcript(src_for_ass, transcript_file)

    # 6. Render
    output_title = args.output_title or slug
    output_mp4 = output_dir / f"{output_title}.mp4"
    if video_file and video_file.exists() and ass_file.exists():
        print("[6/6] Rendering video...")
        render_video(video_file, ass_file, output_mp4)
        print(f"\nDone: {output_mp4}")
    else:
        print("[6/6] Skipped rendering (missing inputs)")

    print(f"\nNext steps:")
    print(f"  1. Screenshot → {frames_dir}")
    print(f"  2. Cover    → {output_dir / 'cover.jpg'}")
    print(f"  3. Metadata → {output_dir / 'B站上传信息.txt'}")
    print(f"  4. Article  → {output_dir / 'B站专栏文章.md'}")


if __name__ == "__main__":
    main()

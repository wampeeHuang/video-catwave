"""Stage ⑦: Generate ASS subtitle file + transcript.

Usage: python stage_07_ass.py --slug <slug> [--bg-opacity 0.5] [--bg-padding 15]
Input:  <output>/_runtime/字幕/04_split.srt
Output: <output>/_runtime/字幕/05.ass + transcript.txt

Background box: per-event drawing rectangle behind both CN+EN lines as one block.
  --bg-opacity 0 disables the box.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    SubEntry, extract_transcript, ms_to_time, read_srt, srt_path, time_to_ms, write_srt,
)

CN_FS = 42  # SimHei
EN_FS = 36  # Microsoft YaHei


def run(slug: str, bg_opacity: float = 0.5, bg_padding: int = 15):
    src = srt_path(slug, "04_split.srt")
    if not src.exists():
        print(f"ERROR: {src} not found. Run stage_06 first.")
        sys.exit(1)

    entries = read_srt(src)
    fixed = _clip_overlaps(entries)
    ass = _generate_ass(fixed, bg_opacity, bg_padding)
    ass_path = srt_path(slug, "05.ass")
    ass_path.write_text(ass, encoding="utf-8")
    label = f"bg={bg_opacity:.0%} pad={bg_padding}px" if bg_opacity > 0 else "no bg"
    print(f"[⑦] ASS: {len(fixed)} events → {ass_path.name}  ({label})")

    cn_entries = [_cn_only(e) for e in fixed]
    transcript = extract_transcript(cn_entries)
    tx_path = srt_path(slug, "transcript.txt")
    tx_path.write_text(transcript, encoding="utf-8")
    print(f"  Transcript → {tx_path.name}")


def _clip_overlaps(entries: list[SubEntry]) -> list[SubEntry]:
    fixed = []
    for i, e in enumerate(entries):
        end_ms = time_to_ms(e.end)
        if i + 1 < len(entries):
            next_start_ms = time_to_ms(entries[i + 1].start)
            if end_ms > next_start_ms:
                end_ms = max(next_start_ms - 20, time_to_ms(e.start) + 500)
        fixed.append(SubEntry(e.index, e.start, ms_to_time(end_ms), e.text))
    return fixed


def _cn_only(e: SubEntry) -> SubEntry:
    parts = e.text.split("\\N", 1)
    return SubEntry(e.index, e.start, e.end, parts[0])


def _px_width(text: str, fs: int) -> int:
    """Estimate pixel width at given font size."""
    w = 0
    for ch in text:
        cp = ord(ch)
        if cp < 128:
            w += int(fs * 0.55)
        elif 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
            w += fs
        else:
            w += fs
    return w


def _bg_box(cn_text: str, en_text: str, padding: int, alpha_hex: str) -> str:
    """Generate drawing rectangle that spans both CN and EN lines as one block.

    Alignment=2 (bottom centre): X=0 is center, Y=0 is bottom of text, Y goes up.
    """
    cn_w = _px_width(cn_text, CN_FS)
    en_w = _px_width(en_text, EN_FS)
    max_w = max(cn_w, en_w)
    hw = max_w // 2 + padding  # half box width

    cn_h = int(CN_FS * 1.25)   # line height
    en_h = int(EN_FS * 1.25)
    gap = 5                     # \N gap
    text_h = cn_h + en_h + gap
    top = text_h + padding
    bottom = -padding

    return (
        f"{{\\c&H000000&\\alpha&H{alpha_hex}&\\p1}}"
        f"m {-hw} {top} l {hw} {top} l {hw} {bottom} l {-hw} {bottom}"
        f"{{\\p0}}{{\\c&HFFFFFF&\\alpha&H00&}}"
    )


def _generate_ass(entries: list[SubEntry], bg_opacity: float, bg_padding: int) -> str:
    alpha_hex = f"{int((1.0 - bg_opacity) * 255):02X}" if bg_opacity > 0 else "00"
    use_bg = bg_opacity > 0

    header = f"""[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Style: Default,SimHei,{CN_FS},&H00FFFFFF&,&H00000000&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,2,200,200,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for e in entries:
        start = _ass_time(e.start)
        end = _ass_time(e.end)
        parts = e.text.split("\\N", 1)
        cn = parts[0].strip()
        en = parts[1].strip() if len(parts) > 1 else ""

        # Text event (Layer 1)
        text = e.text.replace("\\N", "\\N{\\fnMicrosoft YaHei}")
        lines.append(f"Dialogue: 1,{start},{end},Default,,0,0,45,,{text}")

        # Background box event (Layer 0) — separate event avoids libass 0.17.4
        # bug where {\p1} drawing commands leak as visible text when combined
        # with text in the same Dialogue event.
        if use_bg and cn and en:
            box = _bg_box(cn, en, bg_padding, alpha_hex)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,45,,{box}")
        elif use_bg and cn:
            box = _bg_box(cn, cn, bg_padding, alpha_hex)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,45,,{box}")
    return "\n".join(lines)


def _ass_time(srt_time: str) -> str:
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return f"{int(h)}:{m}:{s}.{ms[:2]}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑦ Generate ASS + transcript")
    p.add_argument("--slug", required=True)
    p.add_argument("--bg-opacity", type=float, default=0.5,
                   help="Background box opacity 0.0-1.0 (default 0.5, 0=disabled)")
    p.add_argument("--bg-padding", type=int, default=15,
                   help="Background box padding in px (default 15)")
    args = p.parse_args()
    run(args.slug, bg_opacity=args.bg_opacity, bg_padding=args.bg_padding)

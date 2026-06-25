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

CN_FS = 42       # SimHei
EN_FS = 36       # Microsoft YaHei (matches \fs36 in _generate_ass)


def run(slug: str, bg_opacity: float = 0, bg_padding: int = 15, bord: int = 0, outline_alpha: int = 255):
    src = srt_path(slug, "04_split.srt")
    if not src.exists():
        print(f"ERROR: {src} not found. Run stage_06 first.")
        sys.exit(1)

    entries = read_srt(src)
    fixed = _clip_overlaps(entries)
    ass = _generate_ass(fixed, bg_opacity, bg_padding, bord, outline_alpha)
    ass_path = srt_path(slug, "05.ass")
    ass_path.write_text(ass, encoding="utf-8")
    if bord > 0:
        label = f"bord={bord}px alpha={outline_alpha}"
    elif bg_opacity > 0:
        label = f"bg={bg_opacity:.0%} pad={bg_padding}px"
    else:
        label = "no bg/bord"
    print(f"[⑦] ASS: {len(fixed)} events → {ass_path.name}  ({label})")

    cn_entries = [_cn_only(e) for e in fixed]
    transcript = extract_transcript(cn_entries)
    tx_path = srt_path(slug, "transcript.txt")
    tx_path.write_text(transcript, encoding="utf-8")
    print(f"  Transcript → {tx_path.name}")


def _clip_overlaps(entries: list[SubEntry]) -> list[SubEntry]:
    # Sort by start time; for same start, keep shorter (more specific) entry, drop longer
    entries = sorted(entries, key=lambda e: (time_to_ms(e.start), time_to_ms(e.end) - time_to_ms(e.start)))
    fixed = []
    prev_start_ms = -1
    for e in entries:
        start_ms = time_to_ms(e.start)
        end_ms = time_to_ms(e.end)
        # Drop entries that start at the exact same ms as the one we kept
        if start_ms == prev_start_ms:
            continue
        fixed.append(e)
        prev_start_ms = start_ms

    # Clip end times so entries don't overlap
    for i in range(len(fixed) - 1):
        end_ms = time_to_ms(fixed[i].end)
        next_start_ms = time_to_ms(fixed[i + 1].start)
        if end_ms > next_start_ms:
            min_end = time_to_ms(fixed[i].start) + 500
            fixed[i].end = ms_to_time(max(next_start_ms - 20, min_end))

    # Re-index
    for i, e in enumerate(fixed):
        e.index = i + 1
    return fixed


def _clean_text(text: str) -> str:
    """Strip sound-effect markers and speaker-change arrows."""
    import re
    text = re.sub(r'\[(?:音乐|music|掌声|Applause|笑声|Laughter)\]', '', text)
    text = re.sub(r'>>\s*', '', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def _cn_only(e: SubEntry) -> SubEntry:
    parts = e.text.split("\\N", 1)
    return SubEntry(e.index, e.start, e.end, _clean_text(parts[0]))


def _px_width(text: str, fs: int) -> int:
    """Estimate pixel width at given font size."""
    w = 0
    for ch in text:
        cp = ord(ch)
        if cp < 128:
            w += int(fs * 0.50)
        elif 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
            w += fs
        else:
            w += fs
    return w


def _bg_box(cn_text: str, en_text: str, padding: int, alpha_hex: str) -> str:
    """Generate drawing rectangle behind subtitle text.

    Alignment=2 (bottom centre): X=0 is center, Y=0 is bottom of text, Y goes up.
    """
    cn_w = _px_width(cn_text, CN_FS)
    en_w = _px_width(en_text, EN_FS) if en_text else 0
    max_w = max(cn_w, en_w)
    hw = max_w // 2 + padding

    cn_h = int(CN_FS * 1.25)
    en_h = int(EN_FS * 1.25) if en_text else 0
    gap = 5 if en_text else 0
    text_h = cn_h + en_h + gap
    top = text_h + padding
    bottom = -padding

    return (
        f"{{\\c&H000000&\\alpha&H{alpha_hex}&\\p1}}"
        f"m {-hw} {top} l {hw} {top} l {hw} {bottom} l {-hw} {bottom}"
        f"{{\\p0}}{{\\c&HFFFFFF&\\alpha&H00&}}"
    )


def _generate_ass(entries: list[SubEntry], bg_opacity: float, bg_padding: int, bord: int = 0, outline_alpha: int = 255) -> str:
    alpha_hex = f"{int((1.0 - bg_opacity) * 255):02X}" if bg_opacity > 0 else "00"
    use_bg = bg_opacity > 0

    if bord > 0:
        alpha_hex_outline = f"{outline_alpha:02X}"
        outline_colour = f"&H{alpha_hex_outline}000000&"
        outline_val = bord
        shadow_val = 1
    else:
        outline_colour = "&H00000000&"
        outline_val = 0
        shadow_val = 0

    header = f"""[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Style: Default,SimHei,{CN_FS},&H00FFFFFF&,&H00000000&,{outline_colour},&H00000000&,0,0,0,0,100,100,0,0,1,{outline_val},{shadow_val},2,200,200,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for e in entries:
        start = _ass_time(e.start)
        end = _ass_time(e.end)
        parts = e.text.split("\\N", 1)
        cn = _clean_text(parts[0])
        en = _clean_text(parts[1]) if len(parts) > 1 else ""

        # Text event (Layer 1)
        if en:
            text = f"{cn}\\N{{\\fnMicrosoft YaHei\\fs36}}{en}"
        else:
            text = cn
        lines.append(f"Dialogue: 1,{start},{end},Default,,0,0,45,,{text}")

        # Background box event (Layer 0) — separate event avoids libass 0.17.4
        # bug where {\p1} drawing commands leak as visible text when combined
        # with text in the same Dialogue event.
        if use_bg and cn:
            box = _bg_box(cn, en, bg_padding, alpha_hex)
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,45,,{box}")
    return "\n".join(lines)


def _ass_time(srt_time: str) -> str:
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return f"{int(h)}:{m}:{s}.{ms[:2]}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑦ Generate ASS + transcript")
    p.add_argument("--slug", required=True)
    p.add_argument("--bg-opacity", type=float, default=0,
                   help="Background box opacity 0.0-1.0 (default 0=disabled)")
    p.add_argument("--bg-padding", type=int, default=15,
                   help="Background box padding in px (default 15)")
    p.add_argument("--bord", type=int, default=0,
                   help="Text border/outline in px (default 0=disabled). Netflix standard is 3.")
    p.add_argument("--outline-alpha", type=int, default=255,
                   help="Outline alpha 0-255 (default 255=opaque. 128=50%%, 0=invisible)")
    args = p.parse_args()
    run(args.slug, bg_opacity=args.bg_opacity, bg_padding=args.bg_padding, bord=args.bord, outline_alpha=args.outline_alpha)

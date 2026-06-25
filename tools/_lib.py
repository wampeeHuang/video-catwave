"""Shared library for catwave pipeline stage scripts.

All stage scripts import from here. No stage script imports from another stage script.
Stages communicate through files on disk, not Python objects.

Path conventions (single source of truth):
  Output root:  D:/workspace/_output/猫波信号站/视频/<YYYYMMDD_slug>/
  Lab cache:    <project>/_runtime/<slug>_process/
  Subtitles:    <output>/_runtime/字幕/
  Renders:      <output>/成片/
"""

import dataclasses
import re
import shutil
import subprocess
from pathlib import Path

# ── Path roots ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # lab/2026-06-16-猫波信号站
RUNTIME = Path("D:/workspace/_output/猫波信号站/视频")
PROCESS_ROOT = PROJECT_ROOT / "_runtime"


# ── Data model ───────────────────────────────────────────────────────────────


@dataclasses.dataclass
class SubEntry:
    index: int
    start: str  # "HH:MM:SS,mmm"
    end: str
    text: str


# ── SRT I/O ──────────────────────────────────────────────────────────────────


def parse_srt(text: str) -> list[SubEntry]:
    """Parse SRT text, handling YouTube raw SRT quirks (extra blank lines)."""
    entries = []
    blocks = text.strip().split("\n\n")
    i = 0
    while i < len(blocks):
        lines = blocks[i].strip().split("\n")
        # Merge forward: if this block is just index+timestamp (2 lines, 2nd has "-->"),
        # and next block is text (not a new timestamp block), merge them.
        if len(lines) == 2 and "-->" in lines[1]:
            merged = list(lines)
            j = i + 1
            while j < len(blocks):
                next_lines = blocks[j].strip().split("\n")
                # Stop if next block looks like a new SRT entry (has timestamp on line 1)
                if len(next_lines) >= 2 and "-->" in next_lines[1]:
                    break
                # If next block is just an index number, skip it (already in merged[0])
                if len(next_lines) == 1 and next_lines[0].strip().isdigit():
                    j += 1
                    continue
                merged.extend(next_lines)
                j += 1
            lines = merged
            i = j
        else:
            i += 1

        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        timing = lines[1].strip()
        if " --> " not in timing:
            continue
        start, end = timing.split(" --> ")
        content = "\n".join(lines[2:]).strip()
        if content:
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


# ── Time helpers ─────────────────────────────────────────────────────────────


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


# ── Path resolution ──────────────────────────────────────────────────────────


def extract_slug(url: str) -> str:
    """Derive video slug from YouTube URL."""
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
    return m.group(1)[:20] if m else "video"


def slug_dir(slug: str) -> Path:
    """Resolve slug to output directory. Supports YYYYMMDD_slug prefix match."""
    d = RUNTIME / slug
    if d.exists():
        return d
    hits = sorted(RUNTIME.glob(f"*_{slug}"))
    if hits:
        return hits[0]
    d.mkdir(parents=True, exist_ok=True)
    return d


def subtitle_dir(slug: str) -> Path:
    d = slug_dir(slug) / "_runtime" / "字幕"
    d.mkdir(parents=True, exist_ok=True)
    return d


def output_dir(slug: str) -> Path:
    d = slug_dir(slug) / "成片"
    d.mkdir(parents=True, exist_ok=True)
    return d


def srt_path(slug: str, filename: str) -> Path:
    return subtitle_dir(slug) / filename


def find_video(slug: str) -> Path | None:
    """Find source video. Prefers source_clean.mp4 (stage ④ cut), falls back to source.mp4."""
    # Primary: output directory — prefer clean (cut) video
    out = slug_dir(slug) / "_runtime" / "素材"
    if out.exists():
        clean = out / "source_clean.mp4"
        if clean.exists():
            return clean
        mp4s = sorted(out.glob("*.mp4"))
        if mp4s:
            return mp4s[0]

    # Fallback: lab _runtime/<slug>_process/
    process_dir = PROCESS_ROOT / slug / "_process"
    if not process_dir.exists():
        hits = sorted(PROCESS_ROOT.glob(f"*_{slug}"))
        if hits:
            process_dir = hits[0] / "_process"
    if process_dir.exists():
        mp4s = sorted(process_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[0]
    return None


# ── Encoder detection ─────────────────────────────────────────────────────────


def detect_encoder() -> tuple[str, list[str], int]:
    """Detect best available encoder. NVENC (GPU) > x264 (CPU).
    Returns (codec, quality_params, threads).
    """
    if shutil.which("nvidia-smi") is not None:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=10,
            )
            if "h264_nvenc" in result.stdout:
                return "h264_nvenc", ["-cq", "23", "-preset", "p4", "-rc", "vbr"], 0
        except Exception:
            pass
    return "libx264", ["-crf", "23"], 4


# ── GPU health ─────────────────────────────────────────────────────────────────


def gpu_temp() -> int | None:
    """Read GPU temperature via nvidia-smi. Returns None if unavailable."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        return int(r.stdout.strip())
    except Exception:
        return None


def check_gpu_temp(max_temp: int = 80) -> tuple[int | None, bool]:
    """Pre-render GPU temperature gate. Warns above 70, rejects above max_temp.
    Returns (temp_celsius, ok).
    """
    temp = gpu_temp()
    if temp is None:
        return None, True
    if temp > max_temp:
        print(f"  GPU {temp}C > {max_temp}C, aborted. Wait for cooldown.")
        return temp, False
    if temp > 70:
        print(f"  GPU {temp}C (warm but ok)")
    else:
        print(f"  GPU {temp}C OK")
    return temp, True

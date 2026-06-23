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
from pathlib import Path

# ── Path roots ───────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # lab/2026-06-16-猫波信号站
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
    """Find source video in lab _runtime/<slug>_process/."""
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

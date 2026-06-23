"""Stage ②: Download YouTube video + English auto-subs via yt-dlp.

Usage: python stage_02_download.py --url <URL> --slug <slug>
Input:  YouTube URL
Output: <lab>/_runtime/<slug>_process/source.mp4 + 01_raw.srt
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import PROCESS_ROOT


def run(url: str, slug: str) -> Path:
    process_dir = PROCESS_ROOT / slug / "_process"
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

    print(f"[②] Downloading: {url}")
    subprocess.run(cmd, check=True, cwd=str(process_dir))

    # Rename English SRT to 01_raw.srt
    srt_files = sorted(process_dir.glob("*.en.srt"))
    if not srt_files:
        srt_files = sorted(process_dir.glob("*.srt"))
    if srt_files:
        target = process_dir / "01_raw.srt"
        target.unlink(missing_ok=True)
        srt_files[0].rename(target)
        print(f"  SRT → {target.name}")

    mp4_files = sorted(process_dir.glob("*.mp4"))
    if not mp4_files:
        print("ERROR: No MP4 downloaded")
        sys.exit(1)
    print(f"  Video → {mp4_files[0].name} ({mp4_files[0].stat().st_size / 1024 / 1024:.1f} MB)")
    return mp4_files[0]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="② Download YouTube video + subs")
    p.add_argument("--url", required=True)
    p.add_argument("--slug", required=True)
    args = p.parse_args()
    run(args.url, args.slug)

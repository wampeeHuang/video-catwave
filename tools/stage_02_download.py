"""Stage ②: Download YouTube video + English auto-subs via yt-dlp.

Usage: python stage_02_download.py --url <URL> --slug <slug>
Input:  YouTube URL
Output: <output>/_runtime/素材/source.mp4 + 01_raw.srt
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir


def run(url: str, slug: str) -> Path:
    dl_dir = slug_dir(slug) / "_runtime" / "素材"
    dl_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt",
        "-f", "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]",
        "--output", str(dl_dir / "%(title)s.%(ext)s"),
        "--write-sub", "--sub-format", "srt",
        url,
    ]

    print(f"[②] Downloading: {url}")
    subprocess.run(cmd, check=True, cwd=str(dl_dir))

    # Rename English SRT to 01_raw.srt
    srt_files = sorted(dl_dir.glob("*.en.srt"))
    if not srt_files:
        srt_files = sorted(dl_dir.glob("*.srt"))
    if srt_files:
        target = dl_dir / "01_raw.srt"
        target.unlink(missing_ok=True)
        srt_files[0].rename(target)
        print(f"  SRT -> {target.name}")

    mp4_files = sorted(dl_dir.glob("*.mp4"))
    if not mp4_files:
        print("ERROR: No MP4 downloaded")
        sys.exit(1)
    # Rename to source.mp4 for consistent pipeline reference
    source = dl_dir / "source.mp4"
    source.unlink(missing_ok=True)
    mp4_files[0].rename(source)
    size_mb = source.stat().st_size / 1024 / 1024
    print(f"  Video -> source.mp4 ({size_mb:.1f} MB)")
    return source


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="② Download YouTube video + subs")
    p.add_argument("--url", required=True)
    p.add_argument("--slug", required=True)
    args = p.parse_args()
    run(args.url, args.slug)

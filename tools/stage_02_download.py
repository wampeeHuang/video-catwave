"""Stage ②: Download YouTube video + English auto-subs via yt-dlp.

Usage: python stage_02_download.py --url <URL> --slug <slug>
Input:  YouTube URL
Output: <output>/_runtime/素材/source.mp4 + 01_raw.srt
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir


def run(url: str, slug: str) -> Path:
    dl_dir = slug_dir(slug) / "_runtime" / "素材"
    dl_dir.mkdir(parents=True, exist_ok=True)

    proxy = os.environ.get("VORTEX_PROXY", "")

    cmd = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "-f", "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]",
        "--output", str(dl_dir / "%(title)s.%(ext)s"),
        "--sleep-interval", "5", "--max-sleep-interval", "30",
        "--retries", "5", "--fragment-retries", "5",
    ]
    if proxy:
        cmd[1:1] = ["--proxy", f"http://{proxy}"]
    cmd.append(url)

    delays = [60, 120, 240]
    for attempt, delay in enumerate([0] + delays):
        if attempt > 0:
            print(f"[②] Retry {attempt}/{len(delays)} after {delay}s...")
            time.sleep(delay)
        print(f"[②] Downloading: {url}")
        try:
            subprocess.run(cmd, check=True, cwd=str(dl_dir))
            break
        except subprocess.CalledProcessError as e:
            if attempt < len(delays):
                print(f"  WARN: Download failed (exit {e.returncode}), will retry...")
            else:
                print(f"  ERROR: Download failed after {len(delays)} retries")
                raise

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

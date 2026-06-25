"""Stage ⑧: FFmpeg render with ASS subtitle burn.

Usage: python stage_08_render.py --slug <slug> [--duration 60] [--title "output"]
Input:  source_clean.mp4 (preferred) or source.mp4 + 05.ass
Output: <output>/成片/<title>.mp4

Video cutting happens in stage ④. This stage only burns subtitles.
No concat, no timecode shifting — the timeline was locked at stage ④.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import check_gpu_temp, detect_encoder, find_video, gpu_temp, output_dir, slug_dir, srt_path


def run(slug: str, *, title: str = "output", duration: int = 0, output_subdir: str = ""):
    video_file = find_video(slug)
    if not video_file:
        print(f"ERROR: No video found. Run stage_02_download first.")
        sys.exit(1)

    ass_file = srt_path(slug, "05.ass")
    if not ass_file.exists():
        print(f"ERROR: {ass_file} not found. Run stage_07_ass first.")
        sys.exit(1)

    codec, quality_params, threads = detect_encoder()
    codec_label = "NVENC (GPU)" if codec == "h264_nvenc" else "x264 (CPU)"

    # Pre-render GPU temperature gate
    temp, ok = check_gpu_temp()
    if not ok:
        sys.exit(1)

    if output_subdir:
        out_dir = slug_dir(slug) / output_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = output_dir(slug)
    output_mp4 = out_dir / f"{title}.mp4"

    suffix = " (clean)" if "source_clean" in str(video_file) else ""
    print(f"[⑧] Render: {video_file.name}{suffix} + {ass_file.name}")
    print(f"  Encoder: {codec_label}")

    _prev = os.getcwd()
    try:
        os.chdir(str(ass_file.parent))
        ass_rel = ass_file.name

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_file),
            "-vf", f"ass='{ass_rel}'",
            "-c:v", codec, *quality_params,
        ]
        if threads:
            cmd += ["-threads", str(threads)]
        cmd += ["-c:a", "aac", "-b:a", "128k"]
        if duration > 0:
            print(f"  Duration limit: {duration}s")
            cmd += ["-t", str(duration)]
        cmd += [str(output_mp4)]

        subprocess.run(cmd, check=True)
    finally:
        os.chdir(_prev)

    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    after_temp = gpu_temp()
    temp_info = f"GPU {after_temp}C" if after_temp is not None else "N/A"
    print(f"  → {output_mp4.name} ({size_mb:.1f} MB) | {temp_info}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑧ Render video with ASS subtitles")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", default="output")
    p.add_argument("--duration", type=int, default=0, help="Clip duration in seconds (0=full)")
    p.add_argument("--output-subdir", default="",
                   help="Output subdirectory under slug dir (default: 成片)")
    args = p.parse_args()
    run(args.slug, title=args.title, duration=args.duration, output_subdir=args.output_subdir)

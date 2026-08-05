"""Stage ⑧: FFmpeg render with ASS subtitle burn.

Usage: python stage_08_render.py --slug <slug> [--duration 60] [--title "output"]
Input:  source_clean.mp4 (preferred) or source.mp4 + 05.ass
Output: <output>/成片/<title>.mp4

Video cutting happens in stage ④. This stage only burns subtitles.
No concat, no timecode shifting — the timeline was locked at stage ④.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import check_gpu_temp, detect_encoder, find_video, gpu_temp, output_dir, slug_dir, srt_path

MAX_RETRIES = 2


def _kill_orphaned_ffmpeg(exclude_pids: set | None = None):
    """Kill orphaned ffmpeg processes. Skips exclude_pids and own process tree."""
    exclude_pids = exclude_pids or set()
    try:
        result = subprocess.run(
            ["tasklist", "/fi", "IMAGENAME eq ffmpeg.exe", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=10,
        )
        killed = 0
        for line in result.stdout.strip().split("\n"):
            if "ffmpeg.exe" not in line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            pid = parts[1].strip('"')
            if str(pid) in exclude_pids:
                continue
            try:
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True, timeout=10,
                )
                killed += 1
            except Exception:
                pass
        if killed:
            print(f"  Killed {killed} orphaned ffmpeg process(es)")
    except Exception:
        pass


def _ffprobe_validate(path: Path) -> bool:
    """Verify mp4 has valid moov atom and stream info."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False
        output = result.stdout.strip()
        return "video" in output and output
    except Exception:
        return False


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

    temp, ok = check_gpu_temp()
    if not ok:
        sys.exit(1)

    if output_subdir:
        out_dir = slug_dir(slug) / output_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = output_dir(slug)
    output_mp4 = out_dir / f"{title}.mp4"

    # Estimate required disk space: bitrate ~8 Mbps for 720p NVENC, 1.5x safety
    try:
        src_info = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video_file)],
            capture_output=True, text=True, timeout=15,
        )
        dur_s = float(src_info.stdout.strip()) if src_info.stdout.strip() else 0
    except Exception:
        dur_s = 0
    est_mb = dur_s * 1.0 * 1.5 if dur_s > 0 else 2000  # 8 Mbps ≈ 1 MB/s
    free = shutil.disk_usage(str(out_dir)).free / (1024 * 1024)
    if free < est_mb:
        print(f"ERROR: 磁盘空间不足 — 需要 {est_mb:.0f}MB, 剩余 {free:.0f}MB")
        sys.exit(1)
    print(f"  磁盘: 需要 ~{est_mb:.0f}MB, 剩余 {free:.0f}MB")

    suffix = " (clean)" if "source_clean" in str(video_file) else ""

    ffmpeg_pids: set[str] = set()

    for attempt in range(1 + MAX_RETRIES):
        if attempt > 0:
            print(f"  [Retry {attempt}/{MAX_RETRIES}]")
            if output_mp4.exists():
                output_mp4.unlink()
            time.sleep(3)

        print(f"[⑧] Render: {video_file.name}{suffix} + {ass_file.name}")
        print(f"  Encoder: {codec_label}")

        _prev = os.getcwd()
        proc = None
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

            proc = subprocess.Popen(cmd)
            ffmpeg_pids.add(str(proc.pid))
            ret = proc.wait()
            if ret != 0:
                raise subprocess.CalledProcessError(ret, cmd)
        finally:
            if proc and str(proc.pid) in ffmpeg_pids:
                ffmpeg_pids.discard(str(proc.pid))
            os.chdir(_prev)

        if _ffprobe_validate(output_mp4):
            size_mb = output_mp4.stat().st_size / (1024 * 1024)
            after_temp = gpu_temp()
            temp_info = f"GPU {after_temp}C" if after_temp is not None else "N/A"
            print(f"  -> {output_mp4.name} ({size_mb:.1f} MB) | {temp_info}")
            return
        else:
            print(f"  X ffprobe validation FAILED — corrupt output")

    print(f"ERROR: Render failed after {MAX_RETRIES} retries")
    sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑧ Render video with ASS subtitles")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", default="output")
    p.add_argument("--duration", type=int, default=0, help="Clip duration in seconds (0=full)")
    p.add_argument("--output-subdir", default="",
                   help="Output subdirectory under slug dir (default: 成片)")
    args = p.parse_args()
    run(args.slug, title=args.title, duration=args.duration, output_subdir=args.output_subdir)

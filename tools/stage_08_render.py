"""Stage ⑧: FFmpeg render with ASS subtitle burn + sponsor segment skipping.

Usage: python stage_08_render.py --slug <slug> [--duration 60] [--title "output"]
Input:  <lab>/_runtime/<slug>_process/source.mp4 + 05.ass + _sponsor_cuts.json
Output: <output>/成片/<title>.mp4
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import find_video, output_dir, slug_dir, srt_path


def run(slug: str, *, title: str = "output", duration: int = 0, output_subdir: str = ""):
    video_file = find_video(slug)
    if not video_file:
        print(f"ERROR: No video found. Run stage_02_download first.")
        sys.exit(1)

    ass_file = srt_path(slug, "05.ass")
    if not ass_file.exists():
        print(f"ERROR: {ass_file} not found. Run stage_07_ass first.")
        sys.exit(1)

    if output_subdir:
        out_dir = slug_dir(slug) / output_subdir
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = output_dir(slug)
    output_mp4 = out_dir / f"{title}.mp4"

    # Read sponsor cuts
    cuts_path = srt_path(slug, "_sponsor_cuts.json")
    sponsor_cuts = []
    if cuts_path.exists():
        sponsor_cuts = json.loads(cuts_path.read_text(encoding="utf-8"))
        if sponsor_cuts:
            print(f"[⑧] Sponsor cuts: {len(sponsor_cuts)} ranges → {cuts_path.name}")

    print(f"[⑧] Render: {video_file.name} + {ass_file.name}")

    if duration > 0:
        print(f"  Duration limit: {duration}s")
        _render_clip(video_file, ass_file, output_mp4, duration, sponsor_cuts)
    else:
        _render_full(video_file, ass_file, output_mp4, sponsor_cuts)

    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    print(f"  → {output_mp4.name} ({size_mb:.1f} MB)")


def _render_clip(video: Path, ass: Path, output: Path, duration: int, cuts: list[dict]):
    """Render a clip of `duration` seconds.

    If a sponsor cut starts within the clip, truncate at the cut start
    to avoid timeline mismatch between concat'd video and ASS timecodes.
    """
    effective_duration = float(duration)
    for c in cuts:
        cs = _to_seconds(c["start"])
        if 0 < cs < effective_duration:
            effective_duration = cs
            print(f"  Clip truncated to {effective_duration:.1f}s (sponsor cut at {c['start']})")
            break

    _prev = os.getcwd()
    try:
        os.chdir(str(ass.parent))
        cmd = [
            "ffmpeg", "-y",
            "-ss", "0",
            "-i", str(video),
            "-t", str(effective_duration),
            "-vf", f"ass='{ass.name}'",
            "-c:v", "libx264", "-crf", "23", "-threads", "4",
            "-c:a", "aac", "-b:a", "128k",
            str(output),
        ]
        subprocess.run(cmd, check=True)
    finally:
        os.chdir(_prev)


def _render_full(video: Path, ass: Path, output: Path, cuts: list[dict]):
    _prev = os.getcwd()
    try:
        os.chdir(str(ass.parent))
        ass_rel = ass.name

        if cuts:
            # Build trim filter to skip sponsor ranges
            # ffmpeg -i in.mp4 -vf "select='between(t,0,10)+between(t,20,30)',setpts=N/FRAME_RATE/TB"
            # But with ASS subtitle overlay we need trim on both streams
            # Simpler: use concat demuxer approach
            _render_with_cuts(video, ass, output, cuts)
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", f"ass='{ass_rel}'",
                "-c:v", "libx264", "-crf", "23", "-threads", "4",
                "-c:a", "aac", "-b:a", "128k",
                str(output),
            ]
            subprocess.run(cmd, check=True)
    finally:
        os.chdir(_prev)


def _render_with_cuts(video: Path, ass: Path, output: Path, cuts: list[dict]):
    """Render full video, skipping sponsor time ranges via concat.

    Strategy: split video into non-sponsor segments → concat → burn ASS.
    """
    import tempfile

    # Parse time ranges to skip
    cut_pairs = []
    for c in cuts:
        cut_pairs.append((_to_seconds(c["start"]), _to_seconds(c["end"])))

    # Build segments list: [0, cut1_start], [cut1_end, cut2_start], ...
    segments = []
    last_end = 0.0
    for cs, ce in cut_pairs:
        if cs > last_end:
            segments.append((last_end, cs))
        last_end = ce
    # Final segment after last cut
    segments.append((last_end, None))  # None = to end

    # Create temporary segment files
    tmp_dir = Path(tempfile.mkdtemp())
    seg_files = []
    try:
        for i, (seg_start, seg_end) in enumerate(segments):
            seg_path = tmp_dir / f"seg_{i:03d}.ts"
            cmd = ["ffmpeg", "-y", "-i", str(video)]
            if seg_start > 0:
                cmd += ["-ss", str(seg_start)]
            if seg_end is not None:
                cmd += ["-to", str(seg_end)]
            cmd += ["-c", "copy", str(seg_path)]
            subprocess.run(cmd, check=True, capture_output=True)
            seg_files.append(seg_path)

        # Concat segments
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{f}'" for f in seg_files))

        # Concat + burn ASS
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-vf", f"ass='{ass.name}'",
            "-c:v", "libx264", "-crf", "23", "-threads", "4",
            "-c:a", "aac", "-b:a", "128k",
            str(output),
        ]
        subprocess.run(cmd, check=True)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _to_seconds(srt_time: str) -> float:
    """HH:MM:SS,mmm → seconds"""
    h, m, rest = srt_time.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="⑧ Render video with ASS subtitles")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", default="output")
    p.add_argument("--duration", type=int, default=0, help="Clip duration in seconds (0=full)")
    p.add_argument("--output-subdir", default="",
                   help="Output subdirectory under slug dir (default: 成片)")
    args = p.parse_args()
    run(args.slug, title=args.title, duration=args.duration, output_subdir=args.output_subdir)

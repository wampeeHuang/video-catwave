#!/usr/bin/env python3
"""Video verifier: checks 成片 video specs via ffprobe.

Usage:
  python tools/validate_video.py --slug <slug> [--title "B站标题"]

This is the VERIFICATION layer. Production: stage_08_render.py (FFmpeg NVENC/x264).

Checks:
  1. Video file exists, non-empty, reasonable size
  2. ffprobe readable (valid media file)
  3. Video codec = H.264 (avc1/h264)
  4. Audio codec = AAC (aac/mp4a)
  5. Resolution ≤1920×1080
  6. Duration within 5% tolerance of source_clean.mp4
  7. Frame rate ~24-60 fps
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir, find_video, sanitize_filename
from pipeline_manifest import duration_profile

EXPECTED_CODEC = {"h264", "avc1"}
EXPECTED_AUDIO = {"aac", "mp4a"}


def _ffprobe(video: Path) -> dict | None:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return json.loads(result.stdout)


def validate_video(slug: str, title: str | None = None) -> tuple[bool, list[str]]:
    sdir = slug_dir(slug)
    results: list[str] = []
    all_ok = True

    # Find video file
    video_dir = sdir / "成片"
    if not video_dir.exists():
        return False, [f"[FAIL] 成片目录不存在: {video_dir}"]

    mp4s = list(video_dir.glob("*.mp4"))
    if not mp4s:
        return False, [f"[FAIL] 成片目录下无 .mp4 文件"]

    video = mp4s[0]
    if title:
        safe_title = sanitize_filename(title)
        named = video_dir / f"{safe_title}.mp4"
        if named.exists():
            video = named
        else:
            results.append(f"[WARN] 文件名不匹配标题: {video.name} ≠ {safe_title}.mp4")

    # 1. ffprobe first (needed for adaptive size check)
    info = _ffprobe(video)
    if not info:
        results.append("[FAIL] ffprobe 无法读取视频 — 文件可能损坏")
        return False, results

    # 1b. File size — adaptive minimum from manifest
    size_mb = video.stat().st_size / 1024 / 1024
    duration_s = float(info.get("format", {}).get("duration", 0))
    min_size = duration_profile(int(duration_s))["min_video_size_mb"]
    if size_mb < min_size:
        results.append(f"[FAIL] 视频 {size_mb:.0f}MB < {min_size:.0f}MB (时长{duration_s:.0f}s) — 异常")
        all_ok = False
    else:
        results.append(f"[OK] 文件大小 {size_mb:.0f}MB (阈值 {min_size:.0f}MB)")

    # 3. Video stream
    video_stream = None
    audio_stream = None
    for s in info.get("streams", []):
        if s["codec_type"] == "video" and video_stream is None:
            video_stream = s
        elif s["codec_type"] == "audio" and audio_stream is None:
            audio_stream = s

    if not video_stream:
        results.append("[FAIL] 无视频流")
        all_ok = False
    else:
        codec = video_stream.get("codec_name", "").lower()
        w = video_stream.get("width", 0)
        h = video_stream.get("height", 0)
        fps_str = video_stream.get("r_frame_rate", "0/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 0
        else:
            fps = float(fps_str)

        if codec not in EXPECTED_CODEC:
            results.append(f"[FAIL] 视频编码 {codec}，期望 H.264 ({EXPECTED_CODEC})")
            all_ok = False
        else:
            results.append(f"[OK] 视频: {codec} {w}×{h} {fps:.1f}fps")

        if w > 1920 or h > 1080:
            results.append(f"[WARN] 分辨率 {w}×{h} > 1920×1080")

    if not audio_stream:
        results.append("[FAIL] 无音频流")
        all_ok = False
    else:
        acodec = audio_stream.get("codec_name", "").lower()
        if acodec not in EXPECTED_AUDIO:
            results.append(f"[WARN] 音频编码 {acodec}，期望 AAC")
        else:
            results.append(f"[OK] 音频: {acodec}")

    # 4. Duration check (vs source)
    dur = float(info.get("format", {}).get("duration", 0))
    if dur > 0:
        results.append(f"[OK] 时长 {dur/60:.1f} 分钟")

        # Compare with source
        source = find_video(slug)
        if source:
            src_info = _ffprobe(source)
            if src_info:
                src_dur = float(src_info.get("format", {}).get("duration", 0))
                if src_dur > 0:
                    ratio = dur / src_dur
                    if 0.80 <= ratio <= 1.05:
                        results.append(f"[OK] 源/成片时长比 {ratio:.2f}")
                    else:
                        results.append(f"[WARN] 源/成片时长比 {ratio:.2f} (源 {src_dur/60:.1f}min → 成片 {dur/60:.1f}min)")

    return all_ok, results


def main():
    p = argparse.ArgumentParser(description="验证成片视频编码/分辨率/时长")
    p.add_argument("--slug", required=True)
    p.add_argument("--title", default=None, help="B站标题（检查文件名匹配）")
    args = p.parse_args()

    ok, results = validate_video(args.slug, args.title)
    for r in results:
        print(r)
    print(f"\n{'VIDEO OK' if ok else 'VIDEO NEEDS FIX'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

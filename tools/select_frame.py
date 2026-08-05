#!/usr/bin/env python3
"""Frame selector: automated sharpness scoring replaces manual "pick best face".

Usage:
  python tools/select_frame.py --slug <slug> [--num-frames 7] [--keep-all]

Workflow:
  1. ffprobe video duration
  2. Compute evenly-spaced timestamps (skip first/last 10%)
  3. ffmpeg extract frames → _runtime/frames/
  4. Score each frame: Laplacian variance × skin-tone bonus
  5. Print ranked results, return best frame path

This is the PRODUCTION layer for frame selection. Verification layer: validate_outputs.py
checks that _runtime/frames/ contains ≥5 frames.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir, find_video
from pipeline_manifest import duration_profile


def _ffprobe_duration(video: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0 or not result.stdout:
        stderr = result.stderr.strip() if result.stderr else "(no stderr)"
        raise RuntimeError(f"ffprobe failed (rc={result.returncode}): {stderr}\nvideo={video}")
    import json
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def _extract_frames(video: Path, timestamps: list[float], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(timestamps):
        mm = int(t // 60)
        ss = int(t % 60)
        name = f"frame_{mm:02d}m{ss:02d}s.jpg"
        out = out_dir / name
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(t), "-i", str(video),
             "-vframes", "1", "-q:v", "2", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if out.exists() and out.stat().st_size > 0:
            paths.append(out)
    return paths


def _score_frame(path: Path) -> tuple[float, float]:
    """Return (sharpness, skin_tone_ratio). Both higher = better."""
    from PIL import Image
    img = Image.open(path).convert("RGB")
    w, h = img.size

    # get_flattened_data (Pillow ≥14) preferred; fallback to getdata
    try:
        flat = list(img.get_flattened_data())
    except AttributeError:
        flat = list(img.getdata())

    # --- Laplacian variance (sharpness) ---
    gray = img.convert("L")
    try:
        gy = list(gray.get_flattened_data())
    except AttributeError:
        gy = list(gray.getdata())
    stride = w
    lap_sum = 0.0
    lap_count = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            idx = y * stride + x
            val = (4 * gy[idx]
                   - gy[idx - 1] - gy[idx + 1]
                   - gy[idx - stride] - gy[idx + stride])
            lap_sum += val * val
            lap_count += 1
    sharpness = lap_sum / max(lap_count, 1)

    # --- Skin-tone ratio in center 50% region (face proxy) ---
    cx0, cx1 = w // 4, 3 * w // 4
    cy0, cy1 = h // 3, 2 * h // 3
    skin_count = 0
    total_count = 0
    for y in range(cy0, cy1):
        for x in range(cx0, cx1):
            idx = y * w + x
            r, g, b = flat[idx]
            total_count += 1
            if (r > 95 and g > 40 and b > 20
                    and max(r, g, b) - min(r, g, b) > 15
                    and abs(r - g) > 15
                    and r > g and r > b):
                skin_count += 1
    skin_ratio = skin_count / max(total_count, 1)

    return sharpness, skin_ratio


def select_best_frame(slug: str, num_frames: int = 0, keep_all: bool = False) -> Path | None:
    sdir = slug_dir(slug)
    video = find_video(slug)
    if not video:
        print(f"ERROR: No source video found for slug {slug}")
        return None

    duration = _ffprobe_duration(video)
    print(f"Video: {video.name} ({duration:.0f}s / {duration/60:.1f} min)")

    if num_frames <= 0:
        num_frames = duration_profile(int(duration))["frame_count"]
        print(f"  auto frame_count={num_frames} from duration profile")

    # Timestamps: evenly-spaced, skip first/last 10%
    start = duration * 0.10
    end = duration * 0.90
    if num_frames == 1:
        timestamps = [(start + end) / 2]
    else:
        step = (end - start) / (num_frames - 1)
        timestamps = [start + i * step for i in range(num_frames)]
    print(f"Extracting {len(timestamps)} frames from {timestamps[0]:.0f}s to {timestamps[-1]:.0f}s")

    frames_dir = sdir / "_runtime" / "frames"
    paths = _extract_frames(video, timestamps, frames_dir)
    if not paths:
        print("ERROR: No frames extracted")
        return None

    # Score and rank
    scored = []
    for p in paths:
        sharp, skin = _score_frame(p)
        # Composite: sharpness weighted, skin as bonus multiplier
        composite = sharp * (1.0 + skin * 2.0)
        scored.append((composite, sharp, skin, p))

    scored.sort(reverse=True)

    print(f"\n{'Rank':<6} {'Frame':<20} {'Sharpness':>12} {'Skin%':>8} {'Composite':>12}")
    print("-" * 60)
    for i, (comp, sharp, skin, p) in enumerate(scored):
        marker = " ← BEST" if i == 0 else ""
        print(f"{i+1:<6} {p.name:<20} {sharp:>12.1f} {skin*100:>7.1f}% {comp:>12.1f}{marker}")

    best = scored[0][3]

    # Write selection manifest for audit + validator
    manifest = frames_dir / "selection.json"
    import json as _json
    manifest.write_text(_json.dumps({
        "video": str(video),
        "duration_s": duration,
        "frames_extracted": len(paths),
        "best_frame": best.name,
        "best_sharpness": scored[0][1],
        "best_skin_ratio": scored[0][2],
        "ranking": [{"frame": p.name, "sharpness": s, "skin_ratio": sk, "composite": c}
                    for c, s, sk, p in scored],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nBest frame: {best}")
    print(f"Manifest:  {manifest}")

    return best


def main():
    parser = argparse.ArgumentParser(description="Automated frame selection via sharpness scoring")
    parser.add_argument("--slug", required=True, help="Video slug")
    parser.add_argument("--num-frames", type=int, default=0, help="Frames to extract (0=auto from duration)")
    parser.add_argument("--keep-all", action="store_true", help="Keep all frames for manual review")
    args = parser.parse_args()

    best = select_best_frame(args.slug, args.num_frames, args.keep_all)
    if best:
        print(f"\n→ Run: python tools/gen_cover.py {best} cover.jpg --title \"...\" --sub \"...\"")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

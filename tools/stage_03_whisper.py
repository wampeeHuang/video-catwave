"""Stage ③: Whisper transcription with accurate timestamps.

Replaces YouTube auto-subs as the timeline anchor.
Whisper timestamps are directly tied to the audio waveform — no streaming lag.

Usage: python stage_03_whisper.py --slug <slug> [--duration 0]
Input:  source.mp4
Output: 01_whisper.srt + 01_whisper.json (segments with accurate timestamps)
"""
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Auto-add NVIDIA CUDA DLL paths for CTranslate2 GPU support
_nv_root = Path(sys.base_prefix) / "Lib" / "site-packages" / "nvidia"
if _nv_root.exists():
    for _d in ["cublas/bin", "cuda_nvrtc/bin", "cufft/bin", "curand/bin", "cusolver/bin", "cusparse/bin"]:
        _p = str(_nv_root / _d)
        if os.path.isdir(_p) and _p not in os.environ["PATH"]:
            os.add_dll_directory(_p)

from _lib import SubEntry, ms_to_time, slug_dir


def run(slug: str, *, model_size: str = "small", duration: int = 0):
    video_dir = slug_dir(slug)
    video = video_dir / "_runtime" / "素材" / "source.mp4"
    if not video.exists():
        print(f"ERROR: {video} not found. Run stage_02 first.")
        sys.exit(1)

    import torch
    from ctranslate2 import get_cuda_device_count
    device = "cuda" if get_cuda_device_count() > 0 else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    print(f"[③-Whisper] Transcribing: {video.name}")
    print(f"  Model: {model_size}, device: {device}, compute: {compute_type}")

    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    t0 = time.time()
    raw_segments, info = model.transcribe(
        str(video),
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    elapsed = time.time() - t0
    print(f"  Language: {info.language} ({info.language_probability:.3f})")

    # Convert to SubEntry list, dedup overlapping segments
    entries = []
    segments_list = []
    raw = []
    for seg in raw_segments:
        text = seg.text.strip()
        if not text:
            continue
        raw.append({"start": seg.start, "end": seg.end, "text": text})
        if duration > 0 and seg.end >= duration:
            break

    # Dedup: faster-whisper VAD can produce overlapping segments with same start time.
    # When seg[i] overlaps seg[i-1], shift seg[i]'s start to seg[i-1]'s end + 10ms gap.
    for i in range(1, len(raw)):
        prev_end = raw[i-1]["end"]
        curr_start = raw[i]["start"]
        if curr_start < prev_end - 0.1:  # overlap > 100ms
            raw[i]["start"] = prev_end + 0.01  # 10ms gap

    for i, seg in enumerate(raw):
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        entries.append(SubEntry(
            index=i + 1,
            start=ms_to_time(start_ms),
            end=ms_to_time(end_ms),
            text=seg["text"],
        ))
        segments_list.append({
            "index": i + 1,
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
        })

    sub_dir = video_dir / "_runtime" / "字幕"
    sub_dir.mkdir(parents=True, exist_ok=True)

    # Write SRT — output as 02_seg.srt so downstream stages consume directly
    from _lib import write_srt
    srt_path = sub_dir / "02_seg.srt"
    write_srt(entries, srt_path)

    # Also keep a Whisper-native copy for reference
    whisper_srt = sub_dir / "01_whisper.srt"
    write_srt(entries, whisper_srt)

    # Write JSON (full segment data with float timestamps)
    json_path = sub_dir / "01_whisper.json"
    json_path.write_text(json.dumps(segments_list, ensure_ascii=False, indent=2), encoding="utf-8")

    total_dur = segments_list[-1]["end"] if segments_list else 0
    print(f"  → {len(entries)} segments in {elapsed:.0f}s ({total_dur:.0f}s audio)")
    print(f"  → {srt_path.name}")
    print(f"  → {json_path.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="③ Whisper transcription")
    p.add_argument("--slug", required=True)
    p.add_argument("--model", default="small", choices=["tiny", "small", "medium"])
    p.add_argument("--duration", type=int, default=0, help="Max seconds (0=full)")
    args = p.parse_args()
    run(args.slug, model_size=args.model, duration=args.duration)

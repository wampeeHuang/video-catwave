"""Pipeline orchestrator: stages ②→⑧ for a single candidate.

Usage:
  python tools/pipeline.py --slug <slug> --url <youtube_url> --title "B站标题"

Each stage validates its output before proceeding. Stages with existing
valid output are skipped (idempotent re-run safe).

Exit code 0 = all stages complete, non-zero = failure at some stage.
"""

import argparse, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import sanitize_filename as _safe_filename

# Ensure NVIDIA CUDA DLL dirs are in PATH before spawning any subprocess.
# os.add_dll_directory() in stage_03_whisper.py only affects its own process;
# adding to PATH ensures child processes (subprocess.run) can find the DLLs too.
_nv_root = Path(sys.base_prefix) / "Lib" / "site-packages" / "nvidia"
if _nv_root.exists():
    for _d in ["cublas/bin", "cuda_nvrtc/bin", "cufft/bin", "curand/bin", "cusolver/bin", "cusparse/bin"]:
        _p = str(_nv_root / _d)
        if os.path.isdir(_p) and _p not in os.environ["PATH"]:
            os.environ["PATH"] = _p + ";" + os.environ["PATH"]
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(_p)

from _lib import slug_dir


TOOLS = Path(__file__).parent
PYTHON = sys.executable


MIN_SIZE = {".srt": 100, ".ass": 200, ".mp4": 50 * 1024 * 1024}  # bytes

def _run_stage(name: str, args: list[str], check_files: list[Path], slug: str) -> bool:
    """Run a stage and validate its outputs. Returns True on success."""
    output_dir = slug_dir(slug)

    # Check if outputs already exist (idempotent skip)
    all_exist = True
    for f in check_files:
        resolved = f if f.is_absolute() else output_dir / f
        if not resolved.exists():
            all_exist = False
            break
        min_sz = MIN_SIZE.get(resolved.suffix.lower(), 1)
        if resolved.stat().st_size < min_sz:
            all_exist = False
            break

    if all_exist:
        print(f"[{name}] SKIP — outputs already exist")
        return True

    print(f"[{name}] Running: {' '.join(args)}")
    result = subprocess.run([PYTHON, str(args[0])] + args[1:], cwd=str(TOOLS.parent))
    if result.returncode != 0:
        print(f"[{name}] FAILED (exit {result.returncode})")
        return False

    # Validate outputs
    for f in check_files:
        resolved = f if f.is_absolute() else output_dir / f
        if not resolved.exists() or resolved.stat().st_size == 0:
            print(f"[{name}] FAILED — missing output: {resolved}")
            return False

    print(f"[{name}] OK")
    return True


def run_pipeline(slug: str, url: str, title: str, feishu_rid: str = "", source: str = "") -> bool:
    sdir = slug_dir(slug)
    sub_dir = sdir / "_runtime" / "字幕"
    safe_title = _safe_filename(title)

    stages = [
        ("②-download", [
            str(TOOLS / "stage_02_download.py"), "--url", url, "--slug", slug,
        ], [
            sdir / "_runtime" / "素材" / "source.mp4",
        ]),
        ("③-whisper", [
            str(TOOLS / "stage_03_whisper.py"), "--slug", slug,
        ], [
            sub_dir / "02_seg.srt",
        ]),
        ("④-sponsor", [
            str(TOOLS / "stage_04_sponsor.py"), "--slug", slug,
        ], [
            sub_dir / "02_seg_clean.srt",
        ]),
        ("⑤-translate", [
            str(TOOLS / "stage_05_translate.py"), "--slug", slug,
        ], [
            sub_dir / "03_zh.srt",
        ]),
        ("⑥-split", [
            str(TOOLS / "stage_06_split.py"), "--slug", slug,
        ], [
            sub_dir / "04_split.srt",
        ]),
        ("⑦-ass", [
            str(TOOLS / "stage_07_ass.py"), "--slug", slug, "--bord", "1",
        ], [
            sub_dir / "05.ass",
        ]),
        ("⑧-render", [
            str(TOOLS / "stage_08_render.py"), "--slug", slug, "--title", safe_title,
        ], [
            sdir / "成片" / f"{safe_title}.mp4",
        ]),
    ]

    for name, args, check_files in stages:
        if not _run_stage(name, args, check_files, slug):
            print(f"\nPipeline stopped at {name}")
            return False

    # B站合规门禁 (after translation, before post-pipeline metadata)
    print("[⚠️compliance] Running B站 compliance check...")
    cr = subprocess.run(
        [PYTHON, str(TOOLS / "check_bilibili_compliance.py"), "--slug", slug],
        cwd=str(TOOLS.parent),
    )
    if cr.returncode == 1:
        print("[⚠️compliance] BLOCKED — B站红线命中，禁止上传")
        return False
    elif cr.returncode == 2:
        print("[⚠️compliance] WARNING — 人工审核后上传")
        # Persist compliance report for publish panel
        cr_path = sdir / "_runtime" / "compliance_report.txt"
        cr_path.parent.mkdir(parents=True, exist_ok=True)
        cr_path.write_text(cr.stdout, encoding="utf-8")
    else:
        print("[⚠️compliance] PASS")

    # Auto-fill Feishu copyright risk (if record_id and source known)
    if feishu_rid and source:
        print("[📋feishu] Auto-filling copyright risk...")
        from _feishu import fill_record_risk
        fill_record_risk(feishu_rid, source)
        print("[📋feishu] Done")

    print("\nPipeline ②→⑧ complete.")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="猫波信号站 管线编排 ②→⑧")
    p.add_argument("--slug", required=True)
    p.add_argument("--url", required=True, help="YouTube URL")
    p.add_argument("--title", required=True, help="B站视频标题（也用作文件名）")
    p.add_argument("--feishu-rid", default="", help="飞书 record_id (用于自动回写侵权风险)")
    p.add_argument("--source", default="", help="来源频道名 (用于自动评估侵权风险)")
    args = p.parse_args()
    ok = run_pipeline(args.slug, args.url, args.title, args.feishu_rid, args.source)
    sys.exit(0 if ok else 1)

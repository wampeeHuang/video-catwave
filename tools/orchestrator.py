"""猫波信号站 主编排器 — Stage B+C: production + status board.

Usage:
  python orchestrator.py --date YYYY-MM-DD [--dry-run] [--only-slug <slug>]

Reads _curation/YYYY-MM-DD.json, runs pipeline stages for each "候选" candidate,
then generates status board. Uses checkpoint file for resume after crash.

Exit 0 = all candidates processed, 1 = one or more failed.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir
from cover_design import detect_position, detect_overlay

TOOLS = Path(__file__).parent
PYTHON = sys.executable
OUTPUT_BASE = Path(r"D:\workspace\_output\猫波信号站\视频")
CURATION_DIR = OUTPUT_BASE / "_curation"
MAX_CANDIDATES = 5

ENV = os.environ.copy()
ENV["HTTPS_PROXY"] = "http://127.0.0.1:7897"
ENV["HTTP_PROXY"] = "http://127.0.0.1:7897"
ENV["VORTEX_PROXY"] = "127.0.0.1:7897"  # yt-dlp --proxy expects host:port (no scheme)


def _checkpoint_path(date_str: str) -> Path:
    return CURATION_DIR / f".checkpoint_{date_str}.json"


def _load_checkpoint(date_str: str) -> dict:
    cp = _checkpoint_path(date_str)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8-sig"))
    return {"date": date_str, "completed": [], "failed": []}


def _save_checkpoint(date_str: str, data: dict):
    cp = _checkpoint_path(date_str)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_preflight(slug: str, check_deps: bool = False, check_files: bool = True) -> tuple[bool, list[str]]:
    """Run preflight checks. Imported lazily to avoid circular deps."""
    try:
        from preflight import run_preflight
        return run_preflight(slug, check_deps_flag=check_deps, check_api_flag=False, check_files=check_files)
    except ImportError as e:
        return False, [f"[FAIL] preflight.py 不可用: {e}"]


def _run(cmd: list[str], label: str, timeout: int = 7200):
    """Run a subprocess. Returns True=success, False=failure, '429'=rate-limited."""
    print(f"  [{label}] {' '.join(cmd[:6])}{' ...' if len(cmd) > 6 else ''}")
    try:
        result = subprocess.run(
            [PYTHON] + cmd,
            cwd=str(TOOLS.parent),
            env=ENV,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            print(f"  [{label}] FAILED (exit {result.returncode})")
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            if stderr:
                print(f"    stderr: {stderr[:500]}")
            if stdout:
                print(f"    stdout: {stdout[:500]}")
            if "429" in (stderr + stdout) or "Too Many Requests" in (stderr + stdout):
                print(f"  [{label}] ⛔ YouTube rate limited — stopping pipeline")
                return "429"
            return False
        print(f"  [{label}] OK")
        return True
    except subprocess.TimeoutExpired:
        print(f"  [{label}] TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print(f"  [{label}] ERROR: {e}")
        return False


def _get_default_tags(candidate: dict) -> str:
    """Fixed tag template — no AI judgment, data-driven only."""
    tags = []
    channel = candidate.get("source_channel", "")
    guest = candidate.get("guest", [])

    # Fixed base tags (every video)
    tags.extend(["AI", "深度访谈", "人工智能", "播客翻译", "猫波信号站"])

    # Guest names (as-is, not just last name)
    if isinstance(guest, list):
        for g in guest[:3]:
            name = str(g).strip()
            if name and len(name) >= 2:
                tags.append(name)

    # Channel name (without @ prefix)
    if channel:
        tags.append(channel.replace("@", "").strip())

    # Deduplicate while preserving order
    seen = set()
    result = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return ",".join(result[:10])


def _cover_title(title: str) -> str:
    """Derive short cover title. Takes segment after last delimiter (：—|～).
    If still too long for 120px minimum font (~11 CJK chars), gen_cover will
    warn and validate_cover will fail — operator must shorten the title manually.
    """
    for delim in ['：', '—', '|', '～']:
        if delim in title:
            short = title.rsplit(delim, 1)[-1].strip()
            if short:
                return short
    return title


def _derive_sub(title: str, channel: str, guests: list[str]) -> str:
    """Derive --sub '<嘉宾身份> · <原节目名>' from candidate metadata."""
    show = channel.replace("@", "").strip()
    if not show:
        return ""
    identity = ""
    prefix = title.split("：")[0] if "：" in title else title
    for g in guests:
        first_name = g.strip().split()[0] if g.strip() else ""
        idx = prefix.find(first_name)
        if idx > 0:
            identity = prefix[:idx].strip()
            break
    if not identity:
        import re
        m = re.match(r"^([^\x00-\x7f]+)", prefix)
        if m:
            identity = m.group(1).strip()
    if identity:
        return f"{identity} · {show}"
    return show


def process_candidate(candidate: dict, label: str, date_str: str):
    """Run full production pipeline for one candidate. Returns True=success, False=failure, '429'=rate-limited."""
    slug = candidate["slug"]
    # Ensure slug has YYYYMMDD_ prefix (curation JSON may use bare slugs)
    if not __import__("re").match(r"^\d{8}_", slug):
        date_prefix = date_str.replace("-", "")
        slug = f"{date_prefix}_{slug}"
    url = candidate["url"]
    title = candidate["title"]
    channel = candidate.get("source_channel", "YouTube")
    guests = candidate.get("guest", [])
    sub = _derive_sub(title, channel, guests)

    print(f"\n{'='*60}")
    print(f"[{label}] {title[:80]}")
    print(f"  Slug: {slug}")
    if sub:
        print(f"  Sub: {sub}")

    # ═══ Preflight gate: dependencies (no file checks yet — pipeline hasn't run) ───
    preflight_ok, preflight_msgs = _run_preflight(slug, check_deps=True, check_files=False)
    for m in preflight_msgs:
        print(f"  {m}")
    if not preflight_ok:
        print(f"  [{label}] PREFLIGHT FAILED — dependencies missing, skipping candidate")
        return False

    # B1: pipeline ②→⑧ (download, whisper, translate, render, etc.)
    pipe_result = _run([
        str(TOOLS / "pipeline.py"),
        "--slug", slug, "--url", url, "--title", title,
    ], "pipeline", timeout=7200)
    if pipe_result == "429":
        return "429"
    if not pipe_result:
        return False

    # B站合规检查 — 红线命中 → 阻断，不浪费后续算力
    # exit 0=clean, 1=hard block, 2=warning (建议人工审核)
    bilibili_check = _run([
        str(TOOLS / "check_bilibili_compliance.py"),
        "--slug", slug,
    ], "bilibili_compliance", timeout=30)
    if bilibili_check == "429":
        return "429"
    if not bilibili_check:
        # Check if this was a warning (exit 2) vs hard block (exit 1)
        # Re-run to capture exit code since _run() abstracts it away
        import subprocess as _sp
        rc_result = _sp.run(
            [PYTHON, str(TOOLS / "check_bilibili_compliance.py"), "--slug", slug],
            cwd=str(TOOLS.parent), env=ENV,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        if rc_result.returncode == 2:
            print(f"  [bilibili_compliance] WARNING only (exit 2), not blocking")
        else:
            return False

    # ═══ Gate: Chinese transcript exists (post-pipeline) ───
    # Only check transcript — packaging inputs (metadata.json, cover.jpg etc.)
    # are outputs of later B2 steps, not prerequisites at this point.
    sdir = slug_dir(slug)
    has_transcript = False
    for fp in [sdir / "_runtime" / "字幕" / "03_zh.srt",
               sdir / "_runtime" / "字幕" / "transcript.txt"]:
        if fp.exists() and fp.stat().st_size > 100:
            has_transcript = True
            break
    if not has_transcript:
        print(f"  [{label}] PREFLIGHT FAILED — Chinese transcript missing, cannot proceed")
        return False
    print(f"  [preflight] Chinese transcript OK")

    # B2a: gen_metadata
    tags = _get_default_tags(candidate)
    source = f"YouTube @{channel}"
    meta_cmd = [
        str(TOOLS / "gen_metadata.py"),
        "--slug", slug, "--title", title, "--source", source, "--tags", tags,
        "--ai-chapters",
    ]
    curated_summary = candidate.get("summary", "")
    if curated_summary:
        meta_cmd.extend(["--summary", curated_summary])
    else:
        meta_cmd.append("--ai-summary")
    if not _run(meta_cmd, "gen_metadata", timeout=300):
        return False

    # B2b: gen_cover (select_frame → best frame → PIL cover generation)
    cover_path = slug_dir(slug) / "cover.jpg"
    if not cover_path.exists():
        # Use select_frame.py for automated best-frame selection
        select_ok = _run([
            str(TOOLS / "select_frame.py"), "--slug", slug, "--keep-all",
        ], "select_frame", timeout=120)
        if select_ok:
            sel_json = slug_dir(slug) / "_runtime" / "frames" / "selection.json"
            if sel_json.exists():
                sel = json.loads(sel_json.read_text(encoding="utf-8-sig"))
                best = sel.get("best_frame", "")
                frame_path = slug_dir(slug) / "_runtime" / "frames" / best
                if frame_path.exists():
                    try:
                        cover_t = candidate.get("cover_title") or _cover_title(title)
                        # Auto-detect position + overlay from frame signals
                        skin_ratio = sel.get("best_skin_ratio", 0) or 0
                        position = detect_position(skin_ratio)
                        try:
                            from PIL import Image
                            frame_img = Image.open(frame_path).convert("L")
                            avg_lum = sum(frame_img.getdata()) / (frame_img.width * frame_img.height)
                            overlay = detect_overlay(avg_lum)
                        except Exception:
                            overlay = detect_overlay(-1); avg_lum = -1
                        print(f"  [cover] skin_ratio={skin_ratio:.2f} avg_lum={avg_lum:.0f} → position={position} overlay={overlay}")
                        cmd = [PYTHON, str(TOOLS / "gen_cover.py"),
                               str(frame_path), str(cover_path),
                               "--title", cover_t, "--sub", sub,
                               "--overlay", str(overlay),
                               "--position", position]
                        subprocess.run(
                            cmd,
                            cwd=str(TOOLS.parent), env=ENV,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=120,
                        )
                        print(f"  [gen_cover] {'OK' if cover_path.exists() else 'FAILED'}")
                    except subprocess.TimeoutExpired:
                        print(f"  [gen_cover] TIMEOUT")
                    except Exception as e:
                        print(f"  [gen_cover] ERROR: {e}")
        if not cover_path.exists():
            print(f"  [gen_cover] WARN: cover generation failed, continuing")
    else:
        print(f"  [gen_cover] SKIP — cover already exists")

    # B2c: gen_epub
    author = ", ".join(candidate.get("guest", ["未知"]))
    if not _run([
        str(TOOLS / "gen_epub.py"),
        "--slug", slug, "--title", title, "--author", author, "--source", channel,
    ], "gen_epub", timeout=120):
        return False

    # B2d: gen_publish_panel
    if not _run([
        str(TOOLS / "gen_publish_panel.py"),
        "--slug", slug,
    ], "gen_publish_panel", timeout=60):
        return False

    # B3: validate_outputs
    if not _run([
        str(TOOLS / "validate_outputs.py"),
        "--slug", slug, "--title", title,
    ], "validate_outputs", timeout=60):
        return False

    # B4: update Feishu status 候选 → 待发布
    try:
        from _feishu import find_record_by_slug, get_token, update_record_status, upsert_record
        token = get_token()
        rid, current_status = find_record_by_slug(token, slug)
        # Fallback: use record_id from curation JSON (AI slugs often differ from Feishu slugs)
        if not rid:
            rid = candidate.get("record_id", "") or None
            current_status = "候选"  # trust the sync: curation JSON only includes 候选 items
        if rid and current_status == "候选":
            ok = update_record_status(token, rid, "待发布")
            if ok:
                print(f"  [feishu] {slug}: 候选 → 待发布")
            else:
                print(f"  [feishu] FAILED to update status for {slug}")
        elif rid and current_status == "待发布":
            print(f"  [feishu] {slug}: already 待发布")
        else:
            print(f"  [feishu] {slug}: no Feishu record found (status={current_status})")
    except Exception as e:
        print(f"  [feishu] WARN: {e}")

    print(f"[{label}] DONE")
    return True


def main():
    p = argparse.ArgumentParser(description="猫波信号站 主编排器 B+C")
    p.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="Print plan only")
    p.add_argument("--only-slug", default=None, help="Process only this slug (partial match)")
    p.add_argument("--only-slugs", default=None, help="Comma-separated list of slug patterns")
    args = p.parse_args()

    curation_file = CURATION_DIR / f"{args.date}.json"
    if not curation_file.exists():
        print(f"ERROR: Curation file not found: {curation_file}")
        print(f"  Run Job A (选题 curation) first to generate this file.")
        sys.exit(1)

    # Pre-flight: validate curation JSON structure (skip Feishu dedup — that's Stage A's job)
    print("Validating curation...")
    val_result = subprocess.run(
        [PYTHON, str(TOOLS / "validate_curation.py"), str(curation_file), "--skip-feishu"],
        cwd=str(TOOLS.parent), env=ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    if val_result.returncode != 0:
        print("CURATION VALIDATION FAILED:")
        print(val_result.stdout[:2000])
        if val_result.stderr:
            print(val_result.stderr[:500])
        print(f"\nFix the issues above, then re-run orchestrator.")
        print(f"  python tools/validate_curation.py {curation_file}")
        sys.exit(1)
    print("Curation validation PASSED\n")

    data = json.loads(curation_file.read_text(encoding="utf-8-sig"))
    candidates = data.get("candidates", [])

    # Normalize field names (curation file may use Chinese keys)
    for c in candidates:
        for cn, en in [("URL", "url"), ("标题", "title"), ("title_cn", "title"), ("来源频道名", "source_channel"),
                       ("嘉宾", "guest"), ("总分", "total_score"), ("total", "total_score")]:
            if en not in c and cn in c:
                c[en] = c.pop(cn)

    pending = [c for c in candidates if c.get("status") == "候选"]

    # Hard cap: never process more than MAX_CANDIDATES
    if len(pending) > MAX_CANDIDATES:
        print(f"  HARD CAP: limiting from {len(pending)} to {MAX_CANDIDATES} candidates")
        pending = pending[:MAX_CANDIDATES]

    # Filter by slug patterns
    patterns = []
    if args.only_slug:
        patterns.append(args.only_slug)
    if args.only_slugs:
        patterns.extend(s.strip() for s in args.only_slugs.split(",") if s.strip())
    if patterns:
        pending = [c for c in pending if any(p in c["slug"] for p in patterns)]
        if not pending:
            print(f"No candidate matching patterns: {patterns}")
            sys.exit(1)

    if not pending:
        print("No candidates with status=候选 to process.")
        print("Generating status board...")
        subprocess.run([PYTHON, str(TOOLS / "gen_status_board.py")],
                       cwd=str(TOOLS.parent), env=ENV, encoding="utf-8", errors="replace")
        print("Done.")
        return

    print(f"Found {len(pending)} candidate(s) to process:")
    for i, c in enumerate(pending):
        print(f"  {i+1}. [{c['total_score']:.1f}] {c['title'][:80]} ({c['slug']})")

    if args.dry_run:
        print("\n[Dry run — no actions taken]")
        return

    # Load checkpoint
    checkpoint = _load_checkpoint(args.date)
    completed = set(checkpoint.get("completed", []))
    failed_slugs = []

    for i, candidate in enumerate(pending):
        label = f"{i+1}/{len(pending)}"
        slug = candidate["slug"]

        # Rate-limit: wait 120s between candidates to avoid YouTube 429
        if i > 0:
            print(f"\n  Cooling down 120s before next candidate...")
            import time
            time.sleep(120)

        if slug in completed:
            print(f"\n[{label}] SKIP {slug} — already completed (checkpoint)")
            continue

        ok = process_candidate(candidate, label, args.date)
        if ok == "429":
            failed_slugs.append(slug)
            # Also mark remaining pending as skipped (not failed — will retry later)
            remaining = [c["slug"] for c in list(pending)[i+1:]]
            if remaining:
                print(f"  ⛔ Skipping {len(remaining)} remaining candidate(s) to avoid extending rate limit")
            _save_checkpoint(args.date, checkpoint)
            break
        if ok:
            completed.add(slug)
            checkpoint["completed"] = sorted(completed)
        else:
            failed_slugs.append(slug)
            checkpoint["failed"] = failed_slugs

        _save_checkpoint(args.date, checkpoint)

    # Stage C: gen_status_board
    print(f"\n{'='*60}")
    print("Generating status board...")
    result = subprocess.run(
        [PYTHON, str(TOOLS / "gen_status_board.py")],
        cwd=str(TOOLS.parent), env=ENV,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )
    if result.returncode == 0:
        print("Status board OK")
    else:
        err_msg = result.stderr[:500] if result.stderr else 'unknown'
        print(f"Status board FAILED: {err_msg}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(completed)} completed, {len(failed_slugs)} failed")
    if failed_slugs:
        print(f"  Failed slugs: {', '.join(failed_slugs)}")
    print(f"  Checkpoint: {_checkpoint_path(args.date)}")

    sys.exit(0 if not failed_slugs else 1)


if __name__ == "__main__":
    main()

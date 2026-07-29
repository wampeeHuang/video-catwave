"""Sync Feishu bitable → _curation JSON. Python replacement for sync-feishu-to-curation.ps1.
Python subprocess avoids all PowerShell encoding issues in headless/scheduler context.
"""
import json
import re
import subprocess
import sys
from datetime import date as date_type
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _feishu import fetch_records_filtered, upsert_record, APP_TOKEN, TABLE_ID

OUT_DIR = Path(r"D:\workspace\_output\猫波信号站\视频\_curation")
MIN_DURATION_SEC = 600  # 选题最低时长（与 pipeline_manifest 同步）
FIELD_IDS = [
    "状态", "标题", "Slug", "来源频道名", "嘉宾", "总分",
    "中文摘要", "URL", "时效性", "独占性", "人物权威", "长期价值", "B站BV号",
    "YouTube播放量", "YouTube点赞", "视频发布日期", "播放/天",
]
FILTER = {"logic": "or", "conditions": [["状态", "==", ["候选"]], ["状态", "==", ["待发布"]]]}
SORT = [{"field": "总分", "desc": True}]
MAX_CANDIDATES = 5
FETCH_LIMIT = 100

# Quality gates (defense in depth — agent prompt also enforces these)
BANNED_SOURCES = {"YouTube Search", "youtube search", "Youtube Search"}


def _read_existing_meta(date_str: str) -> dict:
    """Read existing _curation/{date}.json to preserve agent-written meta fields."""
    existing = OUT_DIR / f"{date_str}.json"
    if existing.exists():
        try:
            data = json.loads(existing.read_text(encoding="utf-8"))
            return {
                "sources_scanned": data.get("sources_scanned", 35),
                "total_recent_videos_scanned": data.get("total_recent_videos_scanned", 0),
                "passed_initial_screening": data.get("passed_initial_screening", 0),
                "scan_window": data.get("scan_window", ""),
            }
        except (json.JSONDecodeError, KeyError):
            pass
    return {"sources_scanned": 35, "total_recent_videos_scanned": 0,
            "passed_initial_screening": 0, "scan_window": ""}


def _to_int(v):
    """Coerce Feishu value to int. Returns 0 for non-numeric."""
    try: return int(v)
    except (TypeError, ValueError): return 0


def _cleanup_excess(rows, record_ids, field_idx, all_record_ids):
    """Cap to MAX_CANDIDATES, mark excess 候选 → 排除. Never touch 待发布."""
    if len(rows) <= MAX_CANDIDATES:
        return
    excess = rows[MAX_CANDIDATES:]
    print(f"Capping from {len(rows)} to {MAX_CANDIDATES} records ({len(excess)} excess)")

    def _get_field(record, name):
        i = field_idx.get(name)
        if i is None or i >= len(record):
            return None
        return record[i]

    for r in excess:
        status_val = _get_field(r, "状态")
        if isinstance(status_val, list):
            status_val = status_val[0] if status_val else ""
        if status_val != "候选":
            continue
        # Find record_id: use all_record_ids index lookup
        try:
            idx_in_all = rows.index(r) if r in rows else -1
        except ValueError:
            idx_in_all = -1
        rid = record_ids[rows.index(r)] if r in rows else None
        if not rid:
            continue
        print(f"  Cleanup: {rid} {status_val} -> 排除")
        upsert_record(rid, {"状态": "排除", "废弃原因": f"超出每日{MAX_CANDIDATES}条上限，自动排除"})


def run(date_str: str):
    print(f"=== sync-feishu-to-curation: {date_str} ===")

    # Fetch all records matching status filter (候选 + 待发布).
    # Status is the handoff signal between curation and production pipelines.
    # Do NOT filter by date — date is metadata, not a scope boundary.
    field_names, record_ids, rows = fetch_records_filtered(
        FIELD_IDS, FILTER, SORT, limit=FETCH_LIMIT)
    rows_all = rows[:]
    record_ids_all = record_ids[:]
    print(f"Records fetched: {len(rows)} total (status=候选 or 待发布)")

    field_idx = {name: i for i, name in enumerate(field_names)}

    def get_field(record, name):
        i = field_idx.get(name)
        if i is None or i >= len(record):
            return None
        return record[i]

    # Build Feishu lookup by record_id (full set, not date-scoped — dates may differ from curation date)
    feishu_by_rid = {}
    for i, row in enumerate(rows_all):
        feishu_by_rid[record_ids_all[i]] = row
    all_field_idx = {name: i for i, name in enumerate(field_names)}

    def get_field_all(record, name):
        i = all_field_idx.get(name)
        if i is None or i >= len(record):
            return None
        return record[i]

    # Always check existing curation first — agent candidates take priority.
    # Previous date-scoping design caused data loss: main path overwrote agent-written
    # candidates when even 1 record matched the target date.
    existing = OUT_DIR / f"{date_str}.json"
    existing_data = None
    existing_candidates = []
    if existing.exists():
        try:
            existing_data = json.loads(existing.read_text(encoding="utf-8"))
            existing_candidates = existing_data.get("candidates", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Enrichment: if agent already wrote candidates, always enrich (never overwrite).
    # This path runs regardless of whether date-scoped Feishu records exist.
    if existing_candidates:
        print("Existing file has {0} candidates — enriching from Feishu (full {1} records)".format(len(existing_candidates), len(rows_all)))
        # Build URL→row lookup from full Feishu set
        feishu_by_url = {}
        for i, row_all in enumerate(rows_all):
            url_v = get_field_all(row_all, "URL")
            if url_v:
                url_str = str(url_v)
                if "](" in url_str:
                    m2 = re.search(r"\]\(([^)]+)\)", url_str)
                    if m2:
                        url_str = m2.group(1)
                elif isinstance(url_v, list):
                    url_str = str(url_v[0]) if url_v else ""
                feishu_by_url[url_str.strip()] = (row_all, record_ids_all[i])
        # Normalize agent-written field names to orchestrator-expected keys
        for c in existing_candidates:
            if "score" in c and "total_score" not in c:
                c["total_score"] = c.pop("score")
            if "source" in c and "source_channel" not in c:
                c["source_channel"] = c.pop("source")
            if "upload_date" in c and "date" not in c:
                c["date"] = c.pop("upload_date")

        # Enrich each candidate with YouTube data from Feishu by URL
        for c in existing_candidates:
            url = (c.get("url") or "").strip()
            entry = feishu_by_url.get(url)
            if entry:
                fr, fr_rid = entry
                views_v = _to_int(get_field_all(fr, "YouTube播放量"))
                likes_v = _to_int(get_field_all(fr, "YouTube点赞"))
                c["views"] = views_v
                c["likes"] = likes_v
                status_v = get_field_all(fr, "状态")
                if isinstance(status_v, list):
                    status_v = status_v[0] if status_v else ""
                if status_v:
                    c["status"] = status_v
                c["feishu_status"] = status_v
                if not c.get("record_id"):
                    c["record_id"] = fr_rid
            else:
                c["views"] = 0
                c["likes"] = 0

        # Run Feishu housekeeping (cap + cleanup excess)
        _cleanup_excess(rows, record_ids, field_idx, record_ids)

        # Preserve agent-written meta
        saved_meta = _read_existing_meta(date_str)
        existing_data["date"] = date_str
        for k in ("pool_size", "sources_scanned", "total_recent_videos_scanned",
                   "passed_initial_screening", "scan_window"):
            existing_data[k] = saved_meta.get(k, existing_data.get(k))
        existing_data["candidates"] = existing_candidates

        out_path = OUT_DIR / f"{date_str}.json"
        out_path.write_text(json.dumps(existing_data, ensure_ascii=False, indent=4), encoding="utf-8")
        print("Enriched and saved: {0} ({1} candidates)".format(out_path, len(existing_candidates)))
        return

    # No existing candidates — build from Feishu records
    if len(rows) == 0:
        print("No active records in Feishu table and no existing curation")
        output = {
            "date": date_str, "pool_size": 0, "sources_scanned": 0,
            "total_recent_videos_scanned": 0, "passed_initial_screening": 0, "candidates": []
        }
        out_path = OUT_DIR / f"{date_str}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=4), encoding="utf-8")
        print("Written: {0} (0 candidates)".format(out_path))
        return

    # Enforce cap + cleanup excess
    _cleanup_excess(rows, record_ids, field_idx, record_ids)

    top5 = rows[:MAX_CANDIDATES]

    # Preserve agent-written meta
    saved_meta = _read_existing_meta(date_str)

    candidates = []
    for r in top5:
        idx = rows.index(r)
        rid = record_ids[idx]

        status_val = get_field(r, "状态")
        if isinstance(status_val, list):
            status_val = status_val[0] if status_val else ""

        title_val = get_field(r, "标题") or ""
        slug_val = get_field(r, "Slug") or ""
        channel_val = get_field(r, "来源频道名")
        if isinstance(channel_val, list):
            channel_val = channel_val[0] if channel_val else ""

        guest_val = get_field(r, "嘉宾") or []
        if not isinstance(guest_val, list):
            guest_val = [guest_val] if guest_val else []

        summary_val = get_field(r, "中文摘要") or ""

        url_val = get_field(r, "URL") or ""
        if isinstance(url_val, str) and "](" in url_val:
            m = re.search(r"\]\(([^)]+)\)", url_val)
            if m:
                url_val = m.group(1)
        elif isinstance(url_val, list):
            url_val = url_val[0] if url_val else ""

        bilibili_val = get_field(r, "B站BV号") or ""

        def to_float(v, default=0):
            try: return float(v)
            except (TypeError, ValueError): return default

        # Duration gate — defense in depth (only for 候选, never touch 待发布/已发布)
        duration_ok = True
        if url_val and ("youtube.com" in url_val or "youtu.be" in url_val) and status_val == "候选":
            dur = _check_duration(url_val)
            if dur is not None and dur < MIN_DURATION_SEC:
                print(f"  [duration gate] EXCLUDED {slug_val}: {dur}s < {MIN_DURATION_SEC}s")
                upsert_record(rid, {"状态": "排除", "废弃原因": f"时长 {dur}s < {MIN_DURATION_SEC}s 最低门禁"})
                duration_ok = False
            elif dur is not None:
                print(f"  [duration gate] {slug_val}: {dur}s OK")
            else:
                print(f"  [duration gate] {slug_val}: yt-dlp failed, keeping (can't verify)")

        if not duration_ok:
            continue

        # Source gate — YouTube Search is not a valid channel name
        if channel_val and channel_val in BANNED_SOURCES and status_val == "候选":
            print(f"  [source gate] DOWNGRADE {slug_val}: source='{channel_val}' is banned → marking as 候选 with warning")
            status_val = "候选"
            upsert_record(rid, {"教训备注": "⚠非固定源: YouTube Search (非真实频道名)"})

        # Compute views/day as decision-support metric (not a hard gate)
        # Human operator reviews flagged items in status panel before publishing
        views_val = get_field(r, "YouTube播放量")
        if isinstance(views_val, str):
            try: views_val = int(views_val)
            except (ValueError, TypeError): views_val = 0
        if views_val is None:
            views_val = 0
        likes_val = get_field(r, "YouTube点赞")
        if isinstance(likes_val, str):
            try: likes_val = int(likes_val)
            except (ValueError, TypeError): likes_val = 0
        if likes_val is None:
            likes_val = 0

        candidates.append({
            "slug": slug_val,
            "title": title_val,
            "url": url_val,
            "source_channel": channel_val,
            "guest": guest_val,
            "total_score": to_float(get_field(r, "总分")),
            "timeliness": to_float(get_field(r, "时效性")),
            "exclusivity": to_float(get_field(r, "独占性")),
            "authority": to_float(get_field(r, "人物权威")),
            "longevity": to_float(get_field(r, "长期价值")),
            "summary": summary_val,
            "status": status_val,
            "bilibili_cross_check": bilibili_val,
            "record_id": rid,
            "views": views_val,
            "likes": likes_val,
            "date": str(get_field(r, "视频发布日期") or "").split(" ")[0] if get_field(r, "视频发布日期") else "",
        })

    output = {
        "date": date_str,
        "pool_size": len(rows),
        "sources_scanned": saved_meta["sources_scanned"],
        "total_recent_videos_scanned": saved_meta["total_recent_videos_scanned"],
        "passed_initial_screening": saved_meta["passed_initial_screening"],
        "scan_window": saved_meta.get("scan_window", ""),
        "candidates": candidates,
    }

    out_path = OUT_DIR / f"{date_str}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"Written: {out_path} ({len(candidates)} candidates)")

    # Validate
    if not out_path.exists():
        print(f"FATAL: Output file not created at {out_path}")
        sys.exit(1)
    out_size = out_path.stat().st_size
    if out_size < 10:
        print(f"FATAL: Output file too small ({out_size} bytes)")
        sys.exit(1)
    verify = json.loads(out_path.read_text(encoding="utf-8"))
    print(f"Verified: {out_path} ({out_size} bytes, {len(verify.get('candidates', []))} candidates)")
    print("=== sync-feishu-to-curation done ===")


def _check_duration(url: str) -> int | None:
    """Fetch video duration in seconds via yt-dlp. Returns None on failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "%(duration)s", url],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip().isdigit():
            return int(result.stdout.strip())
    except Exception as e:
        print(f"  [duration] yt-dlp failed for {url[:60]}: {e}")
    return None


if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else date_type.today().isoformat()
    run(date_str)

"""Stage A.5: Create Feishu records for agent-curated candidates.

Reads today's _curation/{date}.json, deduplicates against past 30-day curation
JSON files, fetches YouTube metadata (views/likes) via yt-dlp, creates Feishu
records (status=候选) with full fields including copyright risk, and writes
record_id + enriched data back to the curation JSON.

Usage:
  python onboard_to_feishu.py [YYYY-MM-DD]
"""

import json
import re
import sys
from datetime import date as date_type, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _feishu import create_record, upsert_record, assess_copyright_risk, APP_TOKEN, TABLE_ID
import subprocess

CURATION_DIR = Path(r"D:\workspace\_output\猫波信号站\视频\_curation")
DEDUP_DAYS = 30


def _fetch_youtube_meta(url: str) -> dict:
    """Fetch video views/likes/comments/duration via yt-dlp. Returns {} on failure."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--print",
             "%(view_count)s||%(like_count)s||%(comment_count)s||%(duration_string)s",
             url],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        parts = result.stdout.strip().split("||")
        if len(parts) < 3:
            return {}
        return {
            "views": int(parts[0]) if parts[0].isdigit() else 0,
            "likes": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
            "comments": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
            "duration_str": parts[3] if len(parts) > 3 else "?",
        }
    except Exception:
        return {}


def _extract_vid(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def _gather_seen(days: int, today_str: str) -> dict[str, str]:
    """Scan past {days} curation JSON for slug→record_id and vid→record_id."""
    today = date_type.fromisoformat(today_str)
    seen_slug: dict[str, str] = {}
    seen_vid: dict[str, str] = {}
    for d in range(1, days + 1):
        path = CURATION_DIR / f"{(today - timedelta(days=d)).isoformat()}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, KeyError):
            continue
        for c in data.get("candidates", []):
            slug = (c.get("slug") or "").strip()
            rid = (c.get("record_id") or "").strip()
            vid = _extract_vid(c.get("url", ""))
            if slug:
                seen_slug[slug] = seen_slug.get(slug) or rid or "EXISTS"
            if vid and rid:
                seen_vid[vid] = rid
    return seen_slug, seen_vid


def _build_feishu_fields(c: dict) -> dict:
    guest_val = c.get("guest", [])
    if isinstance(guest_val, list):
        guest_val = ", ".join(str(g).strip() for g in guest_val if g)
    elif not guest_val:
        guest_val = "TBD"

    def _num(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return {
        "Slug": c.get("slug", ""),
        "URL": c.get("url", ""),
        "嘉宾": guest_val,
        "来源频道名": c.get("source_channel", ""),
        "标题": c.get("title", ""),
        "中文摘要": c.get("summary", ""),
        "状态": "候选",
        "视频发布日期": f"{c.get('date', '')} 00:00:00",
        "YouTube播放量": _num(c.get("views")),
        "YouTube点赞": _num(c.get("likes")),
        "YouTube评论": _num(c.get("comments")),
        "时效性": _num(c.get("timeliness")),
        "独占性": _num(c.get("exclusivity")),
        "人物权威": _num(c.get("authority")),
        "长期价值": _num(c.get("longevity")),
        "总分": c.get("total_score", 0),
    }


def run(date_str: str):
    print(f"=== onboard-to-feishu: {date_str} ===")

    cur_file = CURATION_DIR / f"{date_str}.json"
    if not cur_file.exists():
        print(f"ERROR: curation file not found: {cur_file}")
        sys.exit(1)

    data = json.loads(cur_file.read_text(encoding="utf-8-sig"))
    candidates = data.get("candidates", [])
    if not candidates:
        print("No candidates — nothing to do")
        return

    seen_slug, seen_vid = _gather_seen(DEDUP_DAYS, date_str)
    print(f"Dedup: {len(seen_slug)} slugs / {len(seen_vid)} video IDs from last {DEDUP_DAYS} days")

    created = 0
    skipped = 0

    for c in candidates:
        slug = (c.get("slug") or "").strip()
        url = c.get("url", "")
        vid = _extract_vid(url)
        existing_rid = c.get("record_id") or ""

        # Already has valid record_id — skip
        if existing_rid and len(existing_rid) > 5:
            skipped += 1
            continue

        # Check past curation for duplicate slug or URL
        if slug in seen_slug:
            prev = seen_slug[slug]
            if prev and prev != "EXISTS":
                c["record_id"] = prev
                skipped += 1
                print(f"  SKIP {slug}: found record_id from {DEDUP_DAYS}d history")
                continue
            skipped += 1
            print(f"  SKIP {slug}: duplicate in past {DEDUP_DAYS}d, no record_id")
            continue

        if vid and vid in seen_vid:
            c["record_id"] = seen_vid[vid]
            skipped += 1
            print(f"  SKIP {slug}: URL duplicate (vid={vid})")
            continue

        # New candidate — fetch YouTube metadata first
        print(f"  CREATE {slug}...")
        yt = _fetch_youtube_meta(url)
        if yt:
            c["views"] = yt["views"]
            c["likes"] = yt["likes"]
            c["comments"] = yt.get("comments", 0)
            print(f"    yt-dlp: {yt['views']:,} views / {yt['likes']:,} likes / {yt.get('comments',0):,} comments / {yt['duration_str']}")
        else:
            print(f"    yt-dlp WARN: fetch failed, using JSON values")

        fields = _build_feishu_fields(c)
        rid, ok = create_record(fields, APP_TOKEN, TABLE_ID)
        if ok and rid:
            c["record_id"] = rid
            seen_slug[slug] = rid
            if vid:
                seen_vid[vid] = rid
            # Fill copyright risk assessment
            risk, note = assess_copyright_risk(c.get("source_channel", ""))
            upsert_record(rid, {"侵权风险": risk, "侵权风险说明": note}, APP_TOKEN, TABLE_ID)
            created += 1
            print(f"    OK: {rid} risk={risk}")
        else:
            print(f"    FAILED: record not created")

    # Write back
    cur_file.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"Saved: {cur_file} ({len(candidates)} candidates, {created} created, {skipped} skipped)")
    print("=== onboard-to-feishu done ===")


if __name__ == "__main__":
    args = sys.argv[1:]
    d = args[0] if args else date_type.today().isoformat()
    run(d)

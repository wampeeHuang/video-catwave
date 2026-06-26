"""Stage ①: Onboard a new topic to Feishu 选题库.

Fetches YouTube metadata, validates all required fields, and outputs a complete
JSON ready for `lark-cli base +record-upsert`. Use --create to directly write.

Usage:
  python stage_01_topic_onboard.py \
      --url "https://youtube.com/watch?v=XXX" \
      --title "中文标题（嘉宾身份：主题概括）" \
      --guest "嘉宾英文名" \
      --source "来源频道名" \
      --summary "中文摘要（一句话）" \
      --timeliness 3 --exclusivity 3 --authority 2 --longevity 2
      [--slug custom-slug] [--date 2026-06-07] [--status 候选] [--create] [--dry-run]
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def fetch_youtube_metadata(url: str) -> dict:
    """Fetch video metadata via yt-dlp. Returns flat dict or exits."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--print", "%(title)s||%(view_count)s||%(like_count)s||%(upload_date)s||%(duration)s",
                url,
            ],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: yt-dlp failed\n{e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("ERROR: yt-dlp not found in PATH", file=sys.stderr)
        sys.exit(1)

    parts = result.stdout.strip().split("||")
    if len(parts) < 4:
        print(f"ERROR: unexpected yt-dlp output: {result.stdout}", file=sys.stderr)
        sys.exit(1)

    views = int(parts[1]) if parts[1].isdigit() else 0
    likes = int(parts[2]) if parts[2].isdigit() else 0
    upload_date = parts[3]
    if len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

    return {
        "yt_title": parts[0],
        "views": views,
        "likes": likes,
        "upload_date": upload_date,
    }


def generate_slug(guest: str, source: str, url: str) -> str:
    """Generate slug from guest + source channel + video ID."""
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
    vid = m.group(1)[:20] if m else "video"

    # Clean guest: lowercase, replace spaces/hyphens
    g = guest.lower().strip()
    g = re.sub(r"[^a-z0-9]+", "-", g).strip("-")

    # Clean source to short tag
    source_tags = {
        "Lenny's Podcast": "lenny",
        "Latent Space": "latentspace",
        "Lex Fridman Podcast": "lex",
        "Y Combinator": "yc",
        "Training Data": "sequoia",
        "Sequoia Capital": "sequoia",
        "Stanford Online": "stanford",
        "Google DeepMind": "deepmind",
        "Every Inc": "every",
        "Every Inc (AI & I)": "every",
    }
    st = source_tags.get(source, source.lower().replace(" ", "-"))

    return f"{g}-{vid[:12]}-{st}"


def validate_scores(timeliness: int, exclusivity: int, authority: int, longevity: int):
    for name, val in [("时效性", timeliness), ("独占性", exclusivity),
                       ("人物权威", authority), ("长期价值", longevity)]:
        if not 0 <= val <= 5:
            print(f"ERROR: {name} must be 0-5, got {val}", file=sys.stderr)
            sys.exit(1)


def calc_total(timeliness: int, exclusivity: int, authority: int, longevity: int) -> int:
    return timeliness * 3 + exclusivity * 3 + authority * 2 + longevity * 2


def build_record(title: str, guest: str, source: str, summary: str, url: str,
                 slug: str, date: str, status: str, yt_title: str | None,
                 views: int, likes: int,
                 timeliness: int, exclusivity: int, authority: int, longevity: int) -> dict:
    """Build a complete Feishu record as a flat dict (field-name → CellValue)."""
    return {
        # ── core identifiers ──
        "Slug": slug,
        "URL": url,
        "嘉宾": guest,
        "来源频道名": source,
        # ── Chinese content (REQUIRED — must be human-provided or LLM-generated) ──
        "标题": title,
        "中文摘要": summary,
        # ── status ──
        "状态": status,
        "日期": f"{date} 00:00:00",
        # ── YouTube metadata (auto-fetched) ──
        "YouTube播放量": views,
        "YouTube点赞": likes,
        # ── scores ──
        "时效性": timeliness,
        "独占性": exclusivity,
        "人物权威": authority,
        "长期价值": longevity,
        "总分": calc_total(timeliness, exclusivity, authority, longevity),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Stage ①: Onboard a topic to Feishu 选题库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scoring formula: 总分 = 时效性×3 + 独占性×3 + 人物权威×2 + 长期价值×2 (max 30)

Examples:
  %(prog)s --url "https://youtube.com/watch?v=RJjl1TwyfWM" \\
      --title "iPod之父Tony Fadell：AI时代真正的稀缺是品味与判断力" \\
      --guest "Tony Fadell" --source "Lenny's Podcast" \\
      --summary "iPod/iPhone/Nest 创造者 Tony Fadell 对话 Lenny..." \\
      --timeliness 3 --exclusivity 3 --authority 3 --longevity 2 --create
        """,
    )

    # Required
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--title", required=True,
                        help="Chinese title (pattern: 身份+姓名：主题概括)")
    parser.add_argument("--guest", required=True, help="Guest name (English)")
    parser.add_argument("--source", required=True, help="Source channel name")
    parser.add_argument("--summary", required=True, help="Chinese summary (one sentence)")

    # Scores
    parser.add_argument("--timeliness", type=int, required=True,
                        help="时效性 (0-5)")
    parser.add_argument("--exclusivity", type=int, required=True,
                        help="独占性 (0-5)")
    parser.add_argument("--authority", type=int, required=True,
                        help="人物权威 (0-5)")
    parser.add_argument("--longevity", type=int, required=True,
                        help="长期价值 (0-5)")

    # Optional
    parser.add_argument("--slug", default=None,
                        help="Slug (auto-generated from guest+source+video-id if omitted)")
    parser.add_argument("--date", default=None,
                        help="Episode date YYYY-MM-DD (auto from YouTube if omitted)")
    parser.add_argument("--status", default="候选",
                        choices=["候选", "已发布", "排除", "过期"],
                        help="Record status (default: 候选)")
    parser.add_argument("--create", action="store_true",
                        help="Directly create Feishu record via lark-cli")
    parser.add_argument("--base-token", default="F7E8bJie5aX3BvsZz1Xc9KiznNb",
                        help="Feishu base token")
    parser.add_argument("--table-id", default="tblIs359fHfIapwd",
                        help="Feishu table ID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print record without writing")
    parser.add_argument("--out", default=None,
                        help="Write JSON to file instead of stdout")

    args = parser.parse_args()

    # 1. Validate scores
    validate_scores(args.timeliness, args.exclusivity, args.authority, args.longevity)

    # 2. Validate Chinese title is actually Chinese
    if not re.search(r"[一-鿿]", args.title):
        print(f"WARNING: 标题 contains no Chinese characters: {args.title}", file=sys.stderr)

    # 3. Fetch YouTube metadata
    print(f"Fetching: {args.url}")
    yt = fetch_youtube_metadata(args.url)
    print(f"  Title:     {yt['yt_title']}")
    print(f"  Views:     {yt['views']:,}")
    print(f"  Likes:     {yt['likes']:,}")
    print(f"  Published: {yt['upload_date']}")

    # 4. Resolve defaults
    slug = args.slug or generate_slug(args.guest, args.source, args.url)
    date = args.date or yt["upload_date"]

    # 5. Build record
    total = calc_total(args.timeliness, args.exclusivity, args.authority, args.longevity)
    record = build_record(
        title=args.title, guest=args.guest, source=args.source,
        summary=args.summary, url=args.url, slug=slug, date=date,
        status=args.status, yt_title=yt["yt_title"],
        views=yt["views"], likes=yt["likes"],
        timeliness=args.timeliness, exclusivity=args.exclusivity,
        authority=args.authority, longevity=args.longevity,
    )

    # 6. Validate completeness
    required = ["标题", "URL", "嘉宾", "来源频道名", "中文摘要", "Slug", "日期",
                "YouTube播放量", "YouTube点赞", "时效性", "独占性", "人物权威", "长期价值", "总分"]
    missing = [k for k in required if k not in record or record[k] in (None, "", 0)]
    if missing:
        print(f"ERROR: missing required fields: {missing}", file=sys.stderr)
        sys.exit(1)

    # 7. Output
    json_str = json.dumps(record, ensure_ascii=False, indent=2)
    print(f"\n  Slug:     {slug}")
    print(f"  Score:    {total} (T{args.timeliness}×3 + E{args.exclusivity}×3 + A{args.authority}×2 + L{args.longevity}×2)")

    if args.dry_run or not args.create:
        if args.out:
            Path(args.out).write_text(json_str, encoding="utf-8")
            print(f"  Written:  {args.out}")
        else:
            print(f"\n{json_str}")
        print("\nNext: use --create to write directly to Feishu, or pipe to lark-cli")
        return

    # 8. Create Feishu record
    tmp = Path.home() / "_runtime" / f"stage01_{slug}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json_str, encoding="utf-8")

    try:
        result = subprocess.run(
            [
                "lark-cli", "base", "+record-upsert",
                "--base-token", args.base_token,
                "--table-id", args.table_id,
                "--json", f"@_runtime/{tmp.name}",
                "--as", "bot",
            ],
            capture_output=True, text=True, timeout=15,
        )
        print(f"\nlark-cli stdout:\n{result.stdout}")
        if result.returncode != 0:
            print(f"lark-cli stderr:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            rid = resp["data"]["record"]["record_id_list"][0]
            print(f"\n  Created:  {rid}")
            print(f"  URL:      https://fcn7dgp1xcm8.feishu.cn/base/{args.base_token}?table={args.table_id}")
    finally:
        if tmp.exists():
            tmp.unlink()


if __name__ == "__main__":
    main()

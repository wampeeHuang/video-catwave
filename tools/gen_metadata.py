"""Generate metadata.json for B站 upload (stage_16_cdp_upload.py input).

Usage:
  python gen_metadata.py --slug <slug> --title "<title>" --source "<source>" \
      --tags "tag1,tag2,..." [--baidu-link "<url>"]

Chapter timestamps are auto-generated from SRT. Description is read from
_runtime/draft.md or --description flag. Output: <output>/_runtime/metadata.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir


def time_to_seconds(t: str) -> int:
    h, m, rest = t.split(":")
    s = rest.split(",")[0]
    return int(h) * 3600 + int(m) * 60 + int(s)


def seconds_to_timestamp(s: int) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def read_srt_lines(path: Path) -> list[dict]:
    """Parse SRT into start/duration/text entries."""
    text = path.read_text(encoding="utf-8")
    entries = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", lines[1])
        if not m:
            continue
        body = " ".join(lines[2:]).strip()
        if body:
            entries.append({
                "start": m.group(1).replace(".", ","),
                "end": m.group(2).replace(".", ","),
                "text": body,
            })
    return entries


def auto_chapters(entries: list[dict], max_chapters: int = 10) -> list[list[str]]:
    """Generate chapters from SRT: one chapter every N minutes, max 10."""
    if not entries:
        return []

    total_sec = time_to_seconds(entries[-1]["end"])
    chunk_sec = max(300, total_sec // max_chapters)  # at least 5 min per chapter

    chapters = []
    next_at = 0
    for e in entries:
        t = time_to_seconds(e["start"])
        if t >= next_at or len(chapters) == 0:
            title = e["text"]
            # Use only the Chinese part before \N
            if "\\N" in title:
                title = title.split("\\N")[0].strip()
            if len(title) > 16:
                title = title[:14] + ".."
            chapters.append([seconds_to_timestamp(t), title])
            next_at = t + chunk_sec

    # Trim to max
    chapters = chapters[:max_chapters]

    # Ensure first chapter starts at 00:00:00
    if chapters and chapters[0][0] != "00:00:00":
        chapters[0][0] = "00:00:00"

    return chapters


def read_draft_description(slug: str) -> str | None:
    """Try to read description from draft.md."""
    draft = slug_dir(slug) / "_runtime" / "draft.md"
    if not draft.exists():
        return None

    content = draft.read_text(encoding="utf-8")
    # Look for description section
    m = re.search(r"(?:简介|描述|description)[：:]\s*\n?(.+?)(?:\n##|\n#|\Z)", content, re.S)
    if m:
        return m.group(1).strip()
    return None


def build_description(title: str, source: str, baidu_link: str | None = None,
                      custom: str | None = None) -> str:
    if custom:
        desc = custom
    else:
        desc = f"{title}\n\n来源：{source}\n翻译制作：猫波信号站"

    if baidu_link:
        desc += f"\n\n📖 全中文EPUB电子书\n   🔗 {baidu_link}"

    desc += "\n\n#AI编程 #人工智能 #播客翻译 #猫波信号站"
    return desc


def validate_chapters(chapters, max_title_chars=16):
    """B站硬上限: 章节标题 ≤16 字。超长直接报错拦截。"""
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            title = ch.get("title", "")
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            title = ch[1]
        else:
            continue
        n = len(title)
        if n > max_title_chars:
            print(f"ERROR: 章节 {i+1} 标题 {n} 字（上限 {max_title_chars}）: {title[:40]}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Generate metadata.json for B站 upload")
    parser.add_argument("--slug", required=True, help="Video slug")
    parser.add_argument("--title", required=True, help="B站标题 (≤80 chars)")
    parser.add_argument("--source", required=True, help="来源 (e.g. YouTube @LexFridman)")
    parser.add_argument("--tags", required=True, help="Tags, comma-separated (max 10)")
    parser.add_argument("--baidu-link", default=None, help="Baidu Cloud share link")
    parser.add_argument("--description", default=None,
                        help="Custom description (reads draft.md if omitted)")
    parser.add_argument("--chapters", default=None,
                        help="Path to chapters JSON file (auto-generated if omitted)")
    args = parser.parse_args()

    base = slug_dir(args.slug)
    srt = base / "_runtime" / "字幕" / "04_split.srt"

    if not srt.exists():
        print(f"ERROR: SRT not found: {srt}")
        sys.exit(1)

    print(f"Reading: {srt.name}")
    entries = read_srt_lines(srt)
    print(f"  {len(entries)} entries")

    # Chapters
    if args.chapters:
        with open(args.chapters, encoding="utf-8") as f:
            chapters = json.load(f)
    else:
        chapters = auto_chapters(entries)

    validate_chapters(chapters)

    # Description
    draft_desc = read_draft_description(args.slug) if not args.description else None
    description = build_description(
        args.title, args.source, args.baidu_link,
        custom=args.description or draft_desc,
    )

    # Tags
    tags = [t.strip() for t in args.tags.split(",") if t.strip()][:10]

    metadata = {
        "title": args.title,
        "source": args.source,
        "chapters": chapters,
        "tags": tags,
        "description": description,
    }

    out_path = base / "_runtime" / "metadata.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Title:     {metadata['title']} ({len(metadata['title'])} chars)")
    print(f"Tags:      {len(tags)} tags")
    print(f"Chapters:  {len(chapters)} chapters")
    print(f"Desc:      {len(description)} chars")
    print(f"Written:   {out_path}")
    print()
    print(f"Next: python tools/stage_16_cdp_upload.py --slug <slug> --page-id <CDP_PAGE_ID>")


if __name__ == "__main__":
    main()

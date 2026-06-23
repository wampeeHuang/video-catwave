"""Generate EPUB from 03_zh.srt for 微信读书.

Usage:
  python gen_epub.py --slug <slug> --title "<title>" --author "<author>" --source "<YouTube频道>"
  python gen_epub.py --slug <slug> --title "<title>" --author "<author>" --source "<YouTube频道>" --lang zh
"""
import argparse
import re
import sys
from pathlib import Path

from ebooklib import epub

OUTPUT_BASE = Path(r"D:\workspace\_output\猫波信号站\视频")


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = text.strip().split("\n\n")
    entries = []
    for b in blocks:
        lines = b.strip().split("\n")
        if len(lines) < 2:
            continue
        m = re.match(r"(\d+:\d+:\d+[,.]\d+)", lines[1])
        if not m:
            continue
        body = "\n".join(lines[2:])
        parts = body.split("\\N", 1)
        zh = parts[0].strip()
        en = parts[1].strip() if len(parts) > 1 else ""
        entries.append({"start": m.group(1), "zh": zh, "en": en})
    return entries


def time_to_seconds(t: str) -> int:
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + int(float(s))


def build_epub(entries, cover_path, output_path, title, author, source, lang="bilingual", baidu_link=None):
    book = epub.EpubBook()

    slug = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-")[:40])
    book.set_identifier(slug or "epub-001")
    book.set_title(title)
    book.set_language("zh")
    book.add_author(author)
    book.add_metadata("DC", "publisher", "猫波信号站")
    book.add_metadata("DC", "source", f"https://youtube.com/@{source}")

    if cover_path.exists():
        with open(cover_path, "rb") as f:
            book.set_cover("cover.jpg", f.read())
        cover_page = epub.EpubCover(file_name="cover.xhtml")
        cover_page.content = (
            '<div style="text-align:center; padding:20% 0;">'
            '<img src="cover.jpg" alt="cover" style="max-width:100%;"/>'
            "</div>"
        )
        book.add_item(cover_page)

    total_seconds = time_to_seconds(entries[-1]["start"]) if entries else 0
    h, r = divmod(total_seconds, 3600)
    m, s = divmod(r, 60)
    duration = f"{h}小时{m}分" if h else f"{m}分{s}秒"

    css_en = ".en { font-size: 0.85em; color: #666; margin: 0.1em 0 0.6em; }" if lang == "bilingual" else ""
    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=f"""
body {{ font-family: serif; line-height: 1.8; margin: 2em 1em; }}
h1 {{ text-align: center; font-size: 1.4em; margin: 1.5em 0 0.5em; }}
h2 {{ font-size: 1.2em; margin: 1em 0 0.3em; color: #333; }}
.cn {{ font-size: 1em; margin: 0.3em 0; }}
{css_en}
.chapter-time {{ font-size: 0.75em; color: #999; text-align: right; margin: 0 0 0.5em; }}
.title-page {{ text-align: center; padding: 20% 1em; }}
.title-page h1 {{ font-size: 1.8em; }}
.title-page .subtitle {{ font-size: 0.9em; color: #666; margin-top: 1.5em; }}
""",
    )
    book.add_item(style)

    title_page = epub.EpubHtml(title="扉页", file_name="title.xhtml", lang="zh")
    title_page.content = f"""
<div class="title-page">
<h1>{title}</h1>
<p class="subtitle">
来源：YouTube @{source}<br/>
嘉宾：{author}<br/>
<span style="color:#999;">全长 {duration} · {len(entries)} 段对话</span>
</p>
<p class="subtitle" style="margin-top:3em; font-size:0.8em;">
猫波信号站 译制<br/>
猫波雷达滴滴响——又有好信号来了！
</p>"""
    if baidu_link:
        title_page.content += f"""
<p class="subtitle" style="margin-top:1.5em; font-size:0.75em; color:#999;">
📖 更多电子书：{baidu_link}
</p>"""
    title_page.content += """
</div>
"""
    book.add_item(title_page)

    chapters = []
    CHUNK_SECONDS = 300
    chunk = []
    chapter_idx = 0

    def flush_chapter():
        nonlocal chapter_idx, chunk
        if not chunk:
            return
        chapter_idx += 1
        t_start = chunk[0]["start"]
        t_end = chunk[-1]["start"]
        st = time_to_seconds(t_start)
        et = time_to_seconds(t_end)
        ch_title = f"第{chapter_idx}章　{_format_time(st)} – {_format_time(et)}"

        html_parts = [f"<h2>{ch_title}</h2>"]
        for e in chunk:
            html_parts.append(f'<p class="cn">{e["zh"]}</p>')
            if lang == "bilingual" and e["en"]:
                html_parts.append(f'<p class="en">{e["en"]}</p>')
        content = "\n".join(html_parts)

        ch = epub.EpubHtml(title=ch_title, file_name=f"ch{chapter_idx:03d}.xhtml", lang="zh")
        ch.content = content
        book.add_item(ch)
        chapters.append(ch)
        chunk.clear()

    for e in entries:
        t = time_to_seconds(e["start"])
        if chunk and t - time_to_seconds(chunk[0]["start"]) >= CHUNK_SECONDS:
            flush_chapter()
        chunk.append(e)
    flush_chapter()

    spine_items = [title_page] + chapters
    book.toc = [(epub.Section("目录"), [title_page] + chapters)]
    book.spine = ["nav"] + [c.file_name for c in spine_items]
    book.add_item(epub.EpubNav())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)
    return len(chapters)


def _format_time(s: int) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def main():
    parser = argparse.ArgumentParser(description="Generate EPUB from bilingual SRT")
    parser.add_argument("--slug", required=True, help="Video slug (e.g. 20260620_cursor-team-lex-fridman)")
    parser.add_argument("--title", required=True, help="Book title on title page")
    parser.add_argument("--author", required=True, help="Guest name(s)")
    parser.add_argument("--source", required=True, help="YouTube channel name (e.g. lexfridman)")
    parser.add_argument("--lang", choices=["bilingual", "zh"], default="bilingual",
                        help="Language mode: bilingual (default) or zh (Chinese only)")
    parser.add_argument("--baidu-link", default=None,
                        help="Baidu Cloud share link for EPUB colophon")
    args = parser.parse_args()

    base = OUTPUT_BASE / args.slug
    srt = base / "_runtime/字幕/03_zh.srt"
    cover = base / "cover.jpg"
    safe_title = args.title.replace("：", "-").replace(":", "-")
    out = base / "电子书" / f"{safe_title}.epub"

    if not srt.exists():
        print(f"ERROR: SRT not found: {srt}")
        sys.exit(1)

    print(f"Reading: {srt.name}")
    entries = parse_srt(srt)
    print(f"  {len(entries)} entries")

    print(f"Cover: {'OK' if cover.exists() else 'NOT FOUND'}")
    print(f"Building EPUB ({args.lang})...")
    n_ch = build_epub(entries, cover, out, args.title, args.author, args.source, args.lang, args.baidu_link)

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"  -> {out.name} ({size_mb:.1f} MB, {n_ch} chapters)")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()

"""Generate bilingual EPUB from 03_zh.srt for 微信读书."""
import re
import sys
from pathlib import Path

from ebooklib import epub


def parse_srt(path: Path) -> list[dict]:
    """Parse bilingual SRT into list of {start, zh, en}."""
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


def build_epub(entries: list[dict], cover_path: Path, output_path: Path):
    book = epub.EpubBook()

    # Metadata
    book.set_identifier("cursor-team-lex-fridman-2026")
    book.set_title("Cursor创始团队：AI编程的快就是乐趣")
    book.set_language("zh")
    book.add_author("Cursor Team (Michael Truell, Sualp Oif, Arvid Lunark, Aman Sanger)")
    book.add_author("Lex Fridman (Host)")
    book.add_metadata("DC", "publisher", "猫波信号站")
    book.add_metadata("DC", "source", "https://youtube.com/@lexfridman")

    # Cover
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

    # CSS
    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content="""
body { font-family: serif; line-height: 1.8; margin: 2em 1em; }
h1 { text-align: center; font-size: 1.4em; margin: 1.5em 0 0.5em; }
h2 { font-size: 1.2em; margin: 1em 0 0.3em; color: #333; }
.cn { font-size: 1em; margin: 0.3em 0; }
.en { font-size: 0.85em; color: #666; margin: 0.1em 0 0.6em; }
.chapter-time { font-size: 0.75em; color: #999; text-align: right; margin: 0 0 0.5em; }
.title-page { text-align: center; padding: 20% 1em; }
.title-page h1 { font-size: 1.8em; }
.title-page .subtitle { font-size: 0.9em; color: #666; margin-top: 1.5em; }
""",
    )
    book.add_item(style)

    # Title page
    title_page = epub.EpubHtml(
        title="扉页", file_name="title.xhtml", lang="zh"
    )
    title_page.content = f"""
<div class="title-page">
<h1>Cursor创始团队：<br/>AI编程的快就是乐趣</h1>
<p class="subtitle">
Lex Fridman Podcast #447<br/>
对话 Michael Truell · Sualp Oif<br/>
Arvid Lunark · Aman Sanger<br/>
<span style="color:#999;">全长 2小时29分 · {len(entries)} 段双语对话</span>
</p>
<p class="subtitle" style="margin-top:3em; font-size:0.8em;">
猫波信号站 译制<br/>
猫波雷达滴滴响——又有好信号来了！
</p>
</div>
"""
    book.add_item(title_page)

    # Chapters: ~5 minutes each
    chapters = []
    CHUNK_SECONDS = 300  # 5 min
    chunk = []
    chapter_idx = 0
    chunk_start = entries[0]["start"] if entries else "00:00:00"

    def flush_chapter():
        nonlocal chapter_idx, chunk_start, chunk
        if not chunk:
            return
        chapter_idx += 1
        t_start = chunk[0]["start"]
        t_end = chunk[-1]["start"]
        st = time_to_seconds(t_start)
        et = time_to_seconds(t_end)
        title = f"第{chapter_idx}章　{_format_time(st)} – {_format_time(et)}"

        html_parts = [f"<h2>{title}</h2>"]
        for e in chunk:
            html_parts.append(f'<p class="cn">{e["zh"]}</p>')
            if e["en"]:
                html_parts.append(f'<p class="en">{e["en"]}</p>')
        content = "\n".join(html_parts)

        ch = epub.EpubHtml(
            title=title,
            file_name=f"ch{chapter_idx:03d}.xhtml",
            lang="zh",
        )
        ch.content = content
        book.add_item(ch)
        chapters.append(ch)
        chunk = []
        chunk_start = ""

    for e in entries:
        t = time_to_seconds(e["start"])
        if chunk and t - time_to_seconds(chunk[0]["start"]) >= CHUNK_SECONDS:
            flush_chapter()
        if not chunk:
            chunk_start = e["start"]
        chunk.append(e)
    flush_chapter()

    # Spine
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
    base = Path(r"D:\workspace\_output\猫波信号站\视频\20260620_cursor-team-lex-fridman")
    srt = base / "_runtime/字幕/03_zh.srt"
    cover = base / "cover.jpg"
    out = base / "电子书/Cursor创始团队：AI编程的快就是乐趣.epub"

    print(f"Reading: {srt.name}")
    entries = parse_srt(srt)
    print(f"  {len(entries)} entries")

    print(f"Cover: {'OK' if cover.exists() else 'NOT FOUND'}")
    print(f"Building EPUB...")
    n_ch = build_epub(entries, cover, out)

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"  → {out.name} ({size_mb:.1f} MB, {n_ch} chapters)")
    print(f"  → {out}")


if __name__ == "__main__":
    main()

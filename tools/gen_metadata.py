"""Generate metadata.json for B站 upload (stage_16_cdp_upload.py input).

Usage:
  python gen_metadata.py --slug <slug> --title "<title>" --source "<source>" \
      --tags "tag1,tag2,..." [--baidu-link "<url>"] [--ai-chapters]

Chapter timestamps are auto-generated from SRT. Use --ai-chapters for
LLM-curated chapter titles (reads transcript, makes proper summaries).
Description is read from _runtime/draft.md or --description flag.
Output: <output>/_runtime/metadata.json
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir
from pipeline_manifest import duration_profile


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
    """Evenly-spaced chapters from SRT — fallback only, quality is poor (raw transcript snippets)."""
    if not entries:
        return []

    total_sec = time_to_seconds(entries[-1]["end"])
    profile = duration_profile(total_sec)
    chunk_sec = profile["auto_chunk_sec"]

    chapters = []
    next_at = 0
    for e in entries:
        t = time_to_seconds(e["start"])
        if t >= next_at or len(chapters) == 0:
            title = e["text"]
            if "\\N" in title:
                title = title.split("\\N")[0].strip()
            title = title.rstrip("。，！？、：；….,!?;:，．")
            if len(title) > 16:
                title = title[:14] + ".."
            chapters.append([seconds_to_timestamp(t), title])
            next_at = t + chunk_sec

    chapters = chapters[:max_chapters]
    if chapters and chapters[0][0] != "00:00:00":
        chapters[0][0] = "00:00:00"

    return chapters


def _build_timestamped_transcript(entries: list[dict], max_lines: int = 280) -> str:
    """Build timestamped transcript from SRT entries for claude to locate chapters.

    Each line: [HH:MM:SS] text. Sampled evenly to stay under max_lines.
    """
    step = max(1, len(entries) // max_lines)
    lines = []
    for i, e in enumerate(entries):
        if i % step == 0:
            ts = e["start"].split(",")[0]  # strip milliseconds
            lines.append(f"[{ts}] {e['text']}")
    return "\n".join(lines)


def ai_chapters(entries: list[dict], transcript_path: Path, max_chapters: int = 10) -> list[list[str]]:
    """Use claude to find key arguments in transcript, refine into chapter titles.

    Sends timestamped SRT transcript so claude can produce accurate HH:MM:SS timestamps.
    Fails hard on error — no silent fallback to auto_chapters.
    """
    if not transcript_path.exists():
        print("ERROR: transcript.txt not found, cannot generate AI chapters")
        sys.exit(1)

    ts_transcript = _build_timestamped_transcript(entries)

    # Adaptive chapter count based on video duration
    total_sec = time_to_seconds(entries[-1]["end"]) if entries else 3600
    profile = duration_profile(total_sec)
    min_ch = profile["min_chapters"]
    max_ch = profile["max_chapters"]

    prompt = f"""你是B站视频章节编辑。扫描以下播客/访谈文稿，找出{min_ch}-{max_ch}个最重要的**话题转折点**或**核心论点/金句出现的位置**。

步骤：
1. 通读文稿，标记出对话中话题发生明显转换的位置，或嘉宾抛出重要论点/金句的时刻
2. 对每个位置，用 ≤16 个中文字提炼成章节标题
3. 每行开头的 [HH:MM:SS] 是该行在视频中的时间位置，用来确定章节对应的时间戳

要求：
- 标题是**精炼后的论点概括**，不是原文照抄。例如原文说"我觉得AI会在2030年左右达到人类水平"，标题应为"AGI将在2030年前后到来"
- 标题 ≤16 个中文字，末尾不加标点符号
- 章节覆盖视频全程，大致均匀分布（相邻章节间隔不少于总时长的1/12）
- 首章必须是 00:00:00，标题为"开场与嘉宾介绍"或更具体的开场主题概括
- 禁止标题中出现口语填充词（"就是说""那个""然后""反正"）
- 禁止以"我""我们""你""你们"开头
- **时间戳必须从文稿中实际出现的 [HH:MM:SS] 中选取，不要编造**

文稿（每行格式：[HH:MM:SS] 字幕文本）：
{ts_transcript}

输出格式 — 只输出一个 JSON 数组，每项是 [时间戳, 标题]：
[["00:00:00", "开场与嘉宾介绍"], ["00:05:30", "AGI时间线辩论"], ...]

JSON:"""

    try:
        claude_bin = Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"
        if not claude_bin.exists():
            claude_bin = "claude"
        result = subprocess.run(
            [str(claude_bin), "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True, timeout=600,
            encoding="utf-8", errors="replace",
            cwd=str(Path(__file__).parent.parent),
        )
        if result.returncode != 0:
            print(f"ERROR: claude exit={result.returncode}")
            stderr = result.stderr or ""
            if stderr:
                print(f"  stderr: {stderr[:300]}")
            sys.exit(1)

        import re as _re
        clean = _re.sub(r'```[a-z]*\s*', '', result.stdout)
        json_match = _re.search(r'\[\s*\[[\s\S]+?\]\s*\]', clean)
        if not json_match:
            print(f"ERROR: no JSON array found in claude response")
            print(f"  stdout({len(result.stdout)}): {result.stdout[:400]}...")
            sys.exit(1)

        chapters = json.loads(json_match.group())
        valid = []
        for ch in chapters:
            if isinstance(ch, list) and len(ch) == 2:
                title = str(ch[1]).rstrip("。，！？、：；….,!?;:，． ")
                if 1 <= len(title) <= 16:
                    valid.append([str(ch[0]), title])

        if len(valid) < min_ch:
            print(f"ERROR: only {len(valid)} valid chapters (need ≥{min_ch})")
            sys.exit(1)

        # Force first chapter to 00:00:00
        if valid and valid[0][0] != "00:00:00":
            valid[0][0] = "00:00:00"

        print(f"  [ai_chapters] {len(valid)} curated chapters from transcript analysis")
        return valid[:max_chapters]

    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parse failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: ai_chapters failed: {e}")
        sys.exit(1)


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


def ai_summary(entries: list[dict], transcript_path: Path, slug: str, title: str,
               source: str, guest_identity: str = "") -> str | None:
    """Use claude to generate a B站 description summary from transcript.

    Returns the full description text (title + summary + source + EPUB + hashtags),
    or None on failure.
    """
    if not transcript_path.exists():
        print("  [ai_summary] transcript not found, skipping")
        return None

    ts_transcript = _build_timestamped_transcript(entries, max_lines=200)

    prompt = f"""你是B站视频简介编辑。为下面的播客/访谈视频写一段简介正文。

要求：
- 2-3个自然段，总计150-350字
- 第1段：本期嘉宾身份 + 核心话题概述（1-2句话点明主题）
- 第2段：2-4个具体讨论亮点/金句/数据点（不要编号列表，自然段落）
- 第3段（可选）：适合谁看/为什么值得看
- 语气：客观、有信息密度、不夸张不标题党
- 禁止使用"本期视频""本视频""这期节目"等元描述
- 禁止使用"深入探讨""精彩对话""干货满满"等空洞形容词
- 保留原文中的产品/工具名称（如 Codex、Claude），不要自行替换或联想
- 直接用内容说话

视频标题：{title}
来源频道：{source}

文稿（每行格式：[HH:MM:SS] 字幕文本）：
{ts_transcript}

只输出简介正文（2-3段），不要标题，不要时间戳："""

    try:
        claude_bin = Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"
        if not claude_bin.exists():
            claude_bin = "claude"
        result = subprocess.run(
            [str(claude_bin), "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True, timeout=600,
            encoding="utf-8", errors="replace",
            cwd=str(Path(__file__).parent.parent),
        )
        if result.returncode != 0:
            print(f"  [ai_summary] claude exit={result.returncode}")
            stderr = result.stderr or ""
            if stderr:
                print(f"    stderr: {stderr[:200]}")
            return None

        body = result.stdout.strip()
        # Strip markdown block markers
        body = re.sub(r'```[a-z]*\s*', '', body).strip()
        if len(body) < 60:
            print(f"  [ai_summary] output too short ({len(body)} chars), discarding")
            return None

        print(f"  [ai_summary] generated {len(body)}-char summary")
        return body

    except Exception as e:
        print(f"  [ai_summary] failed: {e}")
        return None


def build_description(title: str, source: str, baidu_link: str | None = None,
                      custom: str | None = None, summary: str | None = None) -> str:
    if custom:
        desc = custom
    else:
        desc = title
        if summary:
            desc += "\n\n" + summary
        desc += f"\n\n来源：{source}\n翻译制作：猫波信号站"

    if baidu_link:
        desc += f"\n\n📖 全中文EPUB电子书\n   🔗 {baidu_link}"

    desc += "\n\n#AI编程 #人工智能 #播客翻译 #猫波信号站"
    return desc


def validate_chapters(chapters, max_title_chars=16, transcript_path=None, video_duration_sec=None,
                      strict=True):
    """Validate chapter quality: structure, originality, coverage, spacing.

    Hard gate — any failure = sys.exit(1), pipeline blocked.

    strict=False (auto_chapters from raw transcript) relaxes title quality checks:
    first-person, filler words, verbatim copy — all expected from raw snippets.
    """
    errors = []

    # Adaptive minimum — short videos don't need 10 chapters
    dur = video_duration_sec or 3600
    profile = duration_profile(dur)
    min_for_dur = profile["min_chapters"]
    max_ch = profile["max_chapters"]
    if len(chapters) < min_for_dur:
        errors.append(
            f"章节数 {len(chapters)} < {min_for_dur}（{dur//60}分钟视频需要 ≥{min_for_dur}章）"
        )
    if len(chapters) > max_ch:
        errors.append(f"章节数 {len(chapters)} > {max_ch}，超标")

    if chapters and chapters[0][0] != "00:00:00":
        errors.append(f"首章时间戳不是 00:00:00: {chapters[0][0]}")

    transcript_text = ""
    if transcript_path and transcript_path.exists():
        transcript_text = transcript_path.read_text(encoding="utf-8")

    filler_words = ["就是说", "那个", "然后", "反正", "其实", "所以", "而且", "但是"]
    bad_endings = ["的", "了", "呢", "吧", "吗", "啊", "嘛"]
    seen_titles = set()

    prev_ts = -1
    for i, ch in enumerate(chapters):
        if isinstance(ch, dict):
            title = ch.get("title", "")
            ts = ch.get("timestamp", "00:00:00")
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            ts, title = ch[0], ch[1]
        else:
            continue

        n = len(title)
        if n > max_title_chars:
            errors.append(f"第{i+1}章 标题{n}字（上限{max_title_chars}）: {title[:40]}")
        if n < 2:
            errors.append(f"第{i+1}章 标题过短（{n}字）: {title}")

        # Duplicate check
        if title in seen_titles:
            errors.append(f"第{i+1}章 标题重复: {title}")
        seen_titles.add(title)

        # Verbatim, filler, pronoun checks — only for AI/human-curated titles
        if strict:
            if transcript_text and len(title) >= 6 and title in transcript_text:
                errors.append(f"第{i+1}章 标题原文照抄: {title}")

            for fw in filler_words:
                if fw in title:
                    errors.append(f"第{i+1}章 含口语填充词'{fw}': {title}")
                    break

            if title[0] in ("我", "你"):
                errors.append(f"第{i+1}章 以'{title[0]}'开头: {title}")

            if title[-1] in bad_endings:
                errors.append(f"第{i+1}章 以'{title[-1]}'结尾: {title}")

        # Timestamp
        ts_sec = time_to_seconds(ts + ",000")
        if ts_sec < prev_ts:
            errors.append(f"第{i+1}章 时间戳倒退: {ts} < 前一章")
        min_gap = profile["min_chapter_gap_sec"]
        if i > 0 and ts_sec - prev_ts < min_gap:
            errors.append(f"第{i+1}章 与前一章间隔 <{min_gap}s ({ts_sec - prev_ts}s)")
        prev_ts = ts_sec

    # Coverage: last chapter must be within last 25% of video
    if chapters and video_duration_sec and video_duration_sec > 60:
        last_ts = time_to_seconds(chapters[-1][0] + ",000")
        if last_ts < video_duration_sec * 0.75:
            pct = last_ts / video_duration_sec * 100
            errors.append(f"末章仅覆盖到 {pct:.0f}%，未覆盖视频后半段")

    if errors:
        print(f"\n章节验证失败 ({len(errors)} 项):")
        for e in errors:
            print(f"  - {e}")
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
    parser.add_argument("--ai-chapters", action="store_true",
                        help="Use claude to curate chapter titles from transcript")
    parser.add_argument("--summary", default=None,
                        help="Content summary for description (2-3 paragraphs)")
    parser.add_argument("--ai-summary", action="store_true",
                        help="Use claude to generate description summary from transcript")
    parser.add_argument("--author", default=None, help="Video author/guest name")
    parser.add_argument("--publish-date", default=None, help="Original publish date YYYY-MM-DD")
    parser.add_argument("--source-url", default=None, help="Original video URL (for 转载声明)")
    args = parser.parse_args()

    base = slug_dir(args.slug)
    srt = base / "_runtime" / "字幕" / "04_split.srt"

    if not srt.exists():
        print(f"ERROR: SRT not found: {srt}")
        sys.exit(1)

    print(f"Reading: {srt.name}")
    entries = read_srt_lines(srt)
    print(f"  {len(entries)} entries")

    transcript_path = base / "_runtime" / "字幕" / "transcript.txt"

    # Chapters — short videos skip AI chapters, use auto_chapters
    video_duration = time_to_seconds(entries[-1]["end"]) if entries else None
    profile = duration_profile(video_duration or 3600)
    strict_validation = True
    if args.chapters:
        with open(args.chapters, encoding="utf-8") as f:
            chapters = json.load(f)
    elif args.ai_chapters and video_duration and video_duration >= profile["min_duration_for_ai"]:
        chapters = ai_chapters(entries, transcript_path)
    elif args.ai_chapters:
        print(f"  Video too short ({video_duration}s), using auto_chapters instead of AI")
        chapters = auto_chapters(entries)
        strict_validation = False
    else:
        chapters = auto_chapters(entries)
        strict_validation = False

    validate_chapters(chapters, transcript_path=transcript_path, video_duration_sec=video_duration,
                      strict=strict_validation)

    # Description
    draft_desc = read_draft_description(args.slug) if not args.description else None
    summary = args.summary
    if not summary and args.ai_summary and transcript_path.exists():
        summary = ai_summary(entries, transcript_path, args.slug, args.title, args.source)
    description = build_description(
        args.title, args.source, args.baidu_link,
        custom=args.description or draft_desc,
        summary=summary,
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
    if args.author:
        metadata["author"] = args.author
    if args.publish_date:
        metadata["publish_date"] = args.publish_date
    if args.source_url:
        metadata["source_url"] = args.source_url

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

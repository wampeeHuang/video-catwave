#!/usr/bin/env python3
"""Curation validator — checks curation JSON against all hard constraints from curation-prompt.txt.

Usage:
  python tools/validate_curation.py <curation.json> [--check-sources] [--skip-feishu]

Exit 0 = all candidates pass all constraints.
Exit 1 = one or more violations.

Gatekeeper for Stage A output. Run before orchestrator consumes the curation file.
AI curator should loop on failures until clean — this IS the success criterion.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cover_design import MAX_COVER_CHARS

# ── Constants (mirrored from curation-prompt.txt) ──────────────────────────
MAX_CANDIDATES = 5
MAX_TITLE_CHARS = 80
MIN_SUMMARY_CHARS = 100
MAX_SUMMARY_CHARS = 200
MIN_TOTAL_SCORE = 2.0
MIN_DIMENSION_SCORE = 1.5
MIN_LIKES_VIEWS_RATIO = 0.01
MIN_VPD = 500
MIN_DURATION_SEC = 600  # 10 minutes
VALID_DOMAINS = {"youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com"}

# Patterns that indicate non-guest values in the guest field
NON_GUEST_PATTERNS = [
    re.compile(r"^AI:?\s*Ep\.?\s*\d+", re.I),
    re.compile(r"^Ep\.?\s*\d+", re.I),
    re.compile(r"^第\d+期"),
    re.compile(r"^#\d+"),
]

# Patterns for Shorts/clip/trailer detection in title/slug (rule 3.5)
EXCLUSION_PATTERNS = [
    (re.compile(r"#shorts?", re.I), "#Shorts"),
    (re.compile(r"\bshort\b", re.I), "short"),
    (re.compile(r"\bclip\b", re.I), "clip"),
    (re.compile(r"\bhighlight\b", re.I), "highlight"),
    (re.compile(r"\btrailer\b", re.I), "trailer"),
    (re.compile(r"预告片"), "预告片"),
]


def _has_cjk(text: str) -> bool:
    return bool(re.search(r'[一-鿿㐀-䶿豈-﫿]', text))


def _count_cjk(text: str) -> int:
    return len(re.findall(r'[一-鿿㐀-䶿豈-﫿]', text))


def _parse_domain(url: str) -> str | None:
    m = re.search(r'https?://([^/]+)', url)
    return m.group(1).lower() if m else None


def _is_youtube(url: str) -> bool:
    domain = _parse_domain(url)
    return domain in VALID_DOMAINS if domain else False


def _is_playlist(url: str) -> bool:
    return "&list=" in url or "playlist" in url.lower()


def _check_guest(guest) -> tuple[bool, str]:
    """Validate guest field per rule 5.8."""
    if not guest:
        return False, "嘉宾字段为空"
    if isinstance(guest, list):
        names = [str(g).strip() for g in guest if str(g).strip()]
        if not names:
            return False, "嘉宾列表为空"
        for g in names:
            if g.upper() == "TBD":
                return False, "嘉宾含TBD占位符——人物权威不得高于2分"
            for pat in NON_GUEST_PATTERNS:
                if pat.search(g):
                    return False, f"嘉宾疑似节目名/期号: '{g}'"
        return True, ""
    g = str(guest).strip()
    if not g:
        return False, "嘉宾字段为空"
    if g.upper() == "TBD":
        return False, "嘉宾为TBD——人物权威不得高于2分"
    for pat in NON_GUEST_PATTERNS:
        if pat.search(g):
            return False, f"嘉宾疑似节目名/期号: '{g}'"
    return True, ""


def _calc_vpd(views: int, date_str: str) -> float | None:
    """views / days^0.5 — rule 5.6 formula."""
    if not date_str or not views:
        return None
    try:
        pub = datetime.strptime(date_str, "%Y-%m-%d")
        days = max((datetime.now() - pub).days, 1)
        return views / (days ** 0.5)
    except (ValueError, TypeError):
        return None


def _load_sources() -> set[str]:
    """Load known channel names from 内容源.md."""
    sf = Path(r"D:\workspace\_output\猫波信号站\选题库\内容源.md")
    if not sf.exists():
        return set()
    text = sf.read_text(encoding="utf-8")
    names = set()
    for line in text.splitlines():
        m = re.search(r'\*\*(.+?)\*\*', line)
        if m:
            names.add(m.group(1).strip())
    return names


def _extract_url(value) -> str:
    """Normalize Feishu URL field — handles markdown links, lists, plain strings."""
    s = str(value)
    if "](" in s:
        m = re.search(r"\]\(([^)]+)\)", s)
        if m:
            s = m.group(1)
    return s.strip()


def _fetch_feishu_urls() -> set[str] | None:
    """Fetch all existing YouTube URLs from Feishu. Returns None on API failure."""
    try:
        from _feishu import fetch_records
        records = fetch_records()
        urls = set()
        for r in records:
            url_raw = r.get("fields", {}).get("URL", "")
            url_val = str(url_raw)
            if isinstance(url_raw, list):
                url_val = str(url_raw[0]) if url_raw else ""
            url_clean = _extract_url(url_val)
            if url_clean and ("youtube.com" in url_clean or "youtu.be" in url_clean):
                urls.add(url_clean)
        return urls
    except Exception as e:
        print(f"  [validate_curation] Feishu fetch failed: {e}")
        return None


def _format_duration(sec: int) -> str:
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def validate_curation(filepath: Path, check_sources: bool = False,
                      check_feishu: bool = True) -> tuple[bool, list[str]]:
    results: list[str] = []
    all_ok = True

    # ── File ──
    if not filepath.exists():
        return False, [f"[FAIL] 文件不存在: {filepath}"]
    if filepath.stat().st_size == 0:
        return False, [f"[FAIL] 空文件: {filepath}"]

    try:
        data = json.loads(filepath.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        return False, [f"[FAIL] JSON 解析失败: {e}"]

    results.append(f"[OK] 文件加载 ({filepath.stat().st_size / 1024:.0f} KB)")

    if "candidates" not in data:
        return False, results + ["[FAIL] 缺少 candidates 字段"]

    candidates = data["candidates"]
    if not isinstance(candidates, list):
        return False, results + [f"[FAIL] candidates 应为数组，实际 {type(candidates).__name__}"]

    results.append(f"[OK] candidates: {len(candidates)} 条")

    # ── Rule 9: count cap ──
    if len(candidates) > MAX_CANDIDATES:
        results.append(f"[FAIL] 候选数 {len(candidates)} > {MAX_CANDIDATES}（规则9）")
        all_ok = False

    # ── Rule 6: Feishu dedup (pre-fetch all URLs once) ──
    feishu_urls = None
    if check_feishu:
        results.append(f"\n── 飞书去重 ──")
        feishu_urls = _fetch_feishu_urls()
        if feishu_urls is None:
            results.append(f"[WARN] 飞书API调用失败，跳过去重检查")
        else:
            results.append(f"[OK] 飞书现有 {len(feishu_urls)} 条YouTube记录")

    known_sources = _load_sources() if check_sources else set()

    for i, c in enumerate(candidates):
        slug = c.get("slug", "NO-SLUG")
        label = f"#{i+1} {slug}"
        results.append(f"\n── {label} ──")

        # ── Rule 12: required fields ──
        required = {
            "slug": "Slug",
            "guest": "嘉宾",
            "title": "标题",
            "url": "URL",
            "total_score": "总分",
            "date": "日期",
            "summary": "摘要",
            "cover_title": "封面标题",
        }
        all_fields_present = True
        for field, label_cn in required.items():
            val = c.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                results.append(f"[FAIL] 缺少必填字段: {field} ({label_cn})（规则12）")
                all_ok = False
                all_fields_present = False
        if all_fields_present:
            results.append(f"[OK] 8个必填字段完整")

        # Also check duration (transitional — WARN only for now)
        duration = c.get("duration")
        if duration is None:
            results.append(f"[WARN] 缺少 duration 字段（建议补充，后续版本将升级为FAIL）")
        elif isinstance(duration, (int, float)) and duration > 0:
            if duration < MIN_DURATION_SEC:
                results.append(f"[FAIL] 时长 {_format_duration(int(duration))} < {_format_duration(MIN_DURATION_SEC)}（规则3.5）")
                all_ok = False
            else:
                results.append(f"[OK] 时长 {_format_duration(int(duration))} (≥{_format_duration(MIN_DURATION_SEC)})")

        # Skip deeper checks if critical fields missing
        if not c.get("url") or not c.get("title"):
            continue

        # ── Rule 6: Feishu URL dedup ──
        url = c["url"]
        if feishu_urls is not None and url in feishu_urls:
            results.append(f"[FAIL] URL 已存在于飞书选题库 — 重复录入（规则6）")
            all_ok = False
        elif feishu_urls is not None:
            results.append(f"[OK] 飞书去重通过")

        # ── Rule 5: YouTube domain only ──
        if not _is_youtube(url):
            results.append(f"[FAIL] 非YouTube源: {url}（规则5）")
            all_ok = False
        else:
            if feishu_urls is None:
                results.append(f"[OK] 域名 youtube.com")

        if _is_playlist(url):
            results.append(f"[FAIL] URL 为播放列表（规则5）")
            all_ok = False

        # ── Rule 7: title in Chinese, ≤80 chars ──
        title = c["title"]
        if not _has_cjk(title):
            results.append(f"[FAIL] 标题无中文: {title[:60]}（规则7）")
            all_ok = False
        if len(title) > MAX_TITLE_CHARS:
            results.append(f"[FAIL] 标题 {len(title)}字 > {MAX_TITLE_CHARS}（规则7）")
            all_ok = False
        else:
            results.append(f"[OK] 标题 {len(title)}字 (≤{MAX_TITLE_CHARS})")

        # ── Rule 3.5: Shorts/clip/trailer exclusion ──
        for pat, pat_label in EXCLUSION_PATTERNS:
            if pat.search(title) or pat.search(slug):
                results.append(f"[FAIL] 命中排除模式 '{pat_label}'（规则3.5：Shorts/clip/trailer禁止）")
                all_ok = False
                break

        # ── Rule 7.5: cover_title ──
        ct = c.get("cover_title", "")
        if ct:
            ct_cjk = _count_cjk(ct)
            if ct_cjk > MAX_COVER_CHARS:
                results.append(f"[WARN] 封面标题 {ct_cjk}中文字 > {MAX_COVER_CHARS}（规则7.5，MAX_COVER_CHARS={MAX_COVER_CHARS}）")
            else:
                results.append(f"[OK] 封面标题 {ct_cjk}中文字: {ct}")

        # ── Rule 8: summary 100-200 chars ──
        summary = c.get("summary", "")
        slen = len(summary)
        if slen < MIN_SUMMARY_CHARS:
            results.append(f"[FAIL] 摘要 {slen}字 < {MIN_SUMMARY_CHARS}（规则8）")
            all_ok = False
        elif slen > MAX_SUMMARY_CHARS:
            results.append(f"[FAIL] 摘要 {slen}字 > {MAX_SUMMARY_CHARS}（规则8）")
            all_ok = False
        else:
            results.append(f"[OK] 摘要 {slen}字")

        # ── Rule 5.8: guest ──
        g_ok, g_reason = _check_guest(c.get("guest"))
        if not g_ok:
            results.append(f"[FAIL] {g_reason}（规则5.8）")
            all_ok = False
        else:
            results.append(f"[OK] 嘉宾: {c.get('guest')}")

        # ── Rule 5.7: source channel ──
        channel = c.get("source_channel", "")
        if not channel or not channel.strip():
            results.append(f"[FAIL] 来源频道名为空（规则5.7）")
            all_ok = False
        elif channel.strip().lower() == "youtube search":
            results.append(f"[FAIL] 来源频道名='YouTube Search'（规则5.7禁止）")
            all_ok = False
        elif check_sources and known_sources and channel not in known_sources:
            results.append(f"[WARN] '{channel}' 不在35个已知源 — 应有 '⚠非固定源' 标注")
        else:
            results.append(f"[OK] 来源频道: {channel}")

        # ── Rule 5.5: likes/views ratio ──
        views = c.get("views", 0) or 0
        likes = c.get("likes", 0) or 0
        if views > 0:
            lv = likes / views
            if lv < MIN_LIKES_VIEWS_RATIO:
                results.append(f"[FAIL] 点赞/播放 {lv:.2%} < {MIN_LIKES_VIEWS_RATIO:.0%}（规则5.5）")
                all_ok = False
            else:
                results.append(f"[OK] 点赞/播放 {lv:.2%} (≥{MIN_LIKES_VIEWS_RATIO:.0%})")
        else:
            results.append(f"[WARN] views=0，跳过点赞比校验")

        # ── Rule 5.6: VPD gate ──
        date_str = c.get("date", "")
        vpd = c.get("vpd")
        if vpd is None and views and date_str:
            vpd = _calc_vpd(views, date_str)
        if vpd is not None:
            if vpd < MIN_VPD:
                results.append(f"[FAIL] 加权播放/天 {vpd:.0f} < {MIN_VPD}（规则5.6）")
                all_ok = False
            else:
                results.append(f"[OK] 加权播放/天 {vpd:.0f} (≥{MIN_VPD})")
        else:
            results.append(f"[WARN] 无views/date，无法校验VPD")

        # ── Scoring formula + quality thresholds (rule 10) ──
        total = c.get("total_score", 0) or 0
        dims = {
            "timeliness": c.get("timeliness", 0) or 0,
            "exclusivity": c.get("exclusivity", 0) or 0,
            "authority": c.get("authority", 0) or 0,
            "longevity": c.get("longevity", 0) or 0,
        }

        expected = dims["timeliness"] * 0.3 + dims["exclusivity"] * 0.3 + \
                   dims["authority"] * 0.2 + dims["longevity"] * 0.2
        if abs(total - expected) > 0.11:
            results.append(f"[FAIL] 总分 {total} ≠ 公式计算 {expected:.1f} "
                           f"(时效{dims['timeliness']}×0.3+独占{dims['exclusivity']}×0.3"
                           f"+权威{dims['authority']}×0.2+长期{dims['longevity']}×0.2)")
            all_ok = False
        else:
            results.append(f"[OK] 总分 {total} = 公式验证通过")

        if total < MIN_TOTAL_SCORE:
            results.append(f"[FAIL] 总分 {total} < {MIN_TOTAL_SCORE}（规则10）")
            all_ok = False

        dim_labels = {"timeliness": "时效性", "exclusivity": "独占性",
                      "authority": "人物权威", "longevity": "长期价值"}
        max_dim_val = max(dims.values())
        max_dim_name = dim_labels[max(dims, key=dims.get)]
        if max_dim_val < MIN_DIMENSION_SCORE:
            results.append(f"[FAIL] 最高维度 {max_dim_name}={max_dim_val} < {MIN_DIMENSION_SCORE}（规则10）")
            all_ok = False
        else:
            results.append(f"[OK] 最高维度 {max_dim_name}={max_dim_val} (≥{MIN_DIMENSION_SCORE})")

        for key, val in dims.items():
            if val < 1 or val > 3:
                results.append(f"[WARN] {dim_labels[key]}={val} 超出1-3范围")

        # ── Status ──
        status = c.get("status", "")
        if status and status != "候选":
            results.append(f"[WARN] status='{status}' 非'候选'，orchestrator 会跳过")

        # ── Authority vs TBD rule ──
        guest_raw = c.get("guest", "")
        guest_str = ", ".join(guest_raw) if isinstance(guest_raw, list) else str(guest_raw)
        if "TBD" in guest_str.upper() and dims["authority"] > 2:
            results.append(f"[FAIL] 嘉宾含TBD但人物权威={dims['authority']}>{2}（规则5.8）")
            all_ok = False

    # ── Final tally ──
    results.append(f"\n{'='*40}")
    fail_count = sum(1 for r in results if r.startswith("[FAIL]"))
    warn_count = sum(1 for r in results if r.startswith("[WARN]"))
    if all_ok:
        results.append(f"PASS — {len(candidates)} candidates ready for orchestrator"
                       + (f" ({warn_count} warning(s))" if warn_count else ""))
    else:
        results.append(f"FAIL — {fail_count} violation(s), {warn_count} warning(s)")

    return all_ok, results


def main():
    p = argparse.ArgumentParser(description="Validate curation JSON against all hard constraints")
    p.add_argument("file", help="Path to curation JSON (e.g. _curation/2026-07-28.json)")
    p.add_argument("--check-sources", action="store_true",
                   help="Verify source_channel against 35 known sources")
    p.add_argument("--skip-feishu", action="store_true",
                   help="Skip Feishu URL dedup check (faster, offline)")
    args = p.parse_args()

    ok, results = validate_curation(
        Path(args.file),
        check_sources=args.check_sources,
        check_feishu=not args.skip_feishu,
    )
    for r in results:
        print(r)
    print(f"\n{'CURATION OK' if ok else 'CURATION NEEDS FIX'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

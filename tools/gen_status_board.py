"""Generate 状态面板.html — cross-reference Feishu status with local video dirs.

User workflow:
  1. Publish to B站 → update Feishu status (dropdown, one click)
  2. Panel auto-refreshes hourly via cron; or run this script manually
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _feishu import APP_TOKEN, TABLE_ID, fetch_records, upsert_record

BASE = r"D:\workspace\_output\猫波信号站\视频"
CURATION_DIR = os.path.join(BASE, "_curation")
OUT = os.path.join(BASE, "状态面板.html")


def _fmt_date(val):
    """Extract YYYY-MM-DD from Feishu date field (string 'YYYY-MM-DD HH:MM:SS' or ms timestamp)."""
    if not val:
        return "-"
    s = str(val).strip()
    # String format: "2025-04-10 00:00:00" or "2025-04-10"
    if " " in s:
        return s.split(" ")[0]
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    # Millisecond timestamp (legacy)
    try:
        return datetime.fromtimestamp(int(s) / 1000).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "-"


def _load_curation_rid_map():
    """Read all curation JSONs, return {slug: record_id} for slug→Feishu fallback matching.
    AI curation agent writes clean slugs; Feishu stores YouTube-ID slugs. This bridges them.
    """
    slug_to_rid = {}
    if not os.path.isdir(CURATION_DIR):
        return slug_to_rid
    for fname in sorted(os.listdir(CURATION_DIR)):
        if not fname.endswith(".json") or fname.startswith("."):
            continue
        try:
            data = json.loads(open(os.path.join(CURATION_DIR, fname), encoding="utf-8-sig").read())
            for c in data.get("candidates", []):
                rid = c.get("record_id", "").strip()
                slug = c.get("slug", "").strip()
                if rid and slug and slug not in slug_to_rid:
                    slug_to_rid[slug] = rid
        except Exception:
            pass
    return slug_to_rid


def build_index(records):
    """Build slug→entry and record_id→entry indexes for Feishu lookup + fallback matching."""
    idx = {}
    idx_by_rid = {}
    for r in records:
        f = r["fields"]
        slug = (f.get("Slug") or "").strip()
        rid = r["record_id"]
        status = f.get("状态", "?")
        if isinstance(status, list):
            status = status[0] if status else "?"
        risk = f.get("侵权风险", "")
        if isinstance(risk, list):
            risk = risk[0] if risk else ""
        risk_note = f.get("侵权风险说明", "")
        entry = {
            "status": status,
            "guest": f.get("嘉宾", "-"),
            "yt_url": f.get("URL", ""),
            "record_id": rid,
            "title": f.get("标题", ""),
            "views": f.get("YouTube播放量", "-"),
            "likes": f.get("YouTube点赞", "-"),
            "ratio": f.get("Youtube点赞/播放", None),
            "note": f.get("教训备注", ""),
            "entry_date": _fmt_date(f.get("录入时间")),
            "date": _fmt_date(f.get("视频发布日期")),
            "risk": risk,
            "risk_note": risk_note,
        }
        if slug:
            idx[slug] = entry
        if rid:
            idx_by_rid[rid] = entry
    return idx, idx_by_rid


def scan_local():
    """List local dirs, extract slug from dirname."""
    dirs = []
    if not os.path.isdir(BASE):
        return dirs
    for name in sorted(os.listdir(BASE)):
        path = os.path.join(BASE, name)
        if not os.path.isdir(path):
            continue
        if name.startswith("_"):
            continue
        parts = name.split("_", 1)
        date_str = parts[0] if len(parts) == 2 else ""
        slug = parts[1] if len(parts) == 2 else name
        published = os.path.exists(os.path.join(path, ".published"))
        dirs.append({
            "dirname": name,
            "date": date_str,
            "slug": slug,
            "path": path,
            "published_marker": published,
        })
    return dirs


def sync_published_markers(dirs, idx):
    """If local dir has .published but Feishu != 已发布, update via lark-cli."""
    updated = 0
    for d in dirs:
        if not d["published_marker"]:
            continue
        info = idx.get(d["slug"], {})
        if info.get("status") == "已发布":
            continue
        rid = info.get("record_id")
        if not rid:
            print(f"  SKIP {d['slug']}: no Feishu record found")
            continue
        ok = upsert_record(rid, {"状态": "已发布"})
        if ok:
            print(f"  [SYNC] {d['slug']}: → 已发布")
            info["status"] = "已发布"
            updated += 1
        else:
            print(f"  [FAIL] {d['slug']}: upsert returned False")
    return updated


def file_url(path):
    """Use scheduler API to open the folder in Explorer (file:// blocked by Chrome)."""
    import urllib.parse
    return "http://localhost:3100/api/open-folder?path=" + urllib.parse.quote(path, safe="")


def render(dirs, idx, idx_by_rid, slug_to_rid):
    status_order = {"待发布": 0, "已发布": 1, "候选": 2, "排除": 3, "过期": 4}
    status_colors = {
        "待发布": "#f59e0b", "已发布": "#10b981", "候选": "#6366f1",
        "排除": "#ef4444", "过期": "#6b7280",
    }
    risk_colors = {
        "低风险": "#10b981", "中风险": "#f59e0b", "高风险": "#ef4444", "未评估": "#6b7280",
    }

    def _lookup(slug):
        """Match local dir slug to Feishu entry. Tries: direct slug → curation bridge → record_id."""
        entry = idx.get(slug)
        if entry:
            return entry
        rid = slug_to_rid.get(slug)
        if rid:
            entry = idx_by_rid.get(rid)
            if entry:
                return entry
        return {}

    # Only show 待发布 — this is the operator's action queue
    dirs = [d for d in dirs if _lookup(d["slug"]).get("status") == "待发布"]

    def sort_key(d):
        s = _lookup(d["slug"]).get("status", "?")
        return (status_order.get(s, 99), d["date"], d["slug"])
    dirs.sort(key=sort_key)

    def _fmt_ratio(r):
        if r is None:
            return "-"
        try:
            return f"{float(r):.1f}%"
        except (ValueError, TypeError):
            return "-"

    rows = []
    for d in dirs:
        info = _lookup(d["slug"])
        status = info.get("status", "无飞书记录")
        guest = info.get("guest", "-")
        if isinstance(guest, list):
            guest = ", ".join(guest)
        title = info.get("title", "")
        color = status_colors.get(status, "#6b7280")
        furl = file_url(d["path"])
        views = info.get("views", "-")
        likes = info.get("likes", "-")
        ratio = _fmt_ratio(info.get("ratio"))
        note = info.get("note") or ""
        if isinstance(note, list):
            note = note[0] if note else ""
        entry_date = info.get("entry_date", "-")
        vid_date = info.get("date", "-")

        risk = info.get("risk", "未评估")
        risk_note = info.get("risk_note", "")
        risk_color = risk_colors.get(risk, "#6b7280")
        note_html = f'<span style="color:#f59e0b;font-size:10px" title="{note}">⚠</span>' if note else ""

        rows.append(f"""<tr style="border-left:4px solid {color}">
      <td style="color:{color};font-weight:600;white-space:nowrap">{status}</td>
      <td style="font-size:12px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{title}">{title}</td>
      <td style="font-size:12px;text-align:right;white-space:nowrap">{views}</td>
      <td style="font-size:12px;text-align:right;white-space:nowrap">{likes}</td>
      <td style="font-size:12px;text-align:right;white-space:nowrap">{ratio}</td>
      <td style="color:{risk_color};font-weight:600;font-size:12px;white-space:nowrap" title="{risk_note}">{risk}</td>
      <td style="font-size:11px;white-space:nowrap">{entry_date}</td>
      <td style="font-size:11px;white-space:nowrap">{vid_date}</td>
      <td style="font-size:11px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{d['dirname']}">{d['dirname']}</td>
      <td style="font-size:11px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{note}">{note_html}{note[:60]}</td>
      <td><a href="#" onclick="fetch('{furl}');return false" title="在资源管理器中打开" style="color:#93c5fd;text-decoration:none;font-size:13px;white-space:nowrap;cursor:pointer">打开</a></td>
    </tr>""")

    counts = {}
    for d in dirs:
        s = _lookup(d["slug"]).get("status", "无记录")
        counts[s] = counts.get(s, 0) + 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    count_badges = " ".join(
        f'<span style="background:{status_colors.get(s,"#6b7280")};color:#fff;padding:2px 8px;border-radius:4px;font-size:13px">{s}: {c}</span>'
        for s, c in sorted(counts.items(), key=lambda x: status_order.get(x[0], 99))
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>猫波信号站 · 状态面板</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box }}
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background:#0f172a; color:#e2e8f0; padding:24px }}
  h1 {{ font-size:20px; margin-bottom:4px }}
  .meta {{ color:#94a3b8; font-size:13px; margin-bottom:16px }}
  table {{ width:100%; border-collapse:collapse; font-size:14px }}
  th {{ text-align:left; padding:10px 12px; background:#1e293b; color:#94a3b8; font-weight:500; position:sticky; top:0 }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b }}
  tr:hover td {{ background:#1e293b }}
  a {{ color:#93c5fd; text-decoration:none }}
  a:hover {{ text-decoration:underline }}
  .open-btn {{ display:inline-block; padding:4px 12px; background:#334155; border-radius:4px; font-size:12px; white-space:nowrap }}
  .open-btn:hover {{ background:#475569 }}
</style>
</head>
<body>
<h1>猫波信号站 · 状态面板</h1>
<div class="meta">生成时间: {now} &nbsp;|&nbsp; {count_badges}
  <br><span style="font-size:11px;color:#64748b">工作流: 发布后 → 在对应目录下新建 .published 文件 → 运行 gen_status_board.py → 自动同步飞书 + 刷新面板</span>
</div>
<table>
<thead><tr>
  <th>状态</th><th>标题</th><th>播放</th><th>点赞</th><th>赞/播</th><th>风险</th><th>录入</th><th>日期</th><th>文件名</th><th>备注</th><th>操作</th>
</tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</body>
</html>"""


def main():
    records = []
    try:
        records = fetch_records(None)
    except Exception as e:
        print(f"WARN: Feishu fetch failed ({e}), using local-only data", file=sys.stderr)

    idx, idx_by_rid = build_index(records)
    dirs = scan_local()
    slug_to_rid = _load_curation_rid_map()

    # Sync .published markers → Feishu
    if records:
        print("Checking .published markers...")
        n = sync_published_markers(dirs, idx)
        if n == 0:
            print("  (all in sync)")

    html = render(dirs, idx, idx_by_rid, slug_to_rid)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nWrote: {OUT}")
    print(f"  {len(dirs)} local dirs, {len(idx)} Feishu records indexed")


if __name__ == "__main__":
    main()

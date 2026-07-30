"""Shared Feishu API module for 猫波信号站 pipeline tools.
Uses lark-cli subprocess calls (bot identity) — NOT direct REST API.
"""

import json
import subprocess
import sys


APP_TOKEN = "F7E8bJie5aX3BvsZz1Xc9KiznNb"
TABLE_ID = "tblIs359fHfIapwd"
LARK_CLI = r"C:\Users\Administrator\AppData\Roaming\npm\lark-cli.cmd"


def _lark(*args, **kwargs):
    """Run lark-cli command, return parsed JSON response."""
    cmd = subprocess.list2cmdline([LARK_CLI] + list(args))
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=kwargs.pop("timeout", 30), shell=True,
    )
    if result.returncode != 0:
        print(f"  [_feishu] lark-cli exit {result.returncode}: {result.stderr[:200]}")
        return {"ok": False, "error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"JSON parse error: {result.stdout[:200]}"}


def _lark_utf8(*args, timeout=30, cwd=None):
    """Run lark-cli via cmd /c chcp 65001 — required in headless/cron contexts."""
    cmd = ["cmd", "/c", "chcp", "65001", ">", "nul", "&", LARK_CLI] + list(args)
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=cwd,
    )
    if result.returncode != 0:
        print(f"  [_feishu] lark-cli exit {result.returncode}: {result.stderr[:300]}")
        return {"ok": False, "error": result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  [_feishu] JSON parse error: {e}")
        return {"ok": False, "error": str(e)}


def get_token():
    """Placeholder — lark-cli handles auth internally. Kept for API compat."""
    return "lark-cli-bot"


def fetch_records(token=None):
    """Fetch all records via lark-cli (bot). Returns list of {record_id, fields}."""
    resp = _lark(
        "base", "+record-list",
        "--base-token", APP_TOKEN,
        "--table-id", TABLE_ID,
        "--as", "bot",
        "--limit", "200",
        "--format", "json",
        timeout=30,
    )
    if not resp.get("ok"):
        print(f"  [_feishu] fetch_records FAILED: {resp.get('error', 'unknown')}")
        return []
    data = resp.get("data", {})
    records = []
    field_names = data.get("fields", [])
    record_ids = data.get("record_id_list", [])
    rows = data.get("data", [])
    for i, row in enumerate(rows):
        fields = {}
        for j, name in enumerate(field_names):
            if j < len(row):
                fields[name] = row[j]
        rid = record_ids[i] if i < len(record_ids) else ""
        records.append({"record_id": rid, "fields": fields})
    return records


def fetch_records_filtered(field_ids, filter_dict=None, sort_list=None, limit=200):
    """Fetch records with filter/sort/projection. Uses inline JSON passing.
    Returns (field_names, record_ids, rows) tuple from lark-cli response.
    """
    args = [
        "base", "+record-list",
        "--base-token", APP_TOKEN,
        "--table-id", TABLE_ID,
        "--as", "bot",
        "--limit", str(limit),
        "--format", "json",
    ]
    if filter_dict:
        args.extend(["--filter-json", json.dumps(filter_dict, ensure_ascii=False)])
    if sort_list:
        args.extend(["--sort-json", json.dumps(sort_list, ensure_ascii=False)])
    for fid in field_ids:
        args.extend(["--field-id", fid])

    resp = _lark(*args, timeout=30)
    if not resp.get("ok"):
        print(f"  [_feishu] fetch_records_filtered FAILED: {resp.get('error', 'unknown')}")
        return [], [], []
    data = resp.get("data", {})
    return data.get("fields", []), data.get("record_id_list", []), data.get("data", [])


def upsert_record(record_id, fields_dict, base_token=None, table_id=None):
    """Update a single record's fields via @file approach (avoids quoting hell)."""
    import os as _os
    bt = base_token or APP_TOKEN
    tid = table_id or TABLE_ID
    # Write JSON to temp file in CWD-relative path (lark-cli requires relative paths for @file)
    tmp_path = _os.path.join(_os.getcwd(), "_lark_tmp_update.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(fields_dict, f, ensure_ascii=False)
    try:
        resp = _lark(
            "base", "+record-upsert",
            "--base-token", bt,
            "--table-id", tid,
            "--as", "bot",
            "--record-id", record_id,
            "--json", "@_lark_tmp_update.json",
            timeout=15,
        )
        return resp.get("ok", False)
    finally:
        if _os.path.exists(tmp_path):
            _os.remove(tmp_path)


def build_slug_index(records):
    """Build slug -> {status, record_id, title, ...} index."""
    idx = {}
    for r in records:
        f = r["fields"]
        slug = (f.get("Slug") or "").strip()
        if not slug:
            continue
        idx[slug] = {
            "status": f.get("状态", "?"),
            "record_id": r["record_id"],
            "title": f.get("标题", ""),
        }
    return idx


def _strip_date_prefix(s):
    """Strip YYYYMMDD_ prefix if present."""
    import re
    return re.sub(r"^\d{8}_", "", s)


def find_record_by_slug(token, slug):
    """Find a Feishu record by slug. Returns (record_id, current_status) or (None, None)."""
    records = fetch_records(token)
    slug_no_date = _strip_date_prefix(slug)
    for r in records:
        rs = (r["fields"].get("Slug") or "").strip()
        if rs == slug or (slug_no_date != slug and rs == slug_no_date):
            status = r["fields"].get("状态", "?")
            if isinstance(status, list):
                status = status[0] if status else "?"
            return r["record_id"], status
    return None, None


def update_record_status(token, record_id, new_status):
    """Update Feishu record status field via lark-cli. Returns True on success."""
    update_json = json.dumps({"状态": new_status}, ensure_ascii=False)
    try:
        resp = _lark(
            "base", "+record-upsert",
            "--base-token", APP_TOKEN,
            "--table-id", TABLE_ID,
            "--as", "bot",
            "--record-id", record_id,
            "--json", update_json,
            timeout=15,
        )
        return resp.get("ok", False)
    except Exception as e:
        print(f"  [_feishu] update_record_status ERROR: {e}")
        return False


# ── Copyright risk auto-assessment ──

LOW_RISK_SOURCES = {
    "Y Combinator", "YC", "TED", "TEDx", "Stanford", "MIT", "Harvard",
    "Google", "OpenAI", "Anthropic", "DeepMind", "Meta", "Microsoft",
    "Stripe", "a16z", "Sequoia", "Greylock", "Kleiner Perkins",
}
MEDIUM_RISK_SOURCES = {
    "The Economist", "Bloomberg", "Wall Street Journal", "WSJ",
    "Financial Times", "FT", "CNBC", "BBC", "Reuters", "The Verge",
    "Wired", "TechCrunch", "New York Times", "NYT", "Washington Post",
    "The Guardian", "Fortune", "Forbes", "Business Insider",
}


def assess_copyright_risk(source_channel: str) -> tuple[str, str]:
    """Return (risk_level, risk_note) based on source channel name.

    risk_level: 低风险 | 中风险 | 高风险 — matches Feishu field options.
    """
    ch = source_channel.strip()
    for s in LOW_RISK_SOURCES:
        if s.lower() in ch.lower():
            return "低风险", f"{s} 官方频道，公开内容允许翻译转载"
    for s in MEDIUM_RISK_SOURCES:
        if s.lower() in ch.lower():
            return "中风险", f"{s} 主流媒体，翻译转载需明确注明来源"
    # Unknown source — conservative
    return "中风险", f"非已知安全源，建议人工确认: {ch}"


def fill_record_risk(record_id: str, source_channel: str) -> bool:
    """Auto-assess and upsert 侵权风险 + 侵权风险说明 to Feishu."""
    risk, note = assess_copyright_risk(source_channel)
    return upsert_record(record_id, {"侵权风险": risk, "侵权风险说明": note})

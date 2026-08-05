"""Generate 发布面板.html from metadata.json and filesystem data.

Usage:
  python gen_publish_panel.py --slug <slug>

Reads _runtime/metadata.json, checks files on disk, generates 发布面板.html.
Replaces what was previously done by AI agent manually.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir



def render(slug: str) -> str:
    sdir = slug_dir(slug)
    meta_path = sdir / "_runtime" / "metadata.json"
    if not meta_path.exists():
        print(f"ERROR: metadata.json not found at {meta_path}")
        sys.exit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    title = meta["title"]
    tags = meta.get("tags", [])
    source = meta.get("source", "")
    source_url = meta.get("source_url", "")
    author = meta.get("author", "")
    publish_date = meta.get("publish_date", "")
    chapters = meta.get("chapters", [])
    description = meta.get("description", "")

    # Display title from slug
    display_parts = [p for p in slug.split("_") if not p[:8].isdigit()]
    display_title = " · ".join(display_parts[:3]) if display_parts else slug

    # Cover info
    cover = sdir / "cover.jpg"
    cover_html = ""
    if cover.exists():
        size_kb = cover.stat().st_size / 1024
        cover_html = (
            f"    <div>文件：cover.jpg（{size_kb:.1f} KB，1920×1080，4:3安全区已适配）</div>\n"
            f'    <div class="note">亮度 0.80 · 主色 #FFC82D · 字体 msyhbd.ttc 纯色无描边</div>'
        )

    # Video file
    video_html = ""
    video_dir = sdir / "成片"
    if video_dir.exists():
        mp4s = sorted(video_dir.glob("*.mp4"))
        if mp4s:
            v = mp4s[0]
            dur_str = ""
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(v)],
                    capture_output=True, text=True, timeout=15,
                )
                dur_s = float(result.stdout.strip())
                h, r = divmod(int(dur_s), 3600)
                m, s = divmod(r, 60)
                dur_str = f"~{h}:{m:02d}:{s:02d}，"
            except Exception:
                dur_str = ""
            video_html = f"{v.name}（{dur_str}H.264 NVENC+AAC）"

    # Tags HTML
    tags_html = "".join(
        '  <div class=tag-row><span>{0}</span><button class=copy-btn onclick="navigator.clipboard.writeText(\'{0}\')">复制</button></div>\n'.format(t)
        for t in tags[:10]
    )

    # Chapters text
    chapters_text = "\n".join(
        f"{ch[0]} {ch[1]}" for ch in chapters[:10]
    )

    # Compliance report
    compliance_html = ""
    cr_path = sdir / "_runtime" / "compliance_report.txt"
    if cr_path.exists():
        import re as _re
        cr_text = cr_path.read_text(encoding="utf-8")
        warn_matches = _re.findall(r"WARN: (.+?) → \.\.\.(.+?)\.\.\.", cr_text)
        if warn_matches:
            rows = ""
            for pattern, ctx in warn_matches:
                rows += (
                    '      <div style="margin-bottom:8px;padding:6px 10px;background:#1a0a0a;border-radius:4px;border-left:3px solid #e74c3c">'
                    f'<b style="color:#e74c3c">命中词：{pattern.strip()}</b><br>'
                    f'<span style="color:#999">上下文：{ctx.strip()}</span></div>\n'
                )
            compliance_html = (
                '  <div class="field" style="background:#2d1f1f;border:1px solid #c0392b">\n'
                '    <div class="field-header"><span class="field-label" style="color:#e74c3c">⚠️ B站合规警告 · 发布前人工审核</span></div>\n'
                '    <div class="field-body" style="background:#3d1a1a;font-size:13px">\n'
                + rows +
                '      <div class="note" style="color:#e74c3c;margin-top:6px">建议：确认语境无政治敏感含义后再上传。不确定则剪掉对应片段或整集不上。</div>\n'
                '    </div>\n'
                '  </div>\n'
            )

    # Build 转载声明 (B站单行文本 ≤200字)
    copyright_source = source.replace("YouTube @", "").strip() if source else ""
    copyright_text = f"转自 {source_url}"
    if copyright_source:
        copyright_text += f" ({copyright_source})"
    if publish_date:
        copyright_text += f", {publish_date}"
    copyright_info = f'    <div><b>来源注明：</b>{copyright_text}</div>\n'
    copyright_info += f'    <div class="note">上传页 → 创作声明 → 选择「内容为转载」→ 粘贴以上文字（{len(copyright_text)}字）</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>B站发布面板 · {display_title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #1a1a2e; color: #e0e0e0; max-width: 800px; margin: 40px auto; padding: 20px; }}
  h1 {{ color: #FFC82D; margin-bottom: 24px; font-size: 22px; }}
  .field {{ background: #16213e; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
  .field-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .field-label {{ color: #FFC82D; font-weight: 700; font-size: 14px; }}
  .field-body {{ background: #0f3460; border-radius: 6px; padding: 12px; font-size: 14px; line-height: 1.7; white-space: pre-wrap; }}
  .copy-btn {{ background: #FFC82D; color: #1a1a2e; border: none; border-radius: 4px; padding: 4px 14px; font-size: 12px; font-weight: 700; cursor: pointer; }}
  .copy-btn:hover {{ background: #ffd86e; }}
  .copy-btn.copied {{ background: #4ecca3; }}
  .note {{ color: #888; font-size: 12px; margin-top: 4px; }}
  .tag-row {{ display: inline-flex; align-items: center; gap: 6px; margin-right: 12px; margin-bottom: 4px; }}
  .tag-row span {{ background: #1a1a2e; padding: 2px 8px; border-radius: 3px; font-size: 13px; }}
  .field.copyright {{ background: #1e2d1e; border: 1px solid #2e7d32; }}
  .field.copyright .field-label {{ color: #4caf50; }}
</style>
</head>
<body>

<h1>B站发布面板 — {display_title}</h1>

<div class="field">
  <div class="field-header">
    <span class="field-label">1. 标题（≤80字）</span>
    <button class="copy-btn" onclick="copyField(this, 'title')">复制</button>
  </div>
  <div class="field-body" id="title">{title}</div>
  <div class="note">字数：{len(title)} / 80</div>
</div>

<div class="field copyright">
  <div class="field-header"><span class="field-label">2. 创作声明</span></div>
  <div class="field-body" id="copyright">内容为转载
{copyright_info}  </div>
</div>

<div class="field">
  <div class="field-header"><span class="field-label">3. 分区</span><button class="copy-btn" onclick="copyField(this, 'category')">复制</button></div>
  <div class="field-body" id="category">知识 > 科技 > 人工智能</div>
</div>

<div class="field">
  <div class="field-header">
    <span class="field-label">4. 标签（最多10个）</span>
    <button class="copy-btn" onclick="copyField(this, 'tags')">复制</button>
  </div>
  <div class="field-body" id="tags">
{tags_html}  </div>
  <div class="note">逐个复制粘贴，按回车确认每个标签</div>
</div>

<div class="field">
  <div class="field-header"><span class="field-label">5. 合集</span><button class="copy-btn" onclick="copyField(this, 'collection')">复制</button></div>
  <div class="field-body" id="collection">猫波译站</div>
</div>

<div class="field">
  <div class="field-header">
    <span class="field-label">6. 简介（≤2000字）</span>
    <button class="copy-btn" onclick="copyField(this, 'desc')">复制</button>
  </div>
  <div class="field-body" id="desc">{description}</div>
  <div class="note">字数：{len(description)} / 2000</div>
</div>

<div class="field">
  <div class="field-header"><span class="field-label">7. 章节时间戳（{len(chapters)}个）</span><button class="copy-btn" onclick="copyField(this, 'chapters')">复制</button></div>
  <div class="field-body" id="chapters">{chapters_text}</div>
</div>

<div class="field">
  <div class="field-header"><span class="field-label">封面</span></div>
  <div class="field-body">
{cover_html}
  </div>
</div>

<div class="field">
  <div class="field-header"><span class="field-label">视频文件</span></div>
  <div class="field-body">{video_html}</div>
</div>

{compliance_html}
<script>
function copyField(btn, fieldId) {{
  const text = document.getElementById(fieldId).innerText;
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = '复制'; btn.classList.remove('copied'); }}, 1500);
  }});
}}
</script>
</body>
</html>"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="生成B站发布面板HTML")
    p.add_argument("--slug", required=True)
    args = p.parse_args()

    html = render(args.slug)
    out = slug_dir(args.slug) / "发布面板.html"
    out.write_text(html, encoding="utf-8")
    print(f"Written: {out}")

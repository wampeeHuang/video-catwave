#!/usr/bin/env python3
"""B站视频封面生成器。从视频截图 + 标题文字生成 1920×1080 封面 JPG。

用法:
  python gen_cover.py <frame.jpg> <cover.jpg> --title "主标题" [--sub "副标题"] [--source "出处行"]

设计参数（_ref/生产参数.md §1 唯一真相源）:
  --brightness 0.80   底图亮度（黑色透明度）
  --color #FFC82D     主色（暖黄）
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# ── 设计参数（来源: _ref/生产参数.md §1 封面）──────────
CANVAS = (1920, 1080)
YELLOW = (255, 200, 45)       # #FFC82D 暖黄
WHITE = (252, 250, 245)       # #FCFAF5 暖白
GRAY = (200, 200, 200)        # 底部信息条
FONT_BOLD = "simhei.ttf"      # 黑体 — 系统最粗中文
FONT_REGULAR = "msyh.ttc"     # 微软雅黑 Regular — 底部信息条
FONT_FALLBACK = "msyhbd.ttc"  # 微软雅黑 Bold — 回退
BRIGHTNESS = 0.80
LINE_W, LINE_H = 120, 4       # 装饰线
STROKE = 2                    # 文字四周填充


def _find_font(name: str) -> str | None:
    fonts_dir = Path("C:/Windows/Fonts")
    direct = fonts_dir / name
    if direct.exists():
        return str(direct)
    stem = name.rsplit(".", 1)[0].lower()
    for pat in [f"{stem}.*", f"{stem.title()}.*", f"{stem.upper()}.*"]:
        hits = list(fonts_dir.glob(pat))
        if hits:
            return str(hits[0])
    return None


def _load_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    chains = {
        "bold":    [FONT_BOLD, FONT_FALLBACK],
        "regular": [FONT_REGULAR, FONT_FALLBACK, FONT_BOLD],
    }
    for name in chains.get(weight, chains["bold"]):
        path = _find_font(name)
        if path:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_with_stroke(draw, xy, text, font, fill, stroke_width=STROKE, stroke_fill=(0, 0, 0)):
    """Draw text with 8-direction black fill simulating extra bold."""
    x, y = xy
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill, anchor="mm")


def _wrap_title(draw, text: str, max_fs: int, safe_width: int) -> list[tuple[str, int]]:
    """Break long title into lines if needed. Each line ≥ 80px."""
    for fs in range(max_fs, 70, -10):
        font = _load_font(fs, "bold")
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= safe_width:
            return [(text, fs)]

    punct = set("，。！？、；：")
    for fs in range(max_fs, 70, -10):
        font = _load_font(fs, "bold")
        lines = _split_text(draw, text, font, safe_width, punct)
        if all(draw.textbbox((0, 0), ln, font=font)[2] <= safe_width for ln in lines):
            return [(ln, fs) for ln in lines]

    font = _load_font(80, "bold")
    lines = _split_text(draw, text, font, safe_width, set())
    return [(ln, 80) for ln in lines]


def _split_text(draw, text: str, font, max_w: int, punct: set) -> list[str]:
    """Split text at best break point near middle, each segment ≤ max_w."""
    lines = []
    remaining = text
    while remaining:
        if draw.textbbox((0, 0), remaining, font=font)[2] <= max_w:
            lines.append(remaining)
            break
        mid = len(remaining) // 2
        best = None
        for offset in range(len(remaining)):
            for sign in (1, -1):
                idx = mid + offset * sign
                if not (0 < idx < len(remaining)):
                    continue
                if punct and remaining[idx] in punct:
                    best = idx + 1
                    break
                if best is None and remaining[idx] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    if ord(remaining[idx]) >= 128:
                        best = idx
            if best and punct and remaining[best - 1] in punct:
                break
            if best:
                break
        if best is None:
            best = mid
        candidate = remaining[:best]
        if draw.textbbox((0, 0), candidate, font=font)[2] > max_w:
            while candidate and draw.textbbox((0, 0), candidate, font=font)[2] > max_w:
                candidate = candidate[:-1]
            best = len(candidate)
        lines.append(remaining[:best])
        remaining = remaining[best:]
    return lines


def _draw_line(draw, cx, y):
    """Draw decorative line 120×4px."""
    x0, x1 = cx - LINE_W // 2, cx + LINE_W // 2
    draw.rectangle([x0, y, x1, y + LINE_H], fill=YELLOW)


def _draw_bottom_bar(draw, source_text: str):
    """Draw bottom info bar: 'YouTube · <source> | 猫波译站'."""
    bar_text = f"YouTube · {source_text}  |  猫波译站" if source_text else "猫波译站"
    font = _load_font(24, "regular")
    bbox = draw.textbbox((0, 0), bar_text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((CANVAS[0] // 2, CANVAS[1] - 30), bar_text, font=font, fill=GRAY, anchor="mm")


def generate_cover(
    frame_path: Path,
    output_path: Path,
    title: str,
    subtitle: str = "",
    source_line: str = "",
    brightness: float = BRIGHTNESS,
    accent_color: tuple[int, int, int] = YELLOW,
):
    img = Image.open(frame_path).convert("RGB")
    img = img.resize(CANVAS, Image.LANCZOS)

    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)
    draw = ImageDraw.Draw(img)

    safe_w = 1440 - 120  # Safe area with padding

    # Title: 165px max, wrap if needed
    title_lines = _wrap_title(draw, title, 165, safe_w)

    # Build line stack
    lines = []  # (kind, text, size, color, weight)
    show_decoration = False

    if subtitle:
        lines.append(("sub", subtitle, 62, WHITE, "bold"))
    for i, (line_text, line_size) in enumerate(title_lines):
        kind = "title" if i == 0 else "title_cont"
        lines.append((kind, line_text, line_size, accent_color, "bold"))
        if i == 0 and subtitle:
            show_decoration = True
    if source_line:
        lines.append(("source", source_line, 28, WHITE, "bold"))

    # Calculate total height
    text_block_h = 0
    gaps = []
    for i, (kind, text, size, color, weight) in enumerate(lines):
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        h = bbox[3] - bbox[1] + STROKE * 2
        text_block_h += h
        gaps.append(0)
        if i < len(lines) - 1:
            if kind == "sub" and show_decoration:
                g = 16 + LINE_H + 16  # gap above + line + gap below
            elif kind in ("title_cont", "sub"):
                g = 30
            elif kind == "title":
                g = 40
            else:
                g = 30
            gaps[i] = g
            text_block_h += g

    cx, cy = CANVAS[0] // 2, CANVAS[1] // 2
    y = cy - text_block_h // 2

    # Draw text stack
    for i, (kind, text, size, color, weight) in enumerate(lines):
        font = _load_font(size, weight)
        line_y = y + size // 2 + STROKE
        _draw_text_with_stroke(draw, (cx, line_y), text, font, color)
        h = size + STROKE * 2
        y += h + gaps[i]

        # Decorative line between subtitle and title
        if kind == "sub" and show_decoration:
            _draw_line(draw, cx, y - gaps[i] + 8)

    # Bottom bar
    _draw_bottom_bar(draw, source_line)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=92, optimize=True)
    size_mb = output_path.stat().st_size / (1024 * 1024)

    if size_mb > 4.8:
        img.save(str(output_path), "JPEG", quality=75, optimize=True)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Re-compressed to {size_mb:.1f} MB (B站 ≤5MB limit)")

    print(f"Cover saved: {output_path} ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Generate B站 video cover (spec: _ref/生产参数.md §1)")
    parser.add_argument("frame", help="Path to video screenshot (1920x1080 recommended)")
    parser.add_argument("output", help="Output path (cover.jpg)")
    parser.add_argument("--title", required=True, help="Main title text (≤15 chars recommended)")
    parser.add_argument("--sub", default="", help="Subtitle / second line")
    parser.add_argument("--source", default="", help="Source attribution line")
    parser.add_argument("--brightness", type=float, default=BRIGHTNESS)
    parser.add_argument("--color", default="#FFC82D", help="Accent color hex")
    args = parser.parse_args()

    color = tuple(int(args.color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))

    generate_cover(
        frame_path=Path(args.frame),
        output_path=Path(args.output),
        title=args.title,
        subtitle=args.sub,
        source_line=args.source,
        brightness=args.brightness,
        accent_color=color,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""B站视频封面生成器。从视频截图 + 标题文字生成 1920×1080 封面 JPG。

用法:
  python gen_cover.py <frame.jpg> <cover.jpg> --title "黄字第1行" [--title2 "黄字第2行"] [--sub "白字副标题"]

设计:
  黄字在上（165px max，独立自缩至 4:3 安全区），白字在下（62px）。
  纯色无描边，居中对称。最多两行黄字 + 一行白字。
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# ── 设计参数 ──────────────────────────────────────────────────────────────
CANVAS = (1920, 1080)
SAFE_W = 1440
SAFE_PAD = 60
YELLOW = (255, 200, 45)       # #FFC82D
WHITE = (252, 250, 245)       # #FCFAF5
FONT_BOLD = "msyhbd.ttc"      # 微软雅黑 Bold
FONT_REGULAR = "msyh.ttc"     # 微软雅黑 Regular
FONT_FALLBACK = "simhei.ttf"  # 黑体回退
BRIGHTNESS = 0.80


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
        "bold":    [FONT_BOLD, FONT_REGULAR, FONT_FALLBACK],
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


def _fit_size(draw, text: str, max_fs: int) -> tuple[int, ImageFont.FreeTypeFont]:
    """Return (font_size, font) that fits text in 4:3 safe area."""
    font = _load_font(max_fs, "bold")
    tw = draw.textbbox((0, 0), text, font=font)[2]
    safe_max = SAFE_W - SAFE_PAD * 2
    if tw <= safe_max:
        return max_fs, font
    fs = int(max_fs * safe_max / tw)
    return fs, _load_font(fs, "bold")


def generate_cover(
    frame_path: Path,
    output_path: Path,
    title: str,
    subtitle: str = "",
    title2: str = "",
    brightness: float = BRIGHTNESS,
    accent_color: tuple[int, int, int] = YELLOW,
):
    img = Image.open(frame_path).convert("RGB")
    img = img.resize(CANVAS, Image.LANCZOS)

    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)
    draw = ImageDraw.Draw(img)

    safe_max = SAFE_W - SAFE_PAD * 2

    # Build line stack: yellow title lines → white subtitle
    lines = []  # (kind, text, size, color, weight)

    for t in [title, title2]:
        if t:
            fs, _ = _fit_size(draw, t, 165)
            if fs < 165:
                print(f"  Title shrunk 165→{fs}px to fit safe area ({safe_max}px)")
            lines.append(("title", t, fs, accent_color, "bold"))

    if subtitle:
        lines.append(("sub", subtitle, 62, WHITE, "bold"))

    # Calculate text block height
    text_block_h = 0
    for i, (kind, text, size, color, weight) in enumerate(lines):
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_block_h += bbox[3] - bbox[1]
        if i < len(lines) - 1:
            if kind == "title" and i + 1 < len(lines) and lines[i + 1][0] == "title":
                text_block_h += 20   # tight gap between yellow lines
            elif kind == "title":
                text_block_h += 40   # yellow → white gap
            elif kind == "sub":
                text_block_h += 30

    # Centered layout
    y = (CANVAS[1] - text_block_h) // 2 - 40

    for i, (kind, text, size, color, weight) in enumerate(lines):
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw.text((CANVAS[0] // 2, y + text_h // 2), text, font=font, fill=color, anchor="mm")
        y += text_h
        if i < len(lines) - 1:
            if kind == "title" and lines[i + 1][0] == "title":
                y += 20
            elif kind == "title":
                y += 40
            else:
                y += 30

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
    parser = argparse.ArgumentParser(description="Generate B站 video cover")
    parser.add_argument("frame", help="Path to video screenshot (1920x1080 recommended)")
    parser.add_argument("output", help="Output path (cover.jpg)")
    parser.add_argument("--title", required=True, help="Yellow title line 1 (top)")
    parser.add_argument("--title2", default="", help="Yellow title line 2 (optional)")
    parser.add_argument("--sub", default="", help="White subtitle (bottom)")
    parser.add_argument("--brightness", type=float, default=BRIGHTNESS)
    parser.add_argument("--color", default="#FFC82D", help="Accent color hex")
    args = parser.parse_args()

    color = tuple(int(args.color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))

    generate_cover(
        frame_path=Path(args.frame),
        output_path=Path(args.output),
        title=args.title,
        title2=args.title2,
        subtitle=args.sub,
        brightness=args.brightness,
        accent_color=color,
    )


if __name__ == "__main__":
    main()

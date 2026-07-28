#!/usr/bin/env python3
"""B站视频封面生成器。从视频截图 + 标题文字生成 1920×1080 封面 JPG。

用法:
  python gen_cover.py <frame.jpg> <cover.jpg> --title "黄字第1行" [--title2 "黄字第2行"] --sub "白字副标题"

设计:
  黄字在上（165px max，独立自缩至 4:3 安全区），白字在下（62px）。
  纯色无描边，居中对称。最多两行黄字 + 一行白字。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cover_design import (
    CANVAS, SAFE_W, SAFE_PAD, YELLOW, WHITE,
    FONT_BOLD, FONT_REGULAR, FONT_FALLBACK,
    MIN_TITLE_FS, MIN_SUB_FS, MAX_TITLE_FS, MAX_SUB_FS,
    BRIGHTNESS,
)

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


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


def _fit_size(draw, text: str, max_fs: int, min_fs: int = MIN_TITLE_FS) -> tuple[int, ImageFont.FreeTypeFont]:
    """Return (font_size, font) that fits text in 4:3 safe area. Never below min_fs."""
    font = _load_font(max_fs, "bold")
    tw = draw.textbbox((0, 0), text, font=font)[2]
    safe_max = SAFE_W - SAFE_PAD * 2
    if tw <= safe_max:
        return max_fs, font
    fs = int(max_fs * safe_max / tw)
    if fs < min_fs:
        print(f"  WARN: {len(text)}字标题需缩至{fs}px < {min_fs}px底线 — 请精简封面标题（120px≈11中文字）")
        return min_fs, _load_font(min_fs, "bold")
    return fs, _load_font(fs, "bold")


def generate_cover(
    frame_path: Path,
    output_path: Path,
    title: str,
    subtitle: str = "",
    title2: str = "",
    brightness: float = BRIGHTNESS,
    accent_color: tuple[int, int, int] = YELLOW,
    overlay: int = 0,
    position: str = "center",
):
    img = Image.open(frame_path).convert("RGB")
    img = img.resize(CANVAS, Image.LANCZOS)

    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)

    if overlay > 0:
        alpha = int(overlay / 100 * 255)
        mask = Image.new('RGBA', CANVAS, (0, 0, 0, alpha))
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, mask)
        img = img.convert('RGB')

    draw = ImageDraw.Draw(img)

    safe_max = SAFE_W - SAFE_PAD * 2

    # Build line stack: yellow title lines → white subtitle
    lines = []  # (kind, text, size, color, weight)

    for t in [title, title2]:
        if t:
            fs, _ = _fit_size(draw, t, MAX_TITLE_FS, MIN_TITLE_FS)
            if fs < MAX_TITLE_FS:
                print(f"  Title shrunk {MAX_TITLE_FS}→{fs}px to fit safe area ({safe_max}px)")
            lines.append(("title", t, fs, accent_color, "bold"))

    if subtitle:
        fs, _ = _fit_size(draw, subtitle, MAX_SUB_FS, MIN_SUB_FS)
        if fs < 62:
            print(f"  Subtitle shrunk {MAX_SUB_FS}→{fs}px to fit safe area")
        lines.append(("sub", subtitle, fs, WHITE, "bold"))

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

    # Vertical position
    if position == "bottom":
        y = CANVAS[1] - text_block_h - 140
    else:
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

    # ── Inline validation: white text required when --sub is non-empty ──
    if subtitle:
        pixels = list(img.getdata())
        total = len(pixels)
        white_px = sum(1 for r, g, b in pixels if r >= 220 and g >= 220 and b >= 220)
        white_pct = white_px / total * 100
        if white_pct < 0.1:
            print(f"  FAIL: White subtitle missing! Only {white_pct:.2f}% white pixels (need >=0.1%)")
            print(f"  Check --sub parameter or font availability.")
            import sys
            sys.exit(2)
        yellow_px = sum(1 for r, g, b in pixels if r > 200 and g > 150 and b < 100)
        yellow_pct = yellow_px / total * 100
        print(f"  Validation PASS: yellow {yellow_pct:.1f}% / white {white_pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Generate B站 video cover")
    parser.add_argument("frame", help="Path to video screenshot (1920x1080 recommended)")
    parser.add_argument("output", help="Output path (cover.jpg)")
    parser.add_argument("--title", required=True, help="Yellow title line 1 (top)")
    parser.add_argument("--title2", default="", help="Yellow title line 2 (optional)")
    parser.add_argument("--sub", required=True, help="White subtitle: '<身份> · <节目名>' (use '' to skip)")
    parser.add_argument("--brightness", type=float, default=BRIGHTNESS)
    parser.add_argument("--overlay", type=int, default=0, help="Black overlay opacity 0-100")
    parser.add_argument("--position", default="center", choices=["center", "bottom"],
                        help="Text position: center or bottom")
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
        overlay=args.overlay,
        position=args.position,
    )


if __name__ == "__main__":
    main()

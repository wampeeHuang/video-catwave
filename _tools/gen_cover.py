#!/usr/bin/env python3
"""B站视频封面生成器。从视频截图 + 标题文字生成 1920×1080 封面 JPG。

用法:
  python _tools/gen_cover.py <frame.jpg> <output/cover.jpg> --title "主标题" [--sub "副标题"] [--source "出处行"]

设计参数（可命令行覆盖）:
  --brightness 0.80   底图亮度（黑色透明度）
  --color #FFC82D     主色（暖黄）
  --font SimHei        中文字体名
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
YELLOW = (255, 200, 45)       # #FFC82D
WHITE = (252, 250, 245)       # #FCFAF5
DARK_OVERLAY = (0, 0, 0)      # 填充描边用纯黑
FONT_BOLD = "simhei.ttf"      # Windows Fonts 目录下自动查找
FONT_THIN = "seguiemj.ttf"    # Segoe UI Emoji（底部信息条）
BRIGHTNESS = 0.80
PERIMETER_FILL = 2            # 四周填充 px（模拟超粗）


def _find_font(name: str) -> str:
    candidates = [
        Path(f"C:/Windows/Fonts/{name}"),
        Path(f"C:/Windows/Fonts/{name.title()}"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Fallback: search Fonts dir
    fonts_dir = Path("C:/Windows/Fonts")
    for f in fonts_dir.glob("*.ttf"):
        if name.lower() in f.name.lower():
            return str(f)
    return name


def _draw_bold_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    anchor: str = "ma",
):
    """Draw text with perimeter fill for simulated extra bold weight."""
    x, y = xy
    for dx, dy in [
        (-2, -2), (-2, 0), (-2, 2),
        (0, -2), (0, 2),
        (2, -2), (2, 0), (2, 2),
    ]:
        draw.text((x + dx, y + dy), text, font=font, fill=DARK_OVERLAY, anchor=anchor)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


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

    # Apply brightness (simulates dark overlay transparency)
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)

    draw = ImageDraw.Draw(img)

    font_bold_path = _find_font(FONT_BOLD)
    font_thin_path = _find_font(FONT_THIN)

    # Build layout from bottom up
    lines = []
    if subtitle:
        lines.append(("sub", subtitle, 62, accent_color))
    if title:
        lines.append(("title", title, 165, accent_color if not subtitle else WHITE))
    if source_line:
        lines.append(("source", source_line, 28, WHITE))

    # Calculate total height
    total_h = 0
    spacings = []
    for i, (kind, text, size, color) in enumerate(lines):
        try:
            f = ImageFont.truetype(font_bold_path, size)
        except Exception:
            f = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=f)
        h = bbox[3] - bbox[1]
        total_h += h
        if i < len(lines) - 1:
            gap = 40 if kind == "title" else 30
            total_h += gap
            spacings.append(gap)
        spacings.append(h)

    # Accent line (between title and subtitle)
    if title and subtitle:
        total_h += 12  # line height
        total_h += 20  # gap

    # Bottom bar
    bar_h = 60
    total_h += bar_h + 20

    # Start Y (centered)
    y_center = CANVAS[1] // 2
    y = y_center - total_h // 2 + 60  # slight upward bias

    font_bold_large = None
    try:
        font_bold_large = ImageFont.truetype(font_bold_path, 165)
    except Exception:
        font_bold_large = ImageFont.load_default()

    # Draw accent line if both title and subtitle present
    if title and subtitle:
        line_y = y + 80
        line_w = 120
        draw.rectangle(
            [CANVAS[0] // 2 - line_w // 2, line_y, CANVAS[0] // 2 + line_w // 2, line_y + 4],
            fill=accent_color,
        )
        y = line_y + 30

    # Draw text lines
    for kind, text, size, color in lines:
        try:
            font = ImageFont.truetype(font_bold_path, size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        x = CANVAS[0] // 2

        if kind in ("title", "sub"):
            _draw_bold_text(draw, (x, y + text_h // 2), text, font, color, anchor="mm")
        else:
            draw.text((x, y + text_h // 2), text, font=font, fill=color, anchor="mm")

        y += text_h + (40 if kind == "title" else 30)

    # Bottom info bar
    bar_y = CANVAS[1] - bar_h - 30
    try:
        font_thin = ImageFont.truetype(font_thin_path, 22)
    except Exception:
        font_thin = ImageFont.load_default()

    info_text = "YouTube · Sequoia Capital  |  猫波译站"
    bbox = draw.textbbox((0, 0), info_text, font=font_thin)
    draw.text(
        (CANVAS[0] // 2, bar_y),
        info_text,
        font=font_thin,
        fill=(200, 200, 200),
        anchor="ma",
    )

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=92, optimize=True)

    # Check file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Cover saved: {output_path} ({size_mb:.1f} MB)")

    if size_mb > 5:
        # Re-encode with lower quality
        img.save(str(output_path), "JPEG", quality=75, optimize=True)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Re-compressed to {size_mb:.1f} MB to fit B站 5MB limit")


def main():
    parser = argparse.ArgumentParser(description="Generate B站 video cover")
    parser.add_argument("frame", help="Path to video screenshot (1920x1080 recommended)")
    parser.add_argument("output", help="Output path (cover.jpg)")
    parser.add_argument("--title", required=True, help="Main title text")
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

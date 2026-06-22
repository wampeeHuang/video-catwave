#!/usr/bin/env python3
"""B站视频封面生成器。从视频截图 + 标题文字生成 1920×1080 封面 JPG。

用法:
  python _tools/gen_cover.py <frame.jpg> <output/cover.jpg> --title "主标题" [--sub "副标题"] [--source "出处行"]

设计参数（可命令行覆盖）:
  --brightness 0.80   底图亮度（黑色透明度）
  --color #FFC82D     主色（暖黄）
  --font msyhbd.ttc    中文字体名（覆盖粗体） --font-regular 覆盖常规字重
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
SAFE_W = 1440   # B站首页推荐 4:3 裁剪区宽度（左右各裁 240px）
SAFE_PAD = 60   # 4:3 安全区内边距
YELLOW = (255, 200, 45)       # #FFC82D
WHITE = (252, 250, 245)       # #FCFAF5
FONT_BOLD = "msyhbd.ttc"      # 微软雅黑 Bold — 粗体标题
FONT_REGULAR = "msyh.ttc"     # 微软雅黑 Regular — 副标题、底部信息条
FONT_LIGHT = "msyhl.ttc"      # 微软雅黑 Light — 更轻字重
FONT_FALLBACK = "simhei.ttf"  # 黑体最后回退
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
    """Load Chinese-capable font by weight: bold > regular > light."""
    chains = {
        "bold":    [FONT_BOLD, FONT_REGULAR, FONT_FALLBACK],
        "regular": [FONT_REGULAR, FONT_LIGHT, FONT_FALLBACK, FONT_BOLD],
        "light":   [FONT_LIGHT, FONT_REGULAR, FONT_FALLBACK],
    }
    for name in chains.get(weight, chains["bold"]):
        path = _find_font(name)
        if path:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_cover(
    frame_path: Path,
    output_path: Path,
    title: str,
    subtitle: str = "",
    source_line: str = "",
    brightness: float = BRIGHTNESS,
    accent_color: tuple[int, int, int] = YELLOW,
    layout: str = "C",
    person_side: str = "left",
):
    img = Image.open(frame_path).convert("RGB")
    img = img.resize(CANVAS, Image.LANCZOS)

    draw = ImageDraw.Draw(img)

    # Fit title font size to 4:3 safe area
    title_size = 165
    title_font = _load_font(title_size, "bold")
    tw = draw.textbbox((0, 0), title, font=title_font)[2]
    safe_max = SAFE_W - SAFE_PAD * 2  # 1320px
    if tw > safe_max:
        title_size = int(165 * safe_max / tw)
        print(f"  Title shrunk {165}→{title_size}px to fit 4:3 safe area "
              f"({tw}→{safe_max}px)")

    # Text block: subtitle → accent bar → title (source_line is bottom bar only)
    lines = []
    if title:
        lines.append(("title", title, title_size, accent_color, "bold"))
    if subtitle:
        lines.append(("sub", subtitle, 62, WHITE, "bold"))

    # Calculate text block height
    text_block_h = 0
    for i, (kind, text, size, color, weight) in enumerate(lines):
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_block_h += bbox[3] - bbox[1]
        if i < len(lines) - 1:
            text_block_h += 40 if kind == "title" else 30
    # ── Layout dispatch ──────────────────────────────────────────────────
    if layout == "A":
        _draw_layout_a(img, draw, lines, text_block_h, accent_color, person_side)
    elif layout == "B":
        _draw_layout_b(img, draw, lines, text_block_h, accent_color, brightness)
    elif layout == "D":
        _draw_layout_d(img, draw, lines, text_block_h, accent_color)
    else:  # C (default): centered symmetric
        _draw_layout_c(img, draw, lines, text_block_h, accent_color, brightness)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=92, optimize=True)

    # Validate lengths
    if len(title) > 8:
        print(f"WARNING: Title is {len(title)} chars — methodology recommends 4-8 chars for cover大字")
    if subtitle and len(subtitle) > 16:
        print(f"WARNING: Subtitle is {len(subtitle)} chars — methodology recommends 10-16 chars for L2")

    # Check file size
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Cover saved: {output_path} ({size_mb:.1f} MB)")

    if size_mb > 4.8:
        img.save(str(output_path), "JPEG", quality=75, optimize=True)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Re-compressed to {size_mb:.1f} MB to fit B站 4.8MB limit")


# ── Layout implementations ─────────────────────────────────────────────────

def _draw_layout_a(img, draw, lines, text_block_h, accent_color, person_side):
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(BRIGHTNESS)

    if person_side == "left":
        text_cx = int(CANVAS[0] * 0.72)
        accent_x = int(CANVAS[0] * 0.72)
    else:
        text_cx = int(CANVAS[0] * 0.28)
        accent_x = int(CANVAS[0] * 0.28)

    y = (CANVAS[1] - text_block_h) // 2

    for kind, text, size, color, weight in lines:
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw.text((text_cx, y + text_h // 2), text, font=font, fill=color, anchor="mm")
        y += text_h + (40 if kind == "title" else 30)


def _draw_layout_b(img, draw, lines, text_block_h, accent_color, brightness):
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)

    pad_x, pad_y = 60, 40
    box_w = CANVAS[0] - pad_x * 2
    box_h = text_block_h + pad_y * 2
    box_x, box_y = pad_x, (CANVAS[1] - box_h) // 2 - 30

    overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 128))
    img.paste(overlay, (box_x, box_y), overlay)

    draw_on = ImageDraw.Draw(img)
    y = box_y + pad_y + 10

    for kind, text, size, color, weight in lines:
        font = _load_font(size, weight)
        bbox = draw_on.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw_on.text((CANVAS[0] // 2, y + text_h // 2), text, font=font, fill=color, anchor="mm")
        y += text_h + (40 if kind == "title" else 30)


def _draw_layout_c(img, draw, lines, text_block_h, accent_color, brightness):
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(brightness)

    y = (CANVAS[1] - text_block_h) // 2 - 40

    for kind, text, size, color, weight in lines:
        font = _load_font(size, weight)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw.text((CANVAS[0] // 2, y + text_h // 2), text, font=font, fill=color, anchor="mm")
        y += text_h + (40 if kind == "title" else 30)


def _draw_layout_d(img, draw, lines, text_block_h, accent_color):
    bar_h = int(CANVAS[1] * 0.35)
    canvas = Image.new("RGB", CANVAS, (20, 20, 20))

    img_cropped = img.resize((CANVAS[0], CANVAS[1] - bar_h), Image.LANCZOS)
    canvas.paste(img_cropped, (0, bar_h))

    draw_on = ImageDraw.Draw(canvas)

    y = (bar_h - text_block_h) // 2
    text_cx = CANVAS[0] // 2

    for kind, text, size, color, weight in lines:
        font = _load_font(size, weight)
        bbox = draw_on.textbbox((0, 0), text, font=font)
        text_h = bbox[3] - bbox[1]
        draw_on.text((text_cx, y + text_h // 2), text, font=font, fill=color, anchor="mm")
        y += text_h + (40 if kind == "title" else 30)

    img.paste(canvas)


def main():
    parser = argparse.ArgumentParser(description="Generate B站 video cover")
    parser.add_argument("frame", help="Path to video screenshot (1920x1080 recommended)")
    parser.add_argument("output", help="Output path (cover.jpg)")
    parser.add_argument("--title", required=True, help="Main title text")
    parser.add_argument("--sub", default="", help="Subtitle / second line")
    parser.add_argument("--source", default="", help="Source attribution line")
    parser.add_argument("--brightness", type=float, default=BRIGHTNESS)
    parser.add_argument("--color", default="#FFC82D", help="Accent color hex")
    parser.add_argument("--layout", default="C", choices=["A", "B", "C", "D"],
                        help="Layout: A=person+text split, B=overlay box, C=centered, D=top/bottom split")
    parser.add_argument("--person-side", default="left", choices=["left", "right"],
                        help="Person position for layout A (default: left)")
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
        layout=args.layout,
        person_side=args.person_side,
    )


if __name__ == "__main__":
    main()

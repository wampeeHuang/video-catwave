#!/usr/bin/env python3
"""Cover verifier: checks cover.jpg against gen_cover.py spec.

Usage:
  python tools/validate_cover.py --slug <slug> [--frame <frame.jpg>]

This is the VERIFICATION layer. Production layer: gen_cover.py.
The constants below mirror gen_cover.py — both files MUST be updated together.
They form the dual-layer truth: one produces, one verifies.

Checks:
  1. File exists, is valid JPEG, readable by PIL
  2. Dimensions 1920×1080
  3. File size 80KB–5MB (B站 upload limit)
  4. Yellow text present (#FFC82D range, ≥0.3% coverage)
  5. White text present (#FCFAF5 range, ≥0.1% coverage) if --expect-sub
  6. Brightness ≤ source frame × 0.88 (darkening applied) if --frame given
  7. Text centered (yellow pixels concentrated in middle 60% band)
  8. Font availability (msyhbd.ttc on disk)
  9. White text cluster count — >1 cluster flags possible extra branding text

LIMITATION: Cannot verify rendered text content without OCR.
Channel branding (猫波译站/猫波信号站) on cover is a HUMAN-REVIEW gate.
See AGENT_GUIDE.md §3 for correct --sub format: "<嘉宾身份> · <来源>"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import slug_dir
from cover_design import (
    CANVAS, YELLOW, WHITE, FONT_BOLD,
    MIN_TITLE_PX, MIN_SUB_FS,
    EXPECTED_BRIGHTNESS_FACTOR,
    YELLOW_MIN_COVERAGE, WHITE_MIN_COVERAGE,
    MIN_FILE_SIZE_KB, MAX_FILE_SIZE_MB,
)

# validate_cover measures actual rendered pixel height, which is ~10px less
# than the PT font size due to PIL font metrics. Adjust threshold accordingly.
MIN_TITLE_PX = MIN_TITLE_PX - 10
MIN_SUB_PX = MIN_SUB_FS - 10


def validate_cover(slug: str, frame_path: Path | str | None = None,
                   expect_sub: bool = True) -> tuple[bool, list[str]]:
    sdir = slug_dir(slug)
    cover = sdir / "cover.jpg"
    results: list[str] = []
    all_ok = True

    # 1. Existence + validity
    if not cover.exists():
        return False, [f"[FAIL] cover.jpg 不存在: {cover}"]
    if cover.stat().st_size == 0:
        return False, [f"[FAIL] cover.jpg 是空文件"]

    try:
        from PIL import Image
        img = Image.open(cover)
        img.verify()
        img = Image.open(cover).convert("RGB")  # re-open after verify
    except Exception as e:
        return False, [f"[FAIL] cover.jpg 无法作为图像读取: {e}"]

    # 2. Dimensions
    w, h = img.size
    if (w, h) != CANVAS:
        results.append(f"[FAIL] 尺寸 {w}×{h}，期望 {CANVAS[0]}×{CANVAS[1]}")
        all_ok = False
    else:
        results.append(f"[OK] 尺寸 {w}×{h}")

    # 3. File size
    size_kb = cover.stat().st_size / 1024
    size_mb = size_kb / 1024
    if size_kb < MIN_FILE_SIZE_KB:
        results.append(f"[FAIL] 文件 {size_kb:.0f}KB 过小（<{MIN_FILE_SIZE_KB}KB），可能未渲染文字")
        all_ok = False
    elif size_mb > MAX_FILE_SIZE_MB:
        results.append(f"[WARN] 文件 {size_mb:.1f}MB 接近B站上限（≤5MB）")
    else:
        results.append(f"[OK] 文件大小 {size_kb:.0f}KB ({size_mb:.2f}MB)")

    # 4. Yellow text presence
    try:
        pixels = list(img.get_flattened_data())
    except AttributeError:
        pixels = list(img.getdata())
    total = len(pixels)

    yellow_count = 0
    white_count = 0
    yellow_x_sum = 0
    for i, (r, g, b) in enumerate(pixels):
        if r > 220 and g > 170 and b < 80:
            yellow_count += 1
            yellow_x_sum += i % w
        if r > 240 and g > 240 and b > 230:
            white_count += 1

    yellow_cov = yellow_count / total
    if yellow_cov < YELLOW_MIN_COVERAGE:
        results.append(f"[FAIL] 暖黄文字覆盖率 {yellow_cov:.2%} < {YELLOW_MIN_COVERAGE:.1%}，文字可能缺失")
        all_ok = False
    else:
        results.append(f"[OK] 暖黄文字 ({yellow_cov:.2%} 覆盖)")

    # 5. White text (subtitle)
    white_cov = white_count / total
    if expect_sub and white_cov < WHITE_MIN_COVERAGE:
        results.append(f"[WARN] 暖白文字覆盖率 {white_cov:.2%} < {WHITE_MIN_COVERAGE:.1%}，副标题可能缺失")
    elif white_cov >= WHITE_MIN_COVERAGE:
        results.append(f"[OK] 暖白文字 ({white_cov:.2%} 覆盖)")

    # 5b. White text cluster count — multiple clusters = possible extra branding
    if white_count > 0:
        white_rows = [0] * h
        for idx in range(total):
            r, g, b = pixels[idx]
            if r > 240 and g > 240 and b > 230:
                white_rows[idx // w] += 1
        clusters = 0
        in_cluster = False
        for cnt in white_rows:
            if cnt >= 20 and not in_cluster:
                clusters += 1; in_cluster = True
            elif cnt < 20 and in_cluster:
                in_cluster = False
        if clusters > 1:
            results.append(f"[WARN] 白字检测到 {clusters} 个独立行 — 可能含频道水印，需人工审查")

    # 6. Brightness check (needs source frame)
    if frame_path:
        frame_path = Path(frame_path)
        if frame_path.exists():
            try:
                frame = Image.open(frame_path).convert("RGB")
                frame = frame.resize(CANVAS, Image.LANCZOS)
                try:
                    frame_pixels = list(frame.get_flattened_data())
                except AttributeError:
                    frame_pixels = list(frame.getdata())
                cover_sum = sum(r + g + b for r, g, b in pixels) / (total * 3)
                frame_sum = sum(r + g + b for r, g, b in frame_pixels) / (total * 3)
                ratio = cover_sum / max(frame_sum, 1)
                if ratio > EXPECTED_BRIGHTNESS_FACTOR:
                    results.append(f"[WARN] 亮度比 {ratio:.2f} > {EXPECTED_BRIGHTNESS_FACTOR}，底图可能未压暗")
                else:
                    results.append(f"[OK] 亮度比 {ratio:.2f}（压暗已应用）")
            except Exception as e:
                results.append(f"[WARN] 无法检查亮度: {e}")

    # 7. Text centering
    if yellow_count > 0:
        avg_x = yellow_x_sum / yellow_count
        left_margin = avg_x / w
        if 0.25 < left_margin < 0.75:
            results.append(f"[OK] 文字居中 (avg x={avg_x:.0f}px, {left_margin:.1%} from left)")
        else:
            results.append(f"[WARN] 文字可能未居中 (avg x={avg_x:.0f}px, {left_margin:.1%} from left)")

    # 8. Font size estimation — yellow pixel row spans → approximate px height
    yellow_rows = [0] * h
    for idx in range(total):
        r, g, b = pixels[idx]
        if r > 220 and g > 170 and b < 80:
            yellow_rows[idx // w] += 1

    max_yellow_span = 0
    cur_span = 0
    for cnt in yellow_rows:
        if cnt >= 5:
            cur_span += 1
            max_yellow_span = max(max_yellow_span, cur_span)
        else:
            cur_span = 0

    if max_yellow_span > 0 and max_yellow_span < MIN_TITLE_PX:
        results.append(f"[FAIL] 标题字号约 {max_yellow_span}px < {MIN_TITLE_PX}px 最小限制，文字过小看不清")
        all_ok = False
    elif max_yellow_span > 0:
        results.append(f"[OK] 标题字号约 {max_yellow_span}px (≥{MIN_TITLE_PX}px)")

    # 9. Font availability
    fonts_dir = Path("C:/Windows/Fonts")
    font_path = fonts_dir / FONT_BOLD
    if font_path.exists():
        results.append(f"[OK] 字体 {FONT_BOLD} 可用")
    else:
        results.append(f"[WARN] 字体 {FONT_BOLD} 未找到，gen_cover.py 将回退 SimHei")

    return all_ok, results


def main():
    p = argparse.ArgumentParser(description="验证封面是否符合 gen_cover.py 管线规范")
    p.add_argument("--slug", required=True, help="Video slug")
    p.add_argument("--frame", default=None, help="源截图路径（用于亮度对比检查）")
    p.add_argument("--no-sub", action="store_true", help="不检查副标题白字")
    args = p.parse_args()

    ok, results = validate_cover(args.slug, args.frame, expect_sub=not args.no_sub)
    for r in results:
        print(r)
    status = "PASS" if ok else "FAIL"
    print(f"\n{'COVER OK' if ok else 'COVER NEEDS FIX'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

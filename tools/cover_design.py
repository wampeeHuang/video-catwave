"""Cover design contract — single source of truth for gen_cover.py + validate_cover.py + orchestrator.py.

All design parameters, thresholds, and detection logic live here.
Rendering and validation import from this file; no design constant is duplicated.
"""

from dataclasses import dataclass

# ── Canvas & safe area ────────────────────────────────────────────────────
CANVAS = (1920, 1080)
SAFE_W = 1440           # 4:3 safe area width within 16:9 canvas
SAFE_PAD = 60           # left/right padding within safe area

# ── Color palette ─────────────────────────────────────────────────────────
YELLOW = (255, 200, 45)     # #FFC82D — title
WHITE = (252, 250, 245)     # #FCFAF5 — subtitle

# ── Font stack ────────────────────────────────────────────────────────────
FONT_BOLD = "msyhbd.ttc"
FONT_REGULAR = "msyh.ttc"
FONT_FALLBACK = "simhei.ttf"

# ── Font sizes ────────────────────────────────────────────────────────────
MAX_TITLE_FS = 165      # max title font size before shrinking
MAX_SUB_FS = 62         # max subtitle font size before shrinking
MIN_TITLE_FS = 130      # hard floor — ~10 CJK chars at 120px safe width
MIN_SUB_FS = 48         # hard floor for subtitle

# ── Title length ──────────────────────────────────────────────────────────
# Estimated max CJK characters that fit at MIN_TITLE_FS within safe area
MAX_COVER_CHARS = SAFE_W // (MIN_TITLE_FS * 0.85)  # ≈12 (0.85 accounts for inter-char spacing)


@dataclass
class CoverParams:
    """Computed cover parameters passed to gen_cover.generate_cover()."""
    position: str       # "center" | "bottom"
    overlay: int        # 0-100, black overlay opacity
    brightness: float   # PIL brightness factor (0.0-1.0)
    accent_color: tuple[int, int, int]


# ── Image adjustments ─────────────────────────────────────────────────────
BRIGHTNESS = 0.80


def detect_position(skin_ratio: float) -> str:
    """Return 'bottom' if person is centered in frame, else 'center'."""
    if skin_ratio is None:
        return "center"
    return "bottom" if skin_ratio > 0.05 else "center"


def detect_overlay(avg_luminance: float) -> int:
    """Return overlay opacity (0-100). Brighter frames get deeper overlay."""
    if avg_luminance < 0:
        return 10  # unmeasurable, use safe default
    return 15 if avg_luminance > 110 else 10


def compute_params(skin_ratio: float | None = None, avg_luminance: float = -1.0) -> CoverParams:
    """One-shot: derive all cover params from frame signals."""
    return CoverParams(
        position=detect_position(skin_ratio or 0),
        overlay=detect_overlay(avg_luminance),
        brightness=BRIGHTNESS,
        accent_color=YELLOW,
    )


# ── Validation thresholds (mirrored in validate_cover.py) ──────────────────
YELLOW_MIN_COVERAGE = 0.003    # ≥0.3% yellow pixels
WHITE_MIN_COVERAGE = 0.001     # ≥0.1% white pixels
MIN_FILE_SIZE_KB = 80
MAX_FILE_SIZE_MB = 5.0
EXPECTED_BRIGHTNESS_FACTOR = 0.88

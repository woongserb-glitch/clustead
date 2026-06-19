"""단지별 동적 OG(오픈그래프) 썸네일 PNG 생성.

카카오톡·네이버(카페/블로그)·페이스북 등 링크 미리보기는 SVG를 렌더링하지
않으므로(JPG/PNG만 지원), 1200x630 PNG를 Pillow로 생성한다. 단지명·위치·강점
카테고리(S/A 등급)를 박아 클릭 유도력을 높인다.

- 생성 비용을 줄이기 위해 결과를 디스크에 캐시한다(필드 해시 기준).
- 한글 폰트는 번들 → 나눔(도커) → 맑은고딕(윈도우 개발) 순으로 탐색한다.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 브랜드 팔레트(static/brand/og-clustead.svg 기준)
NAVY = (21, 36, 59)        # #15243B 배경
WHITE = (255, 255, 255)
GRAY = (154, 167, 184)     # #9AA7B8 보조 텍스트
BLUE = (91, 141, 239)      # #5B8DEF 강조

# 등급별 칩 색상(style.css .grade-* 의 라이트 배지 톤)
GRADE_CHIP = {
    "S": ((234, 248, 241), (31, 122, 85)),
    "A": ((238, 247, 242), (47, 143, 107)),
    "B": ((238, 244, 250), (85, 122, 149)),
    "C": ((255, 246, 232), (183, 107, 43)),
    "D": ((255, 240, 237), (180, 83, 59)),
}

WIDTH, HEIGHT = 1200, 630
MARGIN = 90

# 캐시 무효화용 — 레이아웃/디자인을 바꾸면 올린다.
TEMPLATE_VERSION = "1"

_BASE_DIR = Path(__file__).resolve().parent.parent
_BUNDLED_FONT_DIR = _BASE_DIR / "static" / "fonts"

# (regular, bold) 후보 경로. 앞에서부터 존재하는 것을 사용.
_FONT_CANDIDATES = [
    (_BUNDLED_FONT_DIR / "NanumGothic.ttf", _BUNDLED_FONT_DIR / "NanumGothicBold.ttf"),
    (Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
     Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")),
    (Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"),
     Path("/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf")),
    (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgun.ttf",
     Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgunbd.ttf"),
]

_resolved_fonts = None  # (regular_path, bold_path) 캐시


def _resolve_font_paths():
    global _resolved_fonts
    if _resolved_fonts is not None:
        return _resolved_fonts
    for regular, bold in _FONT_CANDIDATES:
        if regular.exists():
            _resolved_fonts = (str(regular), str(bold) if bold.exists() else str(regular))
            return _resolved_fonts
    # 한글 폰트를 못 찾으면 Pillow 기본 폰트로라도 동작(한글은 깨질 수 있음).
    _resolved_fonts = (None, None)
    return _resolved_fonts


def _font(size, bold=False):
    regular, bold_path = _resolve_font_paths()
    path = bold_path if bold else regular
    if path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


def fonts_available():
    """한글 폰트가 실제로 잡혔는지(번들/시스템) 여부."""
    return _resolve_font_paths()[0] is not None


def _text_width(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)[2]


def _fit_font(draw, text, max_width, start_size, min_size, bold=True):
    """텍스트가 max_width를 넘지 않는 가장 큰 폰트를 찾는다."""
    size = start_size
    while size > min_size:
        font = _font(size, bold=bold)
        if _text_width(draw, text, font) <= max_width:
            return font
        size -= 4
    return _font(min_size, bold=bold)


def _draw_aperture(draw, cx, cy, scale, color):
    """og-clustead.svg 의 6엽 조리개 마크를 단순 다각형으로 재현."""
    import math
    base = [(50, 9), (85.5, 29.5), (65, 49.5), (57, 36.8)]
    for i, deg in enumerate((0, 60, 120, 180, 240, 300)):
        rad = math.radians(deg)
        cos, sin = math.cos(rad), math.sin(rad)
        pts = []
        for x, y in base:
            dx, dy = x - 50, y - 50
            rx = dx * cos - dy * sin
            ry = dx * sin + dy * cos
            pts.append((cx + rx * scale, cy + ry * scale))
        fill = color if i != 1 else (color[0], color[1], color[2], 110)
        draw.polygon(pts, fill=color)


def render_apartment_og(name, location, chips):
    """단지 OG PNG(bytes) 생성.

    name: 단지명, location: "송파구 가락동", chips: [(label, grade), ...] 상위 강점.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(img)

    # 상단 브랜드 라인
    _draw_aperture(draw, MARGIN + 18, 92, 0.62, WHITE)
    brand_font = _font(34, bold=True)
    draw.text((MARGIN + 52, 74), "C L U S T E A D", font=brand_font, fill=WHITE)

    # 라벨
    label_font = _font(30, bold=True)
    draw.text((MARGIN, 196), "서울 생활 인프라 분석", font=label_font, fill=BLUE)

    # 단지명(폭에 맞춰 자동 축소)
    name = (name or "").strip() or "서울 아파트"
    name_font = _fit_font(draw, name, WIDTH - MARGIN * 2, 96, 52, bold=True)
    draw.text((MARGIN, 244), name, font=name_font, fill=WHITE)

    # 위치
    loc_y = 244 + (name_font.size + 22)
    if location:
        loc_font = _font(40, bold=False)
        draw.text((MARGIN, loc_y), location, font=loc_font, fill=GRAY)

    # 강점 칩(상위 3개)
    chip_y = 470
    chip_x = MARGIN
    chip_font = _font(30, bold=True)
    for label, grade in (chips or [])[:3]:
        grade = (grade or "").upper()
        bg, fg = GRADE_CHIP.get(grade, GRADE_CHIP["B"])
        text = f"{label} {grade}" if grade else label
        tw = _text_width(draw, text, chip_font)
        pad_x, pad_h = 26, 56
        if chip_x + tw + pad_x * 2 > WIDTH - MARGIN:
            break
        draw.rounded_rectangle(
            [chip_x, chip_y, chip_x + tw + pad_x * 2, chip_y + pad_h],
            radius=pad_h // 2, fill=bg,
        )
        draw.text((chip_x + pad_x, chip_y + (pad_h - chip_font.size) // 2 - 2),
                  text, font=chip_font, fill=fg)
        chip_x += tw + pad_x * 2 + 16

    # 하단 도메인
    domain_font = _font(28, bold=False)
    draw.text((MARGIN, HEIGHT - 70), "clustead.com", font=domain_font, fill=BLUE)

    return _to_png(img)


def render_default_og(tagline="집값이 아니라 생활 인프라로 보는 서울 아파트"):
    """홈/탐색/비교/지역 페이지용 기본 브랜드 OG PNG(bytes)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(img)

    _draw_aperture(draw, WIDTH // 2, 232, 1.25, WHITE)
    wordmark = _font(92, bold=True)
    tw = _text_width(draw, "CLUSTEAD", wordmark)
    draw.text(((WIDTH - tw) // 2, 300), "CLUSTEAD", font=wordmark, fill=WHITE)

    sub = _font(32, bold=False)
    tw = _text_width(draw, tagline, sub)
    draw.text(((WIDTH - tw) // 2, 432), tagline, font=sub, fill=GRAY)

    dom = _font(28, bold=False)
    tw = _text_width(draw, "clustead.com", dom)
    draw.text(((WIDTH - tw) // 2, 520), "clustead.com", font=dom, fill=BLUE)

    return _to_png(img)


def _to_png(img):
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def cache_key(name, location, chips):
    raw = "|".join([
        TEMPLATE_VERSION,
        name or "",
        location or "",
        ",".join(f"{l}:{g}" for l, g in (chips or [])),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

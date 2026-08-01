#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PWA 홈화면 아이콘(PNG) 생성 — static/favicon.svg 의 APERTURE 마크를 그대로 래스터화.

favicon.svg 는 SVG 라 홈화면 아이콘으로 못 쓴다(안드로이드/iOS 모두 PNG 요구).
cairosvg 같은 SVG 렌더러를 런타임 의존성에 추가하지 않으려고, 마크의 폴리곤
좌표를 여기서 직접 재현해 Pillow 로 그린다. 좌표/색을 favicon.svg 와 동기화할 것.

출력(static/icons/):
  icon-192.png            안드로이드 홈화면(any)
  icon-512.png            스플래시/스토어(any)
  icon-512-maskable.png   안드로이드 적응형 아이콘(maskable) — 마크를 작게 두어
                          원형/스퀴클로 잘려도 안 잘리는 세이프존 확보
  apple-touch-icon.png    iOS 홈화면(180x180). iOS 가 자체 마스크를 씌우므로
                          모서리 라운딩 없이 꽉 찬 사각형으로 낸다.

실행: python scripts/generate_pwa_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

# favicon.svg 와 동일한 브랜드 값.
BG = (21, 36, 59)          # #15243B
MARK = (255, 255, 255)     # #FFFFFF
BLADE = [(50, 9), (85.5, 29.5), (65, 49.5), (57, 36.8)]
ANGLES = [0, 60, 120, 180, 240, 300]
FADED_ANGLE = 60           # 우측 블레이드만 반투명(=열린 C 공간)
FADED_ALPHA = 102          # 0.4 * 255

SS = 4                     # 슈퍼샘플링 배율(계단현상 제거용)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "static", "icons")


def _rotate(x, y, deg, cx=50.0, cy=50.0):
    r = math.radians(deg)
    dx, dy = x - cx, y - cy
    return (cx + dx * math.cos(r) - dy * math.sin(r),
            cy + dx * math.sin(r) + dy * math.cos(r))


def _draw_mark(img, size, content_frac):
    """100x100 로고 박스를 캔버스 중앙에 content_frac 비율로 그린다."""
    scale = size * content_frac / 100.0
    off = (size - size * content_frac) / 2.0

    def to_px(x, y):
        return (off + x * scale, off + y * scale)

    for deg in ANGLES:
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pts = [to_px(*_rotate(x, y, deg)) for x, y in BLADE]
        ImageDraw.Draw(layer).polygon(
            pts,
            fill=MARK + (FADED_ALPHA if deg == FADED_ANGLE else 255,),
        )
        img.alpha_composite(layer)


def make_icon(path, size, radius_frac=0.22, content_frac=0.80):
    """radius_frac: 모서리 라운딩(캔버스 대비). 0 이면 사각형(iOS 용)."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    bg = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    if radius_frac > 0:
        d.rounded_rectangle([0, 0, big - 1, big - 1],
                            radius=big * radius_frac, fill=BG + (255,))
    else:
        d.rectangle([0, 0, big - 1, big - 1], fill=BG + (255,))
    img.alpha_composite(bg)

    _draw_mark(img, big, content_frac)

    img = img.resize((size, size), Image.LANCZOS)
    img.save(path, "PNG", optimize=True)
    print(f"  {os.path.relpath(path, ROOT)}  ({size}x{size})")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("PWA 아이콘 생성:")
    make_icon(os.path.join(OUT_DIR, "icon-192.png"), 192)
    make_icon(os.path.join(OUT_DIR, "icon-512.png"), 512)
    # maskable: 안드로이드가 최대 ~20% 를 잘라내므로 마크를 60% 로 축소하고
    # 배경은 모서리 라운딩 없이 꽉 채운다(OS 가 원형/스퀴클로 마스킹).
    make_icon(os.path.join(OUT_DIR, "icon-512-maskable.png"), 512,
              radius_frac=0.0, content_frac=0.60)
    # iOS: 투명/라운딩 없이. iOS 가 알아서 스퀴클 마스크를 씌운다.
    make_icon(os.path.join(OUT_DIR, "apple-touch-icon.png"), 180,
              radius_frac=0.0, content_frac=0.68)
    print("완료.")


if __name__ == "__main__":
    main()

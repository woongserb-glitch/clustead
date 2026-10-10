"""동별 건물 위치 공용 함수 — baseline 빌더(지하철·버스·한강·교육환경)가 같이 쓴다.

원천: data/derived/vworld/complex_buildings_v5.jsonl (브이월드 도로명주소 건물 + 건축물대장 + 카카오로
마스터 단지와 매칭한 동 건물 윤곽). 원칙(2026-10-10):
  - 등급 지표는 각 동에서 대표 좌표처럼 계산한 값의 중간값(중간 동). 대단지 끝 동 하나가 시설에 붙었다고
    단지 전체가 좋게 나오지 않고, 대표 좌표가 어디 찍혔는지에 휘둘리지도 않는다.
  - 목록·필터는 동 전체를 합치고 항목마다 '몇 개 동' 을 남긴다.
  - 동 건물이 2개 미만인 단지는 대표 좌표 그대로.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BUILDINGS_PATH = BASE_DIR / "data" / "derived" / "vworld" / "complex_buildings_v5.jsonl"


def _clean(value):
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def complex_key(name, gu, dong):
    return (_clean(name), _clean(gu), _clean(dong))


def load_dong_points(path=BUILDINGS_PATH):
    """{(이름, 구, 동): [(lat, lng), …]} — 단지의 각 동 건물 중심. 파일이 없으면 빈 dict."""
    path = Path(path)
    if not path.exists():
        return {}
    from shapely.geometry import shape

    points = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            pts = []
            for building in row.get("buildings", []):
                try:
                    c = shape(building["geom"]).centroid
                    pts.append((c.y, c.x))
                except Exception:
                    continue
            if pts:
                points[complex_key(*row["key"])] = pts
    return points


def points_for(dong_points, name, gu, dong, lat, lng):
    """동 건물이 2개 이상이면 그 중심들, 아니면 대표 좌표 하나. (points, basis)"""
    pts = dong_points.get(complex_key(name, gu, dong)) or []
    if len(pts) >= 2:
        return pts, "dong"
    return [(float(lat), float(lng))], "center"


def median_low(values):
    ordered = sorted(v for v in values if v is not None and v != "")
    return ordered[(len(ordered) - 1) // 2] if ordered else ""


class GridIndex:
    """위경도 격자 버킷 — '이 점 반경 R m 안의 항목' 을 전수 스캔 없이 찾는다."""

    def __init__(self, items, lat_key="lat", lng_key="lng", cell_deg=0.01):
        self.cell = cell_deg
        self.buckets = {}
        for item in items:
            try:
                lat, lng = float(item[lat_key]), float(item[lng_key])
            except (KeyError, TypeError, ValueError):
                continue
            self.buckets.setdefault((int(lat / cell_deg), int(lng / cell_deg)), []).append(item)

    def near(self, lat, lng, radius_m):
        span = int(radius_m / (self.cell * 88000)) + 1
        ci, cj = int(lat / self.cell), int(lng / self.cell)
        for i in range(ci - span, ci + span + 1):
            for j in range(cj - span, cj + span + 1):
                yield from self.buckets.get((i, j), ())

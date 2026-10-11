"""카카오 3종(편의점·카페·슈퍼) 동별 계산 공용 — 동마다 API 를 부르지 않고 가까운 동끼리 묶어 조회한다.

원칙은 scripts/dong_points 와 같다(등급 지표 = 중간 동, 목록 = 동 전체 합침). 다만 카카오는 호출
비용이 있어(편의점·카페는 카테고리 + 브랜드별 키워드 검색), 동 건물이 GRID_M 보다 넓게 퍼진 단지만
GRID_M 격자로 동을 묶어 묶음 중심에서 한 번 조회하고, 각 동까지 거리는 그 결과로 다시 잰다.
묶음 중심에서 가장 먼 동까지 거리만큼 조회 반경을 넓혀 받아서, 어느 동 기준으로도 반경 안 매장을
빠뜨리지 않는다. 동이 GRID_M 안에 모인 단지는 예전처럼 대표 좌표 한 점(기존 캐시 그대로)이다.
"""

import math

from scripts.dong_points import load_dong_points, points_for

GRID_M = 150
M_PER_DEG_LAT = 111000
M_PER_DEG_LNG = 88400   # 위도 37.5° 근사


def _dist(a, b):
    return math.hypot((a[0] - b[0]) * M_PER_DEG_LAT, (a[1] - b[1]) * M_PER_DEG_LNG)


def query_groups(dong_points, apartment):
    """(basis, [(조회 지점, 반경 여유 m, [그 지점이 맡는 동 점들])]).

    basis="center" 이면 조회 지점은 대표 좌표 하나, 맡는 점도 대표 좌표 하나."""
    lat, lng = float(apartment["lat"]), float(apartment["lng"])
    points, basis = points_for(dong_points, apartment["name"], apartment["gu"], apartment["dong"], lat, lng)
    if basis != "dong":
        return "center", [((lat, lng), 0, [(lat, lng)])]
    center = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    if max(_dist(p, center) for p in points) <= GRID_M:
        return "center", [((lat, lng), 0, [(lat, lng)])]
    cells = {}
    for p in points:
        cells.setdefault((int(p[0] * M_PER_DEG_LAT // GRID_M), int(p[1] * M_PER_DEG_LNG // GRID_M)), []).append(p)
    groups = []
    for members in cells.values():
        q = (round(sum(p[0] for p in members) / len(members), 6), round(sum(p[1] for p in members) / len(members), 6))
        slack = max(_dist(p, q) for p in members)
        groups.append((q, int(math.ceil(slack / 10.0) * 10), members))
    return "dong", groups


def with_distance(places, lat, lng):
    """조회 지점 기준 distance 를 이 동 기준으로 다시 잰 사본(빌더 헬퍼들이 place["distance"] 를 쓴다)."""
    from services.geo_service import get_distance_m

    out = []
    for place in places:
        try:
            d = get_distance_m(lat, lng, float(place["lat"]), float(place["lng"]))
        except (KeyError, TypeError, ValueError):
            continue
        out.append({**place, "distance": int(round(d))})
    out.sort(key=lambda p: p["distance"])
    return out


def union_items(per_dong_items):
    """동마다 만든 카드 목록을 합친다: 같은 매장(이름·좌표)은 한 번, 거리는 가장 가까운 동, 동 수 기록."""
    merged = {}
    for items in per_dong_items:
        for item in items:
            key = (item.get("label"), item.get("lat"), item.get("lng"))
            m = merged.get(key)
            if m is None:
                merged[key] = {**item, "dong_count": 1}
            else:
                m["dong_count"] += 1
                if item.get("distance", 999999) < m.get("distance", 999999):
                    m["distance"] = item["distance"]
    return sorted(merged.values(), key=lambda it: (it.get("distance", 999999), str(it.get("label"))))


__all__ = ["GRID_M", "load_dong_points", "query_groups", "with_distance", "union_items"]

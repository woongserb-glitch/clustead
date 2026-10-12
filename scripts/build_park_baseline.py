"""공원 baseline.

주 지표 park_distance: 단지 대표 좌표에서 '1만㎡ 이상 조성 공원' 윤곽까지 거리(m).
원천은 data/park/vworld_parks.geojson(scripts/build_park_source_vworld.py) — 도시계획시설
공원 중 조성된 곳. 예전에는 서울시 주요 공원 133곳의 대표점까지 거리라 동네 근린·어린이공원이
빠졌다(중앙값 942m → 225m). 원천 파일이 없으면 예전 방식(park.csv 대표점)으로 만든다.

칸: name,gu,dong,lat,lng,nearest_park,park_distance (기존과 같음)
  + park_kind, park_area_m2, park_count_1km, child_park_count_500m, park_items_json(1km 안 공원)
  + park_basis, park_dong_count
  + large_park_name, large_park_distance: 10만㎡ 이상 공원(조건으로 탐색 '대형공원') 윤곽까지 거리, 동별이면
    중간 동 값(2026-10-12). 예전엔 탐색이 대표 좌표→서울시 주요공원 대표점으로 따로 계산해 카드와 어긋났다.

동별(scripts/dong_points 원칙, 2026-10-11): 동 건물마다 '1만㎡ 이상 공원까지 거리' 를 재고 등급 지표
park_distance 는 중간 동 값. 대표 공원은 가장 많은 동이 가장 가깝다고 꼽은 공원. 목록은 어느 동에서든
1km 안인 공원을 합치고, 거리는 가장 가까운 동 기준 + 그 공원까지 동마다 거리 범위(nearest_min/max).
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.preload_service import (  # noqa: E402
    load_apartment_data,
    apartment_data,
    load_park_data,
    park_data,
)
from services.baseline_builder_service import find_nearest_place  # noqa: E402
from scripts.dong_points import load_dong_points, median_low, points_for  # noqa: E402

SOURCE = "data/park/vworld_parks.geojson"
OUTPUT = "data/baseline/park_baseline.csv"
BIG_M2 = 10000          # 주 지표 대상 공원 면적
LARGE_M2 = 100000       # 대형공원(카드 칩·탐색 필터와 같은 기준)
LIST_RADIUS_M = 1000    # 카드·지도 목록 반경(걸어서 가는 거리)
MAX_ITEMS = 80          # 카드의 "1km 안 공원 N곳" 이 실제 개수가 되도록 넉넉히
DEG = 1 / 111000


def build_from_vworld():
    from shapely.geometry import Point, shape
    from shapely.ops import nearest_points
    from shapely.strtree import STRtree

    feats = json.load(open(SOURCE, encoding="utf-8"))["features"]
    geoms = [shape(f["geometry"]) for f in feats]
    props = [f["properties"] for f in feats]
    tree = STRtree(geoms)
    print(f"[PARK] 원천 공원 {len(feats)}곳 (1만㎡ 이상 {sum(1 for p in props if p['area_m2'] >= BIG_M2)})")

    def dist_m(g, pt):
        # 위도 37.5° 근사(경도 1° ≈ 88.4km)로 미터 환산. 단지가 공원 안이면 0.
        a, b = nearest_points(g, pt)
        return ((a.y - b.y) * 111000) ** 2 + ((a.x - b.x) * 88400) ** 2, a

    big_idx = [i for i, p in enumerate(props) if p["area_m2"] >= BIG_M2]
    large_idx = [i for i, p in enumerate(props) if p["area_m2"] >= LARGE_M2]
    large_tree = STRtree([geoms[i] for i in large_idx])

    def nearest_large(lat, lng):
        """가장 가까운 10만㎡ 이상 공원 (d, i). 도 단위 최근접으로 후보를 잡고 미터로 다시 잰다."""
        pt = Point(float(lng), float(lat))
        if not large_idx:
            return None
        k = int(large_tree.nearest(pt))
        rough = round(dist_m(geoms[large_idx[k]], pt)[0] ** 0.5)
        best = None
        for j in large_tree.query(pt.buffer(max(rough, 50) * DEG * 1.4)):
            i = large_idx[int(j)]
            d = round(dist_m(geoms[i], pt)[0] ** 0.5)
            if best is None or (d, i) < best:
                best = (d, i)
        return best

    def compute_at(lat, lng):
        """한 점에서: 1km 안 공원 [(d, i, edge)], 가장 가까운 1만㎡ 이상 공원 (d, i)."""
        pt = Point(float(lng), float(lat))
        near = []
        for i in tree.query(pt.buffer(LIST_RADIUS_M * DEG * 1.3)):
            i = int(i)
            d2, edge = dist_m(geoms[i], pt)
            d = round(d2 ** 0.5)
            if d <= LIST_RADIUS_M:
                near.append((d, i, edge))
        near.sort(key=lambda x: (x[0], x[1]))
        big = next(((d, i) for d, i, _ in near if props[i]["area_m2"] >= BIG_M2), None)
        if big is None:  # 목록 반경 안에 큰 공원이 없으면 서울 전체에서 찾는다
            best = None
            for i in big_idx:
                d2, _ = dist_m(geoms[i], pt)
                if best is None or d2 < best[0]:
                    best = (d2, i)
            big = (round(best[0] ** 0.5), best[1]) if best else None
        return near, big

    def merge_fragments(near):
        """같은 이름·거리 150m 안 조각을 한 공원으로 — [(d, i)] (목록 합치기와 같은 규칙)."""
        kept = []
        for d, i, _ in near:
            if not any(props[j]["name"] == props[i]["name"] and d - e < 150 for e, j in kept):
                kept.append((d, i))
        return kept

    dong_points = load_dong_points()
    rows = []
    for apt in apartment_data:
        points, basis = points_for(dong_points, apt["name"], apt["gu"], apt["dong"], apt["lat"], apt["lng"])
        per_point = [compute_at(lat, lng) for lat, lng in points]
        larges = [x for x in (nearest_large(lat, lng) for lat, lng in points) if x]
        if larges:
            votes = {}
            for d, i in larges:
                votes.setdefault(i, []).append(d)
            large_top = min(votes, key=lambda i: (-len(votes[i]), min(votes[i]), i))
            large = (median_low([d for d, _ in larges]), large_top)
        else:
            large = None

        # 공원별로 동 전체를 합친다: 가장 가까운 동의 거리·윤곽점, 그 공원까지 동마다 거리 범위.
        merged = {}
        for near, _ in per_point:
            for d, i, edge in near:
                m = merged.get(i)
                if m is None:
                    merged[i] = {"d": d, "edge": edge, "min": d, "max": d, "n": 1}
                else:
                    if d < m["d"]:
                        m["d"], m["edge"] = d, edge
                    m["min"], m["max"], m["n"] = min(m["min"], d), max(m["max"], d), m["n"] + 1
        near = sorted(((m["d"], i, m["edge"]) for i, m in merged.items()), key=lambda x: (x[0], x[1]))

        bigs = [b for _, b in per_point if b]
        if bigs and basis == "dong":
            votes = {}
            for d, i in bigs:
                votes.setdefault(i, []).append(d)
            top = min(votes, key=lambda i: (-len(votes[i]), min(votes[i]), i))
            big = (median_low([d for d, _ in bigs]), top)
        else:
            big = bigs[0] if bigs else None

        # 한 공원이 도면에서 여러 조각으로 나뉜 경우(같은 이름·거리 150m 안)는 하나로 합친다.
        items = []
        for d, i, edge in near:
            name = props[i]["name"]
            same = next((it for it in items if it["name"] == name and d - it["distance"] < 150), None)
            if same:
                same["area_m2"] += props[i]["area_m2"]
                continue
            item = {
                "name": name, "subtype": props[i]["kind"], "distance": d,
                "area_m2": props[i]["area_m2"], "lat": round(edge.y, 7), "lng": round(edge.x, 7),
            }
            if basis == "dong":
                m = merged[i]
                item.update({"dong_count": m["n"], "nearest_min": m["min"], "nearest_max": m["max"]})
            items.append(item)
        # 개수 지표는 중간 동 기준(등급과 같은 원칙), 목록은 동 전체.
        park_count = median_low([len(merge_fragments(nr)) for nr, _ in per_point])
        child_count = median_low([
            sum(1 for d, i in merge_fragments(nr) if d <= 500 and "어린이" in props[i]["kind"]) for nr, _ in per_point
        ])
        items = items[:MAX_ITEMS]
        rows.append([
            apt["name"], apt["gu"], apt["dong"], apt["lat"], apt["lng"],
            props[big[1]]["name"] if big else "", big[0] if big else "",
            props[big[1]]["kind"] if big else "", props[big[1]]["area_m2"] if big else "",
            park_count,
            child_count,
            json.dumps(items, ensure_ascii=False),
            basis,
            len(points) if basis == "dong" else 1,
            props[large[1]]["name"] if large else "", large[0] if large else "",
        ])
    return rows


def build_from_major_parks():
    load_park_data()
    rows = []
    for apt in apartment_data:
        nearest, distance = find_nearest_place(apt["lat"], apt["lng"], park_data)
        if nearest is None:
            continue
        rows.append([apt["name"], apt["gu"], apt["dong"], apt["lat"], apt["lng"],
                     nearest["name"], distance, "", "", "", "", "[]", "center", 1, "", ""])
    return rows


def main():
    print("[BUILD] apartment preload")
    load_apartment_data()
    rows = build_from_vworld() if os.path.exists(SOURCE) else build_from_major_parks()
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "gu", "dong", "lat", "lng", "nearest_park", "park_distance",
                         "park_kind", "park_area_m2", "park_count_1km", "child_park_count_500m", "park_items_json",
                         "park_basis", "park_dong_count", "large_park_name", "large_park_distance"])
        writer.writerows(rows)
    print(f"[DONE] {OUTPUT} 생성 완료 ({len(rows)}행)")


if __name__ == "__main__":
    main()

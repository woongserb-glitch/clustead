"""공원 baseline.

주 지표 park_distance: 단지 대표 좌표에서 '1만㎡ 이상 조성 공원' 윤곽까지 거리(m).
원천은 data/park/vworld_parks.geojson(scripts/build_park_source_vworld.py) — 도시계획시설
공원 중 조성된 곳. 예전에는 서울시 주요 공원 133곳의 대표점까지 거리라 동네 근린·어린이공원이
빠졌다(중앙값 942m → 225m). 원천 파일이 없으면 예전 방식(park.csv 대표점)으로 만든다.

칸: name,gu,dong,lat,lng,nearest_park,park_distance (기존과 같음)
  + park_kind, park_area_m2, park_count_1km, child_park_count_500m, park_items_json(1km 안 공원)
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

SOURCE = "data/park/vworld_parks.geojson"
OUTPUT = "data/baseline/park_baseline.csv"
BIG_M2 = 10000          # 주 지표 대상 공원 면적
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

    rows = []
    for apt in apartment_data:
        pt = Point(float(apt["lng"]), float(apt["lat"]))
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
            for i, p in enumerate(props):
                if p["area_m2"] < BIG_M2:
                    continue
                d2, _ = dist_m(geoms[i], pt)
                if best is None or d2 < best[0]:
                    best = (d2, i)
            big = (round(best[0] ** 0.5), best[1]) if best else None
        # 한 공원이 도면에서 여러 조각으로 나뉜 경우(같은 이름·거리 150m 안)는 하나로 합친다.
        items = []
        for d, i, edge in near:
            name = props[i]["name"]
            same = next((it for it in items if it["name"] == name and d - it["distance"] < 150), None)
            if same:
                same["area_m2"] += props[i]["area_m2"]
                continue
            items.append({
                "name": name, "subtype": props[i]["kind"], "distance": d,
                "area_m2": props[i]["area_m2"], "lat": round(edge.y, 7), "lng": round(edge.x, 7),
            })
        park_count = sum(1 for it in items if it["distance"] <= 1000)
        child_count = sum(1 for it in items if it["distance"] <= 500 and "어린이" in it["subtype"])
        items = items[:MAX_ITEMS]
        rows.append([
            apt["name"], apt["gu"], apt["dong"], apt["lat"], apt["lng"],
            props[big[1]]["name"] if big else "", big[0] if big else "",
            props[big[1]]["kind"] if big else "", props[big[1]]["area_m2"] if big else "",
            park_count,
            child_count,
            json.dumps(items, ensure_ascii=False),
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
                     nearest["name"], distance, "", "", "", "", "[]"])
    return rows


def main():
    print("[BUILD] apartment preload")
    load_apartment_data()
    rows = build_from_vworld() if os.path.exists(SOURCE) else build_from_major_parks()
    with open(OUTPUT, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "gu", "dong", "lat", "lng", "nearest_park", "park_distance",
                         "park_kind", "park_area_m2", "park_count_1km", "child_park_count_500m", "park_items_json"])
        writer.writerows(rows)
    print(f"[DONE] {OUTPUT} 생성 완료 ({len(rows)}행)")


if __name__ == "__main__":
    main()

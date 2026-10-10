import json
import math
import pandas as pd

from services.preload_service import (
    load_apartment_data,
    apartment_data,
    load_bus_stop_data,
    bus_stop_data,
    load_bus_route_data,
    bus_route_data,
)

OUTPUT_PATH = "data/baseline/bus_baseline.csv"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dong_points import GridIndex, load_dong_points, median_low, points_for  # noqa: E402


def haversine(lat1, lng1, lat2, lng2):
    R = 6371000

    lat1 = math.radians(lat1)
    lng1 = math.radians(lng1)
    lat2 = math.radians(lat2)
    lng2 = math.radians(lng2)

    dlat = lat2 - lat1
    dlng = lng2 - lng1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlng / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def classify_bus_type(route_name):
    route = str(route_name).strip().upper()

    if not route:
        return "unknown"

    # 심야버스
    if route.startswith("N"):
        return "night"

    # 광역버스 (M버스 / G버스)
    if route.startswith("M") or route.startswith("G"):
        return "express"

    # 마을버스 (한글 포함)
    if any("가" <= ch <= "힣" for ch in route):
        return "village"

    # 숫자 기반
    if route.isdigit():

        # 공항버스
        if route.startswith("6"):
            return "airport"

        # 광역버스: 9000번대(4자리). 일반 4자리 지선 판정보다 먼저 걸러야
        # 9401 등 광역이 '지선'으로 오분류되지 않는다.
        if len(route) == 4 and route.startswith("9"):
            return "express"

        # 지선버스
        if len(route) == 4:
            return "local"

        # 간선버스
        if len(route) == 3:
            return "main"

        # 광역버스
        if route.startswith("9"):
            return "express"

    return "unknown"


print("[LOAD] apartment data")
load_apartment_data()

print("[LOAD] bus stop data")
load_bus_stop_data()

print("[LOAD] bus route data")
load_bus_route_data()

print()

# NODE_ID → route list
route_map = {}

for route in bus_route_data:
    node_id = route.get("node_id")

    if not node_id:
        continue

    if node_id not in route_map:
        route_map[node_id] = set()

    route_map[node_id].add(
        route.get("route_name", "")
    )

print("[ROUTE MAP]", len(route_map))

TYPE_LABEL = {"main": "간선", "local": "지선", "express": "광역", "night": "심야", "village": "마을", "airport": "공항"}
stop_index = GridIndex(bus_stop_data)
dong_points = load_dong_points()
print("[DONG POINTS]", len(dong_points))


def compute_at(lat, lng):
    """한 지점(대표 좌표 또는 동 건물 중심)의 정류장·노선."""
    stop_count_300m = stop_count_500m = 0
    nearest_stop, nearest_distance = "", 999999
    route_set = set()
    items = []
    candidates = list(stop_index.near(lat, lng, 1500)) or bus_stop_data
    for stop in candidates:
        dist = haversine(lat, lng, stop["lat"], stop["lng"])
        if dist <= 300:
            stop_count_300m += 1
        if dist <= 500:
            stop_count_500m += 1
        if dist < nearest_distance:
            nearest_distance, nearest_stop = dist, stop["name"]
        node_id = stop.get("node_id")
        if dist <= 500 and node_id in route_map:
            stop_routes = sorted(route_map[node_id])
            route_set.update(stop_routes)
            by_type = {}
            for route_name in stop_routes:
                by_type.setdefault(TYPE_LABEL.get(classify_bus_type(route_name), "기타"), []).append(route_name)
            for label, routes in by_type.items():
                items.append({
                    "subtype": label,
                    "label": f"{stop['name']} · {', '.join(routes[:8])}",
                    "distance": round(dist),
                    "_key": (node_id, label),
                })
    return {
        "stop_300": stop_count_300m, "stop_500": stop_count_500m,
        "nearest_stop": nearest_stop, "nearest_distance": round(nearest_distance),
        "routes": route_set, "items": items,
    }


def type_counts(route_set):
    counts = {key: 0 for key in TYPE_LABEL}
    for route_name in route_set:
        kind = classify_bus_type(route_name)
        if kind in counts:
            counts[kind] += 1
    return counts


results = []

total = len(apartment_data)

for idx, apt in enumerate(apartment_data):

    if idx % 100 == 0:
        print(f"[{idx}/{total}]")

    # 동별(scripts/dong_points 원칙): 등급 지표(500m 안 노선 수)는 중간 동 값. 노선·정류장 목록과
    # 노선 종류 수는 동 전체를 합친다(어느 동에서든 500m 안 — 탐색 노선 필터도 이 기준).
    points, basis = points_for(dong_points, apt["name"], apt["gu"], apt["dong"], apt["lat"], apt["lng"])
    per_point = [compute_at(lat, lng) for lat, lng in points]

    union_routes = set().union(*(p["routes"] for p in per_point))
    merged = {}
    for p in per_point:
        for item in p["items"]:
            entry = merged.get(item["_key"])
            if entry is None:
                entry = merged[item["_key"]] = {**item, "dong_within_500": 0}
            entry["distance"] = min(entry["distance"], item["distance"])
            entry["dong_within_500"] += 1
    bus_items = sorted(merged.values(), key=lambda e: (e["distance"], e["label"]))
    for item in bus_items:
        item.pop("_key", None)
        if basis != "dong":
            item.pop("dong_within_500", None)

    nearest_names = [p["nearest_stop"] for p in per_point if p["nearest_stop"]]
    nearest_stop = max(set(nearest_names), key=nearest_names.count) if nearest_names else ""
    counts = type_counts(union_routes)
    route_list = sorted(union_routes)

    results.append({
        "name": apt["name"],
        "gu": apt["gu"],
        "dong": apt["dong"],
        "lat": apt["lat"],
        "lng": apt["lng"],

        "bus_stop_count_300m": median_low([p["stop_300"] for p in per_point]),
        "bus_stop_count_500m": median_low([p["stop_500"] for p in per_point]),

        "nearest_bus_stop": nearest_stop,
        "nearest_bus_stop_distance": median_low([p["nearest_distance"] for p in per_point]),

        "bus_route_count": median_low([len(p["routes"]) for p in per_point]),
        "main_bus_count": counts["main"],
        "local_bus_count": counts["local"],
        "express_bus_count": counts["express"],
        "night_bus_count": counts["night"],
        "village_bus_count": counts["village"],
        "airport_bus_count": counts["airport"],

        "available_bus_routes": ", ".join(route_list[:20]),

        "bus_items_json": json.dumps(bus_items, ensure_ascii=False),
        "bus_basis": basis,
        "bus_dong_count": len(points),
        "bus_route_count_union": len(route_list),
    })

df = pd.DataFrame(results)

df.to_csv(
    OUTPUT_PATH,
    index=False,
    encoding="utf-8-sig"
)

print()
print("[DONE]", OUTPUT_PATH)
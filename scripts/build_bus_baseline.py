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

results = []

total = len(apartment_data)

for idx, apt in enumerate(apartment_data):

    if idx % 100 == 0:
        print(f"[{idx}/{total}]")

    lat = apt["lat"]
    lng = apt["lng"]

    stop_count_300m = 0
    stop_count_500m = 0

    nearest_stop = ""
    nearest_distance = 999999

    route_set = set()
    bus_items = []

    main_bus_count = 0
    local_bus_count = 0
    express_bus_count = 0
    night_bus_count = 0
    village_bus_count = 0
    airport_bus_count = 0

    for stop in bus_stop_data:

        dist = haversine(
            lat,
            lng,
            stop["lat"],
            stop["lng"]
        )

        if dist <= 300:
            stop_count_300m += 1

        if dist <= 500:
            stop_count_500m += 1

        if dist < nearest_distance:
            nearest_distance = dist
            nearest_stop = stop["name"]

        node_id = stop.get("node_id")

        if dist <= 500 and node_id in route_map:
            stop_routes = sorted(list(route_map[node_id]))
            route_set.update(stop_routes)

            routes_by_type = {}

            for route_name in stop_routes:
                bus_type = classify_bus_type(route_name)

                if bus_type == "main":
                    label = "간선"
                elif bus_type == "local":
                    label = "지선"
                elif bus_type == "express":
                    label = "광역"
                elif bus_type == "night":
                    label = "심야"
                elif bus_type == "village":
                    label = "마을"
                elif bus_type == "airport":
                    label = "공항"
                else:
                    label = "기타"

                if label not in routes_by_type:
                    routes_by_type[label] = []

                routes_by_type[label].append(route_name)

            for label, routes in routes_by_type.items():
                bus_items.append({
                    "subtype": label,
                    "label": f"{stop['name']} · {', '.join(routes[:8])}",
                    "distance": round(dist),
                })

    for route_name in route_set:

        bus_type = classify_bus_type(route_name)

        if bus_type == "main":
            main_bus_count += 1

        elif bus_type == "local":
            local_bus_count += 1

        elif bus_type == "express":
            express_bus_count += 1

        elif bus_type == "night":
            night_bus_count += 1

        elif bus_type == "village":
            village_bus_count += 1

        elif bus_type == "airport":
            airport_bus_count += 1

    route_list = sorted(list(route_set))

    results.append({
        "name": apt["name"],
        "gu": apt["gu"],
        "dong": apt["dong"],
        "lat": lat,
        "lng": lng,

        "bus_stop_count_300m": stop_count_300m,
        "bus_stop_count_500m": stop_count_500m,

        "nearest_bus_stop": nearest_stop,
        "nearest_bus_stop_distance": round(nearest_distance),

        "bus_route_count": len(route_list),
        "main_bus_count": main_bus_count,
        "local_bus_count": local_bus_count,
        "express_bus_count": express_bus_count,
        "night_bus_count": night_bus_count,
        "village_bus_count": village_bus_count,
        "airport_bus_count": airport_bus_count,

        "available_bus_routes": ", ".join(route_list[:20]),

        "bus_items_json": json.dumps(bus_items, ensure_ascii=False),
    })

df = pd.DataFrame(results)

df.to_csv(
    OUTPUT_PATH,
    index=False,
    encoding="utf-8-sig"
)

print()
print("[DONE]", OUTPUT_PATH)
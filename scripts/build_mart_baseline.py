import csv
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.preload_service import (
    load_apartment_data,
    apartment_data,
)

from services.kakao_local_service import (
    search_category,
)

from services.baseline_builder_service import (
    build_result_card_items,
)

from services.geo_service import get_distance_m

from services.poi_service import MART_CATEGORY_GROUPS


print("[BUILD] apartment preload")
load_apartment_data()

output_path = "data/baseline/mart_baseline.csv"
STORE_LIST_PATH = "data/mart/large_warehouse_stores.csv"

# 대형/창고형은 서울 전체 70여 개뿐인 고정 점포 → 점포 리스트(build_mart_store_list.py
# 로 생성, API 0콜)와 단지 좌표의 거리만 계산한다(API 0콜). 슈퍼마켓은 점포가 많고
# 도보권 500m라 기존 MT1 카테고리 검색(1.5km 캐시)을 그대로 거른다.


def load_store_list():
    """{group_key: [{name, brand, lat, lng}...]} — 대형/창고형 점포."""
    brand_to_group = {}
    for gkey in ("large_mart", "warehouse_mart"):
        for brand in MART_CATEGORY_GROUPS[gkey]["brands"]:
            brand_to_group[brand] = gkey
    grouped = {"large_mart": [], "warehouse_mart": []}
    with open(STORE_LIST_PATH, encoding="utf-8-sig", newline="") as file:
        for store in csv.DictReader(file):
            gkey = brand_to_group.get(store.get("brand"))
            if not gkey:
                continue
            grouped[gkey].append({
                "name": store["name"],
                "brand": store["brand"],
                "lat": float(store["lat"]),
                "lng": float(store["lng"]),
            })
    return grouped


def store_places(stores, lat, lng):
    """점포 리스트를 단지 기준 거리(distance) 포함 place dict로 변환(API 0콜)."""
    places = []
    for store in stores:
        distance = get_distance_m(lat, lng, store["lat"], store["lng"])
        places.append({
            "category": "mart",
            "label": f"🛒 {store['name']}",
            "name": store["name"],
            "lat": store["lat"],
            "lng": store["lng"],
            "distance": int(round(distance)),
        })
    return places


def compute_group(group, places, lat, lng):
    """group의 반경 내에서 group 브랜드만 집계 → (count, diversity, brand_stats, items)."""
    radius = group["radius"]
    brands = group["brands"]
    items_all = build_result_card_items("mart", lat, lng, places, radius)
    items = [item for item in items_all if item.get("subtype") in brands]

    brand_stats = {}
    for brand in brands:
        b_items = [item for item in items if item.get("subtype") == brand]
        nearest = min((item["distance"] for item in b_items), default="")
        brand_stats[brand] = {"count": len(b_items), "nearest_distance": nearest}

    group_count = sum(stat["count"] for stat in brand_stats.values())
    diversity = sum(1 for stat in brand_stats.values() if stat["count"] > 0)
    return group_count, diversity, brand_stats, items


def build_header():
    header = ["name", "gu", "dong", "lat", "lng"]
    for gkey, group in MART_CATEGORY_GROUPS.items():
        radius = group["radius"]
        header.append(f"{gkey}_count_{radius}m")
        header.append(f"{gkey}_brand_diversity")
        for brand in group["brands"]:
            header.append(f"{brand}_count_{radius}m")
            header.append(f"nearest_{brand}_distance")
        header.append(f"{gkey}_items_json")
    return header


store_list = load_store_list()
print(f"[BUILD] 점포 리스트 로드: 대형 {len(store_list['large_mart'])} / "
      f"창고형 {len(store_list['warehouse_mart'])}")

with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.writer(file)
    writer.writerow(build_header())

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):
        try:
            lat = apartment["lat"]
            lng = apartment["lng"]

            # 슈퍼: MT1 카테고리 검색(1.5km 캐시)을 500m로 거름. 대형/창고형: 점포
            # 리스트와 거리계산(API 0콜).
            group_places = {
                "large_mart": store_places(store_list["large_mart"], lat, lng),
                "super_mart": search_category("mart", lat, lng),
                "warehouse_mart": store_places(store_list["warehouse_mart"], lat, lng),
            }

            row = [apartment["name"], apartment["gu"], apartment["dong"], lat, lng]
            log_counts = {}

            for gkey, group in MART_CATEGORY_GROUPS.items():
                count, diversity, brand_stats, items = compute_group(
                    group, group_places[gkey], lat, lng
                )
                row.append(count)
                row.append(diversity)
                for brand in group["brands"]:
                    row.append(brand_stats[brand]["count"])
                    row.append(brand_stats[brand]["nearest_distance"])
                row.append(json.dumps(items, ensure_ascii=False))
                log_counts[group["label"]] = count

            writer.writerow(row)

            if (index + 1) % 500 == 0:
                print(
                    f"[{index+1}/{total}] {apartment['name']} → "
                    + " / ".join(f"{k} {v}" for k, v in log_counts.items())
                )

        except Exception as e:
            print(f"[ERROR] {apartment.get('name')} : {e}")

print(f"[DONE] {output_path} 생성 완료")

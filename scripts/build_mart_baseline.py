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
    search_keyword,
)

from services.baseline_builder_service import (
    build_result_card_items,
)

from services.poi_service import MART_CATEGORY_GROUPS


print("[BUILD] apartment preload")
load_apartment_data()

output_path = "data/baseline/mart_baseline.csv"

# 대형/창고형은 넓은 반경(3km/5km)이라 카테고리 검색(45-cap)으로는 멀리 있는 매장이
# 누락된다 → 브랜드 키워드 검색(MT1 필터로 이마트24 등 오염 제거)으로 수집한다.
# 슈퍼마켓은 도보권 500m라 기존 카테고리 검색(1.5km 캐시) 결과를 그대로 거른다.
LARGE_KEYWORDS = ["이마트", "홈플러스", "롯데마트"]
WAREHOUSE_KEYWORDS = ["코스트코", "트레이더스"]


def dedupe(places):
    seen = set()
    result = []
    for place in places:
        key = (round(float(place["lat"]), 6), round(float(place["lng"]), 6),
               place.get("label", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(place)
    return result


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


with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.writer(file)
    writer.writerow(build_header())

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):
        try:
            lat = apartment["lat"]
            lng = apartment["lng"]

            # 그룹별 장소 수집
            super_places = search_category("mart", lat, lng)

            large_places = []
            for keyword in LARGE_KEYWORDS:
                large_places += search_keyword(keyword, lat, lng, 3000, "MT1")
            large_places = dedupe(large_places)

            warehouse_places = []
            for keyword in WAREHOUSE_KEYWORDS:
                warehouse_places += search_keyword(keyword, lat, lng, 5000, "MT1")
            warehouse_places = dedupe(warehouse_places)

            group_places = {
                "large_mart": large_places,
                "super_mart": super_places,
                "warehouse_mart": warehouse_places,
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

            print(
                f"[{index+1}/{total}] {apartment['name']} → "
                + " / ".join(f"{k} {v}" for k, v in log_counts.items())
            )

            time.sleep(0.15)

        except Exception as e:
            print(f"[ERROR] {apartment.get('name')} : {e}")

print(f"[DONE] {output_path} 생성 완료")

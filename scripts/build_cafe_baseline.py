import csv
import json
import time

from services.preload_service import (
    load_apartment_data,
    apartment_data
)

from services.kakao_local_service import (
    require_fetchable,
    search_category
)

from services.baseline_builder_service import (
    build_result_card_items,
    count_places_within_radius,
    extract_subtype_stats,
    merge_places,
    search_brand_places,
    get_subtype_csv_columns,
    get_subtype_csv_values,
)


print("[BUILD] apartment preload")
load_apartment_data()

# POI 를 못 가져오는 상태(키 없음+캐시 만료)로 빌드가 진행되면 baseline 이
# 전 단지 0 으로 덮어써진다. 첫 단지 좌표로 미리 확인하고 아니면 중단한다.
require_fetchable(
    "cafe",
    apartment_data[0]["lat"],
    apartment_data[0]["lng"],
)

output_path = (
    "data/baseline/cafe_baseline.csv"
)

with open(
    output_path,
    "w",
    newline="",
    encoding="utf-8-sig"
) as file:

    writer = csv.writer(file)

    writer.writerow([
        "name",
        "gu",
        "dong",
        "lat",
        "lng",
        "cafe_count_300m",
        "cafe_count_500m",
        "franchise_total_500m",
        "brand_diversity_500m",
        "cafe_access_score_raw",
        "cafe_items_json",
    ] + get_subtype_csv_columns(
        "cafe",
        500
    ))

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            places = search_category(
                "cafe",
                apartment["lat"],
                apartment["lng"]
            )

            count_300m, _ = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    places,
                    300
                )
            )

            count_500m, _ = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    places,
                    500
                )
            )

            # 브랜드별 개수는 브랜드 키워드 검색으로 센다(카테고리 검색 45곳 한도 회피, 2026-10-02).
            # 전체 개수(count_300m·500m)는 지금처럼 카테고리 검색 값이다.
            brand_places, brand_capped = search_brand_places(
                "cafe",
                apartment["lat"],
                apartment["lng"],
                500
            )
            if brand_capped:
                print(f"[WARN] {apartment['name']} 브랜드 검색도 45곳 한도: {brand_capped}")

            # 브랜드 검색과 카테고리 검색을 합쳐 센다(같은 매장은 한 번). 키워드 검색도 드물게
            # 매장을 놓쳐서(2026-10-02: 오금현대 메가MGC 방이오금점) 한쪽만 쓰면 줄어드는 단지가 생긴다.
            brand_and_category = merge_places(places, brand_places)
            subtype_stats = extract_subtype_stats(
                "cafe",
                brand_and_category,
                500
            )

            franchise_total_500m = sum(
                int(stat.get("count", 0) or 0)
                for stat in subtype_stats.values()
            )

            brand_diversity_500m = sum(
                1
                for stat in subtype_stats.values()
                if int(stat.get("count", 0) or 0) > 0
            )

            cafe_access_score_raw = (
                franchise_total_500m
                + brand_diversity_500m * 2
            )

            items = build_result_card_items(
                "cafe",
                apartment["lat"],
                apartment["lng"],
                brand_and_category,
                500
            )

            writer.writerow([
                apartment["name"],
                apartment["gu"],
                apartment["dong"],
                apartment["lat"],
                apartment["lng"],
                count_300m,
                count_500m,
                franchise_total_500m,
                brand_diversity_500m,
                cafe_access_score_raw,
                json.dumps(items, ensure_ascii=False),
            ] + get_subtype_csv_values(
                "cafe",
                subtype_stats,
                500
            ))

            print(
                f"[{index+1}/{total}] "
                f"{apartment['name']} "
                f"→ 카페 {count_500m}개"
            )

            time.sleep(0.15)

        except Exception as e:

            print(
                f"[ERROR] "
                f"{apartment.get('name')} : {e}"
            )

print(
    f"[DONE] {output_path} 생성 완료"
)

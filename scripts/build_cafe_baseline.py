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


from services import kakao_local_service
from scripts.dong_points import median_low
from scripts.kakao_dong import load_dong_points, query_groups, union_items, with_distance
from services.poi_service import SUBTYPE_RULES

DONG_POINTS = load_dong_points()


def cafe_stats(merged_d):
    stats = extract_subtype_stats("cafe", merged_d, 500)
    franchise = sum(int(stat.get("count", 0) or 0) for stat in stats.values())
    diversity = sum(1 for stat in stats.values() if int(stat.get("count", 0) or 0) > 0)
    return stats, franchise, diversity, franchise + diversity * 2


def require_no_api_failure(apartment):
    if kakao_local_service.API_FAILS["n"]:
        raise SystemExit(f"[ABORT] 카카오 API 실패 {kakao_local_service.API_FAILS['n']}회({apartment['name']}) — "
                         "한도·키를 확인하고 다시 실행(캐시된 조회는 다시 부르지 않는다)")


def dong_row(apartment, groups):
    """동별: 묶음 지점마다 한 번 조회(반경을 맡은 동까지 넓혀), 동마다 거리를 다시 재서 센다.
    개수·점수 칸은 중간 동, 브랜드 최근접은 가장 가까운 동, 목록은 동 전체 합침."""
    per_dong = []
    for (qlat, qlng), slack, members in groups:
        places = search_category("cafe", qlat, qlng, radius=500 + slack)
        brand_places, brand_capped = search_brand_places("cafe", qlat, qlng, 500 + slack)
        if brand_capped:
            print(f"[WARN] {apartment['name']} 브랜드 검색도 45곳 한도: {brand_capped}")
        require_no_api_failure(apartment)
        merged = merge_places(places, brand_places)
        for lat, lng in members:
            cat_d = with_distance(places, lat, lng)
            merged_d = with_distance(merged, lat, lng)
            stats, franchise, diversity, score = cafe_stats(merged_d)
            per_dong.append({
                "c300": sum(1 for p in cat_d if p["distance"] <= 300),
                "c500": sum(1 for p in cat_d if p["distance"] <= 500),
                "franchise": franchise, "diversity": diversity, "score": score, "stats": stats,
                "items": build_result_card_items("cafe", lat, lng, merged_d, 500),
            })
    stats = {}
    for rule in SUBTYPE_RULES.get("cafe", []):
        key = rule["name"]
        nearest = [d["stats"][key]["nearest_distance"] for d in per_dong if d["stats"][key]["nearest_distance"] != ""]
        stats[key] = {
            "count": median_low([d["stats"][key]["count"] for d in per_dong]) or 0,
            "nearest_distance": min(nearest) if nearest else "",
        }
    mid = lambda k: median_low([d[k] for d in per_dong]) or 0  # noqa: E731
    return (mid("c300"), mid("c500"), mid("franchise"), mid("diversity"), mid("score"),
            union_items([d["items"] for d in per_dong]), stats)


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
    ) + ["cafe_basis", "cafe_dong_count"])

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            basis, groups = query_groups(DONG_POINTS, apartment)
            if basis == "dong":
                c300, c500, franchise, diversity, score, items, subtype_stats = dong_row(apartment, groups)
                writer.writerow([
                    apartment["name"], apartment["gu"], apartment["dong"], apartment["lat"], apartment["lng"],
                    c300, c500, franchise, diversity, score, json.dumps(items, ensure_ascii=False),
                ] + get_subtype_csv_values("cafe", subtype_stats, 500)
                  + ["dong", sum(len(m) for _, _, m in groups)])
                print(f"[{index+1}/{total}] {apartment['name']} → 카페(동별 {len(groups)}지점) 프랜차이즈 {franchise} "
                      f"[API {kakao_local_service.API_CALLS['n']}]")
                time.sleep(0.15)
                continue

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
            ) + ["center", 1])

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
    f"[DONE] {output_path} 생성 완료 (카카오 API {kakao_local_service.API_CALLS['n']}회)"
)

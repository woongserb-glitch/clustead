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
    get_subtype_csv_columns,
    get_subtype_csv_values,
)


print("[BUILD] apartment preload")
load_apartment_data()

# POI 를 못 가져오는 상태(키 없음+캐시 만료)로 빌드가 진행되면 baseline 이
# 전 단지 0 으로 덮어써진다. 첫 단지 좌표로 미리 확인하고 아니면 중단한다.
require_fetchable(
    "convenience",
    apartment_data[0]["lat"],
    apartment_data[0]["lng"],
)

output_path = (
    "data/baseline/convenience_baseline.csv"
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
        "convenience_count_300m",
        "convenience_count_500m",
        "convenience_items_json",
    ] + get_subtype_csv_columns(
        "convenience",
        500
    ))

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            places = search_category(
                "convenience",
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

            subtype_stats = extract_subtype_stats(
                "convenience",
                places,
                500
            )

            items = build_result_card_items(
                "convenience",
                apartment["lat"],
                apartment["lng"],
                places,
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
                json.dumps(items, ensure_ascii=False),
            ] + get_subtype_csv_values(
                "convenience",
                subtype_stats,
                500
            ))

            print(
                f"[{index+1}/{total}] "
                f"{apartment['name']} "
                f"→ 편의점 {count_500m}개"
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

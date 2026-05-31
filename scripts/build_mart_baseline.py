import csv
import json
import time

from services.preload_service import (
    load_apartment_data,
    apartment_data
)

from services.kakao_local_service import (
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

output_path = (
    "data/baseline/mart_baseline.csv"
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
        "mart_count_500m",
        "mart_count_1000m",
        "mart_count_1500m",
        "mart_items_json",
    ] + get_subtype_csv_columns(
        "mart",
        1500
    ))

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            places = search_category(
                "mart",
                apartment["lat"],
                apartment["lng"]
            )

            count_500m, _ = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    places,
                    500
                )
            )

            count_1000m, _ = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    places,
                    1000
                )
            )

            count_1500m, _ = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    places,
                    1500
                )
            )

            subtype_stats = extract_subtype_stats(
                "mart",
                places,
                1500
            )

            items = build_result_card_items(
                "mart",
                apartment["lat"],
                apartment["lng"],
                places,
                1500
            )

            writer.writerow([
                apartment["name"],
                apartment["gu"],
                apartment["dong"],
                apartment["lat"],
                apartment["lng"],
                count_500m,
                count_1000m,
                count_1500m,
                json.dumps(items, ensure_ascii=False),
            ] + get_subtype_csv_values(
                "mart",
                subtype_stats,
                1500
            ))

            print(
                f"[{index+1}/{total}] "
                f"{apartment['name']} "
                f"→ 마트 {count_1500m}개"
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

import csv

from services.preload_service import (
    load_apartment_data,
    apartment_data,
    load_park_data,
    park_data
)

from services.baseline_builder_service import (
    find_nearest_place
)


print("[BUILD] apartment preload")
load_apartment_data()

print("[BUILD] park preload")
load_park_data()

output_path = "data/baseline/park_baseline.csv"

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
        "nearest_park",
        "park_distance"
    ])

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            nearest_park, distance = find_nearest_place(
                apartment["lat"],
                apartment["lng"],
                park_data
            )

            if nearest_park is None:
                continue

            writer.writerow([
                apartment["name"],
                apartment["gu"],
                apartment["dong"],
                apartment["lat"],
                apartment["lng"],
                nearest_park["name"],
                distance
            ])

            print(
                f"[{index+1}/{total}] "
                f"{apartment['name']} "
                f"→ {nearest_park['name']} "
                f"({distance}m)"
            )

        except Exception as e:

            print(
                f"[ERROR] {apartment.get('name')} : {e}"
            )

print(
    f"[DONE] {output_path} 생성 완료"
)
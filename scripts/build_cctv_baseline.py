import csv

from services.preload_service import (
    load_apartment_data,
    apartment_data,
    load_cctv_data,
    cctv_data,
    cctv_camera_weights
)


def camera_weight(place):
    return cctv_camera_weights.get((place["lat"], place["lng"]), 1)

from services.baseline_builder_service import (
    count_places_within_radius
)


print("[BUILD] apartment preload")
load_apartment_data()

print("[BUILD] cctv preload")
load_cctv_data()

output_path = "data/baseline/cctv_baseline.csv"

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
        "cctv_count_300m",
        "cctv_count_500m",
        "cctv_point_count_300m",
        "cctv_point_count_500m",
        "safety_cctv_count_500m",
        "child_cctv_count_500m",
        "traffic_cctv_count_500m",
        "facility_cctv_count_500m",
        "nearest_cctv",
        "nearest_cctv_distance"
    ])

    total = len(apartment_data)

    for index, apartment in enumerate(apartment_data):

        try:

            point_count_300m, places_300m = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    cctv_data,
                    300
                )
            )

            point_count_500m, places_500m = (
                count_places_within_radius(
                    apartment["lat"],
                    apartment["lng"],
                    cctv_data,
                    500
                )
            )

            # 자치구별 등록 단위 차이를 보정한 '카메라 대수'가 정본 지표다.
            # 행 수(=지주/등록 건수)는 지도 마커 수와 맞춰보기 위해 함께 남긴다.
            # build_cctv_camera_weights 참고.
            count_300m = round(
                sum(camera_weight(p) for p in places_300m)
            )

            count_500m = round(
                sum(camera_weight(p) for p in places_500m)
            )

            safety_count = 0
            child_count = 0
            traffic_count = 0
            facility_count = 0

            for place in places_500m:

                subtype = place.get("subtype", "")
                weight = camera_weight(place)

                if subtype == "생활방범":
                    safety_count += weight

                elif subtype == "어린이보호":
                    child_count += weight

                elif subtype == "교통/단속":
                    traffic_count += weight

                elif subtype == "시설안전":
                    facility_count += weight

            safety_count = round(safety_count)
            child_count = round(child_count)
            traffic_count = round(traffic_count)
            facility_count = round(facility_count)

            nearest_name = ""
            nearest_distance = ""

            if places_500m:

                nearest = places_500m[0]

                nearest_name = nearest.get("name", "")
                nearest_distance = nearest.get(
                    "distance",
                    ""
                )

            writer.writerow([
                apartment["name"],
                apartment["gu"],
                apartment["dong"],
                apartment["lat"],
                apartment["lng"],
                count_300m,
                count_500m,
                point_count_300m,
                point_count_500m,
                safety_count,
                child_count,
                traffic_count,
                facility_count,
                nearest_name,
                nearest_distance
            ])

            print(
                f"[{index + 1}/{total}] "
                f"{apartment['name']} "
                f"→ CCTV 500m {count_500m}대"
                f"({point_count_500m}건)"
            )

        except Exception as e:

            print(
                f"[ERROR] "
                f"{apartment.get('name')} : {e}"
            )

print(
    f"[DONE] {output_path} 생성 완료"
)
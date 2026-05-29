import csv

import geopandas as gpd
from shapely.geometry import Point

from services.preload_service import (
    load_apartment_data,
    load_school_data,
    apartment_data,
    school_data,
)
from services.geo_service import get_distance_m


SHP_PATH = "data/school/zone/초등학교통학구역.shp"
OUTPUT_PATH = "data/baseline/school_zone_baseline.csv"


def clean_school_zone_name(value):
    return (
        str(value or "")
        .replace("통학구역", "")
        .replace("공동통학구역", "")
        .strip()
    )


def find_elementary_school(school_name):
    clean_name = clean_school_zone_name(school_name)
    if not clean_name:
        return None

    for school in school_data:
        if school.get("subtype") != "elementary":
            continue
        name = str(school.get("name") or "").strip()
        if name == clean_name:
            return school

    for school in school_data:
        if school.get("subtype") != "elementary":
            continue
        name = str(school.get("name") or "").strip()
        if clean_name in name or name in clean_name:
            return school

    return None


def elementary_access_score(distance):
    if distance in [None, ""]:
        return 10

    try:
        distance = float(distance)
    except Exception:
        return 10

    if distance <= 150:
        return 95
    if distance <= 300:
        return 88
    if distance <= 500:
        return 78
    if distance <= 800:
        return 62
    if distance <= 1200:
        return 45
    if distance <= 1500:
        return 30
    return 15


def main():
    print("[LOAD] apartment data")
    load_apartment_data()
    load_school_data()

    print("[LOAD] school zone shp")
    zones = gpd.read_file(SHP_PATH)

    seoul_zones = zones[
        zones["EDU_UP_NM"] == "서울특별시교육청"
    ].copy()

    print(f"[SCHOOL ZONE] 서울 통학구역 {len(seoul_zones)}개 로드")

    apt_points = []

    for apt in apartment_data:
        apt_points.append({
            "name": apt.get("name"),
            "gu": apt.get("gu"),
            "dong": apt.get("dong"),
            "lat": apt.get("lat"),
            "lng": apt.get("lng"),
            "geometry": Point(
                apt.get("lng"),
                apt.get("lat")
            ),
        })

    apt_gdf = gpd.GeoDataFrame(
        apt_points,
        crs="EPSG:4326"
    ).to_crs(seoul_zones.crs)

    rows = []

    for index, apt in apt_gdf.iterrows():
        matched = seoul_zones[
            seoul_zones.contains(
                apt.geometry
            )
        ]

        normal_zones = matched[
            matched["HAKGUDO_GB"].astype(str) == "0"
        ]

        shared_zones = matched[
            matched["HAKGUDO_GB"].astype(str) == "1"
        ]

        primary_zone = None

        if not normal_zones.empty:
            primary_zone = normal_zones.iloc[0]
        elif not matched.empty:
            primary_zone = matched.iloc[0]

        primary_zone_id = ""
        primary_zone_name = ""
        primary_education_office = ""
        school_zone_base_date = ""

        if primary_zone is not None:
            primary_zone_id = primary_zone.get("HAKGUDO_ID", "")
            primary_zone_name = primary_zone.get("HAKGUDO_NM", "")
            primary_education_office = primary_zone.get("EDU_NM", "")
            school_zone_base_date = primary_zone.get("BASE_DT", "")

        assigned_elementary_school = clean_school_zone_name(primary_zone_name)
        assigned_elementary_distance_m = ""
        assigned_school = find_elementary_school(assigned_elementary_school)

        if assigned_school:
            try:
                assigned_elementary_distance_m = round(get_distance_m(
                    apt.get("lat"),
                    apt.get("lng"),
                    assigned_school.get("lat"),
                    assigned_school.get("lng"),
                ))
            except Exception:
                assigned_elementary_distance_m = ""

        elementary_score = elementary_access_score(assigned_elementary_distance_m)

        shared_zone_names = []

        for _, row in shared_zones.iterrows():
            shared_zone_names.append(
                row.get("HAKGUDO_NM", "")
            )

        rows.append({
            "name": apt.get("name"),
            "gu": apt.get("gu"),
            "dong": apt.get("dong"),
            "lat": apt.get("lat"),
            "lng": apt.get("lng"),
            "primary_school_zone_id": primary_zone_id,
            "primary_school_zone_name": primary_zone_name,
            "primary_education_office": primary_education_office,
            "assigned_elementary_school": assigned_elementary_school,
            "assigned_elementary_distance_m": assigned_elementary_distance_m,
            "elementary_access_score": elementary_score,
            "shared_school_zone_names": "|".join(shared_zone_names),
            "school_zone_base_date": school_zone_base_date,
            "match_count": len(matched),
            "normal_zone_count": len(normal_zones),
            "shared_zone_count": len(shared_zones),
        })

        if (index + 1) % 100 == 0:
            print(f"[PROGRESS] {index + 1}/{len(apt_gdf)}")

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as file:
        fieldnames = [
            "name",
            "gu",
            "dong",
            "lat",
            "lng",
            "primary_school_zone_id",
            "primary_school_zone_name",
            "primary_education_office",
            "assigned_elementary_school",
            "assigned_elementary_distance_m",
            "elementary_access_score",
            "shared_school_zone_names",
            "school_zone_base_date",
            "match_count",
            "normal_zone_count",
            "shared_zone_count",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"[DONE] {OUTPUT_PATH} 생성 완료")


if __name__ == "__main__":
    main()

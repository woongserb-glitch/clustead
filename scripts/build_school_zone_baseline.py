import json
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
from scripts.dong_points import load_dong_points, points_for, median_low


SHP_PATH = "data/school/zone/초등학교통학구역.shp"
# 브이월드 LT_C_DESCH(scripts/fetch_school_zones_vworld.py). SHP 와 같은 데이터라 있으면 이것을 쓴다.
VWORLD_PATH = "data/school/zone/vworld_desch.geojson"
OUTPUT_PATH = "data/baseline/school_zone_baseline.csv"


def read_zones():
    import os
    if os.path.exists(VWORLD_PATH):
        zones = gpd.read_file(VWORLD_PATH)
        # 브이월드 속성은 소문자(hakgudo_nm …) — SHP 열 이름(HAKGUDO_NM …)에 맞춘다.
        zones = zones.rename(columns={c: c.upper() for c in zones.columns if c != "geometry"})
        # geopandas 가 base_dt 를 날짜로 읽어 '2026-03-20 00:00:00' 이 된다 — SHP 와 같은 'YYYY-MM-DD' 로.
        if "BASE_DT" in zones.columns:
            zones["BASE_DT"] = zones["BASE_DT"].astype(str).str[:10]
        print(f"[LOAD] school zone vworld ({VWORLD_PATH})")
        return zones
    print(f"[LOAD] school zone shp ({SHP_PATH})")
    return gpd.read_file(SHP_PATH)


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

    zones = read_zones()

    seoul_zones = zones[
        zones["EDU_UP_NM"] == "서울특별시교육청"
    ].copy()

    print(f"[SCHOOL ZONE] 서울 통학구역 {len(seoul_zones)}개 로드")

    from shapely.strtree import STRtree
    normal_wgs = seoul_zones[seoul_zones["HAKGUDO_GB"].astype(str) == "0"].to_crs("EPSG:4326")
    zone_geoms = list(normal_wgs.geometry)
    zone_rows = [row for _, row in normal_wgs.iterrows()]
    zone_tree = STRtree(zone_geoms)

    def zone_at(lat, lng):
        pt = Point(lng, lat)
        for i in zone_tree.query(pt):
            if zone_geoms[int(i)].contains(pt):
                return zone_rows[int(i)]
        return None

    dong_points = load_dong_points()
    print(f"[SCHOOL ZONE] 동별 건물 위치가 있는 단지 {len(dong_points)}")

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

        # 동별(scripts/dong_points 원칙): 동마다 통학구역 → 배정초 → 그 학교까지 거리. 대표 배정초는
        # 동 수가 가장 많은 학교, 등급 거리는 중간 동의 '자기 배정초까지' 거리.
        points, basis = points_for(dong_points, apt.get("name"), apt.get("gu"), apt.get("dong"), apt.get("lat"), apt.get("lng"))
        school_dongs = []
        if basis == "dong":
            per_dong = []
            for lat, lng in points:
                zone = zone_at(lat, lng)
                if zone is None:
                    continue
                name = clean_school_zone_name(zone["HAKGUDO_NM"])
                school = find_elementary_school(name)
                dist = round(get_distance_m(lat, lng, school["lat"], school["lng"])) if school else None
                per_dong.append((name, dist, zone))
            if per_dong:
                counts = {}
                for name, dist, zone in per_dong:
                    entry = counts.setdefault(name, {"school": name, "count": 0, "min": None, "max": None, "zone": zone})
                    entry["count"] += 1
                    if dist is not None:
                        entry["min"] = dist if entry["min"] is None else min(entry["min"], dist)
                        entry["max"] = dist if entry["max"] is None else max(entry["max"], dist)
                school_dongs = sorted(counts.values(), key=lambda e: (-e["count"], e["min"] or 0))
                top = school_dongs[0]
                assigned_elementary_school = top["school"]
                primary_zone_id = top["zone"].get("HAKGUDO_ID", "")
                primary_zone_name = top["zone"].get("HAKGUDO_NM", "")
                primary_education_office = top["zone"].get("EDU_NM", "")
                assigned_elementary_distance_m = median_low([d for _, d, _ in per_dong if d is not None])
                elementary_score = elementary_access_score(assigned_elementary_distance_m)
            else:
                basis = "center"

        rows.append({
            "name": apt.get("name"),
            "gu": apt.get("gu"),
            "dong": apt.get("dong"),
            "lat": apt.get("lat"),
            "lng": apt.get("lng"),
            "school_basis": basis,
            "school_dong_count": len(points) if basis == "dong" else 1,
            "school_dong_json": json.dumps([{k: v for k, v in e.items() if k != "zone"} for e in school_dongs], ensure_ascii=False),
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
            "school_basis",
            "school_dong_count",
            "school_dong_json",
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

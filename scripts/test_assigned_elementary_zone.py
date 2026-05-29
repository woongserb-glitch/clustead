import geopandas as gpd
from shapely.geometry import Point

from services.preload_service import (
    load_apartment_data,
    apartment_data,
)


TARGET_APT = "마포래미안푸르지오"
SHP_PATH = "data/school/zone/초등학교통학구역.shp"


print("[LOAD] apartment data")
load_apartment_data()

target = None

for apt in apartment_data:
    if TARGET_APT in apt.get("name", ""):
        target = apt
        break

if not target:
    print(f"[ERROR] 아파트를 찾지 못했습니다: {TARGET_APT}")
    exit()

print(
    "[TARGET]",
    target["name"],
    target["gu"],
    target["dong"],
    target["lat"],
    target["lng"]
)

print("[LOAD] school zone shp")
zones = gpd.read_file(SHP_PATH)

print("[CRS]", zones.crs)
print("[TOTAL ZONES]", len(zones))

seoul_zones = zones[
    zones["EDU_UP_NM"] == "서울특별시교육청"
].copy()

print("[SEOUL ZONES]", len(seoul_zones))

apt_point = gpd.GeoDataFrame(
    [{
        "name": target["name"],
        "geometry": Point(
            target["lng"],
            target["lat"]
        )
    }],
    crs="EPSG:4326"
)

apt_point = apt_point.to_crs(seoul_zones.crs)

matched = seoul_zones[
    seoul_zones.contains(
        apt_point.geometry.iloc[0]
    )
]

print("=" * 60)
print("[MATCH RESULT]")
print("=" * 60)

if matched.empty:
    print("[NO MATCH] 통학구역을 찾지 못했습니다.")
else:
    normal_zones = matched[
        matched["HAKGUDO_GB"].astype(str) == "0"
    ]

    shared_zones = matched[
        matched["HAKGUDO_GB"].astype(str) == "1"
    ]

    print(f"[MATCH COUNT] 전체 {len(matched)}개")
    print(f"[NORMAL] 일반 통학구역 {len(normal_zones)}개")
    print(f"[SHARED] 공동 통학구역 {len(shared_zones)}개")
    print()

    print("[일반 통학구역]")
    for _, row in normal_zones.iterrows():
        print("학구ID:", row.get("HAKGUDO_ID"))
        print("학구명:", row.get("HAKGUDO_NM"))
        print("교육지원청:", row.get("EDU_NM"))
        print("기준일:", row.get("BASE_DT"))
        print("-" * 60)

    print("[공동 통학구역]")
    for _, row in shared_zones.iterrows():
        print("학구ID:", row.get("HAKGUDO_ID"))
        print("학구명:", row.get("HAKGUDO_NM"))
        print("교육지원청:", row.get("EDU_NM"))
        print("기준일:", row.get("BASE_DT"))
        print("-" * 60)
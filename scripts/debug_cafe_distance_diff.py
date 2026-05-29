from services.preload_service import load_apartment_data, apartment_data
from services.kakao_local_service import search_category
from services.geo_service import get_distance_m


TARGET_APT = "마포래미안푸르지오"


load_apartment_data()

target = None

for apt in apartment_data:
    if TARGET_APT in apt.get("name", ""):
        target = apt
        break

if not target:
    print(f"[ERROR] 아파트를 찾지 못했습니다: {TARGET_APT}")
    exit()

lat = target["lat"]
lng = target["lng"]

print("=" * 60)
print(f"[TARGET] {target['name']}")
print(f"[LAT/LNG] {lat}, {lng}")
print("=" * 60)

places = search_category("cafe", lat, lng)

print(f"[KAKAO RESULT COUNT] {len(places)}")

inside_by_local = []
outside_by_local = []

for place in places:
    kakao_distance = place.get("distance")
    local_distance = get_distance_m(
        lat,
        lng,
        place["lat"],
        place["lng"]
    )

    row = {
        "name": place.get("label"),
        "kakao_distance": kakao_distance,
        "local_distance": round(local_distance),
        "gap": round(local_distance - kakao_distance),
    }

    if local_distance <= 500:
        inside_by_local.append(row)
    else:
        outside_by_local.append(row)

print()
print(f"[LOCAL <= 500m COUNT] {len(inside_by_local)}")
print(f"[LOCAL > 500m COUNT] {len(outside_by_local)}")

print()
print("=" * 60)
print("[KAKAO에는 잡혔지만 우리 계산상 500m 초과]")
print("=" * 60)

for row in outside_by_local:
    print(
        f"{row['name']} | "
        f"Kakao={row['kakao_distance']}m | "
        f"Local={row['local_distance']}m | "
        f"Gap={row['gap']}m"
    )
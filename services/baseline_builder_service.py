from services.geo_service import get_distance_m
from services.poi_service import get_subtype_chips


def find_nearest_place(
    source_lat,
    source_lng,
    places
):

    nearest_place = None
    nearest_distance = 999999

    for place in places:

        distance = get_distance_m(
            source_lat,
            source_lng,
            place["lat"],
            place["lng"]
        )

        if distance < nearest_distance:
            nearest_distance = distance
            nearest_place = place

    return nearest_place, round(nearest_distance)

def count_places_within_radius(source_lat, source_lng, places, radius):
    count = 0
    matched_places = []

    for place in places:
        distance = get_distance_m(
            source_lat,
            source_lng,
            place["lat"],
            place["lng"]
        )

        if distance <= radius:
            count += 1
            matched_places.append({
                **place,
                "distance": distance
            })

    matched_places.sort(key=lambda item: item["distance"])

    return count, matched_places


from services.poi_service import SUBTYPE_RULES


def build_result_card_items(category, source_lat, source_lng, places, radius):
    items = []

    for place in places:
        try:
            lat = float(place.get("lat"))
            lng = float(place.get("lng"))
        except Exception:
            continue

        try:
            distance = int(float(place.get("distance")))
        except Exception:
            distance = get_distance_m(source_lat, source_lng, lat, lng)

        if distance > radius:
            continue

        item = {
            "category": place.get("category") or category,
            "label": place.get("label") or place.get("name", ""),
            "distance": int(distance),
            "lat": round(lat, 7),
            "lng": round(lng, 7),
        }

        if place.get("address"):
            item["address"] = place.get("address")

        if place.get("name"):
            item["name"] = place.get("name")

        items.append(item)

    items.sort(key=lambda item: item.get("distance", 999999))
    get_subtype_chips(category, items)
    items.sort(key=lambda item: item.get("distance", 999999))

    return items


def extract_subtype_stats(category, places, radius):
    subtype_rules = SUBTYPE_RULES.get(category, [])
    stats = {}

    for rule in subtype_rules:
        key = rule["name"]

        stats[key] = {
            "count": 0,
            "nearest_distance": ""
        }

    for place in places:
        distance = place.get("distance")

        if distance is None or distance > radius:
            continue

        text = f"{place.get('label', '')} {place.get('name', '')}".lower()

        for rule in subtype_rules:
            key = rule["name"]
            keywords = rule.get("keywords", [])

            matched = any(
                keyword.lower() in text
                for keyword in keywords
            )

            if not matched:
                continue

            stats[key]["count"] += 1

            current_nearest = stats[key]["nearest_distance"]

            if current_nearest == "" or distance < current_nearest:
                stats[key]["nearest_distance"] = distance

            break

    return stats


def get_subtype_csv_columns(category, radius):
    subtype_rules = SUBTYPE_RULES.get(category, [])
    columns = []

    for rule in subtype_rules:
        key = rule["name"]
        columns.append(f"{key}_count_{radius}m")
        columns.append(f"nearest_{key}_distance")

    return columns


def get_subtype_csv_values(category, stats, radius):
    subtype_rules = SUBTYPE_RULES.get(category, [])
    values = []

    for rule in subtype_rules:
        key = rule["name"]
        values.append(stats.get(key, {}).get("count", 0))
        values.append(stats.get(key, {}).get("nearest_distance", ""))

    return values


def _place_key(place):
    return (place.get("label"), round(float(place["lat"]), 6), round(float(place["lng"]), 6))


def search_brand_places(category, lat, lng, radius):
    """카카오 카테고리 검색은 한 번에 45곳까지만 돌려줘서, 카페가 많은 동네는 반경 안
    프랜차이즈가 목록에서 잘린다(2026-10-02: 카페 500m 1,029단지가 45에서 멈춤).
    SUBTYPE_RULES 브랜드마다 키워드 검색(같은 업종 코드, 거리순)으로 따로 받아 그 한도를 피한다.
    표본 검증: 한도 미달 40단지에서 카페 10개·편의점 4개 브랜드 모두 기존 값과 일치(600/600).
    다만 키워드 검색도 드물게 매장을 놓치므로 빌더는 카테고리 결과와 합쳐서(merge_places) 센다.

    반환: (브랜드 매장 목록, 45곳을 꽉 채워 또 잘렸을 수 있는 브랜드 이름 목록)
    """
    from services.kakao_local_service import CATEGORY_CONFIG, search_keyword
    from services.poi_service import SUBTYPE_RULES

    code = CATEGORY_CONFIG[category]["code"]
    found, capped = {}, []
    for rule in SUBTYPE_RULES.get(category, []):
        keywords = [k.lower() for k in rule.get("keywords", [])]
        pois = search_keyword(rule["keywords"][0].strip(), lat, lng, radius, code, label_category=category)
        if len(pois) >= 45:
            capped.append(rule["name"])
        for poi in pois:
            # 키워드 검색은 이름 외 정보로도 걸리므로, 기존과 같은 이름 규칙에 맞는 것만 남긴다.
            if any(k in str(poi.get("label", "")).lower() for k in keywords):
                found.setdefault(_place_key(poi), poi)
    return list(found.values()), capped


def merge_places(primary, extra):
    """카테고리 검색 목록에 브랜드 검색으로만 찾은 매장을 덧붙인다(같은 매장은 한 번)."""
    seen = {_place_key(p) for p in primary}
    return list(primary) + [p for p in extra if _place_key(p) not in seen]

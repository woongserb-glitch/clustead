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

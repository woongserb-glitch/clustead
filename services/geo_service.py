from math import radians, sin, cos, sqrt, atan2


def get_distance_m(lat1, lng1, lat2, lng2):
    earth_radius = 6371000

    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)

    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(d_lng / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return round(earth_radius * c)


def filter_pois_by_radius(pois, center_lat, center_lng, radius):
    filtered = []

    for poi in pois:
        
        if "lat" not in poi or "lng" not in poi:
            continue
        
        distance = get_distance_m(
            center_lat,
            center_lng,
            poi["lat"],
            poi["lng"]
        )

        if distance <= radius:
            new_poi = {
                **poi,
                "distance": distance,
            }
            filtered.append(new_poi)

    filtered.sort(key=lambda x: x["distance"])

    return filtered
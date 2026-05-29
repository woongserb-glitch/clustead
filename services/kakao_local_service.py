import os
import requests


def safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(str(message).encode("cp949", errors="replace").decode("cp949"))


CATEGORY_CONFIG = {
    "subway": {
        "code": "SW8",
        "radius": 800,
        "icon": "🚇",
    },
    "hospital": {
        "code": "HP8",
        "radius": 700,
        "icon": "🏥",
    },
    "cafe": {
        "code": "CE7",
        "radius": 500,
        "icon": "☕",
    },
    "mart": {
        "code": "MT1",
        "radius": 1500,
        "icon": "🛒",
    },
    "pharmacy": {
        "code": "PM9",
        "radius": 700,
        "icon": "💊",
    },
    "convenience": {
        "code": "CS2",
        "radius": 500,
        "icon": "🏪",
    },
}


def search_category(category, lat, lng):
    if category not in CATEGORY_CONFIG:
        return []

    rest_key = os.getenv("KAKAO_REST_API_KEY", "")
    if not rest_key:
        return []

    config = CATEGORY_CONFIG[category]
    url = "https://dapi.kakao.com/v2/local/search/category.json"

    headers = {
        "Authorization": f"KakaoAK {rest_key}"
    }

    all_pois = []

    for page in range(1, 4):
        params = {
            "category_group_code": config["code"],
            "x": lng,
            "y": lat,
            "radius": config["radius"],
            "sort": "distance",
            "size": 15,
            "page": page,
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=5,
            )

            data = response.json()
            documents = data.get("documents", [])

            if not documents:
                break

            for item in documents:
                all_pois.append({
                    "category": category,
                    "label": build_label(category, item.get("place_name", "")),
                    "lat": float(item["y"]),
                    "lng": float(item["x"]),
                    "distance": int(item.get("distance", 0)),
                    "address": item.get("road_address_name") or item.get("address_name", ""),
                })

            if data.get("meta", {}).get("is_end", True):
                break

        except Exception as e:
            print("Kakao API Error:", category, e)
            return []

    safe_print(f"[KAKAO] {category}: {len(all_pois)}개 조회")

    for poi in all_pois[:10]:
        safe_print(f" - {poi['label']} / {poi['distance']}m")

    return all_pois


def build_label(category, name):
    icon = CATEGORY_CONFIG.get(category, {}).get("icon", "📍")
    return f"{icon} {name}"


def get_real_pois(lat, lng, categories=None):
    all_pois = []
    selected_categories = categories or CATEGORY_CONFIG.keys()

    for category in selected_categories:
        if category not in CATEGORY_CONFIG:
            continue
        pois = search_category(category, lat, lng)
        all_pois.extend(pois)

    return all_pois


def get_subway_pois_for_baseline(lat, lng):
    import os
    import requests

    rest_key = os.getenv("KAKAO_REST_API_KEY")

    if not rest_key:
        return []

    url = "https://dapi.kakao.com/v2/local/search/category.json"

    headers = {
        "Authorization": f"KakaoAK {rest_key}"
    }

    params = {
        "category_group_code": "SW8",
        "x": lng,
        "y": lat,
        "radius": 3000,
        "sort": "distance",
        "size": 5,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        data = response.json()

        pois = []

        for item in data.get("documents", []):
            pois.append({
                "name": item.get("place_name"),
                "distance": int(item.get("distance", 99999)),
                "lat": float(item.get("y")),
                "lng": float(item.get("x")),
            })

        return pois

    except Exception as e:
        print("[SUBWAY BASELINE ERROR]", e)
        return []

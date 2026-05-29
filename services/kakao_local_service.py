import json
import os
import time
from pathlib import Path

import requests


def safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        print(str(message).encode("cp949", errors="replace").decode("cp949"))


# --- Kakao POI cache -------------------------------------------------------
# Every /result call fetched cafe/convenience/mart live (3 sequential network
# round-trips, timeout 5s each) — latency, per-view API cost and rate-limit
# exposure. Apartment coordinates are fixed and POI density changes slowly, so
# results are cached by (category, lat, lng) in memory + on disk.
#
# Important: only *successful* fetches are cached. API exceptions / missing key
# return [] WITHOUT caching, so a transient failure can't poison the cache.

_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "kakao"
_MEMORY_CACHE = {}
_CACHE_ENABLED = os.getenv("LIVEFIT_KAKAO_CACHE", "1") != "0"
try:
    _CACHE_TTL_SECONDS = int(os.getenv("LIVEFIT_KAKAO_CACHE_TTL", str(30 * 24 * 3600)))
except ValueError:
    _CACHE_TTL_SECONDS = 30 * 24 * 3600


def _cache_key(category, lat, lng):
    # Round coordinates so float noise doesn't fragment the cache. ~6 decimals
    # is ≈0.1m precision — far finer than POI search radii.
    try:
        lat_r = round(float(lat), 6)
        lng_r = round(float(lng), 6)
    except (TypeError, ValueError):
        lat_r, lng_r = lat, lng
    return f"{category}_{lat_r}_{lng_r}"


def _cache_path(key):
    return _CACHE_DIR / f"{key}.json"


def _cache_get(key):
    if not _CACHE_ENABLED:
        return None

    if key in _MEMORY_CACHE:
        return _MEMORY_CACHE[key]

    path = _cache_path(key)
    if not path.exists():
        return None

    if _CACHE_TTL_SECONDS > 0 and (time.time() - path.stat().st_mtime) > _CACHE_TTL_SECONDS:
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            pois = json.load(file)
    except Exception:
        return None

    _MEMORY_CACHE[key] = pois
    return pois


def _cache_set(key, pois):
    if not _CACHE_ENABLED:
        return

    _MEMORY_CACHE[key] = pois
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with _cache_path(key).open("w", encoding="utf-8") as file:
            json.dump(pois, file, ensure_ascii=False)
    except Exception:
        # Disk cache is best-effort; the in-memory copy still helps this run.
        pass


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


def _fetch_category(category, lat, lng):
    """Hit the Kakao API. Returns (ok, pois); ok=False on missing key or a
    network/parse error so the caller can avoid caching a failure."""
    rest_key = os.getenv("KAKAO_REST_API_KEY", "")
    if not rest_key:
        return False, []

    config = CATEGORY_CONFIG[category]
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {rest_key}"}

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
            response = requests.get(url, headers=headers, params=params, timeout=5)
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
            return False, []

    safe_print(f"[KAKAO] {category}: {len(all_pois)}개 조회")
    for poi in all_pois[:10]:
        safe_print(f" - {poi['label']} / {poi['distance']}m")

    return True, all_pois


def search_category(category, lat, lng):
    if category not in CATEGORY_CONFIG:
        return []

    key = _cache_key(category, lat, lng)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    ok, pois = _fetch_category(category, lat, lng)
    if ok:
        _cache_set(key, pois)

    return pois


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

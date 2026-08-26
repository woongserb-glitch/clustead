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


def clustead_env(key, default=""):
    return os.getenv(f"CLUSTEAD_{key}", os.getenv(f"LIVEFIT_{key}", default))


_CACHE_ENABLED = clustead_env("KAKAO_CACHE", "1") != "0"
try:
    _CACHE_TTL_SECONDS = int(clustead_env("KAKAO_CACHE_TTL", str(30 * 24 * 3600)))
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


def require_fetchable(category, lat, lng):
    """빌드 전용 프리플라이트 — POI 를 실제로 가져올 수 있을 때만 통과시킨다.

    2026-08-25: API 키가 셸에 없고 디스크 캐시도 30일 TTL 을 넘긴 상태에서
    build_all_baselines 를 돌리자 cafe/convenience/mart 가 전 단지 0 으로 덮어써졌는데도
    빌더는 SUCCESS 로 끝났고 validate 도 통과했다(구조만 보고 값은 안 봄).
    런타임(app)은 POI 를 못 얻으면 빈 목록으로 degrade 하는 게 맞지만, 빌드는 그 빈 결과를
    CSV 에 영구 기록하므로 반드시 중단해야 한다. 그래서 서비스 함수가 아니라 빌더
    진입점에서만 호출한다.

    표본 좌표 1건으로 (1) 캐시가 유효한지 (2) 아니면 실제 호출이 되는지 확인하고,
    둘 다 아니면 CSV 를 열기 전에 SystemExit 으로 죽는다.
    의도적으로 빈 baseline 을 만들 때만 CLUSTEAD_ALLOW_EMPTY_KAKAO=1 로 우회한다.
    """
    if clustead_env("ALLOW_EMPTY_KAKAO", "0") == "1":
        safe_print(f"[PREFLIGHT] {category}: ALLOW_EMPTY_KAKAO=1 - 검사 생략")
        return

    if category not in CATEGORY_CONFIG:
        raise SystemExit(f"[PREFLIGHT] 알 수 없는 카테고리: {category}")

    if _cache_get(_cache_key(category, lat, lng)) is not None:
        safe_print(f"[PREFLIGHT] {category}: 디스크 캐시 유효 - 빌드 진행")
        return

    if not os.getenv("KAKAO_REST_API_KEY", ""):
        raise SystemExit("\n".join([
            f"[PREFLIGHT] {category} 중단: KAKAO_REST_API_KEY 가 없고 캐시도 쓸 수 없다.",
            f"  캐시 TTL({_CACHE_TTL_SECONDS}s)이 지났거나 해당 좌표 캐시가 없다.",
            "  해결: .env 의 KAKAO_REST_API_KEY 를 환경에 로드하거나,",
            "        기존 캐시를 그대로 쓰려면 CLUSTEAD_KAKAO_CACHE_TTL=0 을 설정할 것.",
            "  (이대로 진행하면 baseline 이 전 단지 0 으로 덮어써진다)",
        ]))

    ok, _pois = _fetch_category(category, lat, lng)
    if not ok:
        raise SystemExit("\n".join([
            f"[PREFLIGHT] {category} 중단: 키는 있으나 실제 API 호출이 실패했다.",
            "  키 유효성·쿼터·네트워크를 확인할 것.",
            "  (진행하면 baseline 이 전 단지 0 으로 덮어써진다)",
        ]))

    safe_print(f"[PREFLIGHT] {category}: API 호출 정상 - 빌드 진행")


def _fetch_keyword(query, lat, lng, radius, category_group_code=None, label_category="mart"):
    """Kakao 키워드 검색. 브랜드명 + (선택)category_group_code 필터로 특정 브랜드를
    넓은 반경에서 정확히 수집(카테고리 검색의 45-cap 회피)."""
    rest_key = os.getenv("KAKAO_REST_API_KEY", "")
    if not rest_key:
        return False, []

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {rest_key}"}
    all_pois = []

    for page in range(1, 4):
        params = {
            "query": query,
            "x": lng,
            "y": lat,
            "radius": radius,
            "sort": "distance",
            "size": 15,
            "page": page,
        }
        if category_group_code:
            params["category_group_code"] = category_group_code

        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()
            documents = data.get("documents", [])
            if not documents:
                break
            for item in documents:
                all_pois.append({
                    "category": label_category,
                    "label": build_label(label_category, item.get("place_name", "")),
                    "lat": float(item["y"]),
                    "lng": float(item["x"]),
                    "distance": int(item.get("distance", 0)),
                    "address": item.get("road_address_name") or item.get("address_name", ""),
                })
            if data.get("meta", {}).get("is_end", True):
                break
        except Exception as e:
            print("Kakao Keyword API Error:", query, e)
            return False, []

    return True, all_pois


def search_keyword(query, lat, lng, radius, category_group_code=None, label_category="mart"):
    key = _cache_key(f"kw_{query}_{radius}_{category_group_code or ''}", lat, lng)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    ok, pois = _fetch_keyword(query, lat, lng, radius, category_group_code, label_category)
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

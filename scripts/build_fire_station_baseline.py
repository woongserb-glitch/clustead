import json
from pathlib import Path

import pandas as pd
from pyproj import Transformer

BASE_DIR = Path(__file__).resolve().parents[1]
APT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
RAW_PATH = BASE_DIR / "data" / "safety" / "fire_station_seoul.csv"
OUT_PATH = BASE_DIR / "data" / "baseline" / "fire_station_baseline.csv"

RADIUS_M = 1500
MAX_ITEMS = 30


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ["nan", "none", "null"]:
        return ""
    return text


def to_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def get_distance_m(lat1, lng1, lat2, lng2):
    from math import radians, sin, cos, asin, sqrt

    lng1, lat1, lng2, lat2 = map(radians, [lng1, lat1, lng2, lat2])
    dlng = lng2 - lng1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def classify_fire_subtype(name):
    text = clean_text(name)
    if "구조대" in text:
        return "구조대"
    if "안전센터" in text or "119" in text:
        return "안전센터"
    return "기타"


def main():
    apartment_df = read_csv_with_fallback(APT_PATH)
    fire_df = read_csv_with_fallback(RAW_PATH)

    required_apt_cols = ["k-아파트명", "주소(시군구)", "주소(읍면동)", "좌표X", "좌표Y"]
    for col in required_apt_cols:
        if col not in apartment_df.columns:
            raise KeyError(f"아파트 CSV에 '{col}' 컬럼이 없습니다.")

    required_fire_cols = ["서ㆍ센터명", "X좌표", "Y좌표"]
    for col in required_fire_cols:
        if col not in fire_df.columns:
            raise KeyError(f"소방 CSV에 '{col}' 컬럼이 없습니다.")

    # 서울시 중부원점 좌표계로 보고 WGS84로 변환한다.
    transformer = Transformer.from_crs("EPSG:5186", "EPSG:4326", always_xy=True)

    fire_items = []
    for _, row in fire_df.iterrows():
        x = to_float(row.get("X좌표"))
        y = to_float(row.get("Y좌표"))
        name = clean_text(row.get("서ㆍ센터명"))

        if x is None or y is None or not name:
            continue

        try:
            lng, lat = transformer.transform(x, y)
        except Exception:
            continue

        fire_items.append({
            "label": name,
            "subtype": classify_fire_subtype(name),
            "lat": lat,
            "lng": lng,
        })

    results = []

    for _, apt in apartment_df.iterrows():
        apt_name = clean_text(apt.get("k-아파트명"))
        apt_gu = clean_text(apt.get("주소(시군구)"))
        apt_dong = clean_text(apt.get("주소(읍면동)"))
        apt_lng = to_float(apt.get("좌표X"))
        apt_lat = to_float(apt.get("좌표Y"))

        if not apt_name or apt_lat is None or apt_lng is None:
            continue

        nearby = []
        for item in fire_items:
            try:
                distance = round(get_distance_m(apt_lat, apt_lng, item["lat"], item["lng"]))
            except Exception:
                continue

            if distance <= RADIUS_M:
                nearby.append({
                    "label": item["label"],
                    "distance": distance,
                    "subtype": item["subtype"],
                    "lat": item["lat"],
                    "lng": item["lng"],
                })

        nearby.sort(key=lambda item: item.get("distance", 999999))

        safety_center_count = sum(1 for item in nearby if item.get("subtype") == "안전센터")
        rescue_count = sum(1 for item in nearby if item.get("subtype") == "구조대")
        etc_count = sum(1 for item in nearby if item.get("subtype") == "기타")

        nearest = nearby[0] if nearby else {}

        results.append({
            "name": apt_name,
            "gu": apt_gu,
            "dong": apt_dong,
            "fire_station_count_1500m": len(nearby),
            "nearest_fire_station_name": nearest.get("label", ""),
            "nearest_fire_station_subtype": nearest.get("subtype", ""),
            "nearest_fire_station_distance": nearest.get("distance", ""),
            "safety_center_count": safety_center_count,
            "rescue_count": rescue_count,
            "fire_etc_count": etc_count,
            "fire_station_items_json": json.dumps(nearby[:MAX_ITEMS], ensure_ascii=False),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[FIRE BASELINE] raw 시설 {len(fire_items)}개")
    print(f"[FIRE BASELINE] 아파트 {len(results)}개 기준 저장 완료: {OUT_PATH}")


if __name__ == "__main__":
    main()

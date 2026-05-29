import json
import math
from pathlib import Path

import pandas as pd
from pyproj import Transformer

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
COMMERCIAL_DIR = BASE_DIR / "data" / "commercial" / "area"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "commercial_baseline.csv"

COMMERCIAL_RADIUS_M = 1000
MAX_ITEMS = 30

TYPE_DISPLAY_MAP = {
    "골목상권": "골목",
    "발달상권": "대형상권",
    "전통시장": "시장",
    "관광특구": "관광특구",
}

COUNT_COLUMN_MAP = {
    "골목": "alley_count",
    "대형상권": "developed_count",
    "시장": "market_count",
    "관광특구": "tourism_count",
}


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


def find_commercial_area_file():
    candidates = list(COMMERCIAL_DIR.glob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"상권영역 CSV 파일이 없습니다: {COMMERCIAL_DIR}")
    return candidates[0]


def haversine_m(lat1, lng1, lat2, lng2):
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize_commercial_type(raw_type):
    raw_type = str(raw_type or "").strip()
    return TYPE_DISPLAY_MAP.get(raw_type, raw_type or "기타")


def prepare_commercial_areas():
    commercial_path = find_commercial_area_file()
    df = read_csv_with_fallback(commercial_path)

    required = [
        "상권_구분_코드_명",
        "상권_코드",
        "상권_코드_명",
        "엑스좌표_값",
        "와이좌표_값",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"상권영역 필수 컬럼 누락: {missing}")

    transformer = Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)

    areas = []

    for _, row in df.iterrows():
        try:
            x = float(row.get("엑스좌표_값"))
            y = float(row.get("와이좌표_값"))
            if math.isnan(x) or math.isnan(y):
                continue
            lng, lat = transformer.transform(x, y)
            if math.isnan(lat) or math.isnan(lng):
                continue
        except Exception:
            continue

        raw_type = str(row.get("상권_구분_코드_명", "")).strip()
        display_type = normalize_commercial_type(raw_type)

        areas.append({
            "commercial_code": str(row.get("상권_코드", "")).strip(),
            "name": str(row.get("상권_코드_명", "")).strip(),
            "raw_type": raw_type,
            "display_type": display_type,
            "lat": lat,
            "lng": lng,
            "gu": str(row.get("자치구_코드_명", "")).strip(),
            "dong": str(row.get("행정동_코드_명", "")).strip(),
            "area_size": row.get("영역_면적", ""),
        })

    return areas


def prepare_apartments():
    df = read_csv_with_fallback(APARTMENT_PATH)

    apartments = []

    for _, row in df.iterrows():
        try:
            lat = float(row.get("좌표Y"))
            lng = float(row.get("좌표X"))
            if math.isnan(lat) or math.isnan(lng):
                continue
        except Exception:
            continue

        apartments.append({
            "name": str(row.get("k-아파트명", "")).strip(),
            "gu": str(row.get("주소(시군구)", "")).strip(),
            "dong": str(row.get("주소(읍면동)", "")).strip(),
            "lat": lat,
            "lng": lng,
        })

    return apartments


def build_baseline_row(apartment, commercial_areas):
    items = []

    for area in commercial_areas:
        distance = round(
            haversine_m(
                apartment["lat"],
                apartment["lng"],
                area["lat"],
                area["lng"],
            )
        )

        if distance > COMMERCIAL_RADIUS_M:
            continue

        label = area["name"]
        if area["display_type"]:
            label = f"{area['name']} · {area['display_type']}"

        items.append({
            "label": label,
            "distance": int(distance),
            "subtype": area["display_type"],
            "raw_type": area["raw_type"],
            "commercial_code": area["commercial_code"],
            "lat": round(area["lat"], 7),
            "lng": round(area["lng"], 7),
        })

    items.sort(key=lambda item: item.get("distance", 999999))
    nearest = items[0] if items else {}

    counts = {
        "alley_count": 0,
        "developed_count": 0,
        "market_count": 0,
        "tourism_count": 0,
    }

    for item in items:
        count_key = COUNT_COLUMN_MAP.get(item.get("subtype"))
        if count_key:
            counts[count_key] += 1

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "commercial_count_1km": len(items),
        "nearest_commercial_name": str(nearest.get("label", "")).split(" · ")[0],
        "nearest_commercial_type": nearest.get("raw_type", ""),
        "nearest_commercial_display_type": nearest.get("subtype", ""),
        "nearest_commercial_distance": nearest.get("distance", ""),
        **counts,
        "commercial_items_json": json.dumps(items[:MAX_ITEMS], ensure_ascii=False),
    }


def main():
    apartments = prepare_apartments()
    commercial_areas = prepare_commercial_areas()

    rows = []

    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, commercial_areas))

        if idx % 200 == 0:
            print(f"[COMMERCIAL] {idx}/{len(apartments)} 처리")

    output_df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[COMMERCIAL] 상권 영역 {len(commercial_areas)}개 기준")
    print(f"[COMMERCIAL] baseline 저장 완료: {OUTPUT_PATH}")
    print(f"[COMMERCIAL] 아파트 {len(rows)}개")


if __name__ == "__main__":
    main()

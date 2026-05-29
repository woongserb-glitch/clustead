import json
import math
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
BIKE_PATH = BASE_DIR / "data" / "bike" / "bike_station_seoul.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "bike_baseline.csv"

BIKE_RADIUS_M = 500
MAX_ITEMS = 30


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


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


def prepare_bike_stations():
    df = read_csv_with_fallback(BIKE_PATH)

    required = ["대여소_ID", "주소1", "주소2", "위도", "경도"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"따릉이 필수 컬럼 누락: {missing}")

    stations = []

    for _, row in df.iterrows():
        try:
            lat = float(row.get("위도"))
            lng = float(row.get("경도"))
            if math.isnan(lat) or math.isnan(lng):
                continue
            if lat == 0 or lng == 0:
                continue
            if not (33 <= lat <= 39 and 124 <= lng <= 132):
                continue
        except Exception:
            continue

        station_id = str(row.get("대여소_ID", "")).strip()
        address1 = str(row.get("주소1", "")).strip()
        address2 = str(row.get("주소2", "")).strip()

        label = address2 or address1 or station_id or "따릉이 대여소"

        stations.append({
            "station_id": station_id,
            "label": label,
            "address": address1,
            "lat": lat,
            "lng": lng,
        })

    return stations


def build_baseline_row(apartment, stations):
    items = []

    for station in stations:
        distance = round(
            haversine_m(
                apartment["lat"],
                apartment["lng"],
                station["lat"],
                station["lng"],
            )
        )

        if distance > BIKE_RADIUS_M:
            continue

        label = station.get("label", "따릉이 대여소")
        station_id = station.get("station_id", "")

        if station_id:
            display_label = f"{label} · {station_id}"
        else:
            display_label = label

        items.append({
            "label": display_label,
            "distance": int(distance),
            "station_id": station_id,
            "lat": round(station["lat"], 7),
            "lng": round(station["lng"], 7),
        })

    items.sort(key=lambda item: item.get("distance", 999999))
    nearest = items[0] if items else {}

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "bike_station_count_500m": len(items),
        "nearest_bike_station": nearest.get("label", ""),
        "nearest_bike_station_distance": nearest.get("distance", ""),
        "bike_items_json": json.dumps(items[:MAX_ITEMS], ensure_ascii=False),
    }


def main():
    apartments = prepare_apartments()
    stations = prepare_bike_stations()

    rows = []

    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, stations))

        if idx % 200 == 0:
            print(f"[BIKE] {idx}/{len(apartments)} 처리")

    output_df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[BIKE] 유효 따릉이 대여소 {len(stations)}개 기준")
    print(f"[BIKE] baseline 저장 완료: {OUTPUT_PATH}")
    print(f"[BIKE] 아파트 {len(rows)}개")


if __name__ == "__main__":
    main()

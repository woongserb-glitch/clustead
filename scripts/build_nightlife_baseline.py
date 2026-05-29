import json
import math
from pathlib import Path

import pandas as pd
from pyproj import Transformer

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
NIGHTLIFE_DIR = BASE_DIR / "data" / "nightlife"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "nightlife_baseline.csv"

NIGHTLIFE_RADIUS_M = 500
NIGHTLIFE_WIDE_RADIUS_M = 1000
MAX_ITEMS = 30

SUBTYPE_COUNT_COLUMNS = {
    "룸살롱": "room_salon_count",
    "바/주점": "bar_count",
    "클럽/나이트": "club_count",
    "기타": "etc_count",
}


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


def find_nightlife_file():
    candidates = list(NIGHTLIFE_DIR.glob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"유흥주점 CSV 파일이 없습니다: {NIGHTLIFE_DIR}")
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


def normalize_subtype(raw_type):
    raw = str(raw_type or "").strip()

    if "룸살롱" in raw:
        return "룸살롱"

    if any(keyword in raw for keyword in ["스텐드바", "비어", "간이주점"]):
        return "바/주점"

    if any(keyword in raw for keyword in ["카바레", "클럽", "디스코", "나이트"]):
        return "클럽/나이트"

    return "기타"


def prepare_nightlife_places():
    nightlife_path = find_nightlife_file()
    df = read_csv_with_fallback(nightlife_path)

    required = [
        "영업상태명",
        "사업장명",
        "업태구분명",
        "좌표정보(X)",
        "좌표정보(Y)",
    ]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"유흥주점 필수 컬럼 누락: {missing}")

    df = df[df["영업상태명"].astype(str).str.strip() == "영업/정상"].copy()

    transformer = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)
    places = []

    for _, row in df.iterrows():
        try:
            x = float(row.get("좌표정보(X)"))
            y = float(row.get("좌표정보(Y)"))
            if math.isnan(x) or math.isnan(y):
                continue

            lng, lat = transformer.transform(x, y)
            if math.isnan(lat) or math.isnan(lng):
                continue
        except Exception:
            continue

        name = str(row.get("사업장명", "")).strip()
        raw_type = str(row.get("업태구분명", row.get("위생업태명", ""))).strip()
        subtype = normalize_subtype(raw_type)

        if not name:
            name = "유흥주점"

        places.append({
            "name": name,
            "subtype": subtype,
            "raw_type": raw_type,
            "lat": lat,
            "lng": lng,
            "address": str(row.get("도로명주소", "") or row.get("지번주소", "")).strip(),
        })

    return places


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


def build_baseline_row(apartment, places):
    items_500m = []
    count_1km = 0

    for place in places:
        distance = round(
            haversine_m(
                apartment["lat"],
                apartment["lng"],
                place["lat"],
                place["lng"],
            )
        )

        if distance <= NIGHTLIFE_WIDE_RADIUS_M:
            count_1km += 1

        if distance > NIGHTLIFE_RADIUS_M:
            continue

        items_500m.append({
            "label": place["name"],
            "distance": int(distance),
            "subtype": place["subtype"],
            "raw_type": place["raw_type"],
            "lat": round(place["lat"], 7),
            "lng": round(place["lng"], 7),
        })

    items_500m.sort(key=lambda item: item.get("distance", 999999))
    nearest = items_500m[0] if items_500m else {}

    counts = {
        "room_salon_count": 0,
        "bar_count": 0,
        "club_count": 0,
        "etc_count": 0,
    }

    for item in items_500m:
        count_key = SUBTYPE_COUNT_COLUMNS.get(item.get("subtype"), "etc_count")
        counts[count_key] += 1

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "nightlife_count_500m": len(items_500m),
        "nightlife_count_1km": count_1km,
        "nearest_nightlife_name": nearest.get("label", ""),
        "nearest_nightlife_type": nearest.get("raw_type", ""),
        "nearest_nightlife_subtype": nearest.get("subtype", ""),
        "nearest_nightlife_distance": nearest.get("distance", ""),
        **counts,
        "nightlife_items_json": json.dumps(items_500m[:MAX_ITEMS], ensure_ascii=False),
    }


def main():
    apartments = prepare_apartments()
    places = prepare_nightlife_places()

    rows = []

    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, places))

        if idx % 200 == 0:
            print(f"[NIGHTLIFE] {idx}/{len(apartments)} 처리")

    output_df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[NIGHTLIFE] 영업/정상 유흥주점 {len(places)}개 기준")
    print(f"[NIGHTLIFE] baseline 저장 완료: {OUTPUT_PATH}")
    print(f"[NIGHTLIFE] 아파트 {len(rows)}개")


if __name__ == "__main__":
    main()

import csv
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd
from pyproj import Transformer


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from services.preload_service import apartment_data, load_apartment_data

APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
RAW_PATH = BASE_DIR / "data" / "lifestyle_food" / "rest_food_seoul.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "lifestyle_food_baseline.csv"

MAX_ITEMS = 50


SUBTYPE_KEYWORDS = {
    "카페": [
        "커피",
        "카페",
        "까페",
        "다방",
        "스타벅스",
        "투썸",
        "이디야",
        "메가",
        "컴포즈",
        "빽다방",
    ],
    "패스트푸드": [
        "패스트푸드",
        "맥도날드",
        "버거",
        "롯데리아",
        "맘스터치",
        "KFC",
        "써브웨이",
        "서브웨이",
    ],
    "베이커리/디저트": [
        "제과",
        "제빵",
        "베이커리",
        "파리바게뜨",
        "뚜레쥬르",
        "도넛",
        "도너츠",
        "아이스크림",
        "디저트",
    ],
}


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"CSV encoding read failed: {path}")


def clean(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def to_float(value):
    try:
        number = float(str(value).strip())
        if math.isnan(number):
            return None
        return number
    except Exception:
        return None


def first_value(row, *names):
    for name in names:
        if name in row:
            value = clean(row.get(name))
            if value:
                return value
    return ""


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


def parse_gu_dong(address):
    parts = clean(address).split()
    gu = next((part for part in parts if part.endswith("구")), "")
    dong = next((part for part in parts if part.endswith(("동", "가"))), "")
    return gu, dong


def classify_food(row):
    name = first_value(row, "BPLCNM", "사업장명")
    industry = first_value(row, "UPTAENM", "업태구분명", "SNTUPTAENM", "위생업태명")
    text = f"{name} {industry}".upper()

    for subtype, keywords in SUBTYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.upper() in text:
                return subtype

    return ""


def is_open(row):
    state = first_value(row, "TRDSTATENM", "영업상태명")
    detail = first_value(row, "DTLSTATENM", "상세영업상태명")
    close_date = first_value(row, "DCBYMD", "폐업일자")
    text = f"{state} {detail}"

    if close_date:
        return False

    return "폐업" not in text and "취소" not in text and "말소" not in text


def prepare_apartments():
    load_apartment_data()
    apartments = []

    for row in apartment_data:
        lat = to_float(row.get("lat"))
        lng = to_float(row.get("lng"))

        if lat is None or lng is None:
            continue

        apartments.append({
            "name": clean(row.get("name")),
            "gu": clean(row.get("gu")),
            "dong": clean(row.get("dong")),
            "lat": lat,
            "lng": lng,
        })

    return apartments


def prepare_food_places():
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Lifestyle food rawdata not found: {RAW_PATH}")

    df = read_csv_with_fallback(RAW_PATH)
    transformer = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)
    places = []

    for _, row in df.iterrows():
        if not is_open(row):
            continue

        subtype = classify_food(row)
        if not subtype:
            continue

        x = to_float(first_value(row, "X", "좌표정보(X)"))
        y = to_float(first_value(row, "Y", "좌표정보(Y)"))
        name = first_value(row, "BPLCNM", "사업장명")
        address = first_value(row, "RDNWHLADDR", "도로명주소", "SITEWHLADDR", "지번주소")

        if x is None or y is None or not name:
            continue

        lng, lat = transformer.transform(x, y)
        if not (37.35 <= lat <= 37.75 and 126.75 <= lng <= 127.25):
            continue

        gu, dong = parse_gu_dong(address)
        places.append({
            "name": name,
            "label": name,
            "lat": lat,
            "lng": lng,
            "address": address,
            "gu": gu,
            "dong": dong,
            "subtype": subtype,
            "industry": first_value(row, "UPTAENM", "업태구분명", "SNTUPTAENM", "위생업태명"),
        })

    return places


def collect_within(apartment, places, radius, subtype=None):
    result = []
    lat = apartment["lat"]
    lng = apartment["lng"]
    lat_delta = radius / 111000
    lng_delta = radius / (111000 * max(math.cos(math.radians(lat)), 0.2))

    for place in places:
        if subtype and place.get("subtype") != subtype:
            continue
        if abs(place["lat"] - lat) > lat_delta or abs(place["lng"] - lng) > lng_delta:
            continue

        distance = haversine_m(lat, lng, place["lat"], place["lng"])
        if distance <= radius:
            result.append({
                **place,
                "distance": round(distance),
            })

    result.sort(key=lambda item: item["distance"])
    return result


def nearest(items):
    if not items:
        return "", "", ""
    item = items[0]
    return item.get("name", ""), item.get("distance", ""), item.get("subtype", "")


def output_item(item):
    return {
        "label": item.get("name", ""),
        "name": item.get("name", ""),
        "lat": item.get("lat"),
        "lng": item.get("lng"),
        "distance": item.get("distance"),
        "subtype": item.get("subtype", ""),
        "address": item.get("address", ""),
    }


def main():
    print("[LIFESTYLE FOOD] load apartments")
    apartments = prepare_apartments()
    print("[LIFESTYLE FOOD] load raw food places")
    places = prepare_food_places()
    print(f"[LIFESTYLE FOOD] apartments={len(apartments)} food_places={len(places)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "name",
            "gu",
            "dong",
            "lat",
            "lng",
            "lifestyle_food_count_500m",
            "lifestyle_food_count_1km",
            "food_cafe_count_500m",
            "fastfood_count_500m",
            "bakery_dessert_count_500m",
            "nearest_lifestyle_food_name",
            "nearest_lifestyle_food_distance",
            "nearest_lifestyle_food_subtype",
            "lifestyle_food_items_json",
        ])
        writer.writeheader()

        total = len(apartments)
        for index, apartment in enumerate(apartments, start=1):
            food_500m = collect_within(apartment, places, 500)
            food_1km = collect_within(apartment, places, 1000)
            cafe_500m = collect_within(apartment, places, 500, "카페")
            fastfood_500m = collect_within(apartment, places, 500, "패스트푸드")
            bakery_500m = collect_within(apartment, places, 500, "베이커리/디저트")
            nearest_name, nearest_distance, nearest_subtype = nearest(food_1km)

            writer.writerow({
                "name": apartment["name"],
                "gu": apartment["gu"],
                "dong": apartment["dong"],
                "lat": apartment["lat"],
                "lng": apartment["lng"],
                "lifestyle_food_count_500m": len(food_500m),
                "lifestyle_food_count_1km": len(food_1km),
                "food_cafe_count_500m": len(cafe_500m),
                "fastfood_count_500m": len(fastfood_500m),
                "bakery_dessert_count_500m": len(bakery_500m),
                "nearest_lifestyle_food_name": nearest_name,
                "nearest_lifestyle_food_distance": nearest_distance,
                "nearest_lifestyle_food_subtype": nearest_subtype,
                "lifestyle_food_items_json": json.dumps(
                    [output_item(item) for item in food_1km[:MAX_ITEMS]],
                    ensure_ascii=False,
                ),
            })

            if index == 1 or index % 500 == 0 or index == total:
                print(f"[LIFESTYLE FOOD] apartment {index}/{total}")

    print(f"[DONE] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

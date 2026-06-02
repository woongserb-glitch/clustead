import csv
import json
import math
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from services.preload_service import apartment_data, load_apartment_data

APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
HOSPITAL_RAW_PATH = BASE_DIR / "data" / "medical" / "hospital_seoul.csv"
PHARMACY_RAW_PATH = BASE_DIR / "data" / "medical" / "pharmacy_hours_seoul.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "medical_baseline.csv"

MAX_ITEMS = 50
SUPERIOR_HOSPITAL_RADIUS_M = 5000

# 진료과 분류 규칙. 복합명(소아치과·어린이안과 등)이 일반과로 흡수되지 않도록
# 장기/접미 특화과를 먼저, 일반과(소아과·산부인과·내과·외과)를 나중에 매칭한다.
# (텍스트는 이름 + 공식 병원분류명만 사용 — 진료안내/비고의 진료과목 나열은 제외)
HOSPITAL_SUBTYPE_RULES = [
    ("치과", ["치과", "구강", "교정", "임플란트"]),
    ("한의원", ["한의원", "한방", "한의"]),
    ("안과", ["안과", "안센터"]),
    ("이비인후과", ["이비인후과", "이비인후"]),
    ("정형외과", ["정형외과", "관절", "척추"]),
    ("피부과", ["피부과", "피부"]),
    ("비뇨기과", ["비뇨기과", "비뇨"]),
    ("성형외과", ["성형외과"]),
    ("정신건강의학과", ["정신건강의학과", "정신과"]),
    ("재활의학과", ["재활의학과", "재활"]),
    ("가정의학과", ["가정의학과"]),
    ("소아과", ["소아청소년과", "소아과", "어린이"]),
    ("산부인과", ["산부인과", "여성의원"]),
    ("내과", ["내과", "건강검진", "검진"]),
    ("외과", ["외과"]),
]

PHARMACY_SUBTYPE_ORDER = ["일반", "야간", "주말", "휴일"]

# 진료과별 1km 내 전체 카운트 컬럼(items_json cap 영향 없는 정확 카운트).
HOSPITAL_SPECIALTY_SUBTYPES = [subtype for subtype, _ in HOSPITAL_SUBTYPE_RULES]


def specialty_count_column(subtype):
    return f"{subtype}_count_1km"


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


def to_int(value):
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0


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


def classify_hospital_subtype(row, name):
    # 이름 + 공식 병원분류명만 사용한다. 진료안내(DUTYINF)·비고(DUTYETC)에는 해당 의원이
    # '진료 가능한 과목'이 여러 개 나열돼 있어, 이를 포함하면 모든 일반 의원이 소아과 등으로
    # 과대 분류된다(예: 1km 내 소아과가 45곳으로 부풀려짐). 1차 전문과목은 통상 기관명에 드러난다.
    medical_class = first_value(row, "DUTYDIVNAM", "병원분류명")
    text = f"{name} {medical_class}"

    for subtype, keywords in HOSPITAL_SUBTYPE_RULES:
        if any(keyword in text for keyword in keywords):
            return subtype

    return "기타"


def is_superior_hospital(row):
    medical_class = first_value(row, "DUTYDIVNAM", "병원분류명")
    emergency_class = first_value(row, "DUTYEMCLSNAME", "응급의료기관코드명")
    text = f"{medical_class} {emergency_class}"
    return "상급종합병원" in text or "종합병원" in text


def parse_hhmm(value):
    text = clean(value)
    if not text:
        return None
    try:
        number = int(float(text))
    except Exception:
        return None
    hour = number // 100
    minute = number % 100
    if 0 <= hour <= 24 and 0 <= minute < 60:
        return hour * 60 + minute
    return None


def classify_pharmacy_subtypes(row):
    subtypes = []

    close_minutes = [
        parse_hhmm(first_value(row, f"DUTYTIME{day}C"))
        for day in range(1, 9)
    ]

    if any(minutes is not None and minutes >= 22 * 60 for minutes in close_minutes):
        subtypes.append("야간")

    saturday_open = first_value(row, "DUTYTIME6S") and first_value(row, "DUTYTIME6C")
    sunday_open = first_value(row, "DUTYTIME7S") and first_value(row, "DUTYTIME7C")
    holiday_open = first_value(row, "DUTYTIME8S") and first_value(row, "DUTYTIME8C")

    if saturday_open or sunday_open:
        subtypes.append("주말")

    if holiday_open:
        subtypes.append("휴일")

    if not subtypes:
        subtypes.append("일반")

    return [subtype for subtype in PHARMACY_SUBTYPE_ORDER if subtype in subtypes]


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


def prepare_hospitals():
    if not HOSPITAL_RAW_PATH.exists():
        raise FileNotFoundError(f"Hospital rawdata not found: {HOSPITAL_RAW_PATH}")

    df = read_csv_with_fallback(HOSPITAL_RAW_PATH)
    places = []

    for _, row in df.iterrows():
        lat = to_float(first_value(row, "WGS84LAT", "위도", "lat"))
        lng = to_float(first_value(row, "WGS84LON", "경도", "lng", "lon"))
        name = first_value(row, "DUTYNAME", "기관명", "병원명", "name")
        address = first_value(row, "DUTYADDR", "주소", "address")

        if lat is None or lng is None or not name:
            continue

        gu, dong = parse_gu_dong(address)
        emergency = first_value(row, "DUTYERYN", "응급실운영여부") == "1"
        emergency_name = first_value(row, "DUTYEMCLSNAME", "응급의료기관코드명")

        subtype = classify_hospital_subtype(row, name)

        places.append({
            "name": name,
            "label": name,
            "lat": lat,
            "lng": lng,
            "address": address,
            "gu": gu,
            "dong": dong,
            "type": "emergency" if emergency else "hospital",
            "subtype": "응급실" if emergency else subtype,
            "subtypes": ["응급실"] if emergency else [subtype],
            "emergency": emergency,
            "superior_hospital": is_superior_hospital(row),
            "medical_class": first_value(row, "DUTYDIVNAM", "병원분류명"),
            "emergency_class": emergency_name,
        })

    return places


def prepare_pharmacies():
    if not PHARMACY_RAW_PATH.exists():
        raise FileNotFoundError(f"Pharmacy rawdata not found: {PHARMACY_RAW_PATH}")

    df = read_csv_with_fallback(PHARMACY_RAW_PATH)
    places = []

    for _, row in df.iterrows():
        lat = to_float(first_value(row, "WGS84LAT", "위도", "lat"))
        lng = to_float(first_value(row, "WGS84LON", "경도", "lng", "lon"))
        name = first_value(row, "DUTYNAME", "약국명", "기관명", "name")
        address = first_value(row, "DUTYADDR", "주소", "address")

        if lat is None or lng is None or not name:
            continue

        gu, dong = parse_gu_dong(address)
        pharmacy_subtypes = classify_pharmacy_subtypes(row)

        places.append({
            "name": name,
            "label": name,
            "lat": lat,
            "lng": lng,
            "address": address,
            "gu": gu,
            "dong": dong,
            "type": "pharmacy",
            "subtype": pharmacy_subtypes[0],
            "subtypes": pharmacy_subtypes,
            "emergency": False,
        })

    return places


def collect_within(apartment, places, radius, type_filter=None):
    result = []
    lat = apartment["lat"]
    lng = apartment["lng"]
    lat_delta = radius / 111000
    lng_delta = radius / (111000 * max(math.cos(math.radians(lat)), 0.2))

    for place in places:
        if type_filter and place.get("type") != type_filter:
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


def nearest_name_distance(items):
    if not items:
        return "", ""
    return items[0].get("name", ""), items[0].get("distance", "")


def output_item(item, type_override=None, subtype_override=None, subtypes_override=None):
    subtype = subtype_override if subtype_override is not None else item.get("subtype", "")
    subtypes = subtypes_override if subtypes_override is not None else item.get("subtypes", [])
    if not subtypes and subtype:
        subtypes = [subtype]

    return {
        "label": item.get("name", ""),
        "name": item.get("name", ""),
        "lat": item.get("lat"),
        "lng": item.get("lng"),
        "distance": item.get("distance"),
        "subtype": subtype,
        "subtypes": subtypes,
        "type": type_override or item.get("type", ""),
        "address": item.get("address", ""),
        "medical_class": item.get("medical_class", ""),
    }


def main():
    print("[MEDICAL] load apartments")
    apartments = prepare_apartments()

    print("[MEDICAL] load raw hospital/pharmacy")
    hospitals = prepare_hospitals()
    pharmacies = prepare_pharmacies()
    medical_places = hospitals + pharmacies
    superior_hospitals = [place for place in hospitals if place.get("superior_hospital")]

    print(
        f"[MEDICAL] apartments={len(apartments)} hospitals={len(hospitals)} "
        f"superior_hospitals={len(superior_hospitals)} pharmacies={len(pharmacies)}"
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "name",
            "gu",
            "dong",
            "lat",
            "lng",
            "medical_count_500m",
            "medical_count_1km",
            "hospital_count_500m",
            "hospital_count_1km",
            "emergency_count_1km",
            "emergency_count_3km",
            "superior_hospital_count_5km",
            "pharmacy_count_500m",
            "pharmacy_count_1km",
            *[specialty_count_column(subtype) for subtype in HOSPITAL_SPECIALTY_SUBTYPES],
            "nearest_hospital_name",
            "nearest_hospital_distance",
            "nearest_emergency_name",
            "nearest_emergency_distance",
            "nearest_superior_hospital_name",
            "nearest_superior_hospital_distance",
            "nearest_pharmacy_name",
            "nearest_pharmacy_distance",
            "hospital_items_json",
            "emergency_items_json",
            "superior_hospital_items_json",
            "pharmacy_items_json",
            "medical_items_json",
        ])
        writer.writeheader()

        total = len(apartments)
        for index, apartment in enumerate(apartments, start=1):
            medical_500m = collect_within(apartment, medical_places, 500)
            medical_1km = collect_within(apartment, medical_places, 1000)
            hospitals_500m = collect_within(apartment, hospitals, 500, "hospital")
            hospitals_1km = collect_within(apartment, hospitals, 1000, "hospital")
            emergency_1km = collect_within(apartment, hospitals, 1000, "emergency")
            emergency_3km = collect_within(apartment, hospitals, 3000, "emergency")
            superior_5km = collect_within(apartment, superior_hospitals, SUPERIOR_HOSPITAL_RADIUS_M)
            pharmacies_500m = collect_within(apartment, pharmacies, 500, "pharmacy")
            pharmacies_1km = collect_within(apartment, pharmacies, 1000, "pharmacy")

            specialty_counts = {subtype: 0 for subtype in HOSPITAL_SPECIALTY_SUBTYPES}
            for hospital in hospitals_1km:
                subtype = hospital.get("subtype")
                if subtype in specialty_counts:
                    specialty_counts[subtype] += 1

            nearest_hospital_name, nearest_hospital_distance = nearest_name_distance(hospitals_1km)
            nearest_emergency_name, nearest_emergency_distance = nearest_name_distance(emergency_3km)
            nearest_superior_name, nearest_superior_distance = nearest_name_distance(superior_5km)
            nearest_pharmacy_name, nearest_pharmacy_distance = nearest_name_distance(pharmacies_1km)

            display_items = (
                hospitals_1km[:20]
                + emergency_3km[:15]
                + pharmacies_1km[:20]
            )
            display_items = sorted(display_items, key=lambda item: item.get("distance", 999999))[:MAX_ITEMS]

            writer.writerow({
                "name": apartment["name"],
                "gu": apartment["gu"],
                "dong": apartment["dong"],
                "lat": apartment["lat"],
                "lng": apartment["lng"],
                "medical_count_500m": len(medical_500m),
                "medical_count_1km": len(medical_1km),
                "hospital_count_500m": len(hospitals_500m),
                "hospital_count_1km": len(hospitals_1km),
                "emergency_count_1km": len(emergency_1km),
                "emergency_count_3km": len(emergency_3km),
                "superior_hospital_count_5km": len(superior_5km),
                "pharmacy_count_500m": len(pharmacies_500m),
                "pharmacy_count_1km": len(pharmacies_1km),
                **{specialty_count_column(subtype): specialty_counts[subtype]
                   for subtype in HOSPITAL_SPECIALTY_SUBTYPES},
                "nearest_hospital_name": nearest_hospital_name,
                "nearest_hospital_distance": nearest_hospital_distance,
                "nearest_emergency_name": nearest_emergency_name,
                "nearest_emergency_distance": nearest_emergency_distance,
                "nearest_superior_hospital_name": nearest_superior_name,
                "nearest_superior_hospital_distance": nearest_superior_distance,
                "nearest_pharmacy_name": nearest_pharmacy_name,
                "nearest_pharmacy_distance": nearest_pharmacy_distance,
                "hospital_items_json": json.dumps(
                    [output_item(item) for item in hospitals_1km[:MAX_ITEMS]],
                    ensure_ascii=False,
                ),
                "emergency_items_json": json.dumps(
                    [output_item(item) for item in emergency_3km[:MAX_ITEMS]],
                    ensure_ascii=False,
                ),
                "superior_hospital_items_json": json.dumps(
                    [
                        output_item(
                            item,
                            type_override="general-hospital",
                            subtype_override="상급병원",
                            subtypes_override=["상급병원"],
                        )
                        for item in superior_5km[:MAX_ITEMS]
                    ],
                    ensure_ascii=False,
                ),
                "pharmacy_items_json": json.dumps(
                    [output_item(item) for item in pharmacies_1km[:MAX_ITEMS]],
                    ensure_ascii=False,
                ),
                "medical_items_json": json.dumps(
                    [output_item(item) for item in display_items],
                    ensure_ascii=False,
                ),
            })

            if index == 1 or index % 500 == 0 or index == total:
                print(f"[MEDICAL] apartment {index}/{total}")

    print(f"[DONE] {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

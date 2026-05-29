import csv
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
RAW_PATH = BASE_DIR / "data" / "ev_chargers" / "ev_chargers_raw.xml"
FILTERED_PATH = BASE_DIR / "data" / "ev_chargers" / "ev_chargers_seoul_filtered.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "ev_charger_baseline.csv"

SEOUL_BOUNDS = {
    "min_lat": 37.35,
    "max_lat": 37.75,
    "min_lng": 126.75,
    "max_lng": 127.25,
}

MAX_ITEMS = 30


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV encoding read failed: {path}")


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


def row_text(row, *names):
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def table_value(row, *names):
    for name in names:
        if name in row:
            value = clean(row.get(name))
            if value:
                return value
    return ""


def local_name(tag):
    return str(tag).split("}", 1)[-1]


def read_xml_items(path):
    if not path.exists():
        raise FileNotFoundError(f"EV rawdata not found: {path}")

    root = ET.parse(path).getroot()
    items = []

    for element in root.iter():
        if local_name(element.tag).lower() != "item":
            continue

        row = {}
        for child in list(element):
            row[local_name(child.tag)] = clean(child.text)
        if row:
            items.append(row)

    if not items:
        raise RuntimeError(f"No EV charger items found in XML: {path}")

    return items


def prepare_apartments():
    df = read_csv_with_fallback(APARTMENT_PATH)
    apartments = []

    for _, row in df.iterrows():
        lat = to_float(table_value(row, "좌표Y", "醫뚰몴Y"))
        lng = to_float(table_value(row, "좌표X", "醫뚰몴X"))

        if lat is None or lng is None:
            continue

        apartments.append({
            "name": table_value(row, "k-아파트명", "k-?꾪뙆?몃챸"),
            "gu": table_value(row, "주소(시군구)", "二쇱냼(?쒓뎔援?"),
            "dong": table_value(row, "주소(읍면동)", "二쇱냼(?띾㈃??"),
            "lat": lat,
            "lng": lng,
        })

    return apartments


def is_seoul_charger(row, lat, lng):
    address = row_text(row, "addr", "addrDoro", "address", "rdnmadr", "lnmadr")
    zcode = row_text(row, "zcode", "zscode")

    if "서울" in address or zcode.startswith("11"):
        return True

    return (
        SEOUL_BOUNDS["min_lat"] <= lat <= SEOUL_BOUNDS["max_lat"]
        and SEOUL_BOUNDS["min_lng"] <= lng <= SEOUL_BOUNDS["max_lng"]
    )


def is_deleted_or_closed(row):
    del_text = row_text(row, "delYn", "deleteYn", "삭제여부", "폐쇄여부").upper()
    if del_text in {"Y", "1", "TRUE"} or any(token in del_text for token in ["삭제", "폐쇄", "사용불가"]):
        return True

    status = row_text(row, "stat", "chgerStat", "충전기상태")
    status_text = row_text(row, "statNm", "statusName", "상태명")
    closed_tokens = ["폐쇄", "운영중지", "사용불가", "삭제"]

    if status in {"4"}:
        return True

    return any(token in status_text for token in closed_tokens)


def is_fast_charger(row):
    chger_type = row_text(row, "chgerType", "충전기타입", "chargerType")
    output = to_float(row_text(row, "output", "출력"))
    text = " ".join([
        chger_type,
        row_text(row, "method", "powerType", "충전방식"),
    ])

    if output is not None and output >= 50:
        return True

    if any(token in text.upper() for token in ["DC", "콤보", "차데모", "급속"]):
        return True

    return chger_type in {"01", "03", "04", "05", "06"}


def is_restricted(row):
    text = row_text(row, "limitYn", "limitDetail", "이용자제한여부", "이용자제한내용").upper()
    if text in {"N", "0", "FALSE", "없음", "제한없음"}:
        return False
    if text in {"Y", "1", "TRUE"}:
        return True
    return any(token in text for token in ["제한", "전용", "관계자", "입주민", "회원"])


def is_free_parking(row):
    text = row_text(row, "parkingFree", "주차료무료여부").upper()
    return text in {"Y", "1", "TRUE", "무료"} or "무료" in text


def is_available(row):
    status = row_text(row, "stat", "chgerStat", "충전기상태")
    status_text = row_text(row, "statNm", "statusName", "상태명")
    return status == "2" or "충전대기" in status_text or "사용가능" in status_text


def normalize_for_match(value):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", clean(value)).lower()


def possible_inside_complex(apartment, station):
    apt_name = normalize_for_match(apartment.get("name"))
    if len(apt_name) < 3:
        return False

    station_text = normalize_for_match(
        station.get("label", "") + " " + station.get("address", "")
    )
    return apt_name and apt_name in station_text


def prepare_ev_stations():
    raw_rows = read_xml_items(RAW_PATH)
    grouped = {}
    filtered_rows = []

    for row in raw_rows:
        lat = to_float(row_text(row, "lat", "위도", "latitude"))
        lng = to_float(row_text(row, "lng", "lon", "경도", "longitude"))

        if lat is None or lng is None:
            continue
        if not is_seoul_charger(row, lat, lng):
            continue
        if is_deleted_or_closed(row):
            continue

        station_id = row_text(row, "statId", "충전소ID", "stationId")
        station_name = row_text(row, "statNm", "충전소명", "stationName") or "EV 충전소"
        address = row_text(row, "addr", "addrDoro", "address", "rdnmadr", "lnmadr")
        key = station_id or f"{station_name}|{round(lat, 6)}|{round(lng, 6)}"

        if key not in grouped:
            grouped[key] = {
                "station_id": station_id,
                "label": station_name,
                "address": address,
                "lat": lat,
                "lng": lng,
                "operator": row_text(row, "busiNm", "운영기관명"),
                "use_time": row_text(row, "useTime", "이용가능시간"),
                "charger_count": 0,
                "fast_count": 0,
                "slow_count": 0,
                "restricted_count": 0,
                "public_count": 0,
                "free_parking_count": 0,
                "available_count": 0,
                "charger_types": set(),
            }

        station = grouped[key]
        station["charger_count"] += 1

        charger_type = row_text(row, "chgerType", "충전기타입", "chargerType")
        if charger_type:
            station["charger_types"].add(charger_type)

        if is_fast_charger(row):
            station["fast_count"] += 1
        else:
            station["slow_count"] += 1

        if is_restricted(row):
            station["restricted_count"] += 1
        else:
            station["public_count"] += 1

        if is_free_parking(row):
            station["free_parking_count"] += 1

        if is_available(row):
            station["available_count"] += 1

    stations = list(grouped.values())
    stations.sort(key=lambda item: (item.get("label", ""), item.get("station_id", "")))

    for station in stations:
        station["charger_types"] = ", ".join(sorted(station["charger_types"]))
        filtered_rows.append(station)

    FILTERED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FILTERED_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "station_id",
            "label",
            "address",
            "lat",
            "lng",
            "operator",
            "use_time",
            "charger_count",
            "fast_count",
            "slow_count",
            "restricted_count",
            "public_count",
            "free_parking_count",
            "available_count",
            "charger_types",
        ])
        writer.writeheader()
        writer.writerows(filtered_rows)

    return stations


def score_ev_access(row):
    score = 0

    if row["ev_charger_count_300m"] > 0:
        score += 45
    elif row["ev_charger_count_500m"] > 0:
        score += 35
    elif row["ev_charger_count_1km"] > 0:
        score += 20

    score += min(row["ev_charger_count_500m"], 5) * 5
    score += min(row["fast_charger_count_1km"], 10) * 2
    score += min(row["public_charger_count_1km"], 10)
    score -= min(row["restricted_charger_count_1km"], 10) * 2

    return max(0, min(100, int(score)))


def score_level(score):
    if score >= 75:
        return "높음"
    if score >= 55:
        return "좋음"
    if score >= 30:
        return "보통"
    return "낮음"


def build_baseline_row(apartment, stations):
    nearby = []

    for station in stations:
        distance = round(
            haversine_m(
                apartment["lat"],
                apartment["lng"],
                station["lat"],
                station["lng"],
            )
        )

        if distance > 1000:
            continue

        item = {
            "label": station.get("label", "EV 충전소"),
            "distance": int(distance),
            "station_id": station.get("station_id", ""),
            "address": station.get("address", ""),
            "lat": round(station["lat"], 7),
            "lng": round(station["lng"], 7),
            "charger_count": int(station.get("charger_count", 0)),
            "fast_count": int(station.get("fast_count", 0)),
            "slow_count": int(station.get("slow_count", 0)),
            "restricted_count": int(station.get("restricted_count", 0)),
            "public_count": int(station.get("public_count", 0)),
            "free_parking_count": int(station.get("free_parking_count", 0)),
            "available_count": int(station.get("available_count", 0)),
            "operator": station.get("operator", ""),
            "use_time": station.get("use_time", ""),
            "charger_types": station.get("charger_types", ""),
            "possible_inside_complex": possible_inside_complex(apartment, station),
        }
        nearby.append(item)

    nearby.sort(key=lambda item: item.get("distance", 999999))
    nearest = nearby[0] if nearby else {}

    row = {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "ev_charger_count_300m": sum(1 for item in nearby if item["distance"] <= 300),
        "ev_charger_count_500m": sum(1 for item in nearby if item["distance"] <= 500),
        "ev_charger_count_1km": len(nearby),
        "nearest_ev_charger_name": nearest.get("label", ""),
        "nearest_ev_charger_distance": nearest.get("distance", ""),
        "fast_charger_count_1km": sum(item["fast_count"] for item in nearby),
        "slow_charger_count_1km": sum(item["slow_count"] for item in nearby),
        "restricted_charger_count_1km": sum(item["restricted_count"] for item in nearby),
        "public_charger_count_1km": sum(item["public_count"] for item in nearby),
        "free_parking_count_1km": sum(item["free_parking_count"] for item in nearby),
        "available_charger_count_1km": sum(item["available_count"] for item in nearby),
        "possible_inside_complex_count": sum(1 for item in nearby if item["possible_inside_complex"]),
        "ev_charger_items_json": json.dumps(nearby[:MAX_ITEMS], ensure_ascii=False),
    }
    row["ev_charger_score"] = score_ev_access(row)
    row["ev_charger_level"] = score_level(row["ev_charger_score"])

    return row


def main():
    apartments = prepare_apartments()
    stations = prepare_ev_stations()
    rows = []

    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, stations))

        if idx % 200 == 0:
            print(f"[EV] {idx}/{len(apartments)} processed", flush=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[EV] Seoul EV stations used: {len(stations)}", flush=True)
    print(f"[EV] filtered raw saved: {FILTERED_PATH}", flush=True)
    print(f"[EV] baseline saved: {OUTPUT_PATH}", flush=True)
    print(f"[EV] apartments processed: {len(rows)}", flush=True)


if __name__ == "__main__":
    main()

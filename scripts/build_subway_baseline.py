import csv
import json
import math
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from services.geo_service import get_distance_m
from services.preload_service import apartment_data, load_apartment_data


RAW_PATH = BASE_DIR / "data" / "subway" / "subway_station_master.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "subway_baseline.csv"

MAX_ITEMS = 20
ITEM_RADIUS_M = 3000
STATION_CLUSTER_RADIUS_M = 350


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


def read_csv_rows(path):
    for encoding in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            with path.open("r", encoding=encoding, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"CSV encoding read failed: {path}")


def simplify_line_name(value):
    text = clean(value)
    if not text:
        return ""

    for token in [
        "서울교통공사",
        "서울시메트로",
        "한국철도공사",
        "코레일",
        "도시철도",
        "수도권",
        "서울",
    ]:
        text = text.replace(token, "")

    return " ".join(text.split()).strip()


def get_field(row, *names):
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def parse_station_rows():
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"{RAW_PATH} 파일이 없습니다. update_data_pipeline.py로 역사마스터 rawdata를 먼저 내려받으세요."
        )

    rows = read_csv_rows(RAW_PATH)
    stations = []

    for row in rows:
        station_id = get_field(row, "역사_ID", "역사ID", "STATION_ID", "STN_ID")
        name = get_field(row, "역사명", "역명", "STATION_NM", "STN_NM")
        line = simplify_line_name(get_field(row, "호선", "호선명", "LINE_NM", "LINE"))
        lat = to_float(get_field(row, "위도", "LAT", "Y"))
        lng = to_float(get_field(row, "경도", "LNG", "X"))

        if not name or not line or lat is None or lng is None:
            continue

        stations.append({
            "station_id": station_id,
            "name": name,
            "line": line,
            "lat": lat,
            "lng": lng,
        })

    return stations


def add_to_cluster(clusters, row):
    for cluster in clusters:
        if cluster["name"] != row["name"]:
            continue

        distance = get_distance_m(
            cluster["lat"],
            cluster["lng"],
            row["lat"],
            row["lng"],
        )

        if distance <= STATION_CLUSTER_RADIUS_M:
            cluster["rows"].append(row)
            cluster["lines"].add(row["line"])
            cluster["station_ids"].add(row["station_id"])
            count = len(cluster["rows"])
            cluster["lat"] = ((cluster["lat"] * (count - 1)) + row["lat"]) / count
            cluster["lng"] = ((cluster["lng"] * (count - 1)) + row["lng"]) / count
            return

    clusters.append({
        "name": row["name"],
        "lat": row["lat"],
        "lng": row["lng"],
        "lines": {row["line"]},
        "station_ids": {row["station_id"]},
        "rows": [row],
    })


def prepare_station_entities():
    rows = parse_station_rows()
    clusters = []

    for row in rows:
        add_to_cluster(clusters, row)

    entities = []
    for cluster in clusters:
        lines = sorted(cluster["lines"])
        station_ids = sorted({
            station_id for station_id in cluster["station_ids"]
            if station_id
        })
        line_label = "/".join(lines)
        label = f"{cluster['name']}역 · {line_label}"

        entities.append({
            "station_ids": station_ids,
            "name": cluster["name"],
            "label": label,
            "lines": lines,
            "line_label": line_label,
            "lat": cluster["lat"],
            "lng": cluster["lng"],
            "is_transfer": len(lines) >= 2,
        })

    entities.sort(key=lambda item: (item["name"], item["line_label"]))
    return entities, rows


def nearby_items(apartment, stations, radius):
    items = []
    apt_lat = to_float(apartment.get("lat"))
    apt_lng = to_float(apartment.get("lng"))

    if apt_lat is None or apt_lng is None:
        return items

    for station in stations:
        distance = round(get_distance_m(
            apt_lat,
            apt_lng,
            station["lat"],
            station["lng"],
        ))

        if distance > radius:
            continue

        items.append({
            "label": station["label"],
            "name": station["name"],
            "distance": distance,
            "lat": round(station["lat"], 7),
            "lng": round(station["lng"], 7),
            "lines": station["lines"],
            "line_label": station["line_label"],
            "subtype": station["lines"][0] if station["lines"] else "지하철",
            "subtypes": station["lines"] + (["환승역"] if station["is_transfer"] else []),
            "is_transfer": station["is_transfer"],
            "station_ids": station["station_ids"],
        })

    items.sort(key=lambda item: item.get("distance", 999999))
    return items


def nearest_name_distance(items):
    if not items:
        return "", ""
    nearest = items[0]
    return nearest.get("name", ""), nearest.get("distance", "")


def build_row(apartment, stations):
    items_1500m = nearby_items(apartment, stations, ITEM_RADIUS_M)
    items_500m = [item for item in items_1500m if item["distance"] <= 500]
    items_1km = [item for item in items_1500m if item["distance"] <= 1000]
    items_800m = [item for item in items_1500m if item["distance"] <= 800]
    transfer_500m = [item for item in items_500m if item.get("is_transfer")]
    transfer_1km = [item for item in items_1km if item.get("is_transfer")]

    nearest = items_1500m[0] if items_1500m else {}
    nearest_transfer_name, nearest_transfer_distance = nearest_name_distance(transfer_1km)
    line_count_500m = len({
        line
        for item in items_500m
        for line in item.get("lines", [])
    })
    line_count_1km = len({
        line
        for item in items_1km
        for line in item.get("lines", [])
    })

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "nearest_subway": nearest.get("label", ""),
        "subway_distance": nearest.get("distance", ""),
        "nearest_subway_name": nearest.get("name", ""),
        "nearest_subway_distance": nearest.get("distance", ""),
        "nearest_subway_lines": nearest.get("line_label", ""),
        "subway_station_count_500m": len(items_500m),
        "subway_station_count_800m": len(items_800m),
        "subway_station_count_1km": len(items_1km),
        "subway_line_count_500m": line_count_500m,
        "subway_line_count_1km": line_count_1km,
        "transfer_station_count_500m": len(transfer_500m),
        "transfer_station_count_1km": len(transfer_1km),
        "nearest_transfer_station": nearest_transfer_name,
        "nearest_transfer_distance": nearest_transfer_distance,
        "subway_items_500m_json": json.dumps(items_500m[:MAX_ITEMS], ensure_ascii=False),
        "subway_items_json": json.dumps(items_1500m[:MAX_ITEMS], ensure_ascii=False),
    }


def main():
    print("[SUBWAY] load apartment data")
    load_apartment_data()

    print("[SUBWAY] load station master")
    stations, raw_rows = prepare_station_entities()
    print(f"[SUBWAY] raw rows={len(raw_rows)} station entities={len(stations)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "name",
        "gu",
        "dong",
        "lat",
        "lng",
        "nearest_subway",
        "subway_distance",
        "nearest_subway_name",
        "nearest_subway_distance",
        "nearest_subway_lines",
        "subway_station_count_500m",
        "subway_station_count_800m",
        "subway_station_count_1km",
        "subway_line_count_500m",
        "subway_line_count_1km",
        "transfer_station_count_500m",
        "transfer_station_count_1km",
        "nearest_transfer_station",
        "nearest_transfer_distance",
        "subway_items_500m_json",
        "subway_items_json",
    ]

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        valid_apartments = [
            apartment for apartment in apartment_data
            if to_float(apartment.get("lat")) is not None
            and to_float(apartment.get("lng")) is not None
        ]

        skipped = len(apartment_data) - len(valid_apartments)
        if skipped:
            print(f"[SUBWAY] skipped apartments with invalid lat/lng: {skipped}")

        total = len(valid_apartments)
        for index, apartment in enumerate(valid_apartments, start=1):
            row = build_row(apartment, stations)
            writer.writerow(row)

            if index == 1 or index % 500 == 0 or index == total:
                print(
                    f"[SUBWAY] {index}/{total} "
                    f"{apartment['name']} nearest={row['nearest_subway']} "
                    f"distance={row['subway_distance']}"
                )

    print(f"[DONE] {OUTPUT_PATH} 생성 완료")


if __name__ == "__main__":
    main()

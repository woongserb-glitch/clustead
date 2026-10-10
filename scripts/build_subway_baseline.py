import csv
import json
import math
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from services.geo_service import get_distance_m
from services.preload_service import apartment_data, load_apartment_data


RAW_PATH = BASE_DIR / "data" / "subway" / "subway_station_master.csv"
# 동별 건물 윤곽(브이월드 매칭 v5). 있으면 단지 대표 좌표 한 점이 아니라 각 동 건물 위치로 계산한다.
BUILDINGS_PATH = BASE_DIR / "data" / "derived" / "vworld" / "complex_buildings_v5.jsonl"
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


# 역사마스터의 '호선'은 철도 운영상 노선명이라 이용자가 타는 노선과 다르다(2026-10-01 사용자 결정:
# 사이트 전체에서 이용자 노선명으로 합친다). 예: 서울역은 1호선·경부선이 따로 세어져 노선 수가 부풀었다.
LINE_ALIASES = {
    "경부선": "1호선", "경인선": "1호선", "장항선": "1호선",
    "과천선": "4호선", "안산선": "4호선", "진접선": "4호선",
    "일산선": "3호선", "별내선": "8호선", "7호선(인천)": "7호선",
    "9호선(연장)": "9호선", "신분당선(연장)": "신분당선", "신분당선(연장2)": "신분당선",
    "분당선": "수인분당선", "수인선": "수인분당선", "중앙선": "경의중앙선",
    "공항철도1호선": "공항철도", "광역급행철도": "GTX-A",
}
# 경원선은 구간에 따라 1호선(청량리~소요산)과 경의중앙선(용산~왕십리)이 다닌다.
GYEONGWON_JUNGANG_STATIONS = {"왕십리", "응봉", "옥수", "한남", "서빙고", "이촌", "용산"}


def station_key(name):
    """'서울역'과 GTX-A '서울', '이촌(국립중앙박물관)'과 '이촌'을 같은 역으로 묶는 키."""
    text = re.sub(r"\([^)]*\)", "", clean(name)).strip()
    return text[:-1] if text.endswith("역") and len(text) > 1 else text


def canonical_line(line, station_name):
    if line == "경원선":
        return "경의중앙선" if station_key(station_name) in GYEONGWON_JUNGANG_STATIONS else "1호선"
    return LINE_ALIASES.get(line, line)


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
        line = canonical_line(simplify_line_name(get_field(row, "호선", "호선명", "LINE_NM", "LINE")), name)
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
        if station_key(cluster["name"]) != station_key(row["name"]):
            continue

        distance = get_distance_m(
            cluster["lat"],
            cluster["lng"],
            row["lat"],
            row["lng"],
        )

        if distance <= STATION_CLUSTER_RADIUS_M:
            cluster["rows"].append(row)
            # 표시 이름은 '역'으로 끝나는 쪽, 그다음 긴 쪽(GTX-A '서울' → '서울역').
            if (row["name"].endswith("역"), len(row["name"])) > (cluster["name"].endswith("역"), len(cluster["name"])):
                cluster["name"] = row["name"]
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


def load_dong_points():
    """{(이름, 구, 동): [(lat, lng), …]} — 단지의 각 동 건물 중심. 파일이 없으면 빈 dict."""
    if not BUILDINGS_PATH.exists():
        return {}
    from shapely.geometry import shape

    points = {}
    with BUILDINGS_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            pts = []
            for building in row.get("buildings", []):
                try:
                    c = shape(building["geom"]).centroid
                    pts.append((c.y, c.x))
                except Exception:
                    continue
            if pts:
                points[tuple(clean(v) for v in row["key"])] = pts
    return points


def median_low(values):
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2] if ordered else ""


def build_dong_row(apartment, stations, dong_points):
    """동마다 대표 좌표처럼 계산한 뒤, 등급 지표는 중간 동(중앙값) 값으로 쓴다.

    대단지 끝 동 하나가 역에 붙었다고 단지 전체가 역세권이 되지 않고, 대표 좌표가 어디 찍혔는지에
    휘둘리지도 않는다. 역별로는 '그 역이 가장 가까운 동 수·거리 범위' 를 남겨 카드 목록에 쓴다.
    """
    per_dong = []
    for lat, lng in dong_points:
        items = nearby_items({"lat": lat, "lng": lng}, stations, ITEM_RADIUS_M)
        within = [i for i in items if i["distance"] <= 500]
        per_dong.append({
            "items": items,
            "nearest": items[0] if items else None,
            "line_500": len({line for i in within for line in i.get("lines", [])}),
            "station_500": len(within),
            "station_800": sum(1 for i in items if i["distance"] <= 800),
            "station_1km": sum(1 for i in items if i["distance"] <= 1000),
            "transfer_500": sum(1 for i in within if i.get("is_transfer")),
        })
    by_station = {}
    for dong in per_dong:
        for item in dong["items"]:
            entry = by_station.setdefault(item["label"], {**item, "nearest_dong_count": 0, "nearest_min": None,
                                                           "nearest_max": None, "dong_within_500": 0,
                                                           "distance": item["distance"]})
            entry["distance"] = min(entry["distance"], item["distance"])
            if item["distance"] <= 500:
                entry["dong_within_500"] += 1
        nearest = dong["nearest"]
        if nearest:
            entry = by_station[nearest["label"]]
            entry["nearest_dong_count"] += 1
            d = nearest["distance"]
            entry["nearest_min"] = d if entry["nearest_min"] is None else min(entry["nearest_min"], d)
            entry["nearest_max"] = d if entry["nearest_max"] is None else max(entry["nearest_max"], d)
    # 카드 목록: 어떤 동에게든 가장 가까운 역 → 어느 동이든 500m 안인 역 순
    listed = sorted(
        [e for e in by_station.values() if e["nearest_dong_count"] or e["dong_within_500"]],
        key=lambda e: (-e["nearest_dong_count"], -e["dong_within_500"], e["distance"]),
    )
    nearest_dists = [d["nearest"]["distance"] for d in per_dong if d["nearest"]]
    main = listed[0] if listed else {}
    return {
        "subway_basis": "dong",
        "subway_dong_count": len(per_dong),
        "subway_dong_within_500": sum(1 for d in nearest_dists if d <= 500),
        "subway_line_count_500m": median_low([d["line_500"] for d in per_dong]),
        "subway_station_count_500m": median_low([d["station_500"] for d in per_dong]),
        "subway_station_count_800m": median_low([d["station_800"] for d in per_dong]),
        "subway_station_count_1km": median_low([d["station_1km"] for d in per_dong]),
        "transfer_station_count_500m": median_low([d["transfer_500"] for d in per_dong]),
        "nearest_subway_distance": median_low(nearest_dists),
        "subway_distance": median_low(nearest_dists),
        "nearest_subway": main.get("label", ""),
        "nearest_subway_name": main.get("name", ""),
        "nearest_subway_lines": main.get("line_label", ""),
        "subway_dong_stations_json": json.dumps(listed[:MAX_ITEMS], ensure_ascii=False),
        # 탐색의 '역 500m' 필터용: 어느 동이든 500m 안인 역(거리는 가장 가까운 동 기준)
        "subway_items_500m_json": json.dumps([e for e in listed if e["dong_within_500"]][:MAX_ITEMS], ensure_ascii=False),
    }


def build_row(apartment, stations, dong_points=None):
    row = build_center_row(apartment, stations)
    if dong_points and len(dong_points) >= 2:
        row.update(build_dong_row(apartment, stations, dong_points))
    return row


def build_center_row(apartment, stations):
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
        "subway_basis": "center",
        "subway_dong_count": 1,
        "subway_dong_within_500": 1 if nearest.get("distance", 9999) <= 500 else 0,
        "subway_dong_stations_json": "[]",
    }


def main():
    print("[SUBWAY] load apartment data")
    load_apartment_data()

    print("[SUBWAY] load station master")
    stations, raw_rows = prepare_station_entities()
    dong_points = load_dong_points()
    print(f"[SUBWAY] 동별 건물 위치가 있는 단지 {len(dong_points)}")
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
        "subway_basis",
        "subway_dong_count",
        "subway_dong_within_500",
        "subway_dong_stations_json",
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
            key = (clean(apartment.get("name")), clean(apartment.get("gu")), clean(apartment.get("dong")))
            row = build_row(apartment, stations, dong_points.get(key))
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

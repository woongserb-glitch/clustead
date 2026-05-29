import json
import math
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
FACILITY_PATH = BASE_DIR / "data" / "hangang" / "hangang_facilities.csv"
MASTER_PATH = BASE_DIR / "data" / "hangang" / "hangang_park_master.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "hangang_baseline.csv"

RADIUS_M = 3000
MAX_ITEMS = 12
MAX_FACILITY_TAGS = 4

HANGANG_PARK_MASTER = [
    {"park_key": "광나루", "park_name": "광나루한강공원", "lat": 37.5449, "lng": 127.1195},
    {"park_key": "잠실", "park_name": "잠실한강공원", "lat": 37.5186, "lng": 127.0883},
    {"park_key": "뚝섬", "park_name": "뚝섬한강공원", "lat": 37.5297, "lng": 127.0690},
    {"park_key": "잠원", "park_name": "잠원한강공원", "lat": 37.5206, "lng": 127.0146},
    {"park_key": "반포", "park_name": "반포한강공원", "lat": 37.5126, "lng": 126.9966},
    {"park_key": "이촌", "park_name": "이촌한강공원", "lat": 37.5176, "lng": 126.9705},
    {"park_key": "여의도", "park_name": "여의도한강공원", "lat": 37.5284, "lng": 126.9336},
    {"park_key": "양화", "park_name": "양화한강공원", "lat": 37.5437, "lng": 126.9013},
    {"park_key": "망원", "park_name": "망원한강공원", "lat": 37.5556, "lng": 126.8990},
    {"park_key": "난지", "park_name": "난지한강공원", "lat": 37.5667, "lng": 126.8760},
    {"park_key": "강서", "park_name": "강서한강공원", "lat": 37.5866, "lng": 126.8175},
]

FACILITY_PRIORITY = [
    "자전거", "운동시설", "수상/레저", "캠핑", "문화/휴식", "편의시설", "접근시설"
]

FACILITY_KEYWORDS = [
    ("자전거", ["자전거"]),
    ("캠핑", ["캠핑", "야영"]),
    ("수상/레저", ["선착장", "계류", "수상", "요트", "카약", "보트", "수영장", "물놀이"]),
    ("운동시설", ["축구", "농구", "야구", "테니스", "배드민턴", "족구", "게이트볼", "골프", "운동", "체육", "인라인", "스케이트", "트랙"]),
    ("문화/휴식", ["분수", "광장", "무대", "전망", "생태", "잔디", "피크닉", "쉼터", "공연"]),
    ("편의시설", ["매점", "화장실", "주차장", "음수대", "그늘막", "휴게", "샤워", "탈의"]),
    ("접근시설", ["나들목", "승강기", "보행육교", "교량접속", "초록길", "제방"]),
]

DISPLAY_FACILITY_KEYWORDS = [
    ("자전거", ["자전거"]),
    ("캠핑", ["캠핑", "야영"]),
    ("수영장", ["수영장", "물놀이"]),
    ("농구장", ["농구"]),
    ("축구장", ["축구"]),
    ("테니스", ["테니스"]),
    ("야구장", ["야구"]),
    ("족구장", ["족구"]),
    ("분수", ["분수"]),
    ("광장", ["광장"]),
    ("선착장", ["선착장", "계류"]),
    ("매점", ["매점"]),
    ("주차장", ["주차장"]),
    ("화장실", ["화장실"]),
    ("나들목", ["나들목"]),
]


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


def normalize_park_key(value):
    return clean_text(value).replace("한강공원", "").strip()


def to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def get_distance_m(lat1, lng1, lat2, lng2):
    radius = 6371000
    lat1 = math.radians(float(lat1))
    lng1 = math.radians(float(lng1))
    lat2 = math.radians(float(lat2))
    lng2 = math.radians(float(lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(radius * c)


def classify_facility_group(facility_name):
    for group, keywords in FACILITY_KEYWORDS:
        if any(keyword in facility_name for keyword in keywords):
            return group
    return "기타"


def extract_display_tags(facility_names):
    tags = []
    joined = " ".join(facility_names)

    for tag, keywords in DISPLAY_FACILITY_KEYWORDS:
        if any(keyword in joined for keyword in keywords):
            tags.append(tag)

    return tags[:MAX_FACILITY_TAGS]


def pick_primary_group(groups):
    group_set = set(groups)
    for group in FACILITY_PRIORITY:
        if group in group_set:
            return group
    return "기타"


def build_facility_map():
    raw = read_csv_with_fallback(FACILITY_PATH)

    rows = []
    for _, row in raw.iterrows():
        park_key = clean_text(row.get("한강공원명"))
        facility_name = clean_text(row.get("시설명"))
        count = to_int(row.get("한강공원시설수"), 0)

        if not park_key or not facility_name:
            continue

        # 서울 열린데이터 원본의 영문 설명행 제거
        if park_key == "hangangrv_park_nm" or facility_name == "fclt_nm":
            continue

        if count <= 0:
            continue

        rows.append({
            "park_key": park_key,
            "facility_name": facility_name,
            "facility_count": count,
            "facility_group": classify_facility_group(facility_name),
        })

    facility_df = pd.DataFrame(rows)
    facility_df.to_csv(BASE_DIR / "data" / "hangang" / "hangang_facilities_processed.csv", index=False, encoding="utf-8-sig")

    result = {}
    for park_key, group in facility_df.groupby("park_key"):
        facility_names = group["facility_name"].tolist()
        groups = group["facility_group"].tolist()
        display_tags = extract_display_tags(facility_names)
        primary_group = pick_primary_group(groups)

        group_counts = group.groupby("facility_group")["facility_count"].sum().to_dict()
        total_facility_count = int(group["facility_count"].sum())

        result[park_key] = {
            "display_tags": display_tags,
            "primary_group": primary_group,
            "group_counts": group_counts,
            "total_facility_count": total_facility_count,
        }

    return result


def build_hangang_park_master(facility_map):
    master_df = read_csv_with_fallback(MASTER_PATH) if MASTER_PATH.exists() else pd.DataFrame(HANGANG_PARK_MASTER)
    rows = []
    for _, master_row in master_df.iterrows():
        park = {
            "park_key": normalize_park_key(master_row.get("park_key")),
            "park_name": clean_text(master_row.get("park_name")),
            "lat": to_float(master_row.get("lat")),
            "lng": to_float(master_row.get("lng")),
        }
        if not park["park_key"] or park["lat"] is None or park["lng"] is None:
            continue
        meta = facility_map.get(park["park_key"], {})
        tags = meta.get("display_tags", [])
        rows.append({
            **park,
            "primary_group": meta.get("primary_group", "기타"),
            "facility_tags": " · ".join(tags),
            "total_facility_count": meta.get("total_facility_count", 0),
        })

    return rows


def log_master_match_status(facility_map, master_rows):
    raw_keys = set(facility_map.keys())
    master_keys = set(park["park_key"] for park in master_rows)
    matched = raw_keys & master_keys
    missing_in_master = sorted(raw_keys - master_keys)
    missing_in_raw = sorted(master_keys - raw_keys)

    print(f"[HANGANG] raw parks={len(raw_keys)}")
    print(f"[HANGANG] master parks={len(master_keys)}")
    print(f"[HANGANG] matched parks={len(matched)}")
    print(f"[HANGANG] missing in master={len(missing_in_master)}")
    if missing_in_master:
        print(f"[HANGANG WARNING] master missing: {', '.join(missing_in_master)}")
    print(f"[HANGANG] missing in raw={len(missing_in_raw)}")
    if missing_in_raw:
        print(f"[HANGANG WARNING] raw missing: {', '.join(missing_in_raw)}")


def build_baseline():
    apartment_df = read_csv_with_fallback(APARTMENT_PATH)
    facility_map = build_facility_map()
    hangang_parks = build_hangang_park_master(facility_map)
    log_master_match_status(facility_map, hangang_parks)

    rows = []

    for _, apt in apartment_df.iterrows():
        try:
            apt_lat = float(apt.get("좌표Y"))
            apt_lng = float(apt.get("좌표X"))
            if math.isnan(apt_lat) or math.isnan(apt_lng):
                continue
        except Exception:
            continue

        items = []
        for park in hangang_parks:
            distance = get_distance_m(apt_lat, apt_lng, park["lat"], park["lng"])
            if distance > RADIUS_M:
                continue

            tags = clean_text(park.get("facility_tags"))
            label = park["park_name"]
            if tags:
                label = f"{label} · {tags}"

            items.append({
                "label": label,
                "park_name": park["park_name"],
                "distance": distance,
                "lat": park["lat"],
                "lng": park["lng"],
                "subtype": park.get("primary_group", "기타"),
                "facility_tags": tags,
                "facility_count": park.get("total_facility_count", 0),
            })

        items = sorted(items, key=lambda item: item.get("distance", 999999))
        nearest = items[0] if items else {}

        subtype_counts = {key: 0 for key in FACILITY_PRIORITY + ["기타"]}
        for item in items:
            subtype = item.get("subtype", "기타")
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1

        rows.append({
            "name": clean_text(apt.get("k-아파트명")),
            "gu": clean_text(apt.get("주소(시군구)")),
            "dong": clean_text(apt.get("주소(읍면동)")),
            "lat": apt_lat,
            "lng": apt_lng,
            "hangang_count_3km": len(items),
            "nearest_hangang_park": nearest.get("park_name", ""),
            "nearest_hangang_distance": nearest.get("distance", ""),
            "nearest_hangang_facility_tags": nearest.get("facility_tags", ""),
            "bike_count": subtype_counts.get("자전거", 0),
            "sports_count": subtype_counts.get("운동시설", 0),
            "water_leisure_count": subtype_counts.get("수상/레저", 0),
            "camping_count": subtype_counts.get("캠핑", 0),
            "culture_rest_count": subtype_counts.get("문화/휴식", 0),
            "convenience_count": subtype_counts.get("편의시설", 0),
            "access_count": subtype_counts.get("접근시설", 0),
            "hangang_items_json": json.dumps(items[:MAX_ITEMS], ensure_ascii=False),
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[HANGANG] master reference used: {MASTER_PATH}")
    print(f"[HANGANG] baseline 저장: {OUTPUT_PATH}")
    print(f"[HANGANG] 아파트 {len(rows)}개 기준 생성 완료")


if __name__ == "__main__":
    build_baseline()

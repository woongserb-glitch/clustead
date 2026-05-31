import json
import math
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_PATH = BASE_DIR / "data" / "culture" / "culture_raw.csv"
FILTERED_PATH = BASE_DIR / "data" / "culture" / "culture_filtered.csv"
BASELINE_PATH = BASE_DIR / "data" / "baseline" / "culture_baseline.csv"
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"

RADIUS_M = 1500
VALID_STATUS = {"접수중", "안내중"}
VALID_TOP_CATEGORIES = {"문화체험", "체육시설", "교육강좌"}

EXCLUDE_KEYWORDS = [
    "회의실", "강의실", "다목적실", "주민공유공간", "공유공간",
    "강당", "녹화장소", "민원", "청년공간", "청년정보",
    "진료", "복지", "상담", "대관", "공간시설", "업무", "사무",
]

SUBTYPE_ORDER = [
    "공연/행사",
    "전시/관람",
    "체육",
    "키즈",
    "체험",
    "클래스",
    "자연/공원",
    "기타",
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


def to_float(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except Exception:
        return None


def haversine_m(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt

    r = 6371000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    return r * c


def classify_culture_subtype(row):
    top = clean_text(row.get("대분류명"))
    sub = clean_text(row.get("소분류명"))
    name = clean_text(row.get("서비스명"))
    place = clean_text(row.get("장소명"))
    text = f"{top} {sub} {name} {place}"

    if any(k in text for k in ["공연", "행사", "콘서트", "뮤지컬", "연극", "음악회", "무대"]):
        return "공연/행사"

    if any(k in text for k in ["전시", "관람", "미술관", "박물관", "갤러리", "역사", "기록원"]):
        return "전시/관람"

    if top == "체육시설" or any(k in text for k in ["체육", "테니스", "풋살", "축구", "농구", "수영", "스포츠", "체육관", "탁구", "배드민턴", "족구", "피클볼", "야구"]):
        return "체육"

    if any(k in text for k in ["키즈", "어린이", "아동", "유아", "아이", "놀이"]):
        return "키즈"

    if any(k in text for k in ["체험", "탐방", "투어", "도시농업", "공예", "취미", "생태", "정원", "숲"]):
        return "체험"

    if top == "교육강좌" or any(k in text for k in ["강좌", "교육", "수업", "클래스", "강의", "프로그램"]):
        return "클래스"

    if any(k in text for k in ["공원", "산림", "캠핑", "자연", "둘레길", "숲길"]):
        return "자연/공원"

    return "기타"


def should_keep(row):
    status = clean_text(row.get("서비스상태"))
    top = clean_text(row.get("대분류명"))
    sub = clean_text(row.get("소분류명"))
    name = clean_text(row.get("서비스명"))
    place = clean_text(row.get("장소명"))

    if status not in VALID_STATUS:
        return False

    if top not in VALID_TOP_CATEGORIES:
        return False

    text = f"{top} {sub} {name} {place}"
    if any(keyword in text for keyword in EXCLUDE_KEYWORDS):
        return False

    return True


def load_apartments():
    df = read_csv_with_fallback(APARTMENT_PATH)
    apartments = []

    for _, row in df.iterrows():
        lat = to_float(row.get("좌표Y"))
        lng = to_float(row.get("좌표X"))

        if lat is None or lng is None:
            continue

        apartments.append({
            "name": clean_text(row.get("k-아파트명")),
            "gu": clean_text(row.get("주소(시군구)")),
            "dong": clean_text(row.get("주소(읍면동)")),
            "lat": lat,
            "lng": lng,
        })

    return apartments


def build_culture_points():
    df = read_csv_with_fallback(RAW_PATH)

    df["lng"] = pd.to_numeric(df.get("장소X좌표"), errors="coerce")
    df["lat"] = pd.to_numeric(df.get("장소Y좌표"), errors="coerce")

    df = df.dropna(subset=["lat", "lng"])
    df = df[(df["lat"] != 0) & (df["lng"] != 0)]
    df = df[(df["lat"].between(37.35, 37.75)) & (df["lng"].between(126.75, 127.25))]

    rows = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        if not should_keep(row_dict):
            continue

        subtype = classify_culture_subtype(row_dict)
        if subtype == "기타":
            continue

        service_name = clean_text(row.get("서비스명"))
        place_name = clean_text(row.get("장소명")) or service_name or "문화생활"

        # 일부 공공서비스예약 데이터는 장소명에 주소가 들어가 있어 UI 가독성이 떨어진다.
        # 이 경우에는 서비스명을 대표 label로 사용한다.
        label = place_name
        if any(token in place_name for token in ["서울특별시", "서울시", "번지", "길 ", "로 "]):
            label = service_name or place_name

        rows.append({
            "service_id": clean_text(row.get("서비스ID")),
            "label": label,
            "service_name": service_name,
            "place_name": place_name,
            "subtype": subtype,
            "top_category": clean_text(row.get("대분류명")),
            "sub_category": clean_text(row.get("소분류명")),
            "status": clean_text(row.get("서비스상태")),
            "reservation_type": clean_text(row.get("예약구분")),
            "url": clean_text(row.get("바로가기URL")),
            "lat": float(row.get("lat")),
            "lng": float(row.get("lng")),
        })

    filtered_df = pd.DataFrame(rows)
    filtered_df.to_csv(FILTERED_PATH, index=False, encoding="utf-8-sig")
    return rows


def build_baseline():
    apartments = load_apartments()
    culture_points = build_culture_points()
    baseline_rows = []

    print(f"[CULTURE] apartments={len(apartments)}, filtered_points={len(culture_points)}")

    for idx, apt in enumerate(apartments, start=1):
        nearby = []

        for point in culture_points:
            distance = haversine_m(
                apt["lat"],
                apt["lng"],
                point["lat"],
                point["lng"],
            )

            if distance <= RADIUS_M:
                item = dict(point)
                item["distance"] = int(round(distance))
                nearby.append(item)

        nearby.sort(key=lambda item: item.get("distance", 999999))

        subtype_counts = {name: 0 for name in SUBTYPE_ORDER}
        for item in nearby:
            subtype = item.get("subtype", "기타")
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1

        nearest = nearby[0] if nearby else {}

        # 다양성은 0이 아닌 subtype 개수. 추후 점수 고도화용으로 보관한다.
        diversity_count = len([
            name for name, count in subtype_counts.items()
            if name != "기타" and count > 0
        ])

        baseline_rows.append({
            "name": apt["name"],
            "gu": apt["gu"],
            "dong": apt["dong"],
            "lat": apt["lat"],
            "lng": apt["lng"],
            "culture_count_1500m": len(nearby),
            "culture_diversity_count": diversity_count,
            "nearest_culture_name": nearest.get("label", ""),
            "nearest_culture_subtype": nearest.get("subtype", ""),
            "nearest_culture_distance": nearest.get("distance", ""),
            "performance_count": subtype_counts.get("공연/행사", 0),
            "exhibition_count": subtype_counts.get("전시/관람", 0),
            "sports_count": subtype_counts.get("체육", 0),
            "kids_count": subtype_counts.get("키즈", 0),
            "experience_count": subtype_counts.get("체험", 0),
            "class_count": subtype_counts.get("클래스", 0),
            "nature_count": subtype_counts.get("자연/공원", 0),
            "culture_items_json": json.dumps(nearby, ensure_ascii=False),
        })

        if idx % 200 == 0:
            print(f"[CULTURE] {idx}/{len(apartments)} processed")

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(baseline_rows).to_csv(BASELINE_PATH, index=False, encoding="utf-8-sig")
    print(f"[CULTURE] baseline saved: {BASELINE_PATH}")
    print(f"[CULTURE] rows={len(baseline_rows)}")


if __name__ == "__main__":
    build_baseline()

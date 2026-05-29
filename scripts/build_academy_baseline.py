import json
import math
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
ACADEMY_GEOCODED_PATH = BASE_DIR / "data" / "academy" / "academy_geocoded.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "academy_baseline.csv"

ACADEMY_RADIUS_M = 1000
ACADEMY_NEAR_RADIUS_M = 500
MAX_ITEMS = 9999

SUBTYPE_COLUMNS = {
    "입시/보습": "exam_count",
    "영어": "english_count",
    "수학": "math_count",
    "중국어": "chinese_count",
    "일본어": "japanese_count",
    "예체능": "arts_sports_count",
    "독서실": "study_room_count",
    "직업/자격": "career_count",
    "기타": "etc_count",
}

SUBTYPE_ORDER = [
    "독서실",
    "영어",
    "중국어",
    "일본어",
    "수학",
    "예체능",
    "직업/자격",
    "입시/보습",
    "기타",
]

SUBTYPE_KEYWORDS = {
    "독서실": ["독서실", "스터디", "고시원"],
    "영어": ["영어", "토익", "토플", "텝스", "회화", "SAT", "IELTS"],
    "중국어": ["중국어", "HSK"],
    "일본어": ["일본어", "JLPT", "JPT"],
    "수학": ["수학", "초등수학", "중등수학", "고등수학", "수리"],
    "예체능": [
        "음악", "미술", "무용", "댄스", "연기", "연극", "뮤지컬", "실용음악",
        "피아노", "바이올린", "첼로", "성악", "체육", "태권도", "발레", "드럼", "기타"
    ],
    "직업/자격": [
        "직업기술", "컴퓨터", "코딩", "정보처리", "통신기기", "인터넷", "소프트웨어",
        "미용", "간호", "바리스타", "요리", "회계", "세무", "부동산", "자격",
        "성인고시", "공무원", "편입", "전산", "전자", "디자인", "건축", "기계"
    ],
    "입시/보습": ["보습", "논술", "입시", "검정", "진학", "국어", "과학", "사회", "종합", "교과", "초등", "중등", "고등"],
}

CLASSIFY_COLUMNS = [
    "교습과정명",
    "교습과정목록명",
    "교습계열명",
    "분야명",
    "학원명",
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


def contains_keyword(text, keyword):
    if not text or not keyword:
        return False

    upper_text = text.upper()
    upper_keyword = keyword.upper()
    return upper_keyword in upper_text


def classify_academy(row):
    text_parts = []

    for col in CLASSIFY_COLUMNS:
        value = clean_text(row.get(col))
        if value:
            text_parts.append(value)

    text = " ".join(text_parts)

    for subtype in SUBTYPE_ORDER:
        if subtype == "기타":
            continue

        keywords = SUBTYPE_KEYWORDS.get(subtype, [])
        for keyword in keywords:
            if contains_keyword(text, keyword):
                return subtype

    return "기타"


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
            "name": clean_text(row.get("k-아파트명")),
            "gu": clean_text(row.get("주소(시군구)")),
            "dong": clean_text(row.get("주소(읍면동)")),
            "lat": lat,
            "lng": lng,
        })

    return apartments


def prepare_academies():
    if not ACADEMY_GEOCODED_PATH.exists():
        raise FileNotFoundError(
            f"좌표 변환 파일이 없습니다: {ACADEMY_GEOCODED_PATH}\n"
            "먼저 python scripts/geocode_academy_address.py 를 실행해 주세요."
        )

    df = read_csv_with_fallback(ACADEMY_GEOCODED_PATH)

    required = ["학원명", "도로명주소", "등록상태명", "lat", "lng"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"academy_geocoded.csv 필수 컬럼 누락: {missing}")

    df = df[df["등록상태명"].astype(str).str.strip() == "개원"].copy()

    academies = []

    for _, row in df.iterrows():
        try:
            lat = float(row.get("lat"))
            lng = float(row.get("lng"))
            if math.isnan(lat) or math.isnan(lng):
                continue
            if not (33 <= lat <= 39 and 124 <= lng <= 132):
                continue
        except Exception:
            continue

        name = clean_text(row.get("학원명")) or "학원"
        subtype = classify_academy(row)

        academies.append({
            "academy_id": clean_text(row.get("학원지정번호")),
            "name": name,
            "subtype": subtype,
            "lat": lat,
            "lng": lng,
            "road_address": clean_text(row.get("도로명주소")),
            "field": clean_text(row.get("분야명")),
            "course": clean_text(row.get("교습과정명")) or clean_text(row.get("교습과정목록명")),
        })

    return academies


def build_baseline_row(apartment, academies):
    items_1000m = []
    count_500m = 0
    subtype_counts = {column: 0 for column in SUBTYPE_COLUMNS.values()}

    for academy in academies:
        distance = round(
            haversine_m(
                apartment["lat"],
                apartment["lng"],
                academy["lat"],
                academy["lng"],
            )
        )

        if distance > ACADEMY_RADIUS_M:
            continue

        if distance <= ACADEMY_NEAR_RADIUS_M:
            count_500m += 1

        subtype = academy.get("subtype", "기타")
        count_col = SUBTYPE_COLUMNS.get(subtype, "etc_count")
        subtype_counts[count_col] += 1

        items_1000m.append({
            "label": academy["name"],
            "distance": int(distance),
            "subtype": subtype,
            "lat": round(academy["lat"], 7),
            "lng": round(academy["lng"], 7),
            "address": academy.get("road_address", ""),
            "course": academy.get("course", ""),
        })

    items_1000m.sort(key=lambda item: item.get("distance", 999999))
    nearest = items_1000m[0] if items_1000m else {}

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "academy_count_500m": count_500m,
        "academy_count_1000m": len(items_1000m),
        "nearest_academy_name": nearest.get("label", ""),
        "nearest_academy_subtype": nearest.get("subtype", ""),
        "nearest_academy_distance": nearest.get("distance", ""),
        **subtype_counts,
        "academy_items_json": json.dumps(items_1000m, ensure_ascii=False),
    }


def main():
    apartments = prepare_apartments()
    academies = prepare_academies()

    rows = []

    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, academies))

        if idx % 200 == 0:
            print(f"[ACADEMY] {idx}/{len(apartments)} 처리")

    output_df = pd.DataFrame(rows)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[ACADEMY] 유효 학원·교습소 {len(academies)}개 기준")
    print(f"[ACADEMY] baseline 저장 완료: {OUTPUT_PATH}")
    print(f"[ACADEMY] 아파트 {len(rows)}개")


if __name__ == "__main__":
    main()

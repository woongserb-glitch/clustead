import json
import math
import re
from pathlib import Path

import pandas as pd
from pyproj import Transformer

BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
SHOPPING_PATH = BASE_DIR / "data" / "shopping" / "shopping_facilities_seoul.csv"
OUTPUT_PATH = BASE_DIR / "data" / "baseline" / "shopping_baseline.csv"

SHOPPING_RADIUS_M = 3000
MAX_ITEMS = 40

EXCLUDE_UPTAE = {"대형마트"}
EXCLUDE_NAME_KEYWORDS = [
    "이마트",
    "홈플러스",
    "롯데마트",
    "코스트코",
    "트레이더스",
    "GS더프레시",
    "GS수퍼",
    "GS슈퍼",
    "롯데슈퍼",
    "하나로마트",
    "식자재",
    "마트",
]

SUBTYPE_MAP = {
    "백화점": "백화점",
    "복합쇼핑몰": "쇼핑몰",
    "쇼핑센터": "쇼핑몰",
    "시장": "시장",
    "전문점": "전문점",
    "그 밖의 대규모점포": "기타쇼핑",
}

COUNT_COLUMNS = {
    "백화점": "department_count",
    "쇼핑몰": "mall_count",
    "시장": "market_count",
    "전문점": "specialty_count",
    "기타쇼핑": "etc_count",
}


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


def classify_subtype(upjong, name):
    upjong = clean_text(upjong)
    name = clean_text(name)

    if "백화점" in upjong or "백화점" in name:
        return "백화점"
    if "복합" in upjong or "쇼핑몰" in upjong or "쇼핑몰" in name or "몰" in name:
        return "쇼핑몰"
    if "쇼핑센터" in upjong or "쇼핑센터" in name:
        return "쇼핑몰"
    if "시장" in upjong or "시장" in name:
        return "시장"
    if "전문점" in upjong:
        return "전문점"

    return SUBTYPE_MAP.get(upjong, "기타쇼핑")


def is_mart_like(row):
    upjong = clean_text(row.get("업태구분명"))
    name = clean_text(row.get("사업장명"))

    if upjong in EXCLUDE_UPTAE:
        return True

    # 구분없음/준대규모점포 중 슈퍼·마트 성격은 기존 대형마트/마트 카드와 중복되므로 제외한다.
    return any(keyword.lower() in name.lower() for keyword in EXCLUDE_NAME_KEYWORDS)


def prepare_shopping_facilities():
    df = read_csv_with_fallback(SHOPPING_PATH)

    required = ["영업상태명", "상세영업상태명", "사업장명", "업태구분명", "좌표정보(X)", "좌표정보(Y)"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"쇼핑시설 필수 컬럼 누락: {missing}")

    df = df[df["영업상태명"].astype(str).str.contains("영업/정상", na=False)]
    df = df[df["상세영업상태명"].astype(str).str.contains("정상영업", na=False)]

    transformer = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)

    facilities = []
    for _, row in df.iterrows():
        if is_mart_like(row):
            continue

        try:
            x = float(row.get("좌표정보(X)"))
            y = float(row.get("좌표정보(Y)"))
            if math.isnan(x) or math.isnan(y):
                continue
            lng, lat = transformer.transform(x, y)
        except Exception:
            continue

        name = clean_text(row.get("사업장명"))
        if not name:
            continue

        subtype = classify_subtype(row.get("업태구분명"), name)

        facilities.append({
            "label": name,
            "subtype": subtype,
            "raw_type": clean_text(row.get("업태구분명")),
            "store_type": clean_text(row.get("점포구분명")),
            "address": clean_text(row.get("도로명주소")) or clean_text(row.get("지번주소")),
            "lat": round(lat, 7),
            "lng": round(lng, 7),
        })

    return facilities


TRADSIJANG_PATH = BASE_DIR / "data" / "derived" / "vworld" / "LT_P_TRADSIJANG.geojson"


def add_traditional_markets(facilities):
    """브이월드 전통시장(LT_P_TRADSIJANG) 서울분을 '시장'으로 더한다.

    쇼핑 원천(대규모점포 인허가)에는 등록된 시장만 있어 남대문·고척근린시장 같은 전통시장이
    빠졌다(서울 전통시장 188곳 중 이름이 겹치는 건 52곳). 이미 있는 시장과 이름이 같거나
    200m 안이면 같은 시장으로 보고 더하지 않는다.
    """
    if not TRADSIJANG_PATH.exists():
        return facilities
    norm = lambda s: re.sub(r"\s|전통|시장|상점가|골목형|\(.*?\)", "", s or "")
    existing = [f for f in facilities if f["subtype"] == "시장"]
    names = {norm(f["label"]) for f in existing}
    added = 0
    for feat in json.loads(TRADSIJANG_PATH.read_text(encoding="utf-8"))["features"]:
        p = feat["properties"]
        if not str(p.get("adr_jibun", "")).startswith("서울"):
            continue
        lng, lat = feat["geometry"]["coordinates"][:2]
        name = clean_text(p.get("name"))
        if not name or norm(name) in names:
            continue
        if any(haversine_m(lat, lng, f["lat"], f["lng"]) <= 200 for f in existing):
            continue
        facilities.append({
            "label": name if name.endswith(("시장", "상점가")) else f"{name}시장",
            "subtype": "시장",
            "raw_type": "전통시장",
            "store_type": clean_text(p.get("category")),
            "address": clean_text(p.get("adr_road")) or clean_text(p.get("adr_jibun")),
            "lat": round(float(lat), 7),
            "lng": round(float(lng), 7),
        })
        names.add(norm(name))
        added += 1
    print(f"[SHOPPING] 브이월드 전통시장 {added}곳 추가")
    return facilities


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


def build_baseline_row(apartment, facilities):
    items = []

    for facility in facilities:
        distance = round(haversine_m(
            apartment["lat"],
            apartment["lng"],
            facility["lat"],
            facility["lng"],
        ))

        if distance > SHOPPING_RADIUS_M:
            continue

        items.append({
            **facility,
            "distance": int(distance),
        })

    items.sort(key=lambda item: item.get("distance", 999999))
    nearest = items[0] if items else {}

    counts = {column: 0 for column in COUNT_COLUMNS.values()}
    for item in items:
        count_col = COUNT_COLUMNS.get(item.get("subtype"), "etc_count")
        counts[count_col] += 1

    return {
        "name": apartment["name"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "lat": apartment["lat"],
        "lng": apartment["lng"],
        "shopping_count_3km": len(items),
        "nearest_shopping_name": nearest.get("label", ""),
        "nearest_shopping_subtype": nearest.get("subtype", ""),
        "nearest_shopping_distance": nearest.get("distance", ""),
        **counts,
        "shopping_items_json": json.dumps(items[:MAX_ITEMS], ensure_ascii=False),
    }


def main():
    apartments = prepare_apartments()
    facilities = add_traditional_markets(prepare_shopping_facilities())

    rows = []
    for idx, apartment in enumerate(apartments, start=1):
        rows.append(build_baseline_row(apartment, facilities))
        if idx % 300 == 0:
            print(f"[SHOPPING] {idx}/{len(apartments)} 처리")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"[SHOPPING] 쇼핑시설 {len(facilities)}개 기준")
    print(f"[SHOPPING] baseline 저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

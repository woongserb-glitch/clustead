"""아파트 생활권 격자 인덱스 빌드 (1단계: 집계 파이프라인).

기존 baseline 은 전부 '단지 중심 반경 집계'라, 단지가 없는 공간은 데이터에
존재하지 않는다. 이 스크립트는 공간 자체를 질의 가능하게 만든다.

격자
    정사각 100m. 셀 ID = (i, j) = 원점에서의 정수 오프셋.
    100m 셀 9개가 정확히 300m 셀 1개가 되므로(3의 배수) 확대 수준별 집계가
    합산만으로 끝난다. H3 는 부모-자식 육각형이 정확히 포개지지 않아 이 성질이
    없고, C 확장 의존성이 붙는다(런타임 슬림 기조와 배치).

범위
    아파트 생활권(핵심 500m / 확장 1km)에 걸치는 셀만 저장한다. 다만 실측상
    500m 로도 서울 면적의 73%, 1km 면 96% 라 계산량 절감 효과는 거의 없다.
    제한의 의미는 백분위 분모를 '아파트 생활권'으로 두는 통계적 정직성에 있다.

신뢰등급(trust)
    레이어마다 등록 관행이 달라 구간 비교 가능 여부가 다르다. 지도에서 임의
    조합을 허용하면 우리가 검수하지 않은 비교가 화면에 뜨므로, 등급을 데이터가
    들고 다니게 한다. UI 는 이 값으로 경고하거나 비교를 막는다.
      high       전수 등록, 구간 비교 가능
      normalized 보정을 거쳐야 비교 가능(적용 완료)
      medium     대체로 신뢰하나 누락 가능
      low        구간 비교 불가(단일 지역 내 분포 확인용)

사용:
    python scripts/build_grid_index.py
"""

import csv
import math
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

csv.field_size_limit(2**31 - 1)

from services.preload_service import (
    load_cctv_data,
    cctv_data,
    cctv_camera_weights,
    get_cctv_icon_and_subtype,
)


OUTPUT_PATH = "data/grid.db"
APARTMENT_BASELINE = "data/baseline/cctv_baseline.csv"

CELL_SIZE_M = 100
LAT_ORIGIN = 37.40
LNG_ORIGIN = 126.75

# 위경도 1도당 미터(서울 위도 기준 근사). 서울은 위도 폭이 0.3도라
# 이 상수 근사로 생기는 셀 왜곡이 무시할 수준이다.
LAT_M_PER_DEG = 111000.0
LNG_M_PER_DEG = 88800.0

CORE_RADIUS_M = 500
EXTENDED_RADIUS_M = 1000

D_LAT = CELL_SIZE_M / LAT_M_PER_DEG
D_LNG = CELL_SIZE_M / LNG_M_PER_DEG

SEOUL_BOUNDS = (37.40, 37.72, 126.76, 127.19)


def cell_of(lat, lng):
    return (
        int(math.floor((lat - LAT_ORIGIN) / D_LAT)),
        int(math.floor((lng - LNG_ORIGIN) / D_LNG)),
    )


def in_seoul(lat, lng):
    min_lat, max_lat, min_lng, max_lng = SEOUL_BOUNDS
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def read_rows(path, encodings=("utf-8-sig", "cp949", "euc-kr")):
    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"인코딩을 찾지 못했습니다: {path}")


def academy_subtype(row):
    field = row.get("분야명") or ""

    if "입시" in field or "보습" in field:
        return "입시·보습"
    if "독서실" in field:
        return "독서·논술"
    if "국제화" in field or "외국어" in (row.get("교습계열명") or ""):
        return "외국어"
    if "예능" in field:
        return "예체능"
    if "기예" in field or "직업" in field or "기술" in field:
        return "직업·기술"

    return "기타"


def hospital_subtype(row):
    name = row.get("DUTYDIVNAM") or ""

    if name in ("종합병원", "상급종합"):
        return "종합병원"
    if "치과" in name:
        return "치과"
    if "한의" in name or "한방" in name:
        return "한의원"
    if name in ("병원", "요양병원"):
        return "병원"

    return "의원"


def simple(field, default="기타"):
    def extract(row):
        return (row.get(field) or "").strip() or default

    return extract


def constant(value):
    def extract(row):
        return value

    return extract


# (키, 라벨, 경로, 위도컬럼, 경도컬럼, 서브타입함수, 신뢰등급, 비고)
LAYERS = [
    ("academy", "학원", "data/academy/academy_geocoded.csv",
     "lat", "lng", academy_subtype, "medium",
     "지오코딩 실패분 제외"),

    ("school", "학교", "data/school/school.csv",
     "위도", "경도", simple("학교급구분"), "high",
     "교육부 전수"),

    ("child_zone", "어린이보호구역", "data/child_zone/child_protection_zone.csv",
     "latitude", "longitude", simple("fcltyKnd"), "high",
     "법정 지정구역. cctvNumber 는 구별 기입률 편차로 미사용"),

    ("hospital", "병원", "data/medical/hospital_seoul.csv",
     "WGS84LAT", "WGS84LON", hospital_subtype, "medium", ""),

    ("pharmacy", "약국", "data/medical/pharmacy_hours_seoul.csv",
     "WGS84LAT", "WGS84LON", constant("약국"), "medium", ""),

    ("subway", "지하철", "data/subway/subway_station_master.csv",
     "위도", "경도", simple("호선"), "high", ""),

    ("bus_stop", "버스정류장", "data/bus/seoul_bus_stops.csv",
     "Y좌표", "X좌표", simple("정류소 타입"), "high",
     "X/Y 컬럼명이 경도/위도로 뒤바뀌어 있음"),

    ("bike", "따릉이", "data/bike/bike_station_seoul.csv",
     "위도", "경도", constant("대여소"), "high", ""),

    ("ev_charger", "전기차 충전기", "data/ev_chargers/ev_chargers_seoul_filtered.csv",
     "lat", "lng", constant("충전소"), "medium", ""),

    ("culture", "문화시설", "data/culture/culture_filtered.csv",
     "lat", "lng", simple("subtype"), "medium", ""),
]


def build_poi_counts():
    """레이어별 (셀, 서브타입) 개수. CCTV 는 카메라 대수 가중치를 쓴다."""
    counts = {}
    stats = []

    for key, label, path, lat_col, lng_col, subtype_of, trust, note in LAYERS:
        if not os.path.exists(path):
            print(f"[SKIP] {label}: 파일 없음 ({path})")
            continue

        rows = read_rows(path)
        kept = 0
        dropped = 0

        for row in rows:
            try:
                lat = float(row[lat_col])
                lng = float(row[lng_col])
            except (TypeError, ValueError, KeyError):
                dropped += 1
                continue

            if not in_seoul(lat, lng):
                dropped += 1
                continue

            i, j = cell_of(lat, lng)
            counts[(i, j, key, subtype_of(row))] = (
                counts.get((i, j, key, subtype_of(row)), 0) + 1
            )
            kept += 1

        stats.append((key, label, trust, note, kept, dropped))
        print(f"[POI] {label:<14}{kept:>7,}건 집계 (제외 {dropped:,})")

    # CCTV: 지주/카메라 등록 단위 차이를 보정한 가중치로 집계한다.
    load_cctv_data()
    kept = 0

    for point in cctv_data:
        lat = point["lat"]
        lng = point["lng"]

        if not in_seoul(lat, lng):
            continue

        i, j = cell_of(lat, lng)
        _, subtype = get_cctv_icon_and_subtype(point.get("purpose", ""))
        weight = cctv_camera_weights.get((lat, lng), 1)

        key = (i, j, "cctv", subtype)
        counts[key] = counts.get(key, 0) + weight
        kept += 1

    stats.append((
        "cctv", "CCTV", "normalized",
        "자치구별 등록단위 보정 적용. 목적구분(서브타입)은 구간 비교 불가",
        kept, 0,
    ))
    print(f"[POI] {'CCTV':<14}{kept:>7,}건 집계 (카메라 대수 가중)")

    return counts, stats


def build_apartment_cells():
    """단지별 생활권 셀. 겹쳐도 셀 집계는 한 번만 하고 관계만 저장한다."""
    apartments = []

    for row in read_rows(APARTMENT_BASELINE):
        try:
            apartments.append((
                row["name"], row["gu"], row["dong"],
                float(row["lat"]), float(row["lng"]),
            ))
        except (TypeError, ValueError, KeyError):
            continue

    pairs = []
    core_cells = set()
    extended_cells = set()
    span = int(EXTENDED_RADIUS_M / CELL_SIZE_M) + 1

    for index, (name, gu, dong, lat, lng) in enumerate(apartments):
        ci, cj = cell_of(lat, lng)

        for i in range(ci - span, ci + span + 1):
            for j in range(cj - span, cj + span + 1):
                cell_lat = LAT_ORIGIN + (i + 0.5) * D_LAT
                cell_lng = LNG_ORIGIN + (j + 0.5) * D_LNG

                dy = (cell_lat - lat) * LAT_M_PER_DEG
                dx = (cell_lng - lng) * LNG_M_PER_DEG
                distance_sq = dx * dx + dy * dy

                if distance_sq > EXTENDED_RADIUS_M ** 2:
                    continue

                is_core = distance_sq <= CORE_RADIUS_M ** 2
                pairs.append((i, j, index, 1 if is_core else 0))
                extended_cells.add((i, j))

                if is_core:
                    core_cells.add((i, j))

    return apartments, pairs, core_cells, extended_cells


def write_db(counts, stats, apartments, pairs, core_cells, extended_cells):
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)

    connection = sqlite3.connect(OUTPUT_PATH)
    cursor = connection.cursor()

    cursor.executescript("""
        CREATE TABLE grid_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE layer_meta (
            layer TEXT PRIMARY KEY,
            label TEXT,
            trust TEXT,
            note TEXT,
            poi_count INTEGER,
            dropped_count INTEGER
        );

        CREATE TABLE grid_cell (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            layer TEXT NOT NULL,
            subtype TEXT NOT NULL,
            count REAL NOT NULL,
            PRIMARY KEY (i, j, layer, subtype)
        ) WITHOUT ROWID;

        CREATE TABLE grid_zone (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            in_core INTEGER NOT NULL,
            apartment_count INTEGER NOT NULL,
            PRIMARY KEY (i, j)
        ) WITHOUT ROWID;

        CREATE TABLE apartment (
            id INTEGER PRIMARY KEY,
            name TEXT, gu TEXT, dong TEXT,
            lat REAL, lng REAL
        );

        CREATE TABLE grid_apartment (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            apartment_id INTEGER NOT NULL,
            in_core INTEGER NOT NULL
        );
    """)

    cursor.executemany(
        "INSERT INTO grid_meta VALUES (?, ?)",
        [
            ("cell_size_m", str(CELL_SIZE_M)),
            ("lat_origin", repr(LAT_ORIGIN)),
            ("lng_origin", repr(LNG_ORIGIN)),
            ("lat_m_per_deg", repr(LAT_M_PER_DEG)),
            ("lng_m_per_deg", repr(LNG_M_PER_DEG)),
            ("core_radius_m", str(CORE_RADIUS_M)),
            ("extended_radius_m", str(EXTENDED_RADIUS_M)),
            ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S")),
        ],
    )

    cursor.executemany(
        "INSERT INTO layer_meta VALUES (?, ?, ?, ?, ?, ?)",
        [(key, label, trust, note, kept, dropped)
         for key, label, trust, note, kept, dropped in stats],
    )

    cursor.executemany(
        "INSERT INTO grid_cell VALUES (?, ?, ?, ?, ?)",
        [(i, j, layer, subtype, value)
         for (i, j, layer, subtype), value in counts.items()],
    )

    cursor.executemany(
        "INSERT INTO apartment VALUES (?, ?, ?, ?, ?, ?)",
        [(index, name, gu, dong, lat, lng)
         for index, (name, gu, dong, lat, lng) in enumerate(apartments)],
    )

    cursor.executemany(
        "INSERT INTO grid_apartment VALUES (?, ?, ?, ?)",
        pairs,
    )

    cursor.execute("""
        INSERT INTO grid_zone (i, j, in_core, apartment_count)
        SELECT i, j, MAX(in_core), COUNT(*)
        FROM grid_apartment
        GROUP BY i, j
    """)

    cursor.executescript("""
        CREATE INDEX idx_cell_layer ON grid_cell (layer, i, j);
        CREATE INDEX idx_zone_core ON grid_zone (in_core);
        CREATE INDEX idx_ga_apartment ON grid_apartment (apartment_id);
        CREATE INDEX idx_ga_cell ON grid_apartment (i, j);
    """)

    connection.commit()
    connection.execute("VACUUM")
    connection.close()


def main():
    started = time.time()

    counts, stats = build_poi_counts()

    print("[ZONE] 단지 생활권 셀 계산")
    apartments, pairs, core_cells, extended_cells = build_apartment_cells()

    print(
        f"[ZONE] 단지 {len(apartments):,}개 → "
        f"핵심 {len(core_cells):,}셀 / 확장 {len(extended_cells):,}셀, "
        f"관계 {len(pairs):,}쌍"
    )

    # 생활권 밖 셀은 저장하지 않는다.
    inside = {
        key: value
        for key, value in counts.items()
        if (key[0], key[1]) in extended_cells
    }

    print(
        f"[TRIM] 집계 셀 {len({(k[0], k[1]) for k in counts}):,} → "
        f"생활권 내 {len({(k[0], k[1]) for k in inside}):,}"
    )

    write_db(inside, stats, apartments, pairs, core_cells, extended_cells)

    size_mb = os.path.getsize(OUTPUT_PATH) / 1e6
    print(
        f"[DONE] {OUTPUT_PATH} — {size_mb:.1f}MB, "
        f"{time.time() - started:.0f}s"
    )


if __name__ == "__main__":
    main()

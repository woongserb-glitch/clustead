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
import json
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
    load_apartment_data,
    apartment_data,
)


OUTPUT_PATH = "data/grid.db"
DISTRICT_GEOJSON = "data/boundary/seoul_municipalities.geojson"
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

# POI 수집 범위는 서울 경계보다 넓어야 한다. 생활권은 단지에서 1km 뻗고 각
# 레이어는 거기서 다시 최대 1.5km(문화) 반경으로 집계하므로, 서울 밖 POI 를
# 버리면 경계 근처 칸이 과소집계된다(실측: 서울 밖 칸의 CCTV 중앙값 0).
# 전국/수도권 원본을 쓰는 레이어만 실질적으로 혜택을 본다.
POI_MARGIN_DEG = 0.035  # 약 3.9km(위도) / 3.1km(경도)

POI_BOUNDS = (
    SEOUL_BOUNDS[0] - POI_MARGIN_DEG,
    SEOUL_BOUNDS[1] + POI_MARGIN_DEG,
    SEOUL_BOUNDS[2] - POI_MARGIN_DEG,
    SEOUL_BOUNDS[3] + POI_MARGIN_DEG,
)


def cell_of(lat, lng):
    return (
        int(math.floor((lat - LAT_ORIGIN) / D_LAT)),
        int(math.floor((lng - LNG_ORIGIN) / D_LNG)),
    )


def in_poi_range(lat, lng):
    min_lat, max_lat, min_lng, max_lng = POI_BOUNDS
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


def pharmacy_subtype(row):
    """야간 영업 여부. 약국 전체는 병원과 r=0.96 으로 사실상 같은 지표지만,
    22시 이후 영업(5,510 중 444, 8%)은 분포가 다르고 심야 의료 공백이라는
    독립된 정책 질문에 답한다.

    일요일 영업(DUTYTIME7C)은 5,483/5,510 이 채워져 있어 기입 오류로 보고
    쓰지 않는다.
    """
    for day in range(1, 6):
        value = (row.get(f"DUTYTIME{day}C") or "").strip()

        if len(value) >= 3 and value[:2].isdigit() and int(value[:2]) >= 22:
            return "야간(22시 이후)"

    return "일반"


def ev_charger_subtype(row):
    """개방 여부와 급속 여부. 전체를 한 덩어리로 세면 안 된다.

    2,987곳 중 1,094곳(37%)이 아파트 입주민 전용 등 이용제한이다. 그 칸에
    사는 사람이 실제로 쓸 수 있는 충전기가 아닌데 '주변에 충전기 있음' 으로
    잡히면 공급을 그만큼 부풀려 세게 된다.

    충전'소' 단위 레코드라 한 곳에 제한·개방이 섞인 경우가 198곳 있다.
    개방분이 하나라도 있으면 개방으로 본다.
    """
    def count(key):
        try:
            return int(float(row.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    use_time = row.get("use_time") or ""
    restricted = count("restricted_count")
    public = count("public_count")

    if (restricted > 0 and public == 0) or "입주민" in use_time:
        return "이용제한"

    return "급속(개방)" if count("fast_count") > 0 else "완속(개방)"


def simple(field, default="기타"):
    def extract(row):
        return (row.get(field) or "").strip() or default

    return extract


def constant(value):
    def extract(row):
        return value

    return extract


# 영향권 반경은 '결과 페이지에 실제로 표시되는 반경'을 기준으로 한다.
# POI_META 에는 쓰이지 않는 잔재가 섞여 있어 그대로 읽으면 안 된다
# (bus=400 이지만 실제 500, subway=1500 이지만 실제 500).
# 검증법: 결과 페이지에서 '반경 N 내 …' 문구를 직접 확인할 것.
# 학교/어린이보호구역은 제품에 없는 레이어라 여기서 정의한다.
#
# (키, 라벨, 경로, 위도컬럼, 경도컬럼, 서브타입함수, 반경m, 신뢰등급, 비고)
LAYERS = [
    ("academy", "학원", "data/academy/academy_geocoded.csv",
     "lat", "lng", academy_subtype, 1000, "medium",
     "지오코딩 실패분 제외"),

    ("school", "학교", "data/school/school.csv",
     "위도", "경도", simple("학교급구분"), 500, "high",
     "교육부 전수. 반경은 통학 도보권 기준으로 자체 정의"),

    ("child_zone", "어린이보호구역", "data/child_zone/child_protection_zone.csv",
     "latitude", "longitude", simple("fcltyKnd"), 300, "high",
     "법정 지정구역(반경 300m). cctvNumber 는 구별 기입률 편차로 미사용"),

    ("hospital", "병원", "data/medical/hospital_seoul.csv",
     "WGS84LAT", "WGS84LON", hospital_subtype, 500, "medium", ""),

    ("pharmacy", "약국", "data/medical/pharmacy_hours_seoul.csv",
     "WGS84LAT", "WGS84LON", pharmacy_subtype, 500, "medium",
     "약국 전체는 병원과 r=0.96 이라 사실상 같은 지표다. "
     "'야간(22시 이후)' 서브타입으로 걸러야 의미가 생긴다"),

    ("subway", "지하철", "data/subway/subway_station_master.csv",
     "위도", "경도", simple("호선"), 500, "high",
     "반경은 결과 페이지 표기(500m) 기준. POI_META 의 1500m 는 미사용 잔재"),

    ("bus_stop", "버스정류장", "data/bus/seoul_bus_stops.csv",
     "Y좌표", "X좌표", simple("정류소 타입"), 500, "high",
     "X/Y 컬럼명이 경도/위도로 뒤바뀌어 있음. "
     "반경은 build_bus_category_summary 의 500m 기준"
     "(POI_META 의 400m 는 미사용 잔재)"),

    ("bike", "따릉이", "data/bike/bike_station_seoul.csv",
     "위도", "경도", constant("대여소"), 500, "high",
     "원본에 대여소ID·주소·좌표만 있어 서브타입 재료가 없다(거치대 수 없음). "
     "좌표가 0 인 77건(2.2%)은 자동 제외된다"),

    ("ev_charger", "전기차 충전기", "data/ev_chargers/ev_chargers_seoul_filtered.csv",
     "lat", "lng", ev_charger_subtype, 1000, "medium",
     "결과 페이지 표기는 1km 인데 점수는 ev_charger_count_500m 기준이라 제품 내부가 "
     "어긋나 있다. 격자는 표기(1km)를 따른다. "
     "37% 가 입주민 전용 등 이용제한이라 '개방' 서브타입으로 걸러야 한다"),

    # 문화시설 제외 — culture_filtered.csv 는 시설이 아니라 '서울시
    # 공공서비스예약 프로그램' 목록이다. service_name 이 "2026년
    # 미니솟대만들기(매주 일)" 같은 강좌이고, 628행 중 고유 장소는 355개라
    # 한 장소가 최대 22번 중복 계산된다(천왕산 목공 체험장).
    # 모든 레이어와 상관이 0.10~0.29 로 낮았던 건 '독립적 신호' 가 아니라
    # 잘못 들어온 데이터였다. 실제 문화 인프라(공연/전시)는 87건뿐이다.
]

# CCTV 는 '작용형'이라 도달형 반경을 쓰면 안 된다. 카메라 유효 감시 범위는
# 수십 미터인데 500m 안의 146대(중앙값)가 이 칸을 지켜준다는 건 사실이 아니다.
# 200m 로 좁히면 22% 의 칸이 0 이 되어 사각지대가 실제로 드러난다(500m 는 7%).
# 기존 단지 점수(cctv_count_500m)는 '내 생활반경 안에 얼마나 있나'라는 다른
# 질문이므로 500m 를 그대로 둔다. 같은 장소에 두 숫자가 공존한다.
CCTV_RADIUS_M = 200

# 희소하면서 효과가 점적인 레이어는 개수보다 최근접 거리가 체감에 가깝다.
# (반경 내 역이 몇 개냐보다 가장 가까운 역까지 몇 m냐)
DISTANCE_LAYERS = {"subway", "school", "hospital", "pharmacy", "child_zone"}

# 최근접 거리 탐색 상한. 이보다 멀면 NULL 로 두고 UI 에서 '권역 밖'으로 처리.
MAX_DISTANCE_M = 3000


def build_poi_list():
    """레이어별 POI 좌표 목록. CCTV 는 카메라 대수 가중치를 함께 싣는다."""
    pois = []
    stats = []

    for key, label, path, lat_col, lng_col, subtype_of, radius, trust, note in LAYERS:
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

            if not in_poi_range(lat, lng):
                dropped += 1
                continue

            pois.append((lat, lng, key, subtype_of(row), 1.0, radius))
            kept += 1

        stats.append((key, label, trust, note, kept, dropped, radius))
        print(f"[POI] {label:<14}{kept:>7,}건 (반경 {radius}m, 제외 {dropped:,})")

    # CCTV: 지주/카메라 등록 단위 차이를 보정한 가중치로 집계한다.
    load_cctv_data()
    kept = 0

    for point in cctv_data:
        lat = point["lat"]
        lng = point["lng"]

        if not in_poi_range(lat, lng):
            continue

        _, subtype = get_cctv_icon_and_subtype(point.get("purpose", ""))
        weight = cctv_camera_weights.get((lat, lng), 1)

        pois.append((lat, lng, "cctv", subtype, weight, CCTV_RADIUS_M))
        kept += 1

    stats.append((
        "cctv", "CCTV", "normalized",
        "자치구별 등록단위 보정 적용. 목적구분(서브타입)은 구간 비교 불가",
        kept, 0, CCTV_RADIUS_M,
    ))
    print(f"[POI] {'CCTV':<14}{kept:>7,}건 (반경 {CCTV_RADIUS_M}m, 카메라 대수 가중)")

    return pois, stats


def build_point_counts(pois):
    """POI 가 '위치한' 셀 집계. 최대 확대에서의 개별 표시·정확한 위치용."""
    counts = {}

    for lat, lng, layer, subtype, weight, _ in pois:
        i, j = cell_of(lat, lng)
        key = (i, j, layer, subtype)
        counts[key] = counts.get(key, 0) + weight

    return counts


def build_coverage(pois, zone_cells):
    """POI 가 '영향을 주는' 셀 집계.

    지하철역이 있는 칸만 역세권이 아니라 반경 500m 안의 모든 칸이 역세권이다.
    기존 서비스가 단지 좌표 기준으로 하던 반경 집계를, 모든 지점으로 일반화한
    것이다. 즉 '이 칸에 산다면 생활권이 어떻게 되는가'.

    주의: 커버리지는 셀 간 합산이 불가능하다(같은 POI 가 이웃 셀에 중복 계산됨).
    거친 격자로 낮출 때는 합이 아니라 평균을 써야 한다.
    """
    coverage = {}

    for lat, lng, layer, subtype, weight, radius in pois:
        ci, cj = cell_of(lat, lng)
        span = int(radius / CELL_SIZE_M) + 1
        radius_sq = radius * radius

        for i in range(ci - span, ci + span + 1):
            for j in range(cj - span, cj + span + 1):
                if (i, j) not in zone_cells:
                    continue

                cell_lat = LAT_ORIGIN + (i + 0.5) * D_LAT
                cell_lng = LNG_ORIGIN + (j + 0.5) * D_LNG

                dy = (cell_lat - lat) * LAT_M_PER_DEG
                dx = (cell_lng - lng) * LNG_M_PER_DEG

                if dx * dx + dy * dy > radius_sq:
                    continue

                key = (i, j, layer, subtype)
                coverage[key] = coverage.get(key, 0) + weight

    return coverage


def build_nearest_distance(pois, zone_cells):
    """셀 중심에서 레이어별 최근접 POI 까지의 거리(m).

    개수 집계로는 안 잡히는 성질을 본다. 반경 안에 역이 3개든 1개든, 실제
    체감은 '가장 가까운 역까지 몇 m'로 결정된다.

    좁은 반경부터 넓혀가며 탐색해 전 조합 거리계산을 피한다.
    """
    nearest = {}
    by_layer = {}

    for lat, lng, layer, _, _, _ in pois:
        if layer in DISTANCE_LAYERS:
            by_layer.setdefault(layer, []).append((lat, lng))

    for layer, points in by_layer.items():
        buckets = {}

        for lat, lng in points:
            buckets.setdefault(cell_of(lat, lng), []).append((lat, lng))

        for i, j in zone_cells:
            cell_lat = LAT_ORIGIN + (i + 0.5) * D_LAT
            cell_lng = LNG_ORIGIN + (j + 0.5) * D_LNG

            best = None
            ring = 0
            max_ring = int(MAX_DISTANCE_M / CELL_SIZE_M) + 1

            while ring <= max_ring:
                # 이미 찾은 최근접이 현재 링의 최소 도달거리보다 가까우면 종료.
                if best is not None and best <= (ring - 1) * CELL_SIZE_M:
                    break

                for di in range(-ring, ring + 1):
                    for dj in range(-ring, ring + 1):
                        if max(abs(di), abs(dj)) != ring:
                            continue

                        for lat, lng in buckets.get((i + di, j + dj), ()):
                            dy = (cell_lat - lat) * LAT_M_PER_DEG
                            dx = (cell_lng - lng) * LNG_M_PER_DEG
                            distance = math.hypot(dx, dy)

                            if best is None or distance < best:
                                best = distance

                ring += 1

            if best is not None and best <= MAX_DISTANCE_M:
                nearest[(i, j, layer)] = round(best)

    return nearest


def rasterize_districts(zone_cells):
    """행정경계 폴리곤을 격자에 칠해 셀 → 자치구를 정한다.

    셀마다 25개 폴리곤을 점-다각형 판정하면 수천만 연산이 된다. 대신 폴리곤별로
    셀 행(row)을 훑으며 그 위도에서의 교차점을 구해 구간을 칠하는 스캔라인
    방식을 쓴다. 홀(구멍)은 even-odd 규칙에서 자동으로 처리된다.

    반환되지 않은 셀은 서울 경계 밖(경기로 넘어간 생활권)이라 호출부에서
    최근접 단지 구로 보완한다.
    """
    if not os.path.exists(DISTRICT_GEOJSON):
        print(f"[SKIP] 행정경계 없음 ({DISTRICT_GEOJSON}) — 최근접 단지로 대체")
        return {}

    with open(DISTRICT_GEOJSON, encoding="utf-8") as file:
        geo = json.load(file)

    assigned = {}

    for feature in geo["features"]:
        name = feature["properties"].get("name")
        geometry = feature["geometry"]

        if geometry["type"] == "Polygon":
            rings = geometry["coordinates"]
        else:
            rings = [r for poly in geometry["coordinates"] for r in poly]

        edges = []
        min_lat = min_lng = float("inf")
        max_lat = max_lng = float("-inf")

        for ring in rings:
            for index in range(len(ring) - 1):
                lng1, lat1 = ring[index][0], ring[index][1]
                lng2, lat2 = ring[index + 1][0], ring[index + 1][1]

                if lat1 != lat2:
                    edges.append((lat1, lng1, lat2, lng2))

                min_lat = min(min_lat, lat1)
                max_lat = max(max_lat, lat1)
                min_lng = min(min_lng, lng1)
                max_lng = max(max_lng, lng1)

        row_start = int(math.floor((min_lat - LAT_ORIGIN) / D_LAT))
        row_end = int(math.ceil((max_lat - LAT_ORIGIN) / D_LAT))

        for i in range(row_start, row_end + 1):
            lat = LAT_ORIGIN + (i + 0.5) * D_LAT
            crossings = []

            for lat1, lng1, lat2, lng2 in edges:
                if (lat1 <= lat < lat2) or (lat2 <= lat < lat1):
                    t = (lat - lat1) / (lat2 - lat1)
                    crossings.append(lng1 + t * (lng2 - lng1))

            if not crossings:
                continue

            crossings.sort()

            for k in range(0, len(crossings) - 1, 2):
                j_start = int(math.floor((crossings[k] - LNG_ORIGIN) / D_LNG))
                j_end = int(math.floor((crossings[k + 1] - LNG_ORIGIN) / D_LNG))

                for j in range(j_start, j_end + 1):
                    if (i, j) in zone_cells:
                        assigned[(i, j)] = name

    return assigned


def build_household_coverage(zone_cells):
    """셀 반경 안의 세대수. 레이어 반경별로 따로 구한다.

    시설 절대량만 보면 '사람이 많으니 시설도 많다' 와 구분되지 않는다. 강남이
    항상 빨간 건 발견이 아니다. 공급(시설)과 수요(세대)를 **같은 반경**에서
    재야 비율이 성립하므로, 레이어가 쓰는 반경마다 따로 집계한다.

    세대수는 `k-전체세대수`(단지 2,860/2,861 보유, 총 172만 세대).
    """
    load_apartment_data()
    apartments = []

    for row in apartment_data:
        try:
            households = int(str(row.get("household_count", "")).strip())
            lat = float(row["lat"])
            lng = float(row["lng"])
        except (TypeError, ValueError, KeyError):
            continue

        if households > 0:
            apartments.append((lat, lng, households))

    radii = sorted({radius for *_, radius, _, _ in LAYERS} | {CCTV_RADIUS_M})
    result = {}

    for radius in radii:
        span = int(radius / CELL_SIZE_M) + 1
        radius_sq = radius * radius

        for lat, lng, households in apartments:
            ci, cj = cell_of(lat, lng)

            for i in range(ci - span, ci + span + 1):
                for j in range(cj - span, cj + span + 1):
                    if (i, j) not in zone_cells:
                        continue

                    cell_lat = LAT_ORIGIN + (i + 0.5) * D_LAT
                    cell_lng = LNG_ORIGIN + (j + 0.5) * D_LNG

                    dy = (cell_lat - lat) * LAT_M_PER_DEG
                    dx = (cell_lng - lng) * LNG_M_PER_DEG

                    if dx * dx + dy * dy > radius_sq:
                        continue

                    key = (i, j, radius)
                    result[key] = result.get(key, 0) + households

    lookup = {}

    for row in apartment_data:
        try:
            lookup[(row["name"], row["gu"], row["dong"])] = int(
                str(row.get("household_count", "")).strip()
            )
        except (TypeError, ValueError, KeyError):
            continue

    return result, len(apartments), lookup


def build_boundary_distance(zone_cells):
    """셀 중심에서 서울 행정경계까지의 거리(m).

    서울 전용 원본을 쓰는 레이어(11종 중 9종)는 경계 밖 POI 가 없다. 반경이
    경계를 넘는 칸은 그 바깥을 '시설 0' 으로 세는 셈이라 과소집계된다.

    레이어마다 반경이 달라(200~1500m) 플래그를 레이어별로 두면 11개가 된다.
    대신 경계까지의 거리 하나만 저장하고, 조회 시 각 레이어가 자기 반경과
    비교하게 한다(`distance < radius` 이면 영향 있음).

    거리는 100m 격자 위 다중시작 BFS 로 구한다. 셀마다 폴리곤 25,222개 정점을
    재면 15억 연산이지만, 경계 밖 칸에서 퍼뜨리면 격자 크기에 비례한다.
    격자 해상도(100m)만큼의 오차가 있으나 반경 비교에는 충분하다.
    """
    min_lat, max_lat, min_lng, max_lng = POI_BOUNDS
    i_lo, j_lo = cell_of(min_lat, min_lng)
    i_hi, j_hi = cell_of(max_lat, max_lng)

    region = {
        (i, j)
        for i in range(i_lo, i_hi + 1)
        for j in range(j_lo, j_hi + 1)
    }

    inside = set(rasterize_districts(region))

    # 경계 밖 칸에서 시작해 안쪽으로 퍼뜨린다.
    from collections import deque

    distance = {}
    queue = deque()

    for cell in region:
        if cell not in inside:
            distance[cell] = 0
            queue.append(cell)

    while queue:
        i, j = queue.popleft()
        step = distance[(i, j)] + 1

        for nb in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if nb in inside and nb not in distance:
                distance[nb] = step
                queue.append(nb)

    return {
        cell: distance.get(cell, 0) * CELL_SIZE_M
        for cell in zone_cells
    }


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
    # 셀 → (최근접 단지까지 거리², 단지 index). 지도에 구 경계를 그리는 데 쓴다.
    # 생활권 셀은 정의상 1km 안에 단지가 있어 항상 값이 정해진다.
    nearest_apartment = {}
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

                best = nearest_apartment.get((i, j))
                if best is None or distance_sq < best[0]:
                    nearest_apartment[(i, j)] = (distance_sq, index)

    return apartments, pairs, core_cells, extended_cells, nearest_apartment


def write_db(counts, coverage, nearest_distance, nearest, districts,
             boundary_distance, households, household_lookup, stats,
             apartments, pairs, core_cells, extended_cells):
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
            dropped_count INTEGER,
            radius_m INTEGER
        );

        -- POI 가 위치한 셀 (개별 표시용). 셀 간 합산 가능.
        CREATE TABLE grid_cell (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            layer TEXT NOT NULL,
            subtype TEXT NOT NULL,
            count REAL NOT NULL,
            PRIMARY KEY (i, j, layer, subtype)
        ) WITHOUT ROWID;

        -- POI 가 영향을 주는 셀 (밀집도·접근성 표시용).
        -- 이웃 셀에 같은 POI 가 중복 계산되므로 합산 불가. 거칠게 볼 때는 평균.
        CREATE TABLE grid_coverage (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            layer TEXT NOT NULL,
            subtype TEXT NOT NULL,
            count REAL NOT NULL,
            PRIMARY KEY (i, j, layer, subtype)
        ) WITHOUT ROWID;

        -- 셀 중심에서 레이어별 최근접 POI 까지 거리(m). 개수로는 안 잡히는 성질.
        -- 값이 없으면 3km 안에 해당 시설이 없다는 뜻.
        -- 셀 반경 안의 세대수. 공급(시설)과 수요(세대)를 같은 반경에서 재야
        -- 비율이 성립하므로 레이어 반경별로 따로 담는다.
        CREATE TABLE grid_household (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            radius_m INTEGER NOT NULL,
            households INTEGER NOT NULL,
            PRIMARY KEY (i, j, radius_m)
        ) WITHOUT ROWID;

        CREATE TABLE grid_nearest (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            layer TEXT NOT NULL,
            distance_m INTEGER NOT NULL,
            PRIMARY KEY (i, j, layer)
        ) WITHOUT ROWID;

        -- gu/dong 은 최근접 단지에서 물려받은 값이다(행정경계 원본이 아님).
        -- 지도에 기준선을 그리고 셀을 행정구역으로 묶는 용도.
        CREATE TABLE grid_zone (
            i INTEGER NOT NULL,
            j INTEGER NOT NULL,
            in_core INTEGER NOT NULL,
            apartment_count INTEGER NOT NULL,
            gu TEXT,
            dong TEXT,
            boundary_distance_m INTEGER,
            PRIMARY KEY (i, j)
        ) WITHOUT ROWID;

        CREATE TABLE apartment (
            id INTEGER PRIMARY KEY,
            name TEXT, gu TEXT, dong TEXT,
            lat REAL, lng REAL,
            households INTEGER,
            i INTEGER, j INTEGER
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
        "INSERT INTO layer_meta VALUES (?, ?, ?, ?, ?, ?, ?)",
        stats,
    )

    cursor.executemany(
        "INSERT INTO grid_cell VALUES (?, ?, ?, ?, ?)",
        [(i, j, layer, subtype, value)
         for (i, j, layer, subtype), value in counts.items()],
    )

    cursor.executemany(
        "INSERT INTO grid_coverage VALUES (?, ?, ?, ?, ?)",
        [(i, j, layer, subtype, value)
         for (i, j, layer, subtype), value in coverage.items()],
    )

    cursor.executemany(
        "INSERT INTO grid_household VALUES (?, ?, ?, ?)",
        [(i, j, r, n) for (i, j, r), n in households.items()],
    )

    cursor.executemany(
        "INSERT INTO grid_nearest VALUES (?, ?, ?, ?)",
        [(i, j, layer, distance)
         for (i, j, layer), distance in nearest_distance.items()],
    )

    cursor.executemany(
        "INSERT INTO apartment VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (index, name, gu, dong, lat, lng,
             household_lookup.get((name, gu, dong)), *cell_of(lat, lng))
            for index, (name, gu, dong, lat, lng) in enumerate(apartments)
        ],
    )

    cursor.execute("CREATE INDEX idx_apartment_cell ON apartment (i, j)")

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

    # gu 는 행정경계 폴리곤 판정을 우선하고, 경계 밖(경기로 넘어간 생활권)만
    # 최근접 단지 값으로 보완한다. dong 은 경계 데이터가 없어 단지 기준이다.
    cursor.executemany(
        "UPDATE grid_zone SET gu = ?, dong = ? WHERE i = ? AND j = ?",
        [
            (
                districts.get((i, j)) or apartments[index][1],
                apartments[index][2],
                i, j,
            )
            for (i, j), (_, index) in nearest.items()
        ],
    )

    cursor.executemany(
        "UPDATE grid_zone SET boundary_distance_m = ? WHERE i = ? AND j = ?",
        [(d, i, j) for (i, j), d in boundary_distance.items()],
    )

    cursor.execute("CREATE INDEX idx_zone_gu ON grid_zone (gu)")
    cursor.execute(
        "CREATE INDEX idx_zone_boundary ON grid_zone (boundary_distance_m)"
    )

    cursor.executescript("""
        CREATE INDEX idx_cell_layer ON grid_cell (layer, i, j);
        CREATE INDEX idx_coverage_layer ON grid_coverage (layer, i, j);
        CREATE INDEX idx_nearest_layer ON grid_nearest (layer, i, j);
        CREATE INDEX idx_household_r ON grid_household (radius_m, i, j);
        CREATE INDEX idx_zone_core ON grid_zone (in_core);
        CREATE INDEX idx_ga_apartment ON grid_apartment (apartment_id);
        CREATE INDEX idx_ga_cell ON grid_apartment (i, j);
    """)

    connection.commit()
    connection.execute("VACUUM")
    connection.close()


def main():
    started = time.time()

    pois, stats = build_poi_list()

    print("[ZONE] 단지 생활권 셀 계산")
    apartments, pairs, core_cells, extended_cells, nearest_apartment = (
        build_apartment_cells()
    )

    print(
        f"[ZONE] 단지 {len(apartments):,}개 → "
        f"핵심 {len(core_cells):,}셀 / 확장 {len(extended_cells):,}셀, "
        f"관계 {len(pairs):,}쌍"
    )

    # 생활권 밖 셀은 저장하지 않는다.
    counts = {
        key: value
        for key, value in build_point_counts(pois).items()
        if (key[0], key[1]) in extended_cells
    }

    print(f"[CELL] 위치 집계 {len(counts):,}행")

    print("[COVER] 영향권 집계 (반경 내 모든 셀)")
    coverage = build_coverage(pois, extended_cells)
    print(f"[COVER] 영향권 집계 {len(coverage):,}행")

    print(f"[NEAR] 최근접 거리 계산 ({', '.join(sorted(DISTANCE_LAYERS))})")
    nearest = build_nearest_distance(pois, extended_cells)
    print(f"[NEAR] 최근접 거리 {len(nearest):,}행")

    print("[GU] 행정경계 폴리곤으로 셀 자치구 판정")
    districts = rasterize_districts(extended_cells)
    outside = len(extended_cells) - len(districts)
    print(f"[GU] 경계 내 {len(districts):,}셀 / 경계 밖 {outside:,}셀(최근접 단지로 보완)")

    print("[EDGE] 서울 경계까지 거리 계산")
    boundary_distance = build_boundary_distance(extended_cells)
    for limit in (200, 500, 1000, 1500):
        n = sum(1 for d in boundary_distance.values() if d < limit)
        print(f"[EDGE]   반경 {limit:>4}m 영향 칸 {n:>6,} "
              f"({100 * n / len(extended_cells):.0f}%)")

    print("[HH] 반경별 세대수 집계")
    households, hh_apts, household_lookup = build_household_coverage(
        extended_cells
    )
    print(f"[HH] 단지 {hh_apts:,}개 / {len(households):,}행")

    write_db(counts, coverage, nearest, nearest_apartment, districts,
             boundary_distance, households, household_lookup, stats,
             apartments, pairs, core_cells, extended_cells)

    size_mb = os.path.getsize(OUTPUT_PATH) / 1e6
    print(
        f"[DONE] {OUTPUT_PATH} — {size_mb:.1f}MB, "
        f"{time.time() - started:.0f}s"
    )


if __name__ == "__main__":
    main()

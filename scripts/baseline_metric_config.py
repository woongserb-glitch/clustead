from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
BASELINE_DIR = BASE_DIR / "data" / "baseline"

HIGHER_BETTER = "higher_better"
LOWER_BETTER = "lower_better"


def percentile_column(metric):
    return f"{metric}_seoul_percentile"


def score_column(metric):
    return f"{metric}_seoul_score"


def metric_config(
    *,
    label,
    file,
    required_columns,
    primary_metric,
    direction,
    display_metric_label,
    json_columns=None,
    radius_rules=None,
    percentile_enabled=True,
    ranking_enabled=True,
    validation_enabled=True,
    debug_columns=None,
    extra_metrics=None,
    tiebreaker=None,
    metric_tiebreakers=None,
):
    # extra_metrics: {컬럼: 방향}. 한 baseline 파일이 여러 카드를 먹이는 경우
    # (medical -> 병원/응급실/종합병원/약국) 카드마다 백분위 축이 달라야 한다.
    # primary_metric 은 랭킹·검증에 쓰이는 대표 지표로 그대로 두고, 여기에 더한
    # 지표들은 percentile/score 컬럼만 추가로 생성된다.
    return {
        "label": label,
        "path": str(BASELINE_DIR / file),
        "file": file,
        "required_columns": required_columns,
        "primary_metric": primary_metric,
        "primary_percentile_column": percentile_column(primary_metric),
        "primary_score_column": score_column(primary_metric),
        "display_metric_label": display_metric_label,
        "metrics": {
            primary_metric: direction,
            **(extra_metrics or {}),
        },
        "json_columns": json_columns or [],
        "radius_rules": radius_rules or [],
        # 동점 깨기 보조 지표 {"column":…, "direction":…}.
        # 값이 이산적인 지표는 같은 값이면 백분위가 같아 등급 종류가 3~4개로 줄고,
        # 최빈값에 절반이 몰리면 그 그룹 전체가 한 등급에 묶인다(지하철 0노선
        # 1,389단지=48.4%가 모두 C, A·D 는 아예 안 나옴). 보조 지표로 순위를
        # 나누면 분포가 펴진다.
        "tiebreaker": tiebreaker,
        # 지표별 동점 깨기. extra_metrics 처럼 primary 가 아닌 지표에도 붙인다.
        "metric_tiebreakers": metric_tiebreakers or {},
        "percentile_enabled": percentile_enabled,
        "ranking_enabled": ranking_enabled,
        "validation_enabled": validation_enabled,
        "debug_columns": debug_columns or [],
    }


BASELINE_METRIC_CONFIG = {
    "subway": metric_config(
        label="지하철",
        file="subway_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "subway_line_count_500m"],
        primary_metric="subway_line_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="가장 가까운 지하철역 거리",
        json_columns=["subway_items_500m_json", "subway_items_json"],
        radius_rules=[
            ("subway_station_count_500m", "subway_station_count_800m"),
            ("subway_station_count_800m", "subway_station_count_1km"),
        ],
        # 500m 내 노선수는 0~6 의 7종뿐이고 0 이 48.4%. 같은 노선수면 역이
        # 가까울수록 낫다.
        tiebreaker={"column": "nearest_subway_distance", "direction": LOWER_BETTER},
    ),
    "bus": metric_config(
        label="버스",
        file="bus_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "bus_stop_count_500m", "bus_route_count"],
        primary_metric="bus_route_count",
        direction=HIGHER_BETTER,
        display_metric_label="500m 내 이용 가능 버스 노선 수",
        json_columns=["bus_items_json"],
        radius_rules=[("bus_stop_count_300m", "bus_stop_count_500m")],
    ),
    "bike": metric_config(
        label="따릉이",
        file="bike_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "bike_station_count_500m"],
        primary_metric="bike_station_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="500m 내 따릉이 대여소 수",
        json_columns=["bike_items_json"],
    ),
    "convenience": metric_config(
        label="편의점",
        file="convenience_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "convenience_count_500m"],
        primary_metric="convenience_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="500m 내 편의점 수",
        json_columns=["convenience_items_json"],
        radius_rules=[("convenience_count_300m", "convenience_count_500m")],
    ),
    # 마트 3개 카테고리(같은 mart_baseline.csv를 공유, 그룹별 반경/지표가 다름).
    "large_mart": metric_config(
        label="대형마트",
        file="mart_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "large_mart_count_3000m"],
        primary_metric="large_mart_count_3000m",
        direction=HIGHER_BETTER,
        display_metric_label="3km 내 대형마트(이마트·홈플러스·롯데마트) 수",
        json_columns=["large_mart_items_json"],
    ),
    "super_mart": metric_config(
        label="슈퍼마켓",
        file="mart_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "super_mart_count_500m"],
        primary_metric="super_mart_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="도보권 500m 내 슈퍼마켓 수",
        json_columns=["super_mart_items_json"],
        # 0~5 의 6종뿐이고 0 이 33.9%. 최하값(0곳)이 백분위 83 에 그쳐 D 가 한 건도
        # 안 나왔다. 같은 개수면 가까울수록 낫다.
        tiebreaker={"column": "nearest_super_mart_distance", "direction": LOWER_BETTER},
    ),
    "warehouse_mart": metric_config(
        label="창고형마트",
        file="mart_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "warehouse_mart_count_5000m"],
        primary_metric="warehouse_mart_count_5000m",
        direction=HIGHER_BETTER,
        display_metric_label="5km 내 창고형마트(코스트코·트레이더스) 수",
        json_columns=["warehouse_mart_items_json"],
        # 0~3 의 4종뿐이고 최빈값이 40%. D 가 한 건도 안 나왔다.
        tiebreaker={"column": "nearest_warehouse_mart_distance", "direction": LOWER_BETTER},
    ),
    "cafe": metric_config(
        label="카페",
        file="cafe_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "cafe_count_500m", "franchise_total_500m", "cafe_access_score_raw"],
        primary_metric="cafe_access_score_raw",
        direction=HIGHER_BETTER,
        display_metric_label="카페 접근성(프랜차이즈 수 + 브랜드 다양성)",
        json_columns=["cafe_items_json"],
        radius_rules=[("cafe_count_300m", "cafe_count_500m")],
    ),
    "medical": metric_config(
        label="의료 접근성",
        file="medical_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "medical_count_1km", "hospital_count_500m"],
        primary_metric="medical_count_1km",
        direction=HIGHER_BETTER,
        display_metric_label="1km 내 의료시설 수",
        json_columns=[
            "medical_items_json",
            "hospital_items_json",
            "emergency_items_json",
            "superior_hospital_items_json",
            "pharmacy_items_json",
        ],
        radius_rules=[
            ("medical_count_500m", "medical_count_1km"),
            ("hospital_count_500m", "hospital_count_1km"),
            ("emergency_count_1km", "emergency_count_3km"),
            ("pharmacy_count_500m", "pharmacy_count_1km"),
        ],
        # 종합병원·응급실·약국 카드는 백분위가 없어 등급이 곳수를 0~100 점수로
        # 오독당했다(종합병원 최대 14곳 -> 항상 D). 이들은 "몇 곳이냐"보다
        # "얼마나 가깝냐"가 자연스러운 시설이고 배지·필터도 최근접 거리 기준이라
        # 거리 백분위로 등급 축을 맞춘다.
        extra_metrics={
            "nearest_superior_hospital_distance": LOWER_BETTER,
            "nearest_emergency_distance": LOWER_BETTER,
            "nearest_pharmacy_distance": LOWER_BETTER,
            # 약국만 개수 기준이다. 종합병원·응급실은 카드 개수의 변별력이 낮고
            # 배지·필터도 거리로 통일했지만, 약국 카드는 "근처 N곳"을 전면에
            # 보여주므로 등급이 거리로 매겨지면 화면 숫자와 어긋난다
            # (1곳인데 S, 21곳인데 D 가 동시에 나왔다).
            "pharmacy_count_500m": HIGHER_BETTER,
        },
        # 개수는 이산적이라 동점이 많다. 같은 개수면 가까울수록 낫다.
        metric_tiebreakers={
            "pharmacy_count_500m": {
                "column": "nearest_pharmacy_distance",
                "direction": LOWER_BETTER,
            },
        },
    ),
    "academy": metric_config(
        label="학원",
        file="academy_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "academy_count_1000m"],
        primary_metric="academy_count_1000m",
        direction=HIGHER_BETTER,
        display_metric_label="1km 내 학원 수",
        json_columns=["academy_items_json"],
        radius_rules=[("academy_count_500m", "academy_count_1000m")],
    ),
    "culture": metric_config(
        label="문화생활",
        file="culture_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "culture_count_1500m"],
        primary_metric="culture_count_1500m",
        direction=HIGHER_BETTER,
        display_metric_label="1.5km 내 문화시설 수",
        json_columns=["culture_items_json"],
    ),
    "shopping": metric_config(
        label="쇼핑",
        file="shopping_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "shopping_count_3km"],
        primary_metric="shopping_count_3km",
        direction=HIGHER_BETTER,
        display_metric_label="3km 내 쇼핑시설 수",
        json_columns=["shopping_items_json"],
    ),
    "commercial": metric_config(
        label="상권",
        file="commercial_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "commercial_count_1km"],
        primary_metric="commercial_count_1km",
        direction=HIGHER_BETTER,
        display_metric_label="1km 내 상권 수",
        json_columns=["commercial_items_json"],
    ),
    "nightlife": metric_config(
        label="유흥시설",
        file="nightlife_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "nightlife_count_500m"],
        primary_metric="nightlife_count_500m",
        direction=LOWER_BETTER,
        display_metric_label="500m 내 유흥시설 수",
        json_columns=["nightlife_items_json"],
        radius_rules=[("nightlife_count_500m", "nightlife_count_1km")],
        # 69.7% 가 0 곳이고, LOWER_BETTER 라 0 곳이 최선인데 그 그룹 전체가 한
        # 등급(B)에 묶여 S·A 가 한 건도 안 나왔다. 표시용 nearest_nightlife_distance
        # 는 500m 안에서만 재서 0 곳 단지가 전부 결측이라 쓸 수 없었고, 빌더에
        # nightlife_nearest_any_distance(반경 무관)를 새로 만들어 쓴다.
        # 유흥은 멀수록 좋으므로 HIGHER_BETTER.
        tiebreaker={
            "column": "nightlife_nearest_any_distance",
            "direction": HIGHER_BETTER,
        },
    ),
    "hangang": metric_config(
        label="한강공원",
        file="hangang_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "nearest_hangang_distance"],
        primary_metric="nearest_hangang_distance",
        direction=LOWER_BETTER,
        display_metric_label="가장 가까운 한강공원 거리",
        json_columns=["hangang_items_json"],
    ),
    "fire_station": metric_config(
        label="119 안전",
        file="fire_station_baseline.csv",
        required_columns=["name", "gu", "dong", "nearest_fire_station_distance"],
        primary_metric="nearest_fire_station_distance",
        direction=LOWER_BETTER,
        display_metric_label="가장 가까운 119 안전시설 거리",
        json_columns=["fire_station_items_json"],
    ),
    "ev_charger": metric_config(
        label="전기차 충전",
        file="ev_charger_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "ev_charger_count_500m"],
        primary_metric="ev_charger_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="500m 내 충전소 수",
        json_columns=["ev_charger_items_json"],
        radius_rules=[
            ("ev_charger_count_300m", "ev_charger_count_500m"),
            ("ev_charger_count_500m", "ev_charger_count_1km"),
        ],
    ),
    "cctv": metric_config(
        label="CCTV",
        file="cctv_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "cctv_count_500m"],
        primary_metric="cctv_count_500m",
        direction=HIGHER_BETTER,
        display_metric_label="500m 내 CCTV 수",
        radius_rules=[("cctv_count_300m", "cctv_count_500m")],
    ),
    "park": metric_config(
        label="공원",
        file="park_baseline.csv",
        required_columns=["name", "gu", "dong", "lat", "lng", "park_distance"],
        primary_metric="park_distance",
        direction=LOWER_BETTER,
        display_metric_label="가장 가까운 공원 거리",
    ),
    "school_zone": metric_config(
        label="교육환경",
        file="school_zone_baseline.csv",
        required_columns=[
            "name",
            "gu",
            "dong",
            "lat",
            "lng",
            "assigned_elementary_school",
            "assigned_elementary_distance_m",
            "elementary_access_score",
        ],
        primary_metric="elementary_access_score",
        direction=HIGHER_BETTER,
        display_metric_label="배정초 접근 점수",
        percentile_enabled=True,
        ranking_enabled=True,
        debug_columns=[
            "assigned_elementary_school",
            "assigned_elementary_distance_m",
        ],
    ),
    "transaction_summary": metric_config(
        label="실거래 요약",
        file="transaction_summary.csv",
        required_columns=[
            "name",
            "kapt_code",
            "gu",
            "dong",
            "trade_count_1y",
            "rent_count_1y",
            "data_confidence",
        ],
        primary_metric="trade_count_1y",
        direction=HIGHER_BETTER,
        display_metric_label="최근 1년 매매 거래 건수",
        percentile_enabled=False,
        ranking_enabled=False,
    ),
}

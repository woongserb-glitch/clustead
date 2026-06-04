import json
import csv
import sys
import re
import math

from services.ranking_service import (
    get_ranked_apartments,
    build_apartment_index,
    calculate_weighted_score,
)

import os
from pathlib import Path
from urllib.parse import urlencode

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False
from flask import Flask, jsonify, render_template, request

from services.poi_service import (
    get_category_summaries,
    get_domain_summaries,
    get_preference_labels,
    get_sample_pois,
    CATEGORY_TO_DOMAIN,
    DOMAIN_META,
)
from services.kakao_local_service import get_real_pois
from services.preload_service import load_cctv_data
from services.preload_service import cctv_data
from services.geo_service import filter_pois_by_radius, get_distance_m
from services.transaction_service import (
    empty_transaction_summary,
    get_transaction_summary,
)
from services.insight_service import (
    build_apartment_insight,
    has_feature_from_rows,
    to_number as insight_to_number,
)

from services.preload_service import load_park_data
from services.preload_service import park_data

from services.preload_service import load_apartment_data
from services.preload_service import apartment_data

from services.preload_service import load_subway_baseline_data
from services.preload_service import subway_baseline_data, subway_baseline_index

from services.baseline_service import get_subway_percentiles

from services.preload_service import load_cctv_baseline_data

from services.preload_service import convenience_baseline_data, load_convenience_baseline_data

from services.preload_service import mart_baseline_data, load_mart_baseline_data

from services.preload_service import cafe_baseline_data, load_cafe_baseline_data

from services.ranking_service import get_ranked_apartments

from services.preload_service import school_data, load_school_data

from services.preload_service import school_zone_baseline_data, load_school_zone_baseline_data

from services.preload_service import bus_stop_data, load_bus_stop_data
from services.preload_service import bus_route_data, load_bus_route_data

from services.preload_service import bus_baseline_data, bus_baseline_index, load_bus_baseline_data
from services.preload_service import commercial_baseline_data, commercial_baseline_index, load_commercial_baseline_data
from services.preload_service import nightlife_baseline_data, nightlife_baseline_index, load_nightlife_baseline_data
from services.preload_service import bike_baseline_data, bike_baseline_index, load_bike_baseline_data
from services.preload_service import academy_baseline_data, academy_baseline_index, load_academy_baseline_data
from services.preload_service import culture_baseline_data, culture_baseline_index, load_culture_baseline_data
from services.preload_service import hangang_baseline_data, hangang_baseline_index, load_hangang_baseline_data
from services.preload_service import fire_station_baseline_data, fire_station_baseline_index, load_fire_station_baseline_data
from services.preload_service import shopping_baseline_data, shopping_baseline_index, load_shopping_baseline_data
from services.preload_service import ev_charger_baseline_data, ev_charger_baseline_index, load_ev_charger_baseline_data
from services.preload_service import medical_baseline_data, medical_baseline_index, load_medical_baseline_data
from services.preload_service import lifestyle_food_baseline_data, lifestyle_food_baseline_index, load_lifestyle_food_baseline_data
from services.preload_service import get_indexed_baseline_row
from scripts.baseline_metric_config import (
    BASELINE_METRIC_CONFIG,
    HIGHER_BETTER,
    LOWER_BETTER,
)

load_dotenv()

app = Flask(__name__)

KAKAO_RESULT_FALLBACK_CATEGORIES = ()
KAKAO_RESULT_ALL_CATEGORIES = (
    "subway",
    "hospital",
    "pharmacy",
)
load_cctv_data()
load_park_data()
load_apartment_data()

load_subway_baseline_data()
load_cctv_baseline_data()
load_convenience_baseline_data()
load_mart_baseline_data()
load_cafe_baseline_data()
load_school_data()
load_school_zone_baseline_data()

load_bus_stop_data()
load_bus_route_data()
load_bus_baseline_data()
load_commercial_baseline_data()
load_nightlife_baseline_data()
load_bike_baseline_data()
load_academy_baseline_data()
load_culture_baseline_data()
load_hangang_baseline_data()
load_fire_station_baseline_data()
load_shopping_baseline_data()
load_ev_charger_baseline_data()
load_medical_baseline_data()
load_lifestyle_food_baseline_data()
build_apartment_index()


KAKAO_JAVASCRIPT_KEY = os.getenv("KAKAO_JAVASCRIPT_KEY", "")
DEBUG_LOG = os.getenv("LIVEFIT_DEBUG", "0") == "1"


def debug_log(*args):
    if DEBUG_LOG:
        print(*args)


PREFERENCE_KEYS = [
    "subway",
    "bus",
    "bike",
    "large_mart",
    "super_mart",
    "warehouse_mart",
    "convenience",
    "ev-charger",
    "cafe",
    "hospital",
    "pharmacy",
    "park",
    "hangang",
    "culture",
    "academy",
    "cctv",
    "fire-station",
    "nightlife",
    "commercial",
    "shopping",

]

PREFERENCE_LABELS = get_preference_labels()


def get_baseline_percentile(row, column):
    if not row or not column:
        return None

    value = row.get(column)

    if value is None or value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def format_percentile_label(percentile, scope_label="서울"):
    value = parse_optional_float(percentile)

    if value is None:
        return None

    if value < 1:
        return f"{scope_label} 상위 1% 이내"

    return f"{scope_label} 상위 {max(1, int(value))}%"


def format_distance_m(value):
    number = parse_optional_float(value)

    if number is None:
        return ""

    return f"{int(round(number)):,}m"


app.jinja_env.filters["distance_m"] = format_distance_m


def format_percentile_score(percentile):
    value = parse_optional_float(percentile)

    if value is None:
        return "-"

    score = max(0, min(100, 100 - value))
    return f"{round(score):.0f}점"


def percentile_score_class(percentile):
    value = parse_optional_float(percentile)

    if value is None:
        return "score-normal"

    if value <= 20:
        return "score-good"

    if value >= 80:
        return "score-low"

    return "score-normal"


def percentile_score_value(percentile):
    value = parse_optional_float(percentile)

    if value is None:
        return 0

    return round(max(0, min(100, 100 - value)))


NEAREST_ICON_BY_CATEGORY = {
    "subway": "🚇",
    "bus-baseline": "🚌",
    "bike": "🚲",
    "mart": "🛒",
    "large_mart": "🛒",
    "super_mart": "🏪",
    "warehouse_mart": "📦",
    "convenience": "🏪",
    "cafe": "☕",
    "ev-charger": "⚡",
    "hospital": "🏥",
    "general-hospital": "🏥",
    "emergency-room": "🚑",
    "pharmacy": "💊",
    "culture": "🎭",
    "hangang": "🌊",
    "park": "🌳",
    "academy": "✏️",
    "school-environment": "🏫",
    "fire-station": "🚒",
    "cctv": "🛡",
    "shopping": "🛍️",
    "commercial": "🏙️",
    "nightlife": "🍺",
}

CCTV_ICON_BY_SUBTYPE = {
    "생활방범": "🛡",
    "어린이보호": "🧒",
    "교통/단속": "🚦",
    "시설안전": "🏢",
    "기타": "📹",
}


def compact_label(text):
    value = clean_text(text)
    for icon in NEAREST_ICON_BY_CATEGORY.values():
        value = value.replace(icon, "").strip()
        value = value.replace(icon.replace("\ufe0f", ""), "").strip()
    for icon in CCTV_ICON_BY_SUBTYPE.values():
        value = value.replace(icon, "").strip()
        value = value.replace(icon.replace("\ufe0f", ""), "").strip()
    value = value.replace("\ufe0f", "").strip()
    return value


def hangang_park_name(value):
    text = compact_label(value)
    if not text:
        return ""
    return text.split(" · ")[0].split("[")[0].strip()


def compact_nearest_label(value):
    text = compact_label(value)
    return re.sub(r"^[\W_]+", "", text).strip()


def description_lines(value):
    text = clean_text(value)
    if not text:
        return []
    return [line.strip() for line in re.split(r"(?<=[.!?])\s+", text) if line.strip()]


def nearest_display_label(value, key=None):
    if key == "hangang":
        return hangang_park_name(value)
    return compact_nearest_label(value)


def poi_list_display_label(value, key=None):
    text = compact_label(value)
    if key == "hangang" and text:
        # Scroll-box list rows stay icon-free for consistency with other cards;
        # keep only the extracted park name (no 🌊 prefix).
        return hangang_park_name(text)
    return text


app.jinja_env.filters["description_lines"] = description_lines
app.jinja_env.filters["nearest_display_label"] = nearest_display_label
app.jinja_env.filters["poi_list_display_label"] = poi_list_display_label


def percentile_interpretation(percentile):
    value = parse_optional_float(percentile)

    if value is None:
        return "서울시 기준 상대평가는 참고용으로 확인하세요"

    if value <= 5:
        return "서울시 최상위권입니다"
    if value <= 20:
        return "서울시 기준 우수한 편입니다"
    if value <= 60:
        return "서울시 평균 수준입니다"
    if value <= 80:
        return "서울시 평균보다 다소 낮은 편입니다"
    return "서울시 기준 부족한 편입니다"


def grade_from_score(score):
    value = parse_optional_float(score)

    if value is None:
        value = 0

    if value >= 90:
        return "S", "매우 우수"
    if value >= 70:
        return "A", "우수"
    if value >= 40:
        return "B", "평균 수준"
    if value >= 15:
        return "C", "평균 이하"
    return "D", "부족"


def score_class_from_score(score):
    value = parse_optional_float(score)

    if value is None:
        value = 0

    if value >= 70:
        return "score-good"
    if value >= 40:
        return "score-normal"
    return "score-low"


def interpretation_from_score(score):
    grade, _ = grade_from_score(score)

    if grade == "S":
        return "서울 평균과 비교하면 매우 우수한 편입니다"
    if grade == "A":
        return "서울 평균과 비교하면 우수한 편입니다"
    if grade == "B":
        return "서울 평균과 비슷한 수준입니다"
    if grade == "C":
        return "서울 평균과 비교하면 다소 부족한 편입니다"
    return "서울 평균과 비교하면 부족한 편입니다"


def fallback_score_from_count(count):
    number = to_int(count, 0)

    if number >= 10:
        return 90
    if number >= 5:
        return 75
    if number >= 3:
        return 55
    if number >= 1:
        return 35
    return 10


def school_environment_score(summary):
    distance = parse_optional_float(
        summary.get("assigned_elementary_distance_m")
        or summary.get("assigned_distance")
    )

    if distance is None:
        nearest = summary.get("nearest_poi") or {}
        distance = parse_optional_float(nearest.get("distance"))

    if distance is None:
        return 10

    if distance <= 150:
        return 95
    if distance <= 300:
        return 88
    if distance <= 500:
        return 78
    if distance <= 800:
        return 62
    if distance <= 1200:
        return 45
    if distance <= 1500:
        return 30
    return 15


def normalized_summary_score(summary):
    percentile = parse_optional_float(summary.get("seoul_percentile"))
    if percentile is None:
        percentile = parse_optional_float(summary.get("percentile"))

    if percentile is not None:
        return percentile_score_value(percentile)

    if summary.get("key") == "school-environment":
        return school_environment_score(summary)

    score = summary.get("score")
    if isinstance(score, str):
        match = re.search(r"\d+(?:\.\d+)?", score.replace(",", ""))
        if match:
            score = float(match.group(0))

    value = parse_optional_float(score)
    if value is not None and 0 <= value <= 100:
        return round(value)

    return fallback_score_from_count(summary.get("count"))


def summarize_names(items, limit=3):
    names = []

    for item in items or []:
        name = compact_label(item.get("name") or item.get("label") or item.get("display"))
        name = name.split(" · ")[0].split("[")[0].strip()
        if name.startswith("서울특별시") or name.startswith("서울시"):
            name = compact_label(item.get("subtype") or "")
        if not name or name in names:
            continue
        names.append(name)
        if len(names) >= limit:
            break

    return names


def format_count_phrase(count, unit="곳"):
    number = to_int(count, 0)
    return f"{number:,}{unit}"


def clean_evidence_label(value):
    text = compact_label(value)
    text = re.sub(r"^[\W_]+", "", text).strip()
    text = text.replace("대표 배정초", "").replace("배정초", "").strip()
    return text


def unique_nonempty(values, limit=None):
    result = []

    for value in values:
        text = clean_evidence_label(value)
        if not text or text in result:
            continue
        result.append(text)
        if limit and len(result) >= limit:
            break

    return result


def join_korean_list(values):
    items = unique_nonempty(values)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + ", " + items[-1]


def compact_example_text(values, limit=2, max_chars=34):
    items = unique_nonempty(values, limit)
    while len(items) > 1 and len(join_korean_list(items)) > max_chars:
        items.pop()
    return join_korean_list(items)


def subtype_count_items(summary, include=None, exclude=None, limit=3):
    include = include or []
    exclude = exclude or []
    items = []

    for chip in summary.get("subtype_chips", []) or []:
        label = clean_evidence_label(chip.get("display") or chip.get("name"))
        if not label:
            continue
        if include and not any(token in label for token in include):
            continue
        if exclude and any(token in label for token in exclude):
            continue
        count = to_int(chip.get("count"), 0)
        if count <= 0:
            continue
        items.append((label, count))

    items.sort(key=lambda item: item[1], reverse=True)
    return items[:limit]


def subtype_sentence(summary, unit="곳", include=None, exclude=None, limit=3):
    items = subtype_count_items(
        summary,
        include=include,
        exclude=exclude,
        limit=limit,
    )
    if not items:
        return ""
    examples = [f"{label} {count:,}{unit}" for label, count in items]
    return compact_example_text(examples, limit=limit, max_chars=30)


def nearest_name_and_distance(summary):
    nearest = summary.get("nearest_poi") or {}
    name = clean_evidence_label(nearest.get("label") or nearest.get("name"))
    distance = nearest.get("distance")

    if not name:
        for item in summary.get("pois", []) or []:
            name = clean_evidence_label(item.get("name") or item.get("label"))
            distance = item.get("distance", distance)
            if name:
                break

    distance_text = ""
    if distance not in [None, ""]:
        distance_text = format_distance_m(distance)

    return name, distance_text


def ev_charger_counts(summary):
    fast = 0
    slow = 0

    for label, count in subtype_count_items(summary, limit=10):
        if "급속" in label:
            fast += count
        elif "완속" in label:
            slow += count

    if fast or slow:
        return fast, slow

    for item in summary.get("pois", []) or []:
        fast += to_int(
            item.get("fast_count")
            or item.get("rapid_count")
            or item.get("charger_fast_count")
            or item.get("quick_count"),
            0,
        )
        slow += to_int(
            item.get("slow_count")
            or item.get("charger_slow_count")
            or item.get("normal_count"),
            0,
        )

    return fast, slow


def pharmacy_operating_labels(summary):
    labels = []

    for label, count in subtype_count_items(summary, limit=10):
        if count <= 0:
            continue
        if "야간" in label and "야간" not in labels:
            labels.append("야간")
        if "주말" in label and "주말" not in labels:
            labels.append("주말")
        if ("휴일" in label or "공휴일" in label) and "휴일" not in labels:
            labels.append("휴일")

    return [label for label in ["야간", "주말", "휴일"] if label in labels]


def assigned_elementary_name(summary):
    name = clean_evidence_label(
        summary.get("assigned_elementary_school")
        or summary.get("assigned_school_name")
    )
    if name:
        return name

    for item in summary.get("pois", []) or []:
        subtype = clean_evidence_label(item.get("subtype"))
        if "배정" in subtype or "초" in subtype:
            return clean_evidence_label(item.get("label") or item.get("name"))

    nearest = summary.get("nearest_poi") or {}
    return clean_evidence_label(nearest.get("label") or nearest.get("name"))


def build_category_evidence(summary):
    key = summary.get("key")
    radius = format_distance_m(summary.get("radius"))
    count = to_int(summary.get("count"), 0)

    if key == "subway":
        line_count = to_int(summary.get("line_count_500m"), 0)
        line_names = unique_nonempty([
            chip.get("display") or chip.get("name")
            for chip in summary.get("subtype_chips", [])
            if "환승" not in clean_evidence_label(chip.get("display") or chip.get("name"))
        ], 3)

        if line_count <= 0:
            nearest_name, nearest_distance = nearest_name_and_distance(summary)
            if nearest_name and nearest_distance:
                return f"반경 500m 내 이용 가능한 지하철 노선은 없습니다. 가장 가까운 역은 {nearest_name}으로 {nearest_distance} 거리입니다."
            return "반경 500m 내 이용 가능한 지하철 노선은 없습니다."

        if line_names:
            return f"반경 500m 내 {line_count:,}개 노선을 이용할 수 있습니다. {compact_example_text(line_names)} 접근이 가능합니다."
        return f"반경 500m 내 {line_count:,}개 지하철 노선을 이용할 수 있습니다."

    if key == "bus-baseline":
        route_text = subtype_sentence(summary, unit="개", limit=2)
        if route_text:
            return f"반경 500m 내 버스 정류장 {format_count_phrase(count)}이 있습니다. {route_text} 노선을 이용할 수 있습니다."
        return f"반경 500m 내 버스 정류장 {format_count_phrase(count)}이 있습니다."

    if key == "bike":
        _, nearest_distance = nearest_name_and_distance(summary)
        if nearest_distance:
            return f"반경 500m 내 따릉이 대여소 {format_count_phrase(count)}이 있습니다. 가장 가까운 대여소는 {nearest_distance} 거리입니다."
        return f"반경 500m 내 따릉이 대여소 {format_count_phrase(count)}이 있습니다."

    if key == "ev-charger":
        fast, slow = ev_charger_counts(summary)
        if fast or slow:
            return f"반경 1km 내 충전소 {format_count_phrase(count)}이 있습니다. 급속 {fast:,}기, 완속 {slow:,}기를 이용할 수 있습니다."
        return f"반경 1km 내 전기차 충전소 {format_count_phrase(count)}이 있습니다."

    if key == "cctv":
        subtype_text = subtype_sentence(summary, unit="개", limit=2)
        if subtype_text:
            return f"반경 {radius} 내 CCTV {format_count_phrase(count, '개')}가 확인됩니다. {subtype_text}가 포함됩니다."
        return f"반경 {radius} 내 CCTV {format_count_phrase(count, '개')}가 확인됩니다."

    if key == "fire-station":
        _, nearest_distance = nearest_name_and_distance(summary)
        if nearest_distance:
            return f"반경 {radius} 내 119안전센터 및 구조대가 {format_count_phrase(count)} 있습니다. 가장 가까운 안전센터는 {nearest_distance} 거리입니다."
        return f"반경 {radius} 내 119안전센터 및 구조대가 {format_count_phrase(count)} 있습니다."

    if key == "hospital":
        subtype_text = subtype_sentence(summary, unit="곳", limit=2)
        if subtype_text:
            return f"반경 {radius} 내 병원 {format_count_phrase(count)}이 있습니다. {subtype_text} 등 다양한 진료과를 이용할 수 있습니다."
        return f"반경 {radius} 내 병원 {format_count_phrase(count)}이 있습니다."

    if key == "pharmacy":
        labels = pharmacy_operating_labels(summary)
        if labels:
            return f"반경 {radius} 내 약국 {format_count_phrase(count)}이 있습니다. {'·'.join(labels)} 운영 약국이 확인됩니다."
        return f"반경 {radius} 내 약국 {format_count_phrase(count)}이 있습니다."

    if key == "general-hospital":
        nearest_name, nearest_distance = nearest_name_and_distance(summary)
        if nearest_name and nearest_distance:
            return f"반경 {radius} 내 종합병원 {format_count_phrase(count)}이 있습니다. 가장 가까운 종합병원은 {nearest_name}으로 {nearest_distance} 거리입니다."
        return f"반경 {radius} 내 종합병원 {format_count_phrase(count)}이 있습니다."

    if key == "emergency-room":
        nearest_name, nearest_distance = nearest_name_and_distance(summary)
        if nearest_name and nearest_distance:
            return f"반경 {radius} 내 응급실 {format_count_phrase(count)}이 있습니다. 가장 가까운 응급실은 {nearest_name}으로 {nearest_distance} 거리입니다."
        return f"반경 {radius} 내 응급실 {format_count_phrase(count)}이 있습니다."

    if key == "school-environment":
        name = assigned_elementary_name(summary)
        distance = format_distance_m(
            summary.get("assigned_elementary_distance_m")
            or summary.get("assigned_distance")
            or (summary.get("nearest_poi") or {}).get("distance")
        )
        if name and distance:
            return f"대표 배정 초등학교는 {name}입니다. 대표 좌표 기준 약 {distance} 거리에 위치합니다."
        if name:
            return f"대표 배정 초등학교는 {name}입니다."
        return "대표 배정 초등학교 정보를 확인 중입니다."

    if key == "academy":
        subtype_text = subtype_sentence(summary, unit="곳", limit=2)
        if subtype_text:
            return f"반경 {radius} 내 학원 {format_count_phrase(count)}이 있습니다. {subtype_text} 비중이 높습니다."
        return f"반경 {radius} 내 학원 {format_count_phrase(count)}이 있습니다."

    if key == "culture":
        subtype_text = subtype_sentence(
            summary,
            unit="곳",
            include=["공연", "행사", "전시", "관람", "체험"],
            limit=2,
        )
        if subtype_text:
            return f"반경 {radius} 내 문화시설 {format_count_phrase(count)}이 있습니다. {subtype_text}을 이용할 수 있습니다."
        return f"반경 {radius} 내 문화시설 {format_count_phrase(count)}이 있습니다."

    if key == "park":
        nearest_name, nearest_distance = nearest_name_and_distance(summary)
        if count <= 0:
            return f"반경 {radius} 내 확인된 공원 데이터가 아직 없습니다."
        if nearest_name and nearest_distance:
            return f"반경 {radius} 내 공원 {format_count_phrase(count)}이 있습니다. 가장 가까운 공원은 {nearest_name}으로 {nearest_distance} 거리입니다."
        return f"반경 {radius} 내 공원 {format_count_phrase(count)}이 있습니다."

    if key == "hangang":
        nearest_name, _ = nearest_name_and_distance(summary)
        if nearest_name:
            return f"가장 가까운 한강공원은 {hangang_park_name(nearest_name)}입니다."
        return "가까운 한강공원 접근 정보를 확인합니다."

    if key == "nightlife":
        if count <= 0:
            return f"반경 {radius} 내 확인된 유흥주점 정보가 없습니다."
        return f"반경 {radius} 내 유흥주점 {format_count_phrase(count)}이 확인됩니다."

    if key == "cafe":
        # Card is franchise-only (matches the franchise_total_500m metric).
        if count <= 0:
            return f"반경 {radius} 내 확인된 주요 카페 프랜차이즈가 없습니다."
        cafe_names = summarize_names(summary.get("pois", []), 2)
        if cafe_names:
            return f"반경 {radius} 내 주요 카페 프랜차이즈 {format_count_phrase(count)}이 있습니다. {compact_example_text(cafe_names)} 등을 이용할 수 있습니다."
        return f"반경 {radius} 내 주요 카페 프랜차이즈 {format_count_phrase(count)}이 있습니다."

    names = summarize_names(summary.get("pois", []), 2)
    label = clean_evidence_label(summary.get("label", "생활시설"))
    if names and count > len(names):
        subject = compact_example_text(names)
        return f"반경 {radius} 내 {label} {format_count_phrase(count)}이 있습니다. {subject} 등을 이용할 수 있습니다."

    return f"반경 {radius} 내 {label} {format_count_phrase(count)}이 있습니다."


def enhance_category_summaries(category_summaries):
    # List item icons are intentionally conservative.
    # Card header and nearest-POI rows may use icons, but generic scroll lists should not.
    # Hangang is the only list-level exception requested for visual consistency.
    list_icon_keys = set()

    for summary in category_summaries:
        key = summary.get("key")
        score = normalized_summary_score(summary)
        grade, grade_text = grade_from_score(score)
        summary["score"] = score
        summary["score_class"] = score_class_from_score(score)
        summary["grade"] = grade
        summary["grade_text"] = grade_text
        summary["description"] = build_category_evidence(summary)
        summary["nearest_icon"] = NEAREST_ICON_BY_CATEGORY.get(key, "📍")

        if key in list_icon_keys:
            icon = NEAREST_ICON_BY_CATEGORY.get(key, "")
            for poi in summary.get("pois", []) or []:
                label = clean_text(poi.get("label", ""))
                clean_label = compact_label(label)
                if icon and clean_label:
                    poi["label"] = f"{icon} {clean_label}"

        if key == "cctv":
            # Nearest icon should match the nearest CCTV's subtype (same icon as
            # its subtype chip), not the generic category shield.
            nearest_subtype = (summary.get("nearest_poi") or {}).get("subtype") or "기타"
            summary["nearest_icon"] = CCTV_ICON_BY_SUBTYPE.get(
                nearest_subtype, CCTV_ICON_BY_SUBTYPE["기타"]
            )

            for chip in summary.get("subtype_chips", []) or []:
                name = chip.get("name") or chip.get("display") or "기타"
                icon = CCTV_ICON_BY_SUBTYPE.get(name, CCTV_ICON_BY_SUBTYPE["기타"])
                display = compact_label(chip.get("display") or name)
                chip["display"] = f"{icon} {display}"

            for poi in summary.get("pois", []) or []:
                # Keep CCTV list rows text-only. Subtype context is already represented by chips;
                # injecting display_icon here caused repeated shield icons in the result card.
                poi["label"] = compact_label(poi.get("label") or poi.get("name") or "")
                poi.pop("display_icon", None)

        nearest = summary.get("nearest_poi") or {}
        if nearest.get("label"):
            nearest["label"] = (
                hangang_park_name(nearest.get("label"))
                if key == "hangang"
                else compact_nearest_label(nearest.get("label"))
            )

    return category_summaries


def summary_strength_score(summary):
    percentile = parse_optional_float(summary.get("seoul_percentile"))
    if percentile is not None:
        return percentile_score_value(percentile)

    score = summary.get("score")
    if isinstance(score, str) and not score.strip().replace(".", "", 1).isdigit():
        return None

    value = parse_optional_float(score)
    if value is None:
        return None

    return max(0, min(100, value))


def build_score_based_insight(apartment, category_summaries, fallback):
    candidates = []

    for summary in category_summaries:
        if summary.get("key") in {"nightlife", "school-environment"}:
            continue

        score = summary_strength_score(summary)
        if score is None:
            continue

        candidates.append((score, summary))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    top_summaries = [summary for _, summary in candidates[:3]]

    if not top_summaries:
        return fallback

    features = []
    for summary in top_summaries:
        score = summary_strength_score(summary) or 0
        suffix = "우수" if score >= 60 else "상대 강점"
        label = summary.get("label", "")
        features.append({
            "icon": NEAREST_ICON_BY_CATEGORY.get(summary.get("key"), "•"),
            "label": f"{compact_label(label)} {suffix}",
            "reason": summary.get("description", ""),
            "tone": "good",
        })

    labels = [
        feature["label"].replace(" 우수", "").replace(" 상대 강점", "")
        for feature in features
    ]
    fallback = fallback or {}
    fallback["summary"] = f"{apartment.get('name', '이 단지')}는 " + ", ".join(labels) + " 접근성이 강점입니다."
    fallback["feature_tags"] = features
    fallback["strengths"] = [
        {
            "icon": feature["icon"],
            "title": feature["label"],
            "body": feature["reason"],
            "tone": "good",
        }
        for feature in features
    ]
    return fallback


def format_manwon(value):
    number = parse_optional_float(value)

    if number is None:
        return ""

    number = int(round(number))
    if number >= 10000:
        return f"{number / 10000:.1f}억"

    return f"{number:,}만원"


app.jinja_env.filters["format_manwon"] = format_manwon


def format_thousands(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value


app.jinja_env.filters["thousands"] = format_thousands


def apply_result_percentile_labels(category_summaries, preference_tags, domain_summaries, district):
    def apply_summary_labels(summary):
        if summary.get("display_percentile") is False:
            summary["seoul_percentile"] = None
            summary["gu_percentile"] = None
            summary["seoul_percentile_label"] = None
            summary["gu_percentile_label"] = None
            return

        summary["seoul_percentile_label"] = format_percentile_label(
            summary.get("seoul_percentile"),
            "서울",
        )
        summary["gu_percentile_label"] = format_percentile_label(
            summary.get("gu_percentile"),
            district,
        )

    for summary in category_summaries:
        apply_summary_labels(summary)

    for domain in domain_summaries:
        for summary in domain.get("categories", []):
            apply_summary_labels(summary)

    for tag in preference_tags:
        if tag.get("display_percentile") is False:
            tag["seoul_percentile"] = None
            tag["gu_percentile"] = None
            tag["seoul_percentile_label"] = None
            tag["gu_percentile_label"] = None
            continue

        tag["seoul_percentile_label"] = format_percentile_label(
            tag.get("seoul_percentile"),
            "서울",
        )
        tag["gu_percentile_label"] = format_percentile_label(
            tag.get("gu_percentile"),
            tag.get("district") or district,
        )


def parse_optional_float(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() in ["nan", "none", "null"]:
        return None

    try:
        return float(text)
    except Exception:
        return None


def format_debug_value(value, metric=""):
    number = parse_optional_float(value)

    if number is None:
        # 숫자가 아니면(학교명 등 텍스트) 원문 그대로 표시
        return clean_text(value)

    if "distance" in str(metric).lower():
        return format_distance_m(number)

    if number.is_integer():
        return f"{int(number):,}"

    return f"{number:,.2f}".rstrip("0").rstrip(".")


def format_debug_percentile_value(value):
    number = parse_optional_float(value)

    if number is None:
        return ""

    return f"{number:.2f}"


def read_baseline_csv_for_debug(path):
    field_limit = sys.maxsize

    while True:
        try:
            csv.field_size_limit(field_limit)
            break
        except OverflowError:
            field_limit = int(field_limit / 10)

    encodings = ["utf-8-sig", "utf-8", "cp949"]

    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            return []

    return []


def get_latest_validation_report():
    validation_dir = Path("data") / "validation"

    if not validation_dir.exists():
        return None

    reports = sorted(
        validation_dir.glob("validation_report_v3_6_*.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not reports:
        return None

    return reports[0].name


def build_ranking_debug_options():
    options = []

    for key, config in BASELINE_METRIC_CONFIG.items():
        if not config.get("ranking_enabled", True):
            continue

        metric = config.get("primary_metric", "")
        label = config.get("label") or key
        display_label = config.get("display_metric_label") or metric

        options.append({
            "key": key,
            "label": label,
            "metric": metric,
            "display_label": display_label,
            "direction": config.get("metrics", {}).get(metric, ""),
        })

    return options


def get_admin_ranking_rows(config, sort_key, limit, bottom, gu_filter, dong_filter, query):
    rows = read_baseline_csv_for_debug(config.get("path", ""))
    metric = config.get("primary_metric")
    percentile_column = config.get("primary_percentile_column")
    score_column = config.get("primary_score_column")
    direction = config.get("metrics", {}).get(metric)
    debug_columns = config.get("debug_columns", [])

    filtered = []

    for row in rows:
        name = str(row.get("name") or row.get("apartment_name") or "").strip()
        gu = str(row.get("gu") or "").strip()
        dong = str(row.get("dong") or "").strip()

        if gu_filter and gu_filter != gu:
            continue

        if dong_filter and dong_filter != dong:
            continue

        if query and query not in name:
            continue

        raw_value = row.get(metric, "")
        percentile_value = row.get(percentile_column, "")
        score_value = row.get(score_column, "")

        filtered.append({
            "name": name,
            "gu": gu,
            "dong": dong,
            "raw_value": raw_value,
            "raw_display": format_debug_value(raw_value, metric),
            "percentile": percentile_value,
            "percentile_display": format_debug_percentile_value(percentile_value),
            "score": score_value,
            "score_display": format_debug_percentile_value(score_value),
            "raw_number": parse_optional_float(raw_value),
            "percentile_number": parse_optional_float(percentile_value),
            "score_number": parse_optional_float(score_value),
            "debug_values": [
                format_debug_value(row.get(column, ""), column)
                for column in debug_columns
            ],
        })

    def raw_direction_value(row):
        value = row.get("raw_number")

        if value is None:
            return 0

        if direction == LOWER_BETTER:
            return value

        if direction == HIGHER_BETTER:
            return -value

        return value

    def row_name(row):
        return row.get("name") or ""

    def sort_value(row):
        if sort_key == "percentile_asc":
            percentile = row.get("percentile_number")
            raw = row.get("raw_number")
            return (
                percentile is None or raw is None,
                percentile if percentile is not None else 0,
                raw_direction_value(row),
                row_name(row),
            )

        if sort_key == "raw_desc":
            raw = row.get("raw_number")
            score = row.get("score_number")
            return (
                raw is None,
                -raw if raw is not None else 0,
                score is None,
                -score if score is not None else 0,
                row_name(row),
            )

        if sort_key == "raw_asc":
            raw = row.get("raw_number")
            score = row.get("score_number")
            return (
                raw is None,
                raw if raw is not None else 0,
                score is None,
                -score if score is not None else 0,
                row_name(row),
            )

        score = row.get("score_number")
        raw = row.get("raw_number")
        return (
            score is None or raw is None,
            -score if score is not None else 0,
            raw_direction_value(row),
            row_name(row),
        )

    sorted_rows = sorted(filtered, key=sort_value)

    for index, row in enumerate(sorted_rows, start=1):
        row["rank"] = index

    if bottom:
        visible_rows = sorted_rows[-limit:]
    else:
        visible_rows = sorted_rows[:limit]

    gu_options = sorted({
        str(row.get("gu") or "").strip()
        for row in rows
        if str(row.get("gu") or "").strip()
    })

    dong_options = sorted({
        str(row.get("dong") or "").strip()
        for row in rows
        if str(row.get("dong") or "").strip()
        and (not gu_filter or str(row.get("gu") or "").strip() == gu_filter)
    })

    return {
        "rows": visible_rows,
        "total_count": len(rows),
        "filtered_count": len(filtered),
        "gu_options": gu_options,
        "dong_options": dong_options,
    }


def _build_apartment_view(apt):
    return {
        "name": apt.get("name"),
        "district": apt.get("gu"),
        "dong": apt.get("dong"),
        "road_address": apt.get("road_address"),
        "lat": apt.get("lat"),
        "lng": apt.get("lng"),
        "household_count": apt.get("household_count"),
        "parking_count": apt.get("parking_count"),
        "approval_date": apt.get("approval_date"),
        "builder": apt.get("builder"),
        "area_under_60": apt.get("area_under_60"),
        "area_60_85": apt.get("area_60_85"),
        "area_85_135": apt.get("area_85_135"),
        "area_over_135": apt.get("area_over_135"),
        "scores": {},
        "pois": [],
    }


def get_apartment(name, gu=None, dong=None):
    """Resolve an apartment by identity.

    Apartment names are NOT unique in Seoul (e.g. 신동아아파트 x3), so a bare
    substring + first-match lookup silently returns the wrong complex. Resolve
    with: exact name match first, then disambiguate by gu/dong when provided.
    Substring matching is kept only as a last-resort fallback for free-text
    queries that have no exact hit.
    """
    name_norm = clean_text(name)
    gu_norm = clean_text(gu) if gu else ""
    dong_norm = clean_text(dong) if dong else ""

    if not name_norm:
        return None

    exact = [
        apt for apt in apartment_data
        if clean_text(apt.get("name", "")) == name_norm
    ]

    candidates = exact

    # Fallback: substring match (legacy behaviour) only when nothing matched
    # the name exactly — preserves free-text search while killing the
    # "first apartment that happens to contain this substring" bug.
    if not candidates:
        candidates = [
            apt for apt in apartment_data
            if name_norm in clean_text(apt.get("name", ""))
        ]

    if not candidates:
        return None

    # Disambiguate collisions by gu, then dong (skip a filter if it empties).
    if gu_norm:
        filtered = [
            apt for apt in candidates
            if clean_text(apt.get("gu", "")) == gu_norm
        ]
        if filtered:
            candidates = filtered

    if dong_norm:
        filtered = [
            apt for apt in candidates
            if clean_text(apt.get("dong", "")) == dong_norm
        ]
        if filtered:
            candidates = filtered

    return _build_apartment_view(candidates[0])


def get_school_zone_for_apartment(apartment):
    for row in school_zone_baseline_data:
        if (
            row.get("name") == apartment.get("name")
            and row.get("gu") == apartment.get("district")
            and row.get("dong") == apartment.get("dong")
        ):
            return row

    return None


def format_number(value):
    try:
        if value is None or value == "":
            return ""

        value = str(value).strip()

        if value.lower() == "nan":
            return ""

        return f"{int(float(value)):,}"
    except:
        return ""


def get_year_from_date(value):
    try:
        value = str(value).strip()

        if not value or value.lower() == "nan":
            return ""

        # 2014-09-26 00:00:00 형태
        if "-" in value:
            parts = value.split(" ")[0].split("-")
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[1]}"

        # 20140926.0 형태
        if value.endswith(".0"):
            value = value[:-2]

        # 20140926 형태
        if len(value) >= 6 and value.isdigit():
            return f"{value[:4]}.{value[4:6]}"

        # 2014 형태
        if len(value) == 4 and value.isdigit():
            return value

        return value

    except:
        return ""


def build_area_mix_text(apartment):
    small = format_number(apartment.get("area_under_60"))
    mid = format_number(apartment.get("area_60_85"))
    large = format_number(apartment.get("area_85_135"))
    xlarge = format_number(apartment.get("area_over_135"))

    parts = [
        f"60㎡ 이하 {small or 0}세대",
        f"60~85㎡ {mid or 0}세대",
        f"85~135㎡ {large or 0}세대",
        f"135㎡ 초과 {xlarge or 0}세대",
    ]

    return " / ".join(parts)


def build_complex_info(apartment, school_zone, category_summaries):

    nearest_subway = None

    for summary in category_summaries:
        if summary.get("key") == "subway":
            nearest_subway = summary.get("nearest_poi")
            break

    household_count = format_number(
        apartment.get("household_count")
    )

    parking_count = apartment.get("parking_count")
    household_raw = apartment.get("household_count")

    parking_per_household = ""

    try:
        if parking_count and household_raw:
            parking_per_household = round(
                float(parking_count) / float(household_raw),
                2
            )
    except:
        parking_per_household = ""

    info = {
        "school": "",
        "households": "",
        "approval_year": "",
        "nearest_subway": "",
        "builder": "",
        "parking": "",
        "area_mix": "",
    }

    if school_zone:
        zone_name = school_zone.get(
            "primary_school_zone_name",
            ""
        )

        info["school"] = zone_name.replace(
            "통학구역",
            ""
        )

    if household_count:
        info["households"] = f"{household_count}세대"

    approval_year = get_year_from_date(
        apartment.get("approval_date")
    )

    if approval_year:
        info["approval_year"] = approval_year

    if nearest_subway:
        subway_name = nearest_subway.get("label", "")
        subway_distance = nearest_subway.get("distance", "")

        clean_subway_name = subway_name.replace("🚇", "").strip()

        info["nearest_subway"] = (
            f"🚇 {clean_subway_name} (최근접, {format_distance_m(subway_distance)})"
        )

    builder = apartment.get("builder", "")

    if builder:
        info["builder"] = builder

    if parking_per_household:
        info["parking"] = f"세대당 {parking_per_household}대"

    info["area_mix"] = build_area_mix_text(apartment)

    return info


def parse_baseline_items(row, column, *, float_distance=False):
    """Parse a baseline `*_items_json` cell into a distance-sorted list.

    Centralises the json-parse + float/None guard + distance sort that was
    copy-pasted into every build_X_info (and twice in subway, 5x in medical).
    `float_distance` selects the exact original sort key so output stays
    byte-identical: most categories used int(distance), while subway/medical
    used int(float(distance)) — and those differ for values like "123.0"
    (int("123.0") raises, leaving the list unsorted).
    """
    raw = row.get(column, "[]")
    if raw is None or isinstance(raw, float):
        raw = "[]"

    try:
        items = json.loads(str(raw))
    except Exception:
        items = []

    try:
        if float_distance:
            items = sorted(items, key=lambda item: int(float(item.get("distance", 999999))))
        else:
            items = sorted(items, key=lambda item: int(item.get("distance", 999999)))
    except Exception:
        pass

    return items


def build_simple_map_pois(info, *, category, icon, source, label_fn, subtype_fn):
    """Map markers for the 'standard' POI categories.

    Centralises the shared, fragile boilerplate — the lat/lng float guard and
    the marker dict shape — that was identical across bike/hangang/commercial/
    academy/culture/fire/shopping/nightlife. The genuinely per-category bits
    (label extraction, subtype) stay explicit as small callables in each
    caller, so there is no `if category == ...` branching here and output is
    byte-identical. Excludes subway/bus/medical/ev (meaningfully different
    marker logic).
    """
    if not info:
        return []

    map_pois = []
    for item in info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = label_fn(item)
        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": category,
            "label": f"{icon} {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype_fn(item),
            "source": source,
        })

    return map_pois


def build_count_chips(chip_sources):
    """Build [{name, count}] chips from (name, count) pairs, keeping only
    positive counts. Centralises the int(float())-guarded count loop that was
    duplicated across the count-based chip categories (bus, hangang,
    commercial, shopping, nightlife, academy, culture, fire)."""
    chips = []
    for chip_name, chip_count in chip_sources:
        try:
            chip_count = int(float(chip_count))
        except Exception:
            chip_count = 0

        if chip_count > 0:
            chips.append({
                "name": chip_name,
                "count": chip_count,
            })

    return chips


def build_subway_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(subway_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items = parse_baseline_items(row, "subway_items_json", float_distance=True)
    items_500m = parse_baseline_items(row, "subway_items_500m_json", float_distance=True)

    return {
        "nearest_name": clean_text(row.get("nearest_subway_name") or row.get("nearest_subway", "")),
        "nearest_label": clean_text(row.get("nearest_subway") or row.get("nearest_subway_name", "")),
        "nearest_distance": clean_text(row.get("nearest_subway_distance") or row.get("subway_distance", "")),
        "nearest_lines": clean_text(row.get("nearest_subway_lines", "")),
        "station_count_500m": to_int(row.get("subway_station_count_500m"), 0),
        "station_count_800m": to_int(row.get("subway_station_count_800m"), 0),
        "station_count_1km": to_int(row.get("subway_station_count_1km"), 0),
        "line_count_500m": to_int(row.get("subway_line_count_500m"), 0),
        "line_count_1km": to_int(row.get("subway_line_count_1km"), 0),
        "transfer_station_count_500m": to_int(row.get("transfer_station_count_500m"), 0),
        "transfer_station_count_1km": to_int(row.get("transfer_station_count_1km"), 0),
        "nearest_transfer_station": clean_text(row.get("nearest_transfer_station", "")),
        "nearest_transfer_distance": clean_text(row.get("nearest_transfer_distance", "")),
        "seoul_percentile": get_baseline_percentile(row, "subway_line_count_500m_seoul_percentile"),
        "gu_percentile": None,
        "items": items,
        "items_500m": items_500m,
    }


def build_subway_map_pois(subway_info):
    if not subway_info:
        return []

    map_pois = []

    for item in subway_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = clean_text(item.get("label") or item.get("name") or "지하철역")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "subway",
            "label": f"🚇 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": item.get("subtype") or "지하철",
            "subtypes": item.get("subtypes") or [],
            "source": "서울열린데이터광장",
        })

    return map_pois


def build_subway_category_summary(subway_info):
    if not subway_info:
        return None

    items = subway_info.get("items_500m") or []
    count_500m = to_int(subway_info.get("station_count_500m"), 0)
    line_count_500m = to_int(subway_info.get("line_count_500m"), 0)
    seoul_percentile = subway_info.get("seoul_percentile")
    nearest_name = subway_info.get("nearest_name", "")
    nearest_lines = subway_info.get("nearest_lines", "")
    nearest_label = nearest_name

    if nearest_name and nearest_lines:
        nearest_label = f"{nearest_name}역 · {nearest_lines}"
    elif subway_info.get("nearest_label"):
        nearest_label = subway_info.get("nearest_label")

    subtype_chips = get_subtype_chips_from_items(items, "subway-chip")

    transfer_count = to_int(subway_info.get("transfer_station_count_500m"), 0)
    if transfer_count > 0:
        subtype_chips.append({
            "name": "환승역",
            "display": "환승역",
            "count": transfer_count,
            "style": "subway-chip subway-chip-환승역",
            "nearest_distance": subway_info.get("nearest_transfer_distance"),
        })

    return {
        "key": "subway",
        "label": "🚇 지하철역",
        "domain": "transport",
        "domain_label": "🚇 교통",
        "score": percentile_score_value(seoul_percentile),
        "score_class": percentile_score_class(seoul_percentile),
        "description": "서울시 역사마스터 기준 지하철역, 호선, 환승역 접근성입니다.",
        "radius": 500,
        "count": count_500m,
        "line_count_500m": line_count_500m,
        "seoul_percentile": seoul_percentile,
        "gu_percentile": subway_info.get("gu_percentile"),
        "source": "서울열린데이터광장",
        "nearest_poi": {
            "label": f"🚇 {nearest_label}",
            "distance": subway_info.get("nearest_distance"),
        } if nearest_label else None,
        "subtype_chips": subtype_chips,
        "pois": items,
        "empty": "주변 지하철역 공공데이터가 없습니다.",
        "is_subway_master_summary": True,
    }


def apply_subway_baseline_to_ui(category_summaries, preference_tags, domain_summaries, subway_info, apartment):
    old_subway_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "subway"),
        None
    )
    subway_summary = build_subway_category_summary(subway_info)

    if not subway_info or not subway_summary:
        return category_summaries, preference_tags, domain_summaries

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "subway"
    ]
    category_summaries.insert(0, subway_summary)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "subway"
    ]
    preference_tags.append({
        "key": "subway",
        "label": "🚇 지하철역",
        "value": old_subway_tag.get("value", 4) if old_subway_tag else 4,
        "level": old_subway_tag.get("level", "중요") if old_subway_tag else "중요",
        "level_class": old_subway_tag.get("level_class", "level-high") if old_subway_tag else "level-high",
        "radius": 500,
        "count": subway_info.get("station_count_500m", 0),
        "percentile": None,
        "seoul_percentile": subway_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": subway_summary.get("nearest_poi", {}).get("label", ""),
        "nearest_distance": subway_info.get("nearest_distance", None),
    })

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "subway"
        ]

    transport_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "transport"
            or "교통" in str(domain.get("label", ""))
        ),
        None
    )

    if transport_domain:
        transport_domain["categories"].insert(0, subway_summary)

    return category_summaries, preference_tags, domain_summaries


def build_bus_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(bus_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    route_preview = row.get(
        "available_bus_routes",
        ""
    )

    if route_preview is None:
        route_preview = ""

    if isinstance(route_preview, float):
        route_preview = ""

    route_preview = str(route_preview).strip()

    if len(route_preview) > 60:
        route_preview = (
            route_preview[:60] + "..."
        )

    bus_items = parse_baseline_items(row, "bus_items_json")

    for item in bus_items:
        item["label"] = str(
            item.get("label", "")
        ).replace("?", "·")

    type_chips = []

    chip_sources = [
        ("간선", row.get("main_bus_count", 0)),
        ("지선", row.get("local_bus_count", 0)),
        ("광역", row.get("express_bus_count", 0)),
        ("마을", row.get("village_bus_count", 0)),
        ("심야", row.get("night_bus_count", 0)),
        ("공항", row.get("airport_bus_count", 0)),
    ]

    type_chips = build_count_chips(chip_sources)

    return {
        "stop_count_500m":
            row.get(
                "bus_stop_count_500m",
                0
            ),
        "nearest_stop":
            str(
                row.get(
                    "nearest_bus_stop",
                    ""
                )
            ).replace("?", "·"),

        "nearest_distance":
            row.get(
                "nearest_bus_stop_distance",
                ""
            ),

        "route_count":
            row.get(
                "bus_route_count",
                0
            ),

        "main_count":
            row.get(
                "main_bus_count",
                0
            ),

        "local_count":
            row.get(
                "local_bus_count",
                0
            ),

        "express_count":
            row.get(
                "express_bus_count",
                0
            ),

        "night_count":
            row.get(
                "night_bus_count",
                0
            ),

        "village_count":
            row.get(
                "village_bus_count",
                0
            ),

        "airport_count":
            row.get(
                "airport_bus_count",
                0
            ),

        "routes":
            route_preview,

        "items": bus_items,
        
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "bus_route_count_seoul_percentile"),
    }

    return None


BUS_TYPE_LABELS = {
    "main": "간선",
    "local": "지선",
    "express": "광역",
    "night": "심야",
    "village": "마을",
    "airport": "공항",
    "unknown": "기타",
}


def to_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def clean_text(value):
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in ["nan", "none", "null"]:
        return ""

    return text


def dedupe_tag_text(value):
    text = clean_text(value)
    if not text:
        return ""

    parts = []
    for part in text.replace("/", "·").replace(",", "·").split("·"):
        tag = part.strip()
        if tag and tag not in parts:
            parts.append(tag)

    return " · ".join(parts)


def classify_bus_route_type(route_name):
    route = str(route_name or "").strip().upper()

    if not route:
        return "unknown"

    if route.startswith("N"):
        return "night"

    if route.startswith("M") or route.startswith("G"):
        return "express"

    if any("가" <= ch <= "힣" for ch in route):
        return "village"

    if route.isdigit():
        if route.startswith("6"):
            return "airport"

        if len(route) == 4:
            return "local"

        if len(route) == 3:
            return "main"

        if route.startswith("9"):
            return "express"

    return "unknown"


def build_bus_route_map():
    route_map = {}

    for route in bus_route_data:
        node_id = route.get("node_id")
        route_name = route.get("route_name", "")

        if not node_id or not route_name:
            continue

        route_map.setdefault(node_id, set()).add(str(route_name).strip())

    return route_map


def get_bus_routes_for_stop(stop, route_map):
    node_id = stop.get("node_id")

    if not node_id:
        return []

    return sorted(route_map.get(node_id, []))


BUS_SUBTYPE_PRIORITY = ["광역", "간선", "지선", "마을", "심야", "공항", "기타"]


def get_bus_subtypes(routes):
    """Every route type present at a stop, ordered by priority (deduped),
    e.g. ["간선", "지선", "심야"]. Used for map filtering so a stop is matched
    by EVERY type it serves, not just its primary type."""
    subtype_set = {
        BUS_TYPE_LABELS.get(classify_bus_route_type(route), "기타")
        for route in routes
    }
    return [subtype for subtype in BUS_SUBTYPE_PRIORITY if subtype in subtype_set]


def get_primary_bus_subtype(routes):
    subtypes = get_bus_subtypes(routes)
    return subtypes[0] if subtypes else "기타"


def build_bus_map_pois(apartment):
    route_map = build_bus_route_map()
    bus_pois = []

    for stop in bus_stop_data:
        try:
            distance = get_distance_m(
                apartment["lat"],
                apartment["lng"],
                stop["lat"],
                stop["lng"],
            )
        except Exception:
            continue

        if distance > 500:
            continue

        routes = get_bus_routes_for_stop(stop, route_map)
        subtypes = get_bus_subtypes(routes)
        subtype = subtypes[0] if subtypes else "기타"
        route_preview = ", ".join(routes[:6])
        stop_name = str(stop.get("name", "버스정류장")).replace("?", "·")

        if route_preview:
            label = f"🚍 {stop_name} · {route_preview}"
        else:
            label = f"🚍 {stop_name}"

        bus_pois.append({
            "lat": stop.get("lat"),
            "lng": stop.get("lng"),
            "category": "bus-baseline",
            "label": label,
            "name": stop_name,
            "distance": distance,
            "subtype": subtype,
            "subtypes": subtypes,
            "source": "서울시 버스 데이터",
        })

    return sorted(
        bus_pois,
        key=lambda poi: poi.get("distance", 999999)
    )


def build_bus_category_summary(bus_info):
    if not bus_info:
        return None
    seoul_percentile = bus_info.get("seoul_percentile")

    return {
        "key": "bus-baseline",
        "label": "🚍 버스 접근성",
        "domain_label": "🚇 교통",
        "score": f"{bus_info.get('route_count', 0)}개",
        "score_class": "score-normal",
        "score": percentile_score_value(seoul_percentile),
        "score_class": percentile_score_class(seoul_percentile),
        "description": "반경 500m 기준 버스 정류장 및 이용 가능 노선 정보입니다.",
        "radius": 500,
        "count": bus_info.get("stop_count_500m", 0),
        "seoul_percentile": seoul_percentile,
        "gu_percentile": None,
        "source": "서울시 버스 데이터",
        "nearest_poi": {
            "label": f"🚍 {bus_info.get('nearest_stop', '')}",
            "distance": bus_info.get("nearest_distance", ""),
        },
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"bus-chip bus-chip-{chip.get('name')}",
            }
            for chip in bus_info.get("type_chips", [])
        ],
        "pois": bus_info.get("items", []),
        "empty": "반경 내 확인된 버스 노선 정보가 없습니다.",
        "is_bus_summary": True,
    }


def insert_after_category(summaries, target_key, new_summary):
    if not new_summary:
        return summaries

    cleaned = [
        summary for summary in summaries
        if summary.get("key") not in ["bus", "bus-baseline"]
    ]

    result = []
    inserted = False

    for summary in cleaned:
        result.append(summary)

        if summary.get("key") == target_key:
            result.append(new_summary)
            inserted = True

    if not inserted:
        result.append(new_summary)

    return result


def apply_baseline_category_to_ui(
    category_summaries,
    preference_tags,
    domain_summaries,
    *,
    key,
    summary,
    info,
    new_tag,
    domain_key,
    domain_template,
    anchor_key=None,
    insert_position="after",
    poi_count=None,
    poi_count_mode="increment",
):
    """Shared list-surgery for the per-category apply_X_baseline_to_ui family.

    Removes any existing entry for `key` from category_summaries,
    preference_tags and every domain's categories; then, when info+summary are
    present, inserts the summary relative to `anchor_key` (after every match,
    or before the first match when insert_position="before"; appends when the
    anchor is absent or None), appends the prebuilt preference tag, and merges
    the summary into its domain — creating the domain from `domain_template`
    when missing. poi_count_mode is "increment" (add to existing) or "set"
    (replace). Behaviour matches the hand-written functions; pinned by
    tests/snapshot_result.py.
    """
    def insert(items):
        if not anchor_key:
            return list(items) + [summary]
        result = []
        inserted = False
        if insert_position == "before":
            for item in items:
                if item.get("key") == anchor_key and not inserted:
                    result.append(summary)
                    inserted = True
                result.append(item)
        else:
            for item in items:
                result.append(item)
                if item.get("key") == anchor_key:
                    result.append(summary)
                    inserted = True
        if not inserted:
            result.append(summary)
        return result

    category_summaries = [s for s in category_summaries if s.get("key") != key]
    preference_tags = [t for t in preference_tags if t.get("key") != key]
    for domain in domain_summaries:
        domain["categories"] = [
            s for s in domain.get("categories", []) if s.get("key") != key
        ]

    if not info or not summary:
        return category_summaries, preference_tags, domain_summaries

    category_summaries = insert(category_summaries)
    preference_tags.append(new_tag)

    domain = next(
        (d for d in domain_summaries if d.get("key") == domain_key),
        None,
    )

    if domain is not None:
        domain["categories"] = insert(domain.get("categories", []))
        if poi_count is not None:
            try:
                base = int(domain.get("poi_count", 0)) if poi_count_mode == "increment" else 0
                domain["poi_count"] = base + int(poi_count)
            except Exception:
                domain["poi_count"] = poi_count
    elif domain_template is not None:
        domain_summaries.append(domain_template)

    return category_summaries, preference_tags, domain_summaries


def apply_bus_baseline_to_ui(category_summaries, preference_tags, domain_summaries, bus_info, apartment):
    old_bus_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "bus"),
        None
    )

    bus_summary = build_bus_category_summary(bus_info)

    category_summaries = insert_after_category(
        category_summaries,
        "subway",
        bus_summary
    )

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") not in ["bus", "bus-baseline"]
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") not in ["bus", "bus-baseline"]
        ]

    if not bus_info or not bus_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "bus-baseline",
        "label": "🚍 버스접근성",
        "value": old_bus_tag.get("value", 3) if old_bus_tag else 3,
        "level": old_bus_tag.get("level", "보통") if old_bus_tag else "보통",
        "level_class": old_bus_tag.get("level_class", "level-normal") if old_bus_tag else "level-normal",
        "radius": 500,
        "count": bus_info.get("stop_count_500m", 0),
        "percentile": None,
        "seoul_percentile": bus_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🚍 {bus_info.get('nearest_stop', '')}",
        "nearest_distance": bus_info.get("nearest_distance", None),
    })

    transport_domain = next(
        (
            domain for domain in domain_summaries
            if any(
                category.get("key") == "subway"
                for category in domain.get("categories", [])
            )
        ),
        None
    )

    if transport_domain:
        transport_domain["categories"] = insert_after_category(
            transport_domain.get("categories", []),
            "subway",
            bus_summary
        )

        try:
            transport_domain["poi_count"] = int(bus_info.get("stop_count_500m", 0))
        except Exception:
            transport_domain["poi_count"] = bus_info.get("stop_count_500m", 0)

    return category_summaries, preference_tags, domain_summaries



def build_hangang_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(hangang_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    hangang_items = parse_baseline_items(row, "hangang_items_json")

    for item in hangang_items:
        item["label"] = item.get("park_name", "")

    chip_sources = [
        ("자전거", row.get("bike_count", 0)),
        ("운동시설", row.get("sports_count", 0)),
        ("수상/레저", row.get("water_leisure_count", 0)),
        ("캠핑", row.get("camping_count", 0)),
        ("문화/휴식", row.get("culture_rest_count", 0)),
        ("편의시설", row.get("convenience_count", 0)),
        ("접근시설", row.get("access_count", 0)),
    ]

    type_chips = []
    type_chips = build_count_chips(chip_sources)

    return {
        "hangang_count_3km": row.get("hangang_count_3km", 0),
        "nearest_name": clean_text(row.get("nearest_hangang_park", "")),
        "nearest_distance": clean_text(row.get("nearest_hangang_distance", "")),
        "nearest_facility_tags": clean_text(row.get("nearest_hangang_facility_tags", "")),
        "items": hangang_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "nearest_hangang_distance_seoul_percentile"),
    }

    return None

def build_hangang_map_pois(hangang_info):
    return build_simple_map_pois(
        hangang_info, category="hangang", icon="🌊",
        source="서울시 한강공원 시설현황",
        label_fn=lambda item: str(item.get("park_name") or item.get("label", "한강공원")).replace("🌊", "").strip(),
        subtype_fn=lambda item: item.get("subtype", "한강공원"),
    )


def build_hangang_category_summary(hangang_info):
    if not hangang_info:
        return None

    count = to_int(hangang_info.get("hangang_count_3km"), 0)
    nearest_name = hangang_info.get("nearest_name", "")

    return {
        "key": "hangang",
        "label": "🌊 한강공원",
        "domain": "rest",
        "domain_label": "☕ 휴식/여가",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 3km 기준 한강공원 접근성과 주요 시설 정보를 표시합니다.",
        "radius": 3000,
        "count": count,
        "seoul_percentile": hangang_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 한강공원 시설현황",
        "nearest_poi": {
            "label": nearest_name,
            "distance": hangang_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [],
        "pois": hangang_info.get("items", []),
        "empty": "반경 내 확인된 한강공원 정보가 없습니다.",
        "is_hangang_summary": True,
    }


def apply_hangang_baseline_to_ui(category_summaries, preference_tags, domain_summaries, hangang_info, apartment):
    old_hangang_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "hangang"),
        None
    )

    hangang_summary = build_hangang_category_summary(hangang_info)
    hi = hangang_info or {}
    count = hi.get("hangang_count_3km", 0)

    new_tag = {
        "key": "hangang",
        "label": "🌊 한강공원",
        "value": old_hangang_tag.get("value", 3) if old_hangang_tag else 3,
        "level": old_hangang_tag.get("level", "보통") if old_hangang_tag else "보통",
        "level_class": old_hangang_tag.get("level_class", "level-normal") if old_hangang_tag else "level-normal",
        "radius": 3000,
        "count": count,
        "percentile": None,
        "seoul_percentile": hi.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🌊 {hi.get('nearest_name', '')}" if hi.get("nearest_name") else "",
        "nearest_distance": hi.get("nearest_distance", None),
    }

    domain_template = {
        "key": "rest",
        "label": "☕ 휴식/여가",
        "description": "카페, 공원, 한강 등 휴식 요소",
        "initial_load": True,
        "category_count": 1,
        "poi_count": count,
        "categories": [hangang_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="hangang", summary=hangang_summary, info=hangang_info,
        new_tag=new_tag, domain_key="rest", domain_template=domain_template,
        anchor_key="park", poi_count=count, poi_count_mode="increment",
    )

def build_bike_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(bike_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    bike_items = parse_baseline_items(row, "bike_items_json")

    for item in bike_items:
        item["label"] = f"🚲 {str(item.get('label', '')).replace('🚲', '').strip()}"

    return {
        "station_count_500m": row.get("bike_station_count_500m", 0),
        "nearest_station": clean_text(row.get("nearest_bike_station", "")),
        "nearest_distance": clean_text(row.get("nearest_bike_station_distance", "")),
        "items": bike_items,
        "seoul_percentile": get_baseline_percentile(row, "bike_station_count_500m_seoul_percentile"),
    }

    return None

def build_bike_map_pois(bike_info):
    return build_simple_map_pois(
        bike_info, category="bike", icon="🚲",
        source="서울시 공공자전거 따릉이 대여소 마스터 정보",
        label_fn=lambda item: str(item.get("label", "따릉이 대여소")).replace("🚲", "").strip(),
        subtype_fn=lambda item: "따릉이",
    )


def build_bike_category_summary(bike_info):
    if not bike_info:
        return None

    count = to_int(bike_info.get("station_count_500m"), 0)
    nearest_name = bike_info.get("nearest_station", "")
    seoul_percentile = bike_info.get("seoul_percentile")

    return {
        "key": "bike",
        "label": "🚲 따릉이",
        "domain": "transport",
        "domain_label": "🚇 교통",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "score": percentile_score_value(seoul_percentile),
        "score_class": percentile_score_class(seoul_percentile),
        "description": "반경 500m 기준 서울시 공공자전거 따릉이 대여소 접근성입니다.",
        "radius": 500,
        "count": count,
        "seoul_percentile": seoul_percentile,
        "gu_percentile": None,
        "source": "서울시 따릉이 데이터",
        "nearest_poi": {
            "label": f"🚲 {nearest_name}",
            "distance": bike_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [],
        "pois": bike_info.get("items", []),
        "empty": "반경 내 확인된 따릉이 대여소 정보가 없습니다.",
        "is_bike_summary": True,
    }


def apply_bike_baseline_to_ui(category_summaries, preference_tags, domain_summaries, bike_info, apartment):
    old_bike_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "bike"),
        None
    )

    bike_summary = build_bike_category_summary(bike_info)
    bi = bike_info or {}
    count = bi.get("station_count_500m", 0)

    new_tag = {
        "key": "bike",
        "label": "🚲 따릉이",
        "value": old_bike_tag.get("value", 3) if old_bike_tag else 3,
        "level": old_bike_tag.get("level", "보통") if old_bike_tag else "보통",
        "level_class": old_bike_tag.get("level_class", "level-normal") if old_bike_tag else "level-normal",
        "radius": 500,
        "count": count,
        "percentile": None,
        "seoul_percentile": bi.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🚲 {bi.get('nearest_station', '')}" if bi.get("nearest_station") else "",
        "nearest_distance": bi.get("nearest_distance", None),
    }

    # bus-baseline anchor; transport domain is never created here (matches the
    # original — bike only augments an existing transport domain).
    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="bike", summary=bike_summary, info=bike_info,
        new_tag=new_tag, domain_key="transport", domain_template=None,
        anchor_key="bus-baseline", poi_count=count, poi_count_mode="increment",
    )


def build_ev_charger_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(ev_charger_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items = parse_baseline_items(row, "ev_charger_items_json")

    return {
        "count_300m": to_int(row.get("ev_charger_count_300m"), 0),
        "count_500m": to_int(row.get("ev_charger_count_500m"), 0),
        "count_1km": to_int(row.get("ev_charger_count_1km"), 0),
        "nearest_name": clean_text(row.get("nearest_ev_charger_name", "")),
        "nearest_distance": clean_text(row.get("nearest_ev_charger_distance", "")),
        "fast_count": to_int(row.get("fast_charger_count_1km"), 0),
        "slow_count": to_int(row.get("slow_charger_count_1km"), 0),
        "restricted_count": to_int(row.get("restricted_charger_count_1km"), 0),
        "public_count": to_int(row.get("public_charger_count_1km"), 0),
        "free_parking_count": to_int(row.get("free_parking_count_1km"), 0),
        "available_count": to_int(row.get("available_charger_count_1km"), 0),
        "possible_inside_complex_count": to_int(row.get("possible_inside_complex_count"), 0),
        "score": to_int(row.get("ev_charger_score"), 0),
        "level": clean_text(row.get("ev_charger_level", "")) or "보통",
        "items": items,
        "seoul_percentile": get_baseline_percentile(row, "ev_charger_count_500m_seoul_percentile"),
    }


def build_ev_charger_map_pois(ev_charger_info):
    if not ev_charger_info:
        return []

    map_pois = []

    for item in ev_charger_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = clean_text(item.get("label", "EV 충전소"))
        fast_item_count = to_int(item.get("fast_count"), 0)
        slow_item_count = to_int(item.get("slow_count"), 0)
        subtypes = []

        if fast_item_count > 0:
            subtypes.append("급속")

        if slow_item_count > 0:
            subtypes.append("완속")

        if not subtypes:
            subtypes.append("완속")

        subtype = subtypes[0]

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "ev-charger",
            "label": f"⚡ {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "subtypes": subtypes,
            "source": "공공데이터포털 전국전기차충전소표준데이터",
        })

    return map_pois


def build_ev_charger_category_summary(ev_charger_info):
    if not ev_charger_info:
        return None

    count_500m = to_int(ev_charger_info.get("count_500m"), 0)
    count_1km = to_int(ev_charger_info.get("count_1km"), 0)
    fast_count = to_int(ev_charger_info.get("fast_count"), 0)
    slow_count = to_int(ev_charger_info.get("slow_count"), 0)
    score = to_int(ev_charger_info.get("score"), 0)
    nearest_name = ev_charger_info.get("nearest_name", "")
    items = []

    for item in ev_charger_info.get("items", []):
        fast_item_count = to_int(item.get("fast_count"), 0)
        slow_item_count = to_int(item.get("slow_count"), 0)
        subtypes = []

        if fast_item_count > 0:
            subtypes.append("급속")

        if slow_item_count > 0:
            subtypes.append("완속")

        if not subtypes:
            subtypes.append("완속")

        items.append({
            **item,
            "subtype": subtypes[0],
            "subtypes": subtypes,
            "charger_fast_count": fast_item_count,
            "charger_slow_count": slow_item_count,
            "charger_summary": f"급속 {fast_item_count} / 완속 {slow_item_count}",
        })

    return {
        "key": "ev-charger",
        "label": "⚡ 전기차 충전",
        "domain": "convenience",
        "domain_label": "생활편의",
        "score": f"{count_500m}곳",
        "score_class": "score-good" if score >= 55 else "score-normal",
        "description": (
            f"500m 내 {count_500m}곳, 1km 내 {count_1km}곳 기준의 전기차 충전 접근성입니다."
        ),
        "radius": 1000,
        "count": count_1km,
        "seoul_percentile": ev_charger_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "공공데이터포털 전국전기차충전소표준데이터",
        "nearest_poi": {
            "label": f"⚡ {nearest_name}",
            "distance": ev_charger_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {"name": "급속", "display": "급속", "style": "ev-chip-fast", "count": fast_count},
            {"name": "완속", "display": "완속", "style": "ev-chip-slow", "count": slow_count},
        ],
        "pois": items,
        "empty": "반경 1km 안에서 확인된 전기차 충전소 정보가 없습니다.",
        "is_ev_charger_summary": True,
    }


def apply_ev_charger_baseline_to_ui(category_summaries, preference_tags, domain_summaries, ev_charger_info, apartment):
    old_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "ev-charger"),
        None
    )

    ev_summary = build_ev_charger_category_summary(ev_charger_info)
    ei = ev_charger_info or {}
    count = ei.get("count_1km", 0)

    new_tag = {
        "key": "ev-charger",
        "label": "⚡ 전기차 충전",
        "value": old_tag.get("value", 3) if old_tag else 3,
        "level": old_tag.get("level", ei.get("level", "보통")) if old_tag else ei.get("level", "보통"),
        "level_class": old_tag.get("level_class", "level-normal") if old_tag else "level-normal",
        "radius": 1000,
        "count": count,
        "percentile": None,
        "seoul_percentile": ei.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"⚡ {ei.get('nearest_name', '')}" if ei.get("nearest_name") else "",
        "nearest_distance": ei.get("nearest_distance", None),
    }

    domain_template = {
        "key": "convenience",
        "label": "생활편의",
        "description": "마트, 편의점, 전기차 충전 등 일상 편의시설",
        "initial_load": True,
        "category_count": 1,
        "poi_count": count,
        "categories": [ev_summary],
        "max_score": ei.get("score", 0),
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="ev-charger", summary=ev_summary, info=ev_charger_info,
        new_tag=new_tag, domain_key="convenience", domain_template=domain_template,
        anchor_key="convenience", poi_count=count, poi_count_mode="increment",
    )


def build_medical_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(medical_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    def parse_items(column_name):
        return parse_baseline_items(row, column_name, float_distance=True)

    items = parse_items("medical_items_json")
    hospital_items = parse_items("hospital_items_json") or [
        item for item in items if clean_text(item.get("type")) == "hospital"
    ]
    emergency_items = parse_items("emergency_items_json") or [
        item for item in items if clean_text(item.get("type")) == "emergency"
    ]
    superior_hospital_items = parse_items("superior_hospital_items_json")
    pharmacy_items = parse_items("pharmacy_items_json") or [
        item for item in items if clean_text(item.get("type")) == "pharmacy"
    ]

    return {
        "medical_count_500m": to_int(row.get("medical_count_500m"), 0),
        "medical_count_1km": to_int(row.get("medical_count_1km"), 0),
        "hospital_count_500m": to_int(row.get("hospital_count_500m"), 0),
        "hospital_count_1km": to_int(row.get("hospital_count_1km"), 0),
        "emergency_count_1km": to_int(row.get("emergency_count_1km"), 0),
        "emergency_count_3km": to_int(row.get("emergency_count_3km"), 0),
        "superior_hospital_count_5km": to_int(row.get("superior_hospital_count_5km"), 0),
        "pharmacy_count_500m": to_int(row.get("pharmacy_count_500m"), 0),
        "pharmacy_count_1km": to_int(row.get("pharmacy_count_1km"), 0),
        "nearest_hospital_name": clean_text(row.get("nearest_hospital_name", "")),
        "nearest_hospital_distance": clean_text(row.get("nearest_hospital_distance", "")),
        "nearest_emergency_name": clean_text(row.get("nearest_emergency_name", "")),
        "nearest_emergency_distance": clean_text(row.get("nearest_emergency_distance", "")),
        "nearest_superior_hospital_name": clean_text(row.get("nearest_superior_hospital_name", "")),
        "nearest_superior_hospital_distance": clean_text(row.get("nearest_superior_hospital_distance", "")),
        "nearest_pharmacy_name": clean_text(row.get("nearest_pharmacy_name", "")),
        "nearest_pharmacy_distance": clean_text(row.get("nearest_pharmacy_distance", "")),
        "items": items,
        "hospital_items": hospital_items,
        "emergency_items": emergency_items,
        "superior_hospital_items": superior_hospital_items,
        "pharmacy_items": pharmacy_items,
        "seoul_percentile": get_baseline_percentile(row, "medical_count_1km_seoul_percentile"),
    }


def build_medical_map_pois(medical_info):
    if not medical_info:
        return []

    map_pois = []
    category_map = {
        "hospital": ("hospital", "🏥"),
        "emergency": ("emergency-room", "🚑"),
        "general-hospital": ("general-hospital", "🏥"),
        "pharmacy": ("pharmacy", "💊"),
    }

    map_items = (
        medical_info.get("items", [])
        + medical_info.get("superior_hospital_items", [])
    )

    for item in map_items:
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        item_type = clean_text(item.get("type", "hospital"))
        category, icon = category_map.get(item_type, ("hospital", "🏥"))
        label = clean_text(item.get("label", item.get("name", "의료시설")))
        subtype = clean_text(item.get("subtype", "의료"))

        if category == "general-hospital":
            subtype = "종합병원"

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": category,
            "label": f"{icon} {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울열린데이터광장",
        })

    return map_pois


HOSPITAL_CHIP_ORDER = [
    "내과",
    "소아과",
    "치과",
    "안과",
    "이비인후과",
    "정형외과",
    "산부인과",
    "피부과",
    "한의원",
    "기타",
]

PHARMACY_CHIP_ORDER = ["야간", "주말", "휴일"]


def get_subtype_chips_from_items(items, style_prefix, order=None):
    counts = {}
    for item in items:
        subtypes = item.get("subtypes") or [item.get("subtype", "")]
        for subtype in subtypes:
            subtype = clean_text(subtype)
            if not subtype:
                continue
            counts[subtype] = counts.get(subtype, 0) + 1

    if order:
        subtype_names = [
            subtype for subtype in order
            if subtype != "기타" and counts.get(subtype, 0) > 0
        ]
        extra_names = sorted(
            subtype for subtype in counts
            if subtype not in order and subtype != "기타"
        )
        subtype_names.extend(extra_names)
        if counts.get("기타", 0) > 0:
            subtype_names.append("기타")
    else:
        subtype_names = [subtype for subtype, _ in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:12]]

    chips = []

    for subtype in subtype_names:
        count = counts.get(subtype, 0)
        chips.append({
            "name": subtype,
            "display": subtype,
            "style": f"{style_prefix}-{subtype}",
            "count": count,
        })

    return chips


def build_medical_category_summaries(medical_info):
    if not medical_info:
        return []

    hospital_items = medical_info.get("hospital_items", [])
    emergency_items = medical_info.get("emergency_items", [])
    superior_hospital_items = [
        {**item, "subtype": "종합병원"}
        for item in medical_info.get("superior_hospital_items", [])
    ]
    pharmacy_items = medical_info.get("pharmacy_items", [])

    return [
        {
            "key": "hospital",
            "label": "🏥 병원",
            "domain": "medical",
            "domain_label": "🏥 의료",
            "score": f"{to_int(medical_info.get('hospital_count_500m'), 0)}곳",
            "score_class": "score-normal",
            "description": "도보권(반경 500m) 병원 접근성과 진료과 분포입니다.",
            "radius": 500,
            "count": to_int(medical_info.get("hospital_count_500m"), 0),
            "seoul_percentile": medical_info.get("seoul_percentile"),
            "gu_percentile": None,
            "source": "서울열린데이터광장",
            "nearest_poi": {
                "label": f"🏥 {medical_info.get('nearest_hospital_name')}",
                "distance": medical_info.get("nearest_hospital_distance"),
            } if medical_info.get("nearest_hospital_name") else None,
            "subtype_chips": get_subtype_chips_from_items(hospital_items, "medical-chip", HOSPITAL_CHIP_ORDER),
            "pois": hospital_items,
            "empty": "주변 병원 공공데이터가 없습니다.",
            "is_medical_public_summary": True,
        },
        {
            "key": "general-hospital",
            "label": "🏥 종합병원",
            "domain": "medical",
            "domain_label": "🏥 의료",
            "score": f"{to_int(medical_info.get('superior_hospital_count_5km'), 0)}곳",
            "score_class": "score-normal",
            "description": "반경 5km 기준 종합병원급 의료기관 접근성입니다.",
            "radius": 5000,
            "count": to_int(medical_info.get("superior_hospital_count_5km"), 0),
            "seoul_percentile": None,
            "gu_percentile": None,
            "source": "서울열린데이터광장",
            "nearest_poi": {
                "label": f"🏥 {medical_info.get('nearest_superior_hospital_name')}",
                "distance": medical_info.get("nearest_superior_hospital_distance"),
            } if medical_info.get("nearest_superior_hospital_name") else None,
            "subtype_chips": [],
            "pois": superior_hospital_items,
            "empty": "반경 5km 내 종합병원급 공공데이터가 없습니다.",
            "is_medical_public_summary": True,
        },
        {
            "key": "emergency-room",
            "label": "🚑 응급실",
            "domain": "medical",
            "domain_label": "🏥 의료",
            "score": f"{to_int(medical_info.get('emergency_count_3km'), 0)}곳",
            "score_class": "score-normal",
            "description": "반경 3km 기준 응급실 접근성입니다.",
            "radius": 3000,
            "count": to_int(medical_info.get("emergency_count_3km"), 0),
            "seoul_percentile": None,
            "gu_percentile": None,
            "source": "서울열린데이터광장",
            "nearest_poi": {
                "label": f"🚑 {medical_info.get('nearest_emergency_name')}",
                "distance": medical_info.get("nearest_emergency_distance"),
            } if medical_info.get("nearest_emergency_name") else None,
            "subtype_chips": [],
            "pois": emergency_items,
            "empty": "반경 3km 내 응급실 공공데이터가 없습니다.",
            "is_medical_public_summary": True,
        },
        {
            "key": "pharmacy",
            "label": "💊 약국",
            "domain": "medical",
            "domain_label": "🏥 의료",
            "score": f"{to_int(medical_info.get('pharmacy_count_500m'), 0)}곳",
            "score_class": "score-normal",
            "description": "반경 500m와 1km 기준 약국 접근성입니다.",
            "radius": 500,
            "count": to_int(medical_info.get("pharmacy_count_500m"), 0),
            "seoul_percentile": None,
            "gu_percentile": None,
            "source": "서울열린데이터광장",
            "nearest_poi": {
                "label": f"💊 {medical_info.get('nearest_pharmacy_name')}",
                "distance": medical_info.get("nearest_pharmacy_distance"),
            } if medical_info.get("nearest_pharmacy_name") else None,
            "subtype_chips": get_subtype_chips_from_items(pharmacy_items, "medical-chip", PHARMACY_CHIP_ORDER),
            "pois": pharmacy_items,
            "empty": "주변 약국 공공데이터가 없습니다.",
            "is_medical_public_summary": True,
        },
    ]


def apply_medical_baseline_to_ui(category_summaries, preference_tags, domain_summaries, medical_info, apartment):
    medical_summaries = build_medical_category_summaries(medical_info)

    if not medical_summaries:
        return category_summaries, preference_tags, domain_summaries

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") not in ["hospital", "pharmacy", "emergency-room", "general-hospital", "medical-public"]
    ]
    category_summaries.extend(medical_summaries)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") not in ["hospital", "pharmacy", "emergency-room", "general-hospital", "medical-public"]
    ]
    medical_tag_specs = [
        ("hospital", "🏥 병원", 500, medical_info.get("hospital_count_500m", 0), medical_summaries[0], medical_info.get("seoul_percentile")),
        ("general-hospital", "🏥 종합병원", 5000, medical_info.get("superior_hospital_count_5km", 0), medical_summaries[1], None),
        ("emergency-room", "🚑 응급실", 3000, medical_info.get("emergency_count_3km", 0), medical_summaries[2], None),
        ("pharmacy", "💊 약국", 500, medical_info.get("pharmacy_count_500m", 0), medical_summaries[3], None),
    ]

    for key, label, radius, count, summary, seoul_percentile in medical_tag_specs:
        nearest = summary.get("nearest_poi") or {}
        preference_tags.append({
            "key": key,
            "label": label,
            "value": 3,
            "level": "보통",
            "level_class": "level-normal",
            "radius": radius,
            "count": count,
            "percentile": None,
            "seoul_percentile": seoul_percentile,
            "gu_percentile": None,
            "district": apartment.get("district", ""),
            "nearest_name": nearest.get("label", ""),
            "nearest_distance": nearest.get("distance", None),
        })

    medical_domain = next(
        (domain for domain in domain_summaries if domain.get("key") == "medical"),
        None,
    )

    if medical_domain:
        medical_domain["categories"] = medical_summaries
        medical_domain["category_count"] = len(medical_summaries)
        medical_domain["poi_count"] = medical_info.get("hospital_count_500m", 0)
        medical_domain["max_score"] = max(
            medical_domain.get("max_score", 0),
            to_int(medical_info.get("medical_count_1km"), 0),
        )
    else:
        domain_summaries.append({
            "key": "medical",
            "label": "🏥 의료",
            "description": "병원, 종합병원, 응급실, 약국 접근성",
            "initial_load": True,
            "category_count": len(medical_summaries),
            "poi_count": medical_info.get("hospital_count_500m", 0),
            "categories": medical_summaries,
            "max_score": to_int(medical_info.get("medical_count_1km"), 0),
        })

    return category_summaries, preference_tags, domain_summaries

def build_commercial_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(commercial_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    commercial_items = parse_baseline_items(row, "commercial_items_json")

    type_chips = []
    chip_sources = [
        ("골목", row.get("alley_count", 0)),
        ("대형상권", row.get("developed_count", 0)),
        ("시장", row.get("market_count", 0)),
        ("관광특구", row.get("tourism_count", 0)),
    ]

    type_chips = build_count_chips(chip_sources)

    return {
        "commercial_count_1km": row.get("commercial_count_1km", 0),
        "nearest_name": row.get("nearest_commercial_name", ""),
        "nearest_type": row.get("nearest_commercial_type", ""),
        "nearest_display_type": row.get("nearest_commercial_display_type", ""),
        "nearest_distance": row.get("nearest_commercial_distance", ""),
        "alley_count": row.get("alley_count", 0),
        "developed_count": row.get("developed_count", 0),
        "market_count": row.get("market_count", 0),
        "tourism_count": row.get("tourism_count", 0),
        "items": commercial_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "commercial_count_1km_seoul_percentile"),
    }

    return None

def build_commercial_map_pois(commercial_info):
    return build_simple_map_pois(
        commercial_info, category="commercial", icon="🌃",
        source="서울시 상권분석서비스",
        label_fn=lambda item: item.get("label", "상권"),
        subtype_fn=lambda item: item.get("subtype", "기타"),
    )


def build_commercial_category_summary(commercial_info):
    if not commercial_info:
        return None

    count = to_int(commercial_info.get("commercial_count_1km"), 0)
    nearest_name = commercial_info.get("nearest_name", "")
    nearest_type = commercial_info.get("nearest_display_type", "")

    nearest_label = nearest_name
    if nearest_type:
        nearest_label = f"{nearest_name} · {nearest_type}"

    return {
        "key": "commercial",
        "label": "🌃 상권",
        "domain": "activity",
        "domain_label": "🌃 상권",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 1km 기준 서울시 상권분석서비스 상권영역 접근성입니다.",
        "radius": 1000,
        "count": count,
        "seoul_percentile": commercial_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 상권분석서비스",
        "nearest_poi": {
            "label": f"🌃 {nearest_label}",
            "distance": commercial_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"commercial-chip commercial-chip-{chip.get('name')}",
            }
            for chip in commercial_info.get("type_chips", [])
        ],
        "pois": commercial_info.get("items", []),
        "empty": "반경 내 확인된 상권 정보가 없습니다.",
        "is_commercial_summary": True,
    }


def apply_commercial_baseline_to_ui(category_summaries, preference_tags, domain_summaries, commercial_info, apartment):
    commercial_summary = build_commercial_category_summary(commercial_info)
    ci = commercial_info or {}
    count = ci.get("commercial_count_1km", 0)

    new_tag = {
        "key": "commercial",
        "label": "🌃 상권",
        "value": 3,
        "level": "보통",
        "level_class": "level-normal",
        "radius": 1000,
        "count": count,
        "percentile": None,
        "seoul_percentile": ci.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🌃 {ci.get('nearest_name', '')}",
        "nearest_distance": ci.get("nearest_distance", None),
    }

    domain_template = {
        "key": "activity",
        "label": "🌃 상권",
        "description": "유흥시설, 상권 밀집도",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [commercial_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="commercial", summary=commercial_summary, info=commercial_info,
        new_tag=new_tag, domain_key="activity", domain_template=domain_template,
        poi_count=count, poi_count_mode="increment",
    )



def build_shopping_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(shopping_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    shopping_items = parse_baseline_items(row, "shopping_items_json")

    valid_shopping_subtypes = ["백화점", "쇼핑몰", "전문점"]

    shopping_items = [
        item for item in shopping_items
        if item.get("subtype") in valid_shopping_subtypes
    ]

    chip_sources = [
        ("백화점", row.get("department_count", 0)),
        ("쇼핑몰", row.get("mall_count", 0)),
        ("전문점", row.get("specialty_count", 0)),
    ]

    type_chips = []
    type_chips = build_count_chips(chip_sources)

    # Nearest must come from the SAME filtered population as the list/count.
    # The baked nearest_shopping_* columns are computed over all subtypes
    # (incl. 기타쇼핑), so using them surfaced a nearest that the list/count
    # exclude — derive it from the already-filtered, distance-sorted items.
    nearest = shopping_items[0] if shopping_items else None
    if nearest:
        nearest_name = clean_text(
            str(nearest.get("label") or nearest.get("name") or "")
            .replace("🛍️", "")
            .replace("🛍", "")
        )
        nearest_subtype = clean_text(nearest.get("subtype", ""))
        nearest_distance = clean_text(str(nearest.get("distance", "")))
    else:
        nearest_name = ""
        nearest_subtype = ""
        nearest_distance = ""

    return {
        "shopping_count_3km": len(shopping_items),
        "nearest_name": nearest_name,
        "nearest_subtype": nearest_subtype,
        "nearest_distance": nearest_distance,
        "items": shopping_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "shopping_count_3km_seoul_percentile"),
    }

def build_shopping_map_pois(shopping_info):
    return build_simple_map_pois(
        shopping_info, category="shopping", icon="🛍️",
        source="서울시 대규모점포 인허가 정보",
        label_fn=lambda item: str(item.get("label", "쇼핑시설")).replace("🛍", "").strip(),
        subtype_fn=lambda item: item.get("subtype", "기타쇼핑"),
    )


def build_shopping_category_summary(shopping_info):
    if not shopping_info:
        return None

    count = to_int(shopping_info.get("shopping_count_3km"), 0)
    nearest_name = shopping_info.get("nearest_name", "")
    nearest_subtype = shopping_info.get("nearest_subtype", "")

    nearest_label = nearest_name
    if nearest_subtype:
        nearest_label = f"{nearest_name} · {nearest_subtype}"

    return {
        "key": "shopping",
        "label": "🛍️ 쇼핑",
        "domain": "activity",
        "domain_label": "🌃 상권",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 3km 기준 대형마트를 제외한 백화점, 쇼핑몰 등 쇼핑시설 접근성입니다.",
        "radius": 3000,
        "count": count,
        "seoul_percentile": shopping_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 대규모점포 인허가 정보",
        "nearest_poi": {
            "label": f"🛍️ {nearest_label}",
            "distance": shopping_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"shopping-chip shopping-chip-{chip.get('name')}",
            }
            for chip in shopping_info.get("type_chips", [])
        ],
        "pois": shopping_info.get("items", []),
        "empty": "반경 내 확인된 쇼핑시설 정보가 없습니다.",
        "is_shopping_summary": True,
    }


def apply_shopping_baseline_to_ui(category_summaries, preference_tags, domain_summaries, shopping_info, apartment):
    shopping_summary = build_shopping_category_summary(shopping_info)
    si = shopping_info or {}
    count = si.get("shopping_count_3km", 0)

    new_tag = {
        "key": "shopping",
        "label": "🛍️ 쇼핑",
        "value": 3,
        "level": "보통",
        "level_class": "level-normal",
        "radius": 3000,
        "count": count,
        "percentile": None,
        "seoul_percentile": si.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🛍️ {si.get('nearest_name', '')}" if si.get("nearest_name") else "",
        "nearest_distance": si.get("nearest_distance", None),
    }

    domain_template = {
        "key": "activity",
        "label": "🌃 상권/활기",
        "description": "상권, 쇼핑, 야간상권 등 활동 인프라",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [shopping_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="shopping", summary=shopping_summary, info=shopping_info,
        new_tag=new_tag, domain_key="activity", domain_template=domain_template,
        anchor_key="commercial", poi_count=count, poi_count_mode="increment",
    )

def build_nightlife_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(nightlife_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    nightlife_items = parse_baseline_items(row, "nightlife_items_json")

    chip_sources = [
        ("룸살롱", row.get("room_salon_count", 0)),
        ("바/주점", row.get("bar_count", 0)),
        ("클럽/나이트", row.get("club_count", 0)),
        ("기타", row.get("etc_count", 0)),
    ]

    type_chips = []
    type_chips = build_count_chips(chip_sources)

    for index, item in enumerate(nightlife_items, start=1):
        subtype = clean_text(item.get("subtype", "기타")) or "기타"
        item["original_label"] = clean_text(item.get("label", ""))
        item["label"] = f"{subtype} #{index}"
        item["name"] = item["label"]

    nearest_display = ""
    if nightlife_items:
        nearest_display = nightlife_items[0].get("label", "")

    return {
        "nightlife_count_500m": row.get("nightlife_count_500m", 0),
        "nightlife_count_1km": row.get("nightlife_count_1km", 0),
        "nearest_name": nearest_display,
        "nearest_type": clean_text(row.get("nearest_nightlife_type", "")),
        "nearest_subtype": clean_text(row.get("nearest_nightlife_subtype", "")),
        "nearest_distance": clean_text(row.get("nearest_nightlife_distance", "")),
        "room_salon_count": row.get("room_salon_count", 0),
        "bar_count": row.get("bar_count", 0),
        "club_count": row.get("club_count", 0),
        "etc_count": row.get("etc_count", 0),
        "items": nightlife_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "nightlife_count_500m_seoul_percentile"),
    }

    return None

def build_nightlife_map_pois(nightlife_info):
    return build_simple_map_pois(
        nightlife_info, category="nightlife", icon="🍺",
        source="서울열린데이터광장",
        label_fn=lambda item: item.get("label", "유흥주점"),
        subtype_fn=lambda item: item.get("subtype", "기타"),
    )


def build_nightlife_category_summary(nightlife_info):
    if not nightlife_info:
        return None

    count = to_int(nightlife_info.get("nightlife_count_500m"), 0)
    count_1km = to_int(nightlife_info.get("nightlife_count_1km"), 0)
    nearest_name = nightlife_info.get("nearest_name", "")
    nearest_subtype = nightlife_info.get("nearest_subtype", "")

    nearest_label = nearest_name

    seoul_percentile = nightlife_info.get("seoul_percentile")
    return {
        "key": "nightlife",
        "label": "🍺 유흥주점",
        "domain": "activity",
        "domain_label": "🌃 상권",
        "score": percentile_score_value(seoul_percentile),
        "score_class": percentile_score_class(seoul_percentile),
        "description": "반경 500m 기준 현재 영업 중인 유흥주점 인허가 정보를 표시합니다.",
        "radius": 500,
        "count": count,
        "seoul_percentile": seoul_percentile,
        "gu_percentile": None,
        "display_percentile": True,
        "source": "서울열린데이터광장",
        "nearest_poi": {
            "label": f"🍺 {nearest_label}",
            "distance": nightlife_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"nightlife-chip nightlife-chip-{chip.get('name')}",
            }
            for chip in nightlife_info.get("type_chips", [])
        ],
        "pois": [
            {
                **item,
                "label": str(item.get("label", "")).replace("🍺", "").strip(),
            }
            for item in nightlife_info.get("items", [])
        ],
        "empty": "반경 내 확인된 유흥주점 정보가 없습니다.",
        "is_nightlife_summary": True,
        "extra_count_1km": count_1km,
    }


def apply_nightlife_baseline_to_ui(category_summaries, preference_tags, domain_summaries, nightlife_info, apartment):
    old_nightlife_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "nightlife"),
        None
    )

    nightlife_summary = build_nightlife_category_summary(nightlife_info)
    ni = nightlife_info or {}
    count = ni.get("nightlife_count_500m", 0)

    new_tag = {
        "key": "nightlife",
        "label": "🍺 유흥주점",
        "value": old_nightlife_tag.get("value", 3) if old_nightlife_tag else 3,
        "level": old_nightlife_tag.get("level", "보통") if old_nightlife_tag else "보통",
        "level_class": old_nightlife_tag.get("level_class", "level-normal") if old_nightlife_tag else "level-normal",
        "radius": 500,
        "count": count,
        "percentile": None,
        "seoul_percentile": None,
        "gu_percentile": None,
        "display_percentile": False,
        "district": apartment.get("district", ""),
        "nearest_name": f"🍺 {ni.get('nearest_name', '')}" if ni.get("nearest_name") else "",
        "nearest_distance": ni.get("nearest_distance", None),
    }

    domain_template = {
        "key": "activity",
        "label": "🌃 상권/활기",
        "description": "유흥시설, 상권 밀집도",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [nightlife_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="nightlife", summary=nightlife_summary, info=nightlife_info,
        new_tag=new_tag, domain_key="activity", domain_template=domain_template,
        poi_count=count, poi_count_mode="increment",
    )



ACADEMY_SUBTYPE_ORDER = [
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


def build_academy_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(academy_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    academy_items = parse_baseline_items(row, "academy_items_json")

    for item in academy_items:
        item["label"] = str(item.get("label", "")).replace("🏫", "").strip()

    type_chips = []

    chip_sources = [
        ("입시/보습", row.get("exam_count", 0)),
        ("영어", row.get("english_count", 0)),
        ("수학", row.get("math_count", 0)),
        ("중국어", row.get("chinese_count", 0)),
        ("일본어", row.get("japanese_count", 0)),
        ("예체능", row.get("arts_sports_count", 0)),
        ("독서실", row.get("study_room_count", 0)),
        ("직업/자격", row.get("career_count", 0)),
        ("기타", row.get("etc_count", 0)),
    ]

    type_chips = build_count_chips(chip_sources)

    return {
        "academy_count_1000m": row.get("academy_count_1000m", 0),
        "academy_count_500m": row.get("academy_count_500m", 0),
        "nearest_name": clean_text(row.get("nearest_academy_name", "")),
        "nearest_subtype": clean_text(row.get("nearest_academy_subtype", "")),
        "nearest_distance": clean_text(row.get("nearest_academy_distance", "")),
        "items": academy_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "academy_count_1000m_seoul_percentile"),
    }

    return None

def build_academy_map_pois(academy_info):
    return build_simple_map_pois(
        academy_info, category="academy", icon="🏫",
        source="서울시 학원교습소 정보",
        label_fn=lambda item: str(item.get("label", "학원")).replace("🏫", "").strip(),
        subtype_fn=lambda item: item.get("subtype", "기타"),
    )



SCHOOL_ENVIRONMENT_RADIUS = 1500


def clean_school_zone_name(value):
    text = clean_text(value)
    return (
        text
        .replace("통학구역", "")
        .replace("공동통학구역", "")
        .strip()
    )


def find_school_by_name(school_name):
    clean_name = clean_school_zone_name(school_name)
    if not clean_name:
        return None

    for school in school_data:
        if school.get("subtype") != "elementary":
            continue

        name = clean_text(school.get("name"))
        if name == clean_name:
            return school

    for school in school_data:
        if school.get("subtype") != "elementary":
            continue

        name = clean_text(school.get("name"))
        if clean_name in name or name in clean_name:
            return school

    return None


def build_school_environment_info(apartment, school_zone):
    apt_lat = apartment.get("lat")
    apt_lng = apartment.get("lng")

    assigned_school_name = ""
    assigned_education_office = ""

    if school_zone:
        assigned_school_name = clean_school_zone_name(
            school_zone.get("primary_school_zone_name", "")
        )
        assigned_education_office = clean_text(
            school_zone.get("primary_education_office", "")
        )

    assigned_school = find_school_by_name(assigned_school_name)
    assigned_distance = None

    if assigned_school:
        try:
            assigned_distance = round(get_distance_m(
                apt_lat,
                apt_lng,
                assigned_school.get("lat"),
                assigned_school.get("lng"),
            ))
        except Exception:
            assigned_distance = None

    middle_schools = []
    high_schools = []

    for school in school_data:
        subtype = school.get("subtype")

        if subtype not in ["middle", "high"]:
            continue

        try:
            distance = round(get_distance_m(
                apt_lat,
                apt_lng,
                school.get("lat"),
                school.get("lng"),
            ))
        except Exception:
            continue

        if distance > SCHOOL_ENVIRONMENT_RADIUS:
            continue

        item = {
            "label": clean_text(school.get("name")),
            "distance": distance,
            "subtype": "중학교" if subtype == "middle" else "고등학교",
            "school_type": school.get("school_type", ""),
            "lat": school.get("lat"),
            "lng": school.get("lng"),
            "source": "공공데이터포털 전국초중등학교위치표준데이터",
        }

        if subtype == "middle":
            middle_schools.append(item)
        else:
            high_schools.append(item)

    middle_schools.sort(key=lambda item: item.get("distance", 999999))
    high_schools.sort(key=lambda item: item.get("distance", 999999))

    items = []

    if assigned_school_name:
        assigned_item = {
            "label": assigned_school_name,
            "distance": assigned_distance,
            "subtype": "배정초",
            "school_type": "초등학교",
            "source": "공공데이터포털 초등학교통학구역",
        }

        if assigned_school:
            assigned_item["lat"] = assigned_school.get("lat")
            assigned_item["lng"] = assigned_school.get("lng")

        items.append(assigned_item)

    items.extend(middle_schools[:8])
    items.extend(high_schools[:8])

    nearest_candidates = [
        item for item in middle_schools + high_schools
        if item.get("distance") is not None
    ]

    nearest_school = None
    if nearest_candidates:
        nearest_school = min(
            nearest_candidates,
            key=lambda item: item.get("distance", 999999)
        )

    return {
        "assigned_school_name": assigned_school_name,
        "assigned_education_office": assigned_education_office,
        "assigned_distance": assigned_distance,
        "middle_count": len(middle_schools),
        "high_count": len(high_schools),
        "middle_items": middle_schools,
        "high_items": high_schools,
        "nearest_school": nearest_school,
        "items": items,
        "seoul_percentile": None,
    }


def build_school_environment_map_pois(school_environment_info):
    if not school_environment_info:
        return []

    map_pois = []

    for item in school_environment_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = clean_text(item.get("label", "학교"))
        subtype = clean_text(item.get("subtype", "학교"))

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "school-environment",
            "label": f"🏫 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": item.get("source", "공공데이터포털"),
        })

    return map_pois


def build_school_environment_category_summary(school_environment_info):
    if not school_environment_info:
        return None

    assigned_school_name = school_environment_info.get("assigned_school_name", "")
    middle_count = to_int(school_environment_info.get("middle_count"), 0)
    high_count = to_int(school_environment_info.get("high_count"), 0)
    total_count = (1 if assigned_school_name else 0) + middle_count + high_count

    nearest_poi = None
    assigned_distance = school_environment_info.get("assigned_distance")

    if assigned_school_name and assigned_distance is not None:
        nearest_poi = {
            "label": f"🏫 대표 배정초 {assigned_school_name}",
            "distance": assigned_distance,
        }
    elif school_environment_info.get("nearest_school"):
        nearest_school = school_environment_info.get("nearest_school")
        nearest_poi = {
            "label": f"🏫 {nearest_school.get('label', '')}",
            "distance": nearest_school.get("distance", ""),
        }

    subtype_chips = []

    if assigned_school_name:
        subtype_chips.append({
            "name": "배정초",
            "display": "배정초",
            "count": 1,
            "style": "school-chip school-chip-배정초",
        })

    if middle_count > 0:
        subtype_chips.append({
            "name": "중학교",
            "display": "중학교",
            "count": middle_count,
            "style": "school-chip school-chip-중학교",
        })

    if high_count > 0:
        subtype_chips.append({
            "name": "고등학교",
            "display": "고등학교",
            "count": high_count,
            "style": "school-chip school-chip-고등학교",
        })

    return {
        "key": "school-environment",
        "label": "🏫 교육환경",
        "domain": "education",
        "domain_label": "🏫 교육",
        "score": school_environment_score({
            "assigned_elementary_distance_m": assigned_distance,
            "nearest_poi": nearest_poi,
        }),
        "score_class": "score-normal",
        "description": "대표 배정 초등학교와 반경 1.5km 주변 중·고등학교 접근성 정보입니다.",
        "radius": SCHOOL_ENVIRONMENT_RADIUS,
        "count": total_count,
        "assigned_elementary_school": assigned_school_name,
        "assigned_school_name": assigned_school_name,
        "assigned_elementary_distance_m": assigned_distance,
        "assigned_distance": assigned_distance,
        "seoul_percentile": None,
        "gu_percentile": None,
        "display_percentile": False,
        "source": "공공데이터포털 학교/통학구역 데이터",
        "nearest_poi": nearest_poi,
        "subtype_chips": subtype_chips,
        "pois": school_environment_info.get("items", []),
        "empty": "확인된 학교 정보가 없습니다.",
        "is_school_environment_summary": True,
    }


def apply_school_environment_to_ui(category_summaries, preference_tags, domain_summaries, school_environment_info, apartment):
    school_summary = build_school_environment_category_summary(school_environment_info)
    si = school_environment_info or {}
    count = school_summary.get("count", 0) if school_summary else 0
    assigned_school_name = si.get("assigned_school_name", "")

    new_tag = {
        "key": "school-environment",
        "label": "🏫 교육환경",
        "value": 3,
        "level": "정보",
        "level_class": "level-normal",
        "radius": SCHOOL_ENVIRONMENT_RADIUS,
        "count": count,
        "percentile": None,
        "seoul_percentile": None,
        "gu_percentile": None,
        "display_percentile": False,
        "district": apartment.get("district", ""),
        "nearest_name": f"🏫 {assigned_school_name}" if assigned_school_name else "",
        "nearest_distance": si.get("assigned_distance", None),
    }

    domain_template = {
        "key": "education",
        "label": "🏫 교육",
        "description": "학교, 학원 등 교육 인프라",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [school_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="school-environment", summary=school_summary, info=school_environment_info,
        new_tag=new_tag, domain_key="education", domain_template=domain_template,
        anchor_key="academy", insert_position="before",
        poi_count=count, poi_count_mode="increment",
    )


def build_academy_category_summary(academy_info):
    if not academy_info:
        return None

    count = to_int(academy_info.get("academy_count_1000m"), 0)
    nearest_name = academy_info.get("nearest_name", "")
    nearest_subtype = academy_info.get("nearest_subtype", "")

    nearest_label = nearest_name
    if nearest_subtype:
        nearest_label = f"{nearest_name} · {nearest_subtype}"

    return {
        "key": "academy",
        "label": "✏️ 학원",
        "domain": "education",
        "domain_label": "🏫 교육",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 1km 기준 서울시 학원·교습소 접근성과 교육 유형 분포입니다.",
        "radius": 1000,
        "count": count,
        "seoul_percentile": academy_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 학원교습소 정보",
        "nearest_poi": {
            "label": f"✏️ {nearest_label}",
            "distance": academy_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"academy-chip academy-chip-{chip.get('name')}",
            }
            for chip in academy_info.get("type_chips", [])
        ],
        "pois": academy_info.get("items", []),
        "empty": "반경 내 확인된 학원·교습소 정보가 없습니다.",
        "is_academy_summary": True,
    }


def apply_academy_baseline_to_ui(category_summaries, preference_tags, domain_summaries, academy_info, apartment):
    old_academy_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "academy"),
        None
    )

    academy_summary = build_academy_category_summary(academy_info)
    ai = academy_info or {}
    count = ai.get("academy_count_1000m", 0)

    new_tag = {
        "key": "academy",
        "label": "✏️ 학원",
        "value": old_academy_tag.get("value", 3) if old_academy_tag else 3,
        "level": old_academy_tag.get("level", "보통") if old_academy_tag else "보통",
        "level_class": old_academy_tag.get("level_class", "level-normal") if old_academy_tag else "level-normal",
        "radius": 1000,
        "count": count,
        "percentile": None,
        "seoul_percentile": ai.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"✏️ {ai.get('nearest_name', '')}" if ai.get("nearest_name") else "",
        "nearest_distance": ai.get("nearest_distance", None),
    }

    domain_template = {
        "key": "education",
        "label": "🏫 교육",
        "description": "학원, 교육 인프라",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [academy_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="academy", summary=academy_summary, info=academy_info,
        new_tag=new_tag, domain_key="education", domain_template=domain_template,
        poi_count=count, poi_count_mode="increment",
    )


def build_culture_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(culture_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    culture_items = parse_baseline_items(row, "culture_items_json")

    for item in culture_items:
        place_name = str(item.get("place_name", "")).replace("🎭", "").strip()
        service_name = str(item.get("service_name", "")).replace("🎭", "").strip()
        label = str(item.get("label", "")).replace("🎭", "").strip()

        if place_name and service_name and place_name != service_name:
            full_label = f"{place_name} · {service_name}"
        else:
            full_label = label or place_name or service_name

        item["label"] = full_label

    chip_sources = [
        ("공연/행사", row.get("performance_count", 0)),
        ("전시/관람", row.get("exhibition_count", 0)),
        ("체육", row.get("sports_count", 0)),
        ("키즈", row.get("kids_count", 0)),
        ("체험", row.get("experience_count", 0)),
        ("클래스", row.get("class_count", 0)),
        ("자연/공원", row.get("nature_count", 0)),
    ]

    type_chips = []
    type_chips = build_count_chips(chip_sources)

    return {
        "culture_count_1500m": row.get("culture_count_1500m", 0),
        "culture_diversity_count": row.get("culture_diversity_count", 0),
        "nearest_name": clean_text(row.get("nearest_culture_name", "")),
        "nearest_subtype": clean_text(row.get("nearest_culture_subtype", "")),
        "nearest_distance": clean_text(row.get("nearest_culture_distance", "")),
        "items": culture_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "culture_count_1500m_seoul_percentile"),
    }

    return None

def build_culture_map_pois(culture_info):
    return build_simple_map_pois(
        culture_info, category="culture", icon="🎭",
        source="서울시 공공서비스예약",
        label_fn=lambda item: item.get("label", "문화생활"),
        subtype_fn=lambda item: item.get("subtype", "기타"),
    )


def build_culture_category_summary(culture_info):
    if not culture_info:
        return None

    count = to_int(culture_info.get("culture_count_1500m"), 0)
    nearest_name = culture_info.get("nearest_name", "")
    nearest_subtype = culture_info.get("nearest_subtype", "")

    nearest_label = nearest_name
    if nearest_subtype:
        nearest_label = f"{nearest_name} · {nearest_subtype}"

    return {
        "key": "culture",
        "label": "🎭 문화생활",
        "domain": "culture",
        "domain_label": "🎭 문화생활",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 1.5km 기준 공연, 전시, 체육, 체험 등 문화생활 접근성입니다.",
        "radius": 1500,
        "count": count,
        "seoul_percentile": culture_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 공공서비스예약",
        "nearest_poi": {
            "label": f"🎭 {nearest_label}",
            "distance": culture_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"culture-chip culture-chip-{chip.get('name')}",
            }
            for chip in culture_info.get("type_chips", [])
        ],
        "pois": culture_info.get("items", []),
        "empty": "반경 내 확인된 문화생활 정보가 없습니다.",
        "is_culture_summary": True,
    }


def apply_culture_baseline_to_ui(category_summaries, preference_tags, domain_summaries, culture_info, apartment):
    old_culture_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "culture"),
        None
    )

    culture_summary = build_culture_category_summary(culture_info)
    cu = culture_info or {}
    count = cu.get("culture_count_1500m", 0)

    new_tag = {
        "key": "culture",
        "label": "🎭 문화생활",
        "value": old_culture_tag.get("value", 3) if old_culture_tag else 3,
        "level": old_culture_tag.get("level", "보통") if old_culture_tag else "보통",
        "level_class": old_culture_tag.get("level_class", "level-normal") if old_culture_tag else "level-normal",
        "radius": 1500,
        "count": count,
        "percentile": None,
        "seoul_percentile": cu.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🎭 {cu.get('nearest_name', '')}" if cu.get("nearest_name") else "",
        "nearest_distance": cu.get("nearest_distance", None),
    }

    domain_template = {
        "key": "culture",
        "label": "🎭 문화생활",
        "description": "공연, 전시, 체육, 체험 등 활동형 여가",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [culture_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="culture", summary=culture_summary, info=culture_info,
        new_tag=new_tag, domain_key="culture", domain_template=domain_template,
        poi_count=count, poi_count_mode="set",
    )


def build_fire_station_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(fire_station_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    fire_items = parse_baseline_items(row, "fire_station_items_json")

    type_chips = []
    chip_sources = [
        ("안전센터", row.get("safety_center_count", 0)),
        ("구조대", row.get("rescue_count", 0)),
        ("기타", row.get("fire_etc_count", 0)),
    ]

    type_chips = build_count_chips(chip_sources)

    return {
        "fire_station_count_1500m": row.get("fire_station_count_1500m", 0),
        "nearest_name": clean_text(row.get("nearest_fire_station_name", "")),
        "nearest_subtype": clean_text(row.get("nearest_fire_station_subtype", "")),
        "nearest_distance": clean_text(row.get("nearest_fire_station_distance", "")),
        "items": fire_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "nearest_fire_station_distance_seoul_percentile"),
    }

    return None

def build_fire_station_map_pois(fire_station_info):
    return build_simple_map_pois(
        fire_station_info, category="fire-station", icon="🚒",
        source="서울시 119안전센터/구조대 위치정보",
        label_fn=lambda item: str(item.get("label", "119안전센터/구조대")).replace("🚒", "").strip(),
        subtype_fn=lambda item: item.get("subtype", "기타"),
    )


def build_fire_station_category_summary(fire_station_info):
    if not fire_station_info:
        return None

    count = to_int(fire_station_info.get("fire_station_count_1500m"), 0)
    nearest_name = fire_station_info.get("nearest_name", "")
    nearest_subtype = fire_station_info.get("nearest_subtype", "")

    nearest_label = nearest_name
    if nearest_subtype:
        nearest_label = f"{nearest_name} · {nearest_subtype}"

    return {
        "key": "fire-station",
        "label": "🚒 119안전센터/구조대",
        "domain": "safety",
        "domain_label": "🛡 안전",
        "score": f"{count}곳",
        "score_class": "score-normal",
        "description": "반경 1.5km 기준 119안전센터와 구조대 접근성입니다.",
        "radius": 1500,
        "count": count,
        "seoul_percentile": fire_station_info.get("seoul_percentile"),
        "gu_percentile": None,
        "source": "서울시 119안전센터/구조대 위치정보",
        "nearest_poi": {
            "label": f"🚒 {nearest_label}",
            "distance": fire_station_info.get("nearest_distance", ""),
        } if nearest_name else None,
        "subtype_chips": [
            {
                "name": chip.get("name"),
                "display": chip.get("name"),
                "count": chip.get("count", 0),
                "style": f"fire-chip fire-chip-{chip.get('name')}",
            }
            for chip in fire_station_info.get("type_chips", [])
        ],
        "pois": fire_station_info.get("items", []),
        "empty": "반경 내 확인된 119안전센터/구조대 정보가 없습니다.",
        "is_fire_station_summary": True,
    }


def apply_fire_station_baseline_to_ui(category_summaries, preference_tags, domain_summaries, fire_station_info, apartment):
    old_fire_tag = next(
        (tag for tag in preference_tags if tag.get("key") == "fire-station"),
        None
    )

    fire_summary = build_fire_station_category_summary(fire_station_info)
    fi = fire_station_info or {}
    count = fi.get("fire_station_count_1500m", 0)

    new_tag = {
        "key": "fire-station",
        "label": "🚒 119안전센터/구조대",
        "value": old_fire_tag.get("value", 3) if old_fire_tag else 3,
        "level": old_fire_tag.get("level", "보통") if old_fire_tag else "보통",
        "level_class": old_fire_tag.get("level_class", "level-normal") if old_fire_tag else "level-normal",
        "radius": 1500,
        "count": count,
        "percentile": None,
        "seoul_percentile": fi.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🚒 {fi.get('nearest_name', '')}" if fi.get("nearest_name") else "",
        "nearest_distance": fi.get("nearest_distance", None),
    }

    domain_template = {
        "key": "safety",
        "label": "🛡 안전",
        "description": "CCTV, 119안전센터 등 안전 인프라",
        "initial_load": False,
        "category_count": 1,
        "poi_count": count,
        "categories": [fire_summary],
        "max_score": 0,
    }

    return apply_baseline_category_to_ui(
        category_summaries, preference_tags, domain_summaries,
        key="fire-station", summary=fire_summary, info=fire_station_info,
        new_tag=new_tag, domain_key="safety", domain_template=domain_template,
        anchor_key="cctv", poi_count=count, poi_count_mode="increment",
    )


def get_preferences():
    preferences = {}

    for key in PREFERENCE_KEYS:
        value = request.args.get(key, "3")

        try:
            preferences[key] = int(value)
        except ValueError:
            preferences[key] = 3

    return preferences


def make_result_url(apartment_name, preferences, gu="", dong="", src="home"):
    # Always carry gu/dong so links resolve the exact complex, not the first
    # name match. Names collide across Seoul (e.g. 신동아아파트 x3).
    params = {"apartment": apartment_name}

    if gu:
        params["gu"] = gu
    if dong:
        params["dong"] = dong
    if src:
        params["src"] = src  # 진입경로(home/explore)별 우측 패널 분기

    for key in PREFERENCE_KEYS:
        params[key] = preferences.get(key, 3)

    return "/result?" + urlencode(params)


def normalize_source_label(source):
    source = clean_text(source)
    if not source:
        return ""

    if "Kakao" in source or "카카오" in source:
        return "Kakao"

    if "공공데이터포털" in source:
        return "공공데이터포털"

    if "서울" in source:
        return "서울열린데이터광장"

    return source


def normalize_summary_sources(category_summaries, domain_summaries):
    seen = set()
    summaries = list(category_summaries)
    for domain in domain_summaries:
        summaries.extend(domain.get("categories", []))

    for summary in summaries:
        obj_id = id(summary)
        if obj_id in seen:
            continue
        seen.add(obj_id)
        if "source" in summary:
            summary["source"] = normalize_source_label(summary.get("source", ""))


def get_top_apartments(preferences, limit=5):
    ranked = get_ranked_apartments(
        preferences,
        limit
    )

    for item in ranked:
        item["url"] = make_result_url(
            item["name"],
            preferences,
            item.get("district", ""),
            item.get("dong", ""),
        )

    return ranked


# 도메인 중요도 가중치(큐레이션) — 교통·교육·생활편의를 높게, 문화·상권을 낮게.
DOMAIN_WEIGHTS = {
    "transport": 1.5,
    "education": 1.5,
    "convenience": 1.3,
    "medical": 1.1,
    "safety": 1.0,
    "rest": 0.9,
    "culture": 0.7,
    "activity": 0.7,
}

# 인프라 요약(도메인 등급) 표시 순서 — 아파트 가치판단 중요도 순.
DOMAIN_ORDER = [
    "transport", "education", "convenience", "medical",
    "safety", "rest", "culture", "activity",
]

# 카테고리 상세 카드 표시 순서 — 생활인프라/아파트 가치판단 중요도 순.
CATEGORY_DISPLAY_ORDER = [
    "subway", "bus-baseline", "bus",                                 # 교통
    "school-environment", "school-zone", "academy",                  # 교육
    "large_mart", "super_mart", "warehouse_mart", "convenience", "ev-charger", "bike",  # 생활편의
    "hospital", "general-hospital", "emergency-room", "pharmacy",    # 의료
    "cctv", "fire-station", "fire",                                  # 안전
    "cafe", "park", "hangang",                                       # 휴식
    "culture",                                                      # 문화
    "commercial", "shopping", "nightlife",                          # 상권
]
_CATEGORY_ORDER_INDEX = {key: i for i, key in enumerate(CATEGORY_DISPLAY_ORDER)}


def sort_category_summaries(summaries):
    """카테고리 상세 카드를 중요도 순으로 정렬(미정의 키는 뒤로, 안정 정렬)."""
    return sorted(
        summaries,
        key=lambda s: _CATEGORY_ORDER_INDEX.get(s.get("key"), len(CATEGORY_DISPLAY_ORDER)),
    )


def _score_to_grade(score):
    if score >= 80:
        return "S"
    if score >= 65:
        return "A"
    if score >= 50:
        return "B"
    if score >= 35:
        return "C"
    return "D"


def compute_domain_profile(category_scores):
    """카테고리 서울점수를 도메인별로 묶어 평균·등급을 내고, 큐레이션 가중치로 종합
    대표점수를 산출한다. (점수는 이미 방향 보정됨 — 유흥 등 lower_better 포함)"""
    domain_values = {}
    for category, score in (category_scores or {}).items():
        if not isinstance(score, (int, float)):
            continue
        domain = CATEGORY_TO_DOMAIN.get(category)
        if not domain:
            continue
        domain_values.setdefault(domain, []).append(score)

    domains = []
    weighted_sum = 0.0
    weight_total = 0.0
    for domain_key in DOMAIN_ORDER:
        meta = DOMAIN_META.get(domain_key)
        values = domain_values.get(domain_key)
        if not meta or not values:
            continue
        domain_score = round(sum(values) / len(values))
        weight = DOMAIN_WEIGHTS.get(domain_key, 1.0)
        weighted_sum += domain_score * weight
        weight_total += weight
        domains.append({
            "key": domain_key,
            "label": meta["label"],
            "score": domain_score,
            "grade": _score_to_grade(domain_score),
        })

    representative = round(weighted_sum / weight_total) if weight_total else 0
    return {"representative": representative, "domains": domains}


def compute_representative_score(category_scores):
    """도메인 가중 종합 대표점수(0~100)."""
    return compute_domain_profile(category_scores)["representative"]


def _cosine_similarity(vec_a, vec_b):
    shared = set(vec_a) & set(vec_b)
    if not shared:
        return -1.0
    dot = sum(vec_a[k] * vec_b[k] for k in shared)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return -1.0
    return dot / (norm_a * norm_b)


def get_similar_apartments(apartment_key, category_scores, limit=5):
    """카테고리 점수 벡터 코사인 유사도 + 평균매매가 근접으로 비슷한 단지 추천."""
    index = build_apartment_index()
    price_lookup = _transaction_price_lookup()
    base_vec = category_scores or {}
    if not base_vec:
        return []
    base_price = (price_lookup.get(apartment_key) or {}).get("trade")

    scored = []
    for key, entry in index.items():
        if key == apartment_key:
            continue
        sim = _cosine_similarity(base_vec, entry.get("category_scores") or {})
        if sim < 0:
            continue
        price_factor = 1.0
        cand_price = (price_lookup.get(key) or {}).get("trade")
        if base_price and cand_price:
            price_factor = min(base_price, cand_price) / max(base_price, cand_price)
        combined = sim * (0.7 + 0.3 * price_factor)  # 유사도 70% + 가격근접 30%
        scored.append((combined, key, entry, cand_price))

    scored.sort(key=lambda item: -item[0])
    results = []
    for combined, key, entry, cand_price in scored[:limit]:
        results.append({
            "name": entry["name"],
            "district": entry["district"],
            "dong": entry["dong"],
            "name_suffix": "",
            "meta": _rep_area_meta(key),
            "url": make_result_url(entry["name"], {}, entry["district"], entry["dong"], src="home"),
        })
    return results


def _rep_area_meta(apartment_key):
    """추천 카드 보조줄 — '전용 {대표평형} · 최근 {최근매매가}' 또는 거래없음."""
    rep = _representative_area_lookup().get(apartment_key)
    if rep and rep[1]:
        return f"전용 {rep[0]} · 최근 {format_manwon(rep[1])}"
    return "최근 거래정보 없음"


def get_nearby_apartments(apartment, limit=5):
    """좌표 기준 최근접 단지 추천(자기 제외)."""
    try:
        alat = float(apartment["lat"])
        alng = float(apartment["lng"])
    except Exception:
        return []
    self_key = (
        clean_text(apartment.get("name", "")),
        clean_text(apartment.get("district", "")),
        clean_text(apartment.get("dong", "")),
    )
    index = build_apartment_index()
    candidates = []
    for ap in apartment_data:
        key = (clean_text(ap.get("name", "")), clean_text(ap.get("gu", "")), clean_text(ap.get("dong", "")))
        if key == self_key:
            continue
        try:
            dist = get_distance_m(alat, alng, float(ap["lat"]), float(ap["lng"]))
        except Exception:
            continue
        candidates.append((dist, ap, key))

    candidates.sort(key=lambda item: item[0])
    results = []
    for dist, ap, key in candidates[:limit]:
        results.append({
            "name": ap.get("name"),
            "district": ap.get("gu"),
            "dong": ap.get("dong"),
            "name_suffix": f"({format_distance_m(dist)})",
            "meta": _rep_area_meta(key),
            "url": make_result_url(ap.get("name"), {}, ap.get("gu"), ap.get("dong"), src="explore"),
        })
    return results


def build_lifestyle_summary(category_summaries):
    """Explore 진입 보조블록 — 단지의 강점 도메인(서울 백분위 상위) 요약."""
    items = []
    for summary in category_summaries:
        pct = summary.get("seoul_percentile")
        label = clean_text(summary.get("label", ""))
        if pct is not None and label:
            items.append((pct, label))
    items.sort(key=lambda item: -(item[0] or 0))
    strengths = [{"label": label, "percentile": round(pct)} for pct, label in items[:4]]
    return {"strengths": strengths}


def get_preference_tags(preferences, category_summaries, apartment):
    summary_map = {
        item["key"]: item
        for item in category_summaries
    }

    tags = []

    for key in PREFERENCE_KEYS:
        value = preferences.get(key, 0)

        if value >= 5:
            level = "최우선"
            level_class = "level-highest"
        elif value == 4:
            level = "매우 중요"
            level_class = "level-high"
        elif value == 3:
            level = "보통"
            level_class = "level-normal"
        elif value == 2:
            level = "낮음"
            level_class = "level-low"
        elif value == 1:
            level = "거의 안 봄"
            level_class = "level-min"
        else:
            level = "제외"
            level_class = "level-off"

        summary = summary_map.get(key, {})
        nearest_poi = summary.get("nearest_poi")

        nearest_name = ""
        nearest_distance = None

        if nearest_poi:
            nearest_name = nearest_poi.get("label", "")
            nearest_distance = nearest_poi.get("distance")

        tags.append({
            "key": key,
            "label": PREFERENCE_LABELS[key],
            "value": value,
            "level": level,
            "level_class": level_class,
            "count": summary.get("count", 0),
            "radius": summary.get("radius", 500),
            "percentile": summary.get("percentile", None),
            "nearest_name": nearest_name,
            "nearest_distance": nearest_distance,
            "seoul_percentile": summary.get("seoul_percentile"),
            "gu_percentile": summary.get("gu_percentile"),
            "district": apartment.get("district"),
        })

    return tags


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin/ranking-debug")
def admin_ranking_debug():
    metric_options = build_ranking_debug_options()
    selected_metric = request.args.get("metric") or "ev_charger"

    if selected_metric not in BASELINE_METRIC_CONFIG:
        selected_metric = metric_options[0]["key"] if metric_options else ""

    selected_config = BASELINE_METRIC_CONFIG.get(selected_metric, {})
    sort_key = request.args.get("sort") or "score_desc"

    if sort_key not in ["score_desc", "percentile_asc", "raw_desc", "raw_asc"]:
        sort_key = "score_desc"

    try:
        limit = int(request.args.get("limit", 50))
    except Exception:
        limit = 50

    limit = max(1, min(limit, 500))

    bottom = request.args.get("bottom") == "1"
    gu_filter = clean_text(request.args.get("gu", ""))
    dong_filter = clean_text(request.args.get("dong", ""))
    query = clean_text(request.args.get("q", ""))

    ranking_data = get_admin_ranking_rows(
        selected_config,
        sort_key,
        limit,
        bottom,
        gu_filter,
        dong_filter,
        query,
    )

    primary_metric = selected_config.get("primary_metric", "")

    return render_template(
        "admin_ranking_debug.html",
        metric_options=metric_options,
        selected_metric=selected_metric,
        selected_config=selected_config,
        primary_metric=primary_metric,
        direction=selected_config.get("metrics", {}).get(primary_metric, ""),
        sort_key=sort_key,
        limit=limit,
        bottom=bottom,
        gu_filter=gu_filter,
        dong_filter=dong_filter,
        query=query,
        rows=ranking_data["rows"],
        total_count=ranking_data["total_count"],
        filtered_count=ranking_data["filtered_count"],
        gu_options=ranking_data["gu_options"],
        dong_options=ranking_data["dong_options"],
        latest_validation_report=get_latest_validation_report(),
    )


FEATURE_OPTIONS = [
    {"key": "transfer", "label": "환승역", "icon": "🚇"},
    {"key": "emergency", "label": "응급실", "icon": "🚑"},
    {"key": "general_hospital", "label": "종합병원", "icon": "🏥"},
    {"key": "costco", "label": "코스트코", "icon": "🛒"},
    {"key": "nightlife_low", "label": "유흥 적음", "icon": "🍺"},
    {"key": "hangang", "label": "한강공원", "icon": "🌊"},
    {"key": "culture", "label": "공연/전시", "icon": "🎭"},
]


def normalize_search_text(value):
    return clean_text(value).replace(" ", "").lower()


def get_subway_line_station_index():
    line_map = {}

    for row in subway_baseline_data:
        raw_items = row.get("subway_items_json", "[]")
        try:
            items = json.loads(raw_items) if raw_items else []
        except Exception:
            items = []

        for item in items:
            station_name = clean_text(item.get("name", "")).replace("역", "")
            if not station_name:
                continue

            lines = item.get("lines", [])
            if isinstance(lines, str):
                lines = [part.strip() for part in lines.replace("/", ",").split(",")]

            for line in lines:
                line_name = clean_text(line)
                if not line_name:
                    continue
                line_map.setdefault(line_name, set()).add(station_name)

    return {
        line: sorted(stations)
        for line, stations in sorted(line_map.items())
    }


def get_subway_line_options():
    return list(get_subway_line_station_index().keys())


@app.route("/api/search/apartments")
def api_search_apartments():
    query = normalize_search_text(request.args.get("q", ""))
    limit = max(1, min(to_int(request.args.get("limit"), 12), 30))

    if not query:
        return jsonify({"items": []})

    starts = []
    contains = []

    for apartment in apartment_data:
        name = clean_text(apartment.get("name", ""))
        gu = clean_text(apartment.get("gu") or apartment.get("district", ""))
        dong = clean_text(apartment.get("dong", ""))
        haystack = normalize_search_text(f"{name} {gu} {dong}")
        name_key = normalize_search_text(name)

        if not haystack or query not in haystack:
            continue

        item = {
            "value": name,
            "label": name,
            "meta": f"{gu} {dong}".strip(),
            "gu": gu,
            "dong": dong,
        }

        if name_key.startswith(query):
            starts.append(item)
        else:
            contains.append(item)

    return jsonify({"items": (starts + contains)[:limit]})


@app.route("/api/options/dongs")
def api_options_dongs():
    gu_filter = clean_text(request.args.get("gu", ""))
    dongs = sorted({
        clean_text(item.get("dong", ""))
        for item in apartment_data
        if clean_text(item.get("dong", ""))
        and (not gu_filter or clean_text(item.get("gu") or item.get("district", "")) == gu_filter)
    })
    return jsonify({"items": [{"value": dong, "label": dong} for dong in dongs]})


@app.route("/api/options/subway-lines")
def api_options_subway_lines():
    return jsonify({
        "items": [
            {"value": line, "label": line}
            for line in get_subway_line_options()
        ]
    })


@app.route("/api/options/subway-stations")
def api_options_subway_stations():
    line_filter = clean_text(request.args.get("line", ""))
    query = normalize_search_text(request.args.get("q", ""))
    station_index = get_subway_line_station_index()

    if line_filter:
        station_set = set(station_index.get(line_filter, []))
        for line_name, line_stations in station_index.items():
            if line_name != line_filter and (
                line_name.startswith(line_filter)
                or line_filter.startswith(line_name)
            ):
                station_set.update(line_stations)
        stations = sorted(station_set)
    else:
        stations = sorted({station for stations in station_index.values() for station in stations})

    if query:
        starts = [station for station in stations if normalize_search_text(station).startswith(query)]
        contains = [
            station for station in stations
            if query in normalize_search_text(station)
            and station not in starts
        ]
        stations = starts + contains

    return jsonify({
        "items": [
            {"value": station, "label": f"{station}역"}
            for station in stations[:30]
        ]
    })


@app.route("/api/search/subway-stations")
def api_search_subway_stations():
    return api_options_subway_stations()


@app.route("/api/search/assigned-elementary")
def api_search_assigned_elementary():
    query = normalize_search_text(request.args.get("q", ""))
    names = sorted({name for name in _assigned_elementary_lookup().values() if name})
    if query:
        starts = [n for n in names if normalize_search_text(n).startswith(query)]
        contains = [n for n in names if query in normalize_search_text(n) and n not in starts]
        names = starts + contains
    return jsonify({"items": [{"value": n, "label": n} for n in names[:30]]})


@app.route("/api/search/schools")
def api_search_schools():
    query = normalize_search_text(request.args.get("q", ""))
    level_label = {"middle": "중학교", "high": "고등학교"}
    items = []
    seen = set()
    for row in school_data:
        if row.get("subtype") not in ("middle", "high"):
            continue
        name = clean_text(row.get("name", ""))
        if not name or name in seen:
            continue
        if query and query not in normalize_search_text(name):
            continue
        seen.add(name)
        items.append({"value": name, "label": name, "meta": level_label.get(row.get("subtype"), "")})
    items.sort(key=lambda x: (not normalize_search_text(x["value"]).startswith(query), x["value"]))
    return jsonify({"items": items[:30]})


@app.route("/api/search/bus-routes")
def api_search_bus_routes():
    query = normalize_search_text(request.args.get("q", ""))
    bus_type = clean_text(request.args.get("type", ""))
    by_type = _bus_routes_by_type()
    if bus_type and bus_type in by_type:
        routes = list(by_type[bus_type])
    else:
        seen = set()
        routes = []
        for key in by_type:
            for route in by_type[key]:
                if route not in seen:
                    seen.add(route)
                    routes.append(route)
        routes.sort()
    if query:
        starts = [r for r in routes if normalize_search_text(r).startswith(query)]
        contains = [r for r in routes if query in normalize_search_text(r) and r not in starts]
        routes = starts + contains
    return jsonify({"items": [{"value": r, "label": r} for r in routes[:30]]})


def get_baseline_rows_for_apartment(apartment_name):
    def find_row(rows):
        return next(
            (row for row in rows if clean_text(row.get("name", "")) == clean_text(apartment_name)),
            {},
        )

    return {
        "subway": get_indexed_baseline_row(subway_baseline_index, apartment_name),
        "bus": get_indexed_baseline_row(bus_baseline_index, apartment_name),
        "bike": get_indexed_baseline_row(bike_baseline_index, apartment_name),
        "mart": find_row(mart_baseline_data),
        "convenience": find_row(convenience_baseline_data),
        "cafe": find_row(cafe_baseline_data),
        "medical": get_indexed_baseline_row(medical_baseline_index, apartment_name),
        "academy": get_indexed_baseline_row(academy_baseline_index, apartment_name),
        "nightlife": get_indexed_baseline_row(nightlife_baseline_index, apartment_name),
        "hangang": get_indexed_baseline_row(hangang_baseline_index, apartment_name),
        "culture": get_indexed_baseline_row(culture_baseline_index, apartment_name),
        "ev": get_indexed_baseline_row(ev_charger_baseline_index, apartment_name),
    }


# 학원: 종류(서브타입)별 1km 내 개수. 결과페이지 칩과 동일 분류.
EXPLORE_ACADEMY_TYPES = [
    {"key": "exam", "label": "입시/보습", "column": "exam_count"},
    {"key": "english", "label": "영어", "column": "english_count"},
    {"key": "math", "label": "수학", "column": "math_count"},
    {"key": "arts_sports", "label": "예체능", "column": "arts_sports_count"},
    {"key": "study_room", "label": "독서실", "column": "study_room_count"},
    {"key": "career", "label": "직업/자격", "column": "career_count"},
    {"key": "chinese", "label": "중국어", "column": "chinese_count"},
    {"key": "japanese", "label": "일본어", "column": "japanese_count"},
    {"key": "etc", "label": "기타", "column": "etc_count"},
]
_ACADEMY_TYPE_BY_KEY = {t["key"]: t for t in EXPLORE_ACADEMY_TYPES}
_ACADEMY_KEY_BY_LABEL = {t["label"]: t["key"] for t in EXPLORE_ACADEMY_TYPES}

# Explore 생활 인프라 우선순위 검색 — 카테고리별 서브타입(브랜드/유형)의
# 반경 내 개수 + 최근접 거리 baked 컬럼. 순차 AND 필터 + 선택순서 정렬에 사용.
# Tier 1: 개수 + 서브타입별 최근접 둘 다 보유(정확 구현).
SUBTYPE_SEARCH_CONFIG = {
    "academy": {
        "label": "학원",
        "icon": "📚",
        "radius_label": "반경 1km이내",
        "helper_text": "선택한 종류 학원 수의 합계가 많은 단지가 상위로 추천됩니다.",
        "subtypes": [t["label"] for t in EXPLORE_ACADEMY_TYPES],
    },
    "medical": {
        "label": "의료",
        "icon": "🏥",
        "derived": "medical",
        "radius_label": "반경 500m이내",
        "helper_text": "응급실은 반경 3km이내, 종합병원은 반경 5km이내 기준입니다.",
        "subtypes": ["응급실", "종합병원", "소아과", "산부인과"],
    },
    "culture": {
        "label": "문화",
        "icon": "🎭",
        "derived": "culture",
        "radius_label": "반경 1.5km이내",
        "subtypes": ["공연", "전시", "체육", "키즈", "체험"],
    },
    "park": {
        "label": "공원",
        "icon": "🌳",
        "derived": "park",
        "radius_label": "반경 내 가까운 순",
        "subtypes": ["일반공원", "한강공원", "대형공원"],
    },
    "convenience": {
        "label": "편의점",
        "icon": "🏪",
        "data": convenience_baseline_data,
        "radius_label": "반경 500m이내",
        "subtypes": ["CU", "GS25", "세븐일레븐", "이마트24"],
        "count_col": lambda s: f"{s}_count_500m",
        "nearest_col": lambda s: f"nearest_{s}_distance",
    },
    "super_mart": {
        "label": "슈퍼마켓",
        "icon": "🏪",
        "data": mart_baseline_data,
        "radius_label": "반경 500m이내",
        "subtypes": ["이마트에브리데이", "홈플러스익스프레스", "롯데슈퍼프레시",
                     "노브랜드", "GS더프레시", "하나로마트"],
        "count_col": lambda s: f"{s}_count_500m",
        "nearest_col": lambda s: f"nearest_{s}_distance",
    },
    "large_mart": {
        "label": "대형마트",
        "icon": "🛒",
        "data": mart_baseline_data,
        "radius_label": "반경 3km이내",
        "subtypes": ["이마트", "홈플러스", "롯데마트"],
        "count_col": lambda s: f"{s}_count_3000m",
        "nearest_col": lambda s: f"nearest_{s}_distance",
    },
    "warehouse_mart": {
        "label": "창고형마트",
        "icon": "📦",
        "data": mart_baseline_data,
        "radius_label": "반경 5km이내",
        "subtypes": ["코스트코", "트레이더스"],
        "count_col": lambda s: f"{s}_count_5000m",
        "nearest_col": lambda s: f"nearest_{s}_distance",
    },
    "cafe": {
        "label": "카페",
        "icon": "☕",
        "data": cafe_baseline_data,
        "radius_label": "반경 500m이내",
        "subtypes": ["스타벅스", "투썸플레이스", "메가MGC", "컴포즈커피", "이디야",
                     "빽다방", "할리스", "커피빈", "폴바셋", "엔제리너스"],
        "count_col": lambda s: f"{s}_count_500m",
        "nearest_col": lambda s: f"nearest_{s}_distance",
    },
}

_SUBTYPE_LOOKUP_CACHE = {}


def _subtype_lookup(category):
    """Composite-key {(name,gu,dong): row} map for a subtype-search category,
    built once per process (baselines are loaded in place)."""
    if category not in _SUBTYPE_LOOKUP_CACHE:
        cfg = SUBTYPE_SEARCH_CONFIG.get(category)
        lookup = {}
        for row in (cfg["data"] if cfg else []):
            key = (
                clean_text(row.get("name", "")),
                clean_text(row.get("gu", "")),
                clean_text(row.get("dong", "")),
            )
            lookup[key] = row
        _SUBTYPE_LOOKUP_CACHE[category] = lookup
    return _SUBTYPE_LOOKUP_CACHE[category]


_DERIVED_STATS_CACHE = {}


def _raise_csv_field_limit():
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def _csv_key(row):
    return (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))


def _big_park_nearest_lookup():
    """{(name,gu,dong): 가장 가까운 대형공원(면적 10만㎡+) 거리(m)} — park_data 기반 라이브 계산(캐시)."""
    if "big_park" not in _DERIVED_STATS_CACHE:
        bigs = []
        for park in park_data:
            if park.get("subtype") == "대형공원":
                try:
                    bigs.append((float(park["lat"]), float(park["lng"])))
                except Exception:
                    continue
        result = {}
        for apartment in apartment_data:
            key = _csv_key(apartment)
            try:
                alat, alng = float(apartment["lat"]), float(apartment["lng"])
            except Exception:
                result[key] = None
                continue
            best = None
            for plat, plng in bigs:
                dist = get_distance_m(alat, alng, plat, plng)
                if best is None or dist < best:
                    best = dist
            result[key] = best
        _DERIVED_STATS_CACHE["big_park"] = result
    return _DERIVED_STATS_CACHE["big_park"]


def _derived_category_stats(kind):
    """{(name,gu,dong): {subtype: (count, nearest_distance|None)}} for derived 우선순위
    categories (의료/문화/공원). 캐시."""
    if kind in _DERIVED_STATS_CACHE:
        return _DERIVED_STATS_CACHE[kind]
    _raise_csv_field_limit()
    result = {}

    if kind == "medical":
        # 소아과/산부인과는 도보권(500m) 전체 카운트 컬럼(정확). 응급실(1km)·종합병원(5km)은
        # 차량 이동 시설이라 각자 반경 baked 컬럼 사용. 최근접 거리는 json에서 보강.
        # 진료과 500m 카운트 컬럼이 아직 없는(재빌드 전) CSV는 json 집계로 폴백.
        try:
            with open("data/baseline/medical_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    stats = {
                        "응급실": (to_int(row.get("emergency_count_1km"), 0),
                                 parse_optional_float(row.get("nearest_emergency_distance"))),
                        "종합병원": (to_int(row.get("superior_hospital_count_5km"), 0),
                                  parse_optional_float(row.get("nearest_superior_hospital_distance"))),
                    }
                    try:
                        items = json.loads(row.get("medical_items_json", "[]") or "[]")
                    except Exception:
                        items = []
                    for sub in ("소아과", "산부인과"):
                        near, json_cnt = None, 0
                        for item in items:
                            if clean_text(item.get("subtype", "")) == sub:
                                dist = parse_optional_float(item.get("distance"))
                                if dist is not None and dist <= 500:
                                    json_cnt += 1
                                    if near is None or dist < near:
                                        near = dist
                        col_val = row.get(f"{sub}_count_500m")
                        count = to_int(col_val, 0) if (col_val not in (None, "")) else json_cnt
                        stats[sub] = (count, near)
                    result[_csv_key(row)] = stats
        except Exception:
            pass

    elif kind == "culture":
        colmap = {"공연": "performance_count", "전시": "exhibition_count",
                  "체육": "sports_count", "키즈": "kids_count", "체험": "experience_count"}
        try:
            with open("data/baseline/culture_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    near = parse_optional_float(row.get("nearest_culture_distance"))
                    result[_csv_key(row)] = {
                        label: (to_int(row.get(col), 0), near) for label, col in colmap.items()
                    }
        except Exception:
            pass

    elif kind == "park":
        park_dist = {}
        try:
            with open("data/baseline/park_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    park_dist[_csv_key(row)] = parse_optional_float(row.get("park_distance"))
        except Exception:
            pass
        hangang_dist = {}
        try:
            with open("data/baseline/hangang_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    hangang_dist[_csv_key(row)] = parse_optional_float(row.get("nearest_hangang_distance"))
        except Exception:
            pass
        big = _big_park_nearest_lookup()
        keys = set(park_dist) | set(hangang_dist) | set(big)
        for key in keys:
            pdist = park_dist.get(key)
            hdist = hangang_dist.get(key)
            bdist = big.get(key)
            result[key] = {
                "일반공원": (1 if (pdist is not None and pdist <= 1000) else 0, pdist),
                "한강공원": (1 if (hdist is not None and hdist <= 3000) else 0, hdist),
                "대형공원": (1 if (bdist is not None and bdist <= 3000) else 0, bdist),
            }

    _DERIVED_STATS_CACHE[kind] = result
    return result


def parse_priorities(raw_list):
    """Parse ordered 'category:subtype' priority params. Dedupes identical
    (category, subtype) pairs (same subtype twice is rejected); same category
    with different subtypes is allowed. Invalid entries are dropped."""
    priorities = []
    seen = set()
    for raw in raw_list or []:
        text = clean_text(raw)
        if ":" not in text:
            continue
        category, subtype = text.split(":", 1)
        category = category.strip()
        subtype = subtype.strip()
        cfg = SUBTYPE_SEARCH_CONFIG.get(category)
        if not cfg or subtype not in cfg["subtypes"]:
            continue
        if subtype in seen:        # same subtype must not repeat
            continue
        seen.add(subtype)
        priorities.append((category, subtype))
    return priorities


# Explore 기본 검색 — 평수(전용 ㎡ 4구간 세대수) / 가격(최근1년 평균매매가, 만원).
EXPLORE_AREA_BUCKETS = [
    {"key": "u60", "label": "전용 60㎡ 이하", "column": "area_under_60"},
    {"key": "60_85", "label": "전용 60~85㎡", "column": "area_60_85"},
    {"key": "85_135", "label": "전용 85~135㎡", "column": "area_85_135"},
    {"key": "o135", "label": "전용 135㎡ 초과", "column": "area_over_135"},
]
_AREA_BUCKET_COL = {b["key"]: b["column"] for b in EXPLORE_AREA_BUCKETS}

# 가격: 거래유형(매매/전세)별 금액 구간(만원). 평균값 기준이라 경계는 [min, max) 반열림.
EXPLORE_TRADE_BUCKETS = [
    {"key": "u100000", "label": "10억 이하", "min": None, "max": 100000},
    {"key": "100000_150000", "label": "10억 초과 15억 이하", "min": 100000, "max": 150000},
    {"key": "150000_200000", "label": "15억 초과 20억 이하", "min": 150000, "max": 200000},
    {"key": "200000_300000", "label": "20억 초과 30억 이하", "min": 200000, "max": 300000},
    {"key": "300000_350000", "label": "30억 초과 35억 이하", "min": 300000, "max": 350000},
    {"key": "o350000", "label": "35억 초과", "min": 350000, "max": None},
]
EXPLORE_JEONSE_BUCKETS = [
    {"key": "u30000", "label": "3억 미만", "min": None, "max": 30000},
    {"key": "30000_50000", "label": "3억 이상 5억 미만", "min": 30000, "max": 50000},
    {"key": "50000_70000", "label": "5억 이상 7억 미만", "min": 50000, "max": 70000},
    {"key": "70000_100000", "label": "7억 이상 10억 미만", "min": 70000, "max": 100000},
    {"key": "100000_150000", "label": "10억 이상 15억 미만", "min": 100000, "max": 150000},
    {"key": "o150000", "label": "15억 이상", "min": 150000, "max": None},
]
EXPLORE_PRICE_TYPE_OPTIONS = [
    {"key": "trade", "label": "매매", "column": "avg_trade_amount_1y", "buckets": EXPLORE_TRADE_BUCKETS},
    {"key": "jeonse", "label": "전세", "column": "avg_rent_deposit_1y", "buckets": EXPLORE_JEONSE_BUCKETS},
]
_PRICE_TYPE_COL = {t["key"]: t["column"] for t in EXPLORE_PRICE_TYPE_OPTIONS}
_PRICE_BUCKET_BY_TYPE = {
    t["key"]: {b["key"]: b for b in t["buckets"]} for t in EXPLORE_PRICE_TYPE_OPTIONS
}

# (공원은 우선순위 카테고리로 이동) — 단일지표 임계 필터 슬롯(현재 없음).
EXPLORE_RANGE_FILTERS = []

# 버스: 노선유형(간선/지선/마을/심야/공항/기타)별 번호 검색 — 지하철 노선/역과 동일 컨셉.
EXPLORE_BUS_TYPES = ["간선", "지선", "마을", "심야", "공항", "기타"]

_EXPLORE_LOOKUP_CACHE = {}


def _assigned_elementary_lookup():
    """{(name,gu,dong): 대표배정초 이름} from school_zone baseline."""
    if "assigned_elem" not in _EXPLORE_LOOKUP_CACHE:
        lookup = {}
        for row in school_zone_baseline_data:
            key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
            lookup[key] = clean_text(row.get("assigned_elementary_school", ""))
        _EXPLORE_LOOKUP_CACHE["assigned_elem"] = lookup
    return _EXPLORE_LOOKUP_CACHE["assigned_elem"]


def _midhigh_school_coords(school_name):
    """(lat, lng) of a middle/high school by exact name, else None."""
    target = clean_text(school_name)
    if not target:
        return None
    for row in school_data:
        if row.get("subtype") in ("middle", "high") and clean_text(row.get("name", "")) == target:
            try:
                return (float(row["lat"]), float(row["lng"]))
            except Exception:
                return None
    return None


def _transaction_price_lookup():
    """{(name,gu,dong): {"trade": 평균매매가, "jeonse": 평균전세보증금}} (만원, float|None)."""
    if "price" not in _EXPLORE_LOOKUP_CACHE:
        lookup = {}
        try:
            with open("data/baseline/transaction_summary.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
                    lookup[key] = {
                        "trade": parse_optional_float(row.get("avg_trade_amount_1y")),
                        "jeonse": parse_optional_float(row.get("avg_rent_deposit_1y")),
                    }
        except Exception:
            pass
        _EXPLORE_LOOKUP_CACHE["price"] = lookup
    return _EXPLORE_LOOKUP_CACHE["price"]


def _representative_area_lookup():
    """{(name,gu,dong): (대표평형 라벨, 그 평형 최근 거래가 만원float)} — 거래 최다 평형 기준."""
    if "rep_area" not in _EXPLORE_LOOKUP_CACHE:
        limit = sys.maxsize
        while True:
            try:
                csv.field_size_limit(limit)
                break
            except OverflowError:
                limit = int(limit / 10)
        lookup = {}
        try:
            with open("data/baseline/transaction_summary.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
                    raw = row.get("transaction_area_summary_json", "")
                    try:
                        items = json.loads(raw) if raw else []
                    except Exception:
                        items = []
                    best = None  # (sale_count, area_label, latest_sale)
                    for item in items:
                        sale_count = to_int(item.get("sale_count"), 0)
                        latest_sale = parse_optional_float(item.get("latest_sale"))
                        if sale_count <= 0 or latest_sale is None:
                            continue
                        if best is None or sale_count > best[0]:
                            best = (sale_count, clean_text(item.get("area_label", "")), latest_sale)
                    if best:
                        lookup[key] = (best[1], best[2])
        except Exception:
            pass
        _EXPLORE_LOOKUP_CACHE["rep_area"] = lookup
    return _EXPLORE_LOOKUP_CACHE["rep_area"]


def _baseline_metric_lookup(cache_key, filename, column):
    """{(name,gu,dong): float|None} for one baseline column, cached per process."""
    if cache_key not in _EXPLORE_LOOKUP_CACHE:
        limit = sys.maxsize
        while True:
            try:
                csv.field_size_limit(limit)
                break
            except OverflowError:
                limit = int(limit / 10)
        lookup = {}
        try:
            with open(f"data/baseline/{filename}", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
                    lookup[key] = parse_optional_float(row.get(column))
        except Exception:
            pass
        _EXPLORE_LOOKUP_CACHE[cache_key] = lookup
    return _EXPLORE_LOOKUP_CACHE[cache_key]


def _academy_subtype_lookup():
    """{(name,gu,dong): {subtype_key: count(int)}} — 1km 내 학원 종류별 개수(캐시)."""
    if "academy_subtypes" not in _EXPLORE_LOOKUP_CACHE:
        limit = sys.maxsize
        while True:
            try:
                csv.field_size_limit(limit)
                break
            except OverflowError:
                limit = int(limit / 10)
        lookup = {}
        try:
            with open("data/baseline/academy_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
                    lookup[key] = {t["key"]: to_int(row.get(t["column"]), 0) for t in EXPLORE_ACADEMY_TYPES}
        except Exception:
            pass
        _EXPLORE_LOOKUP_CACHE["academy_subtypes"] = lookup
    return _EXPLORE_LOOKUP_CACHE["academy_subtypes"]


def _bus_route_lookup():
    """{(name,gu,dong): {subtype: set(노선번호)}} — 500m 내 버스, bus_items_json 파싱(캐시).
    label 형식 '정류장 · 노선1, 노선2'에서 마지막 '·' 뒤를 노선 목록으로 사용."""
    if "bus_routes" not in _EXPLORE_LOOKUP_CACHE:
        limit = sys.maxsize
        while True:
            try:
                csv.field_size_limit(limit)
                break
            except OverflowError:
                limit = int(limit / 10)
        lookup = {}
        try:
            with open("data/baseline/bus_baseline.csv", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    key = (clean_text(row.get("name", "")), clean_text(row.get("gu", "")), clean_text(row.get("dong", "")))
                    raw = row.get("bus_items_json", "")
                    try:
                        items = json.loads(raw) if raw else []
                    except Exception:
                        items = []
                    by_type = lookup.setdefault(key, {})
                    for item in items:
                        subtype = clean_text(item.get("subtype", ""))
                        label = item.get("label", "") or ""
                        routes_part = label.rsplit("·", 1)[-1] if "·" in label else ""
                        for route in routes_part.split(","):
                            route = clean_text(route)
                            if subtype and route:
                                by_type.setdefault(subtype, set()).add(route)
        except Exception:
            pass
        _EXPLORE_LOOKUP_CACHE["bus_routes"] = lookup
    return _EXPLORE_LOOKUP_CACHE["bus_routes"]


def _bus_routes_by_type():
    """{subtype: sorted([노선번호…])} — 자동완성용 서울 전체 집계(캐시)."""
    if "bus_routes_by_type" not in _EXPLORE_LOOKUP_CACHE:
        agg = {}
        for by_type in _bus_route_lookup().values():
            for subtype, routes in by_type.items():
                agg.setdefault(subtype, set()).update(routes)
        _EXPLORE_LOOKUP_CACHE["bus_routes_by_type"] = {k: sorted(v) for k, v in agg.items()}
    return _EXPLORE_LOOKUP_CACHE["bus_routes_by_type"]


def build_explore_results(filters, limit=10):
    no_nightlife = bool(filters.get("no_nightlife"))
    gu_filter = clean_text(filters.get("gu", ""))
    dong_filter = clean_text(filters.get("dong", ""))
    line_filter = clean_text(filters.get("line", ""))
    station_filter = clean_text(filters.get("station", "")).replace("역", "")
    priorities = filters.get("priorities", [])

    assigned_elem = clean_text(filters.get("assigned_elementary", ""))
    school_mh = clean_text(filters.get("school", ""))
    area_buckets = [b for b in (filters.get("area_buckets", []) or []) if b in _AREA_BUCKET_COL]
    price_type = clean_text(filters.get("price_type", "")) or "trade"
    if price_type not in _PRICE_BUCKET_BY_TYPE:
        price_type = "trade"
    price_bucket = _PRICE_BUCKET_BY_TYPE[price_type].get(clean_text(filters.get("price", "")))

    # 공원 임계값 선택 파싱
    range_selections = []
    for cfg in EXPLORE_RANGE_FILTERS:
        raw = clean_text(filters.get(cfg["param"], ""))
        opt = next((o for o in cfg["options"] if o["key"] == raw), None)
        if opt:
            range_selections.append((cfg, opt))

    # 버스 노선유형/번호
    bus_type = clean_text(filters.get("bus_type", ""))
    if bus_type not in EXPLORE_BUS_TYPES:
        bus_type = ""
    bus_route = clean_text(filters.get("bus_route", ""))

    # 중/고 선택 시 학교 좌표를 1회 확보(없으면 결과 없음)
    school_coords = _midhigh_school_coords(school_mh) if school_mh else None
    if school_mh and school_coords is None:
        return []

    results = []

    for apartment in apartment_data:
        name = clean_text(apartment.get("name", ""))
        gu = clean_text(apartment.get("gu", ""))
        dong = clean_text(apartment.get("dong", ""))

        if gu_filter and gu_filter != gu:
            continue
        if dong_filter and dong_filter != dong:
            continue

        # Explore는 subway/medical만 사용 — 전체 카테고리(mart/convenience/cafe 선형스캔)
        # 를 만드는 get_baseline_rows_for_apartment 대신 인덱스(O(1)) 직접 조회.
        subway = get_indexed_baseline_row(subway_baseline_index, name, gu, dong) or {}
        matched = []
        score = 0

        if line_filter:
            line_text = str(subway.get("nearest_subway_lines", "")) + " " + str(subway.get("subway_items_json", ""))
            if line_filter not in line_text:
                continue
            matched.append(f"{line_filter} 접근")
            score += 3

        if station_filter:
            station_text = str(subway.get("nearest_subway_name", "")) + " " + str(subway.get("subway_items_json", ""))
            if station_filter not in station_text:
                continue
            matched.append(f"{station_filter}역 접근")
            score += 3

        # 유흥시설 없음: 500m 내 유흥시설이 0곳인 단지만
        if no_nightlife:
            nightlife_count = _baseline_metric_lookup(
                "nightlife500", "nightlife_baseline.csv", "nightlife_count_500m"
            ).get((name, gu, dong))
            if nightlife_count is None or nightlife_count > 0:
                continue
            matched.append("🍺 반경 500m이내 유흥시설 없음")
            score += 1

        # 대표배정초: 해당 학교가 이 단지의 대표배정초인 경우만
        if assigned_elem:
            if _assigned_elementary_lookup().get((name, gu, dong), "") != assigned_elem:
                continue
            matched.append(f"🏫 {assigned_elem} 배정")
            score += 2

        # 중/고: 선택한 학교가 반경 1,500m 내인 단지만
        if school_coords:
            try:
                school_dist = get_distance_m(
                    float(apartment.get("lat")), float(apartment.get("lng")),
                    school_coords[0], school_coords[1],
                )
            except Exception:
                continue
            if school_dist > 1500:
                continue
            matched.append(f"🏫 {school_mh} {int(round(school_dist)):,}m")
            score += 2

        # 평수: 선택 전용면적 구간 중 하나라도 세대가 있는 단지(OR)
        if area_buckets:
            if not any(to_int(apartment.get(_AREA_BUCKET_COL[b]), 0) > 0 for b in area_buckets):
                continue

        # 가격: 거래유형(매매/전세)별 최근1년 평균 구간(거래 없는 단지는 제외)
        if price_bucket:
            price = (_transaction_price_lookup().get((name, gu, dong)) or {}).get(price_type)
            if price is None:
                continue
            if price_bucket["min"] is not None and price < price_bucket["min"]:
                continue
            if price_bucket["max"] is not None and price >= price_bucket["max"]:
                continue
            type_label = "전세" if price_type == "jeonse" else "매매"
            matched.append(f"💰 {type_label} {price_bucket['label']}")
            score += 1

        # 공원: 반경 내 공원 유무(park_distance ≤ 반경) AND 필터(데이터 없으면 제외)
        if range_selections:
            range_ok = True
            for cfg, opt in range_selections:
                val = _baseline_metric_lookup(cfg["param"], cfg["file"], cfg["column"]).get((name, gu, dong))
                if val is None:
                    range_ok = False
                    break
                if cfg["mode"] == "min" and val < opt["value"]:
                    range_ok = False
                    break
                if cfg["mode"] == "max" and val > opt["value"]:
                    range_ok = False
                    break
                matched.append(f"{cfg['icon']} {cfg['label']} {int(round(val))}{cfg['suffix']}")
                score += 1
            if not range_ok:
                continue

        # 버스: 노선유형/번호 — 500m 내 해당 노선(유형 지정 시 그 유형) 보유 단지만
        if bus_route or bus_type:
            by_type = _bus_route_lookup().get((name, gu, dong), {})
            if bus_route:
                if bus_type:
                    has_route = bus_route in by_type.get(bus_type, set())
                else:
                    has_route = any(bus_route in routes for routes in by_type.values())
                if not has_route:
                    continue
                prefix = f"{bus_type} " if bus_type else ""
                matched.append(f"🚌 {prefix}{bus_route}")
                score += 2
            else:  # 유형만 선택 → 해당 유형 노선이 하나라도 있는 단지
                if not by_type.get(bus_type):
                    continue
                matched.append(f"🚌 {bus_type}버스")
                score += 1

        # 생활 인프라 우선순위: 순차 AND 필터(서브타입 보유 = 반경 내 개수 >= 1) +
        # 선택순서 정렬키(개수 DESC, 최근접 거리 ASC).
        sort_key = None
        if priorities:
            sort_parts = []
            priority_ok = True
            for category, subtype in priorities:
                cfg = SUBTYPE_SEARCH_CONFIG[category]
                if category == "academy":
                    academy_key = _ACADEMY_KEY_BY_LABEL.get(subtype, "")
                    arow = _academy_subtype_lookup().get((name, gu, dong)) or {}
                    count = arow.get(academy_key, 0)
                    sort_parts.append(-count)
                    if count > 0:
                        matched.append(f"{cfg['icon']} {subtype} {count}곳")
                    continue
                if cfg.get("derived"):
                    stats = _derived_category_stats(cfg["derived"]).get((name, gu, dong)) or {}
                    count, nearest = stats.get(subtype, (0, None))
                else:
                    row = _subtype_lookup(category).get((name, gu, dong)) or {}
                    count = to_int(row.get(cfg["count_col"](subtype)), 0)
                    nearest = parse_optional_float(row.get(cfg["nearest_col"](subtype)))
                if count < 1:                    # AND: 해당 서브타입 미보유/반경 밖 → 제외
                    priority_ok = False
                    break
                sort_parts.append(-count)
                sort_parts.append(nearest if nearest is not None else float("inf"))
                if cfg.get("derived") == "park":
                    dist_label = f"{int(round(nearest))}m" if nearest is not None else "-"
                    matched.append(f"{cfg['icon']} {subtype} {dist_label}")
                else:
                    matched.append(f"{cfg['icon']} {subtype} {count}곳")
            if not priority_ok:
                continue
            sort_key = tuple(sort_parts)

        subway_distance = insight_to_number(subway.get("subway_distance"))
        if subway_distance is not None and subway_distance <= 800:
            score += 1

        medical = get_indexed_baseline_row(medical_baseline_index, name, gu, dong) or {}
        if insight_to_number(medical.get("nearest_emergency_distance")) is not None:
            score += 1

        results.append({
            "name": name,
            "gu": gu,
            "dong": dong,
            "score": score,
            "sort_key": sort_key,
            "matched_features": matched[:5] or ["생활 균형형"],
            "url": make_result_url(name, get_preferences(), gu, dong, src="explore"),
        })

    def order_key(item):
        parts = []
        if priorities:                     # 그 다음 선택 순서 우선순위(개수 DESC, 최근접 ASC)
            parts.append(item["sort_key"])
        else:
            parts.append(-item["score"])
        parts.extend([item["gu"], item["dong"], item["name"]])
        return tuple(parts)

    results.sort(key=order_key)
    return results[:limit]


def top_rows_from_baseline(rows, metric, reverse=False, limit=10, label=None):
    items = []

    for row in rows:
        value = insight_to_number(row.get(metric))
        if value is None:
            continue
        items.append({
            "name": row.get("name", ""),
            "gu": row.get("gu", ""),
            "dong": row.get("dong", ""),
            "value": value,
            "value_label": label(value) if label else format_debug_value(value, metric),
            "url": make_result_url(row.get("name", ""), get_preferences(), row.get("gu", ""), row.get("dong", "")),
        })

    items.sort(key=lambda item: item["value"], reverse=reverse)
    return items[:limit]


def build_lifestyle_ranking_sections():
    return [
        {
            "title": "의료안심형 TOP 10",
            "description": "1km 내 의료 접근성이 높은 단지",
            "items": top_rows_from_baseline(medical_baseline_data, "medical_count_1km", reverse=True, limit=10, label=lambda v: f"{int(v):,}곳"),
        },
        {
            "title": "환승역 접근 TOP 10",
            "description": "1km 내 환승역 접근성이 좋은 단지",
            "items": top_rows_from_baseline(subway_baseline_data, "nearest_transfer_distance", reverse=False, limit=10),
        },
        {
            "title": "응급실 접근 TOP 10",
            "description": "가까운 응급실까지의 거리가 짧은 단지",
            "items": top_rows_from_baseline(medical_baseline_data, "nearest_emergency_distance", reverse=False, limit=10),
        },
        {
            "title": "한강라이프형 TOP 10",
            "description": "가까운 한강공원 접근성이 좋은 단지",
            "items": top_rows_from_baseline(hangang_baseline_data, "nearest_hangang_distance", reverse=False, limit=10),
        },
        {
            "title": "유흥 적은 주거형 TOP 10",
            "description": "500m 내 유흥시설 수가 적은 단지",
            "items": top_rows_from_baseline(nightlife_baseline_data, "nightlife_count_500m", reverse=False, limit=10, label=lambda v: f"{int(v):,}곳"),
        },
    ]


@app.route("/explore")
def explore():
    priority_args = request.args.getlist("priority")
    for legacy_academy_key in request.args.getlist("academy"):
        academy_type = _ACADEMY_TYPE_BY_KEY.get(clean_text(legacy_academy_key))
        if academy_type:
            priority_args.append(f"academy:{academy_type['label']}")

    filters = {
        "gu": request.args.get("gu", ""),
        "dong": request.args.get("dong", ""),
        "line": request.args.get("line", ""),
        "station": request.args.get("station", ""),
        "no_nightlife": request.args.get("no_nightlife", ""),
        "priorities": parse_priorities(priority_args),
        "assigned_elementary": request.args.get("assigned_elementary", ""),
        "school": request.args.get("school", ""),
        "area_buckets": request.args.getlist("area"),
        "price_type": request.args.get("price_type", ""),
        "price": request.args.get("price", ""),
        "bus_type": request.args.get("bus_type", ""),
        "bus_route": request.args.get("bus_route", ""),
    }
    gu_options = sorted({clean_text(item.get("gu", "")) for item in apartment_data if clean_text(item.get("gu", ""))})
    dong_options = sorted({
        clean_text(item.get("dong", ""))
        for item in apartment_data
        if clean_text(item.get("dong", ""))
        and (not filters["gu"] or clean_text(item.get("gu", "")) == filters["gu"])
    })

    results = build_explore_results(filters)

    # 가격 거래유형 정규화(템플릿 선택 상태/구간 표시용)
    price_type = clean_text(filters["price_type"]) or "trade"
    if price_type not in _PRICE_BUCKET_BY_TYPE:
        price_type = "trade"
    filters["price_type"] = price_type
    current_price_buckets = next(
        t["buckets"] for t in EXPLORE_PRICE_TYPE_OPTIONS if t["key"] == price_type
    )
    price_buckets_by_type = {t["key"]: t["buckets"] for t in EXPLORE_PRICE_TYPE_OPTIONS}

    subtype_search_options = [
        {
            "key": category,
            "label": cfg["label"],
            "icon": cfg["icon"],
            "radius_label": cfg["radius_label"],
            "helper_text": cfg.get("helper_text", ""),
            "subtypes": cfg["subtypes"],
        }
        for category, cfg in SUBTYPE_SEARCH_CONFIG.items()
    ]
    selected_priorities = [
        {
            "category": category,
            "subtype": subtype,
            "label": SUBTYPE_SEARCH_CONFIG[category]["label"],
            "icon": SUBTYPE_SEARCH_CONFIG[category]["icon"],
        }
        for category, subtype in filters["priorities"]
    ]

    return render_template(
        "explore.html",
        filters=filters,
        results=results,
        gu_options=gu_options,
        dong_options=dong_options,
        subway_line_options=get_subway_line_options(),
        subtype_search_options=subtype_search_options,
        selected_priorities=selected_priorities,
        area_bucket_options=EXPLORE_AREA_BUCKETS,
        price_type_options=EXPLORE_PRICE_TYPE_OPTIONS,
        current_price_buckets=current_price_buckets,
        price_buckets_by_type=price_buckets_by_type,
        range_filter_options=EXPLORE_RANGE_FILTERS,
        bus_type_options=EXPLORE_BUS_TYPES,
    )


@app.route("/ranking")
def ranking():
    return render_template(
        "ranking.html",
        ranking_sections=build_lifestyle_ranking_sections(),
    )


@app.route("/result")
def result():
    apartment_name = request.args.get("apartment", "헬리오시티")
    apartment_gu = request.args.get("gu", "")
    apartment_dong = request.args.get("dong", "")
    apartment = get_apartment(apartment_name, apartment_gu, apartment_dong)

    if apartment is None:
        return render_template("index.html"), 404

    school_zone = get_school_zone_for_apartment(apartment)

    scores = apartment["scores"]
    preferences = get_preferences()
    
    kakao_result_mode = os.getenv("LIVEFIT_KAKAO_RESULT_MODE", "").strip().lower()
    legacy_kakao_enabled = os.getenv("LIVEFIT_ENABLE_KAKAO_RESULT", "").strip() == "1"

    if kakao_result_mode == "off":
        real_pois = []
    elif kakao_result_mode == "all" or legacy_kakao_enabled:
        real_pois = get_real_pois(
            apartment["lat"],
            apartment["lng"],
            categories=KAKAO_RESULT_ALL_CATEGORIES,
        )
    else:
        real_pois = []
        if KAKAO_RESULT_FALLBACK_CATEGORIES:
            real_pois = get_real_pois(
                apartment["lat"],
                apartment["lng"],
                categories=KAKAO_RESULT_FALLBACK_CATEGORIES,
            )

    if real_pois:
        pois = real_pois
    else:
        pois = get_sample_pois(apartment)

    nearby_cctvs = filter_pois_by_radius(
        cctv_data,
        apartment["lat"],
        apartment["lng"],
        500
    )

    pois = pois + nearby_cctvs

    nearby_parks = filter_pois_by_radius(
        park_data,
        apartment["lat"],
        apartment["lng"],
        1500
    )

    pois = pois + nearby_parks

    apartment_index = build_apartment_index()

    apartment_key = (
        apartment["name"],
        apartment["district"],
        apartment["dong"],
    )

    ranking_apartment = apartment_index.get(apartment_key)
    base_category_scores = ranking_apartment["category_scores"] if ranking_apartment else {}

    if ranking_apartment:
        preference_score = calculate_weighted_score(
            base_category_scores,
            preferences
        )
    else:
        preference_score = 0

    # 진입경로(home/explore)별 우측 패널 분기
    entry_src = "explore" if request.args.get("src") == "explore" else "home"
    domain_profile = compute_domain_profile(base_category_scores)
    representative_score = domain_profile["representative"]

    if entry_src == "explore":
        recommendations = get_nearby_apartments(apartment)
        recommendations_title = "인근 아파트 단지"
        recommendations_note = "이 단지와 가까운 순으로 추천합니다."
    else:
        recommendations = get_similar_apartments(apartment_key, base_category_scores)
        recommendations_title = "유사 추천 단지"
        recommendations_note = "점수나 가격 유사도에 따른 추천단지입니다."

    top_apartments = get_top_apartments(preferences)
    apartment_with_real_pois = {
        **apartment,
        "pois": pois,
    }

    category_summaries = get_category_summaries(
        apartment_with_real_pois,
        PREFERENCE_KEYS
    )

    _mart_group_keys = {"large_mart", "super_mart", "warehouse_mart"}
    baked_poi_summaries = [
        summary for summary in category_summaries
        if summary.get("key") in ({"cafe", "convenience"} | _mart_group_keys)
    ]
    if baked_poi_summaries:
        # 마트 그룹 카드의 라이브 POI 카테고리는 "mart"이므로 함께 제거한다.
        drop_categories = set()
        for summary in baked_poi_summaries:
            skey = summary.get("key")
            drop_categories.add("mart" if skey in _mart_group_keys else skey)
        pois = [
            poi for poi in pois
            if poi.get("category") not in drop_categories
        ]
        for summary in baked_poi_summaries:
            pois = pois + (summary.get("pois") or [])

    subway_info = build_subway_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    if subway_info:
        subway_summary = build_subway_category_summary(subway_info)
        if subway_summary:
            category_summaries = [
                summary for summary in category_summaries
                if summary.get("key") != "subway"
            ]
            category_summaries.insert(0, subway_summary)

    bus_info = build_bus_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    bike_info = build_bike_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    ev_charger_info = build_ev_charger_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    medical_info = build_medical_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    hangang_info = build_hangang_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    commercial_info = build_commercial_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    shopping_info = build_shopping_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    nightlife_info = build_nightlife_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    academy_info = build_academy_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    school_environment_info = build_school_environment_info(
        apartment,
        school_zone,
    )

    culture_info = build_culture_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    fire_station_info = build_fire_station_info(
        apartment["name"], apartment["district"], apartment["dong"]
    )

    complex_info = build_complex_info(
        apartment,
        school_zone,
        category_summaries
    )

    preference_tags = get_preference_tags(
        preferences,
        category_summaries,
        apartment
    )
    if subway_info:
        pois = [
            poi for poi in pois
            if poi.get("category") != "subway"
        ]
        pois = pois + build_subway_map_pois(subway_info)

    if bus_info:
        pois = pois + build_bus_map_pois(apartment)

    if bike_info:
        pois = pois + build_bike_map_pois(bike_info)

    if ev_charger_info:
        pois = pois + build_ev_charger_map_pois(ev_charger_info)

    if medical_info:
        pois = [
            poi for poi in pois
            if poi.get("category") not in ["hospital", "pharmacy"]
        ]
        pois = pois + build_medical_map_pois(medical_info)

    if hangang_info:
        pois = pois + build_hangang_map_pois(hangang_info)

    if commercial_info:
        pois = pois + build_commercial_map_pois(commercial_info)

    if shopping_info:
        pois = pois + build_shopping_map_pois(shopping_info)

    if nightlife_info:
        pois = pois + build_nightlife_map_pois(nightlife_info)

    if academy_info:
        pois = pois + build_academy_map_pois(academy_info)

    if school_environment_info:
        pois = pois + build_school_environment_map_pois(school_environment_info)

    if culture_info:
        pois = pois + build_culture_map_pois(culture_info)

    if fire_station_info:
        pois = pois + build_fire_station_map_pois(fire_station_info)

    apartment_with_real_pois = {
        **apartment,
        "pois": pois,
    }

    domain_summaries = get_domain_summaries(category_summaries)

    category_summaries, preference_tags, domain_summaries = apply_bus_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        bus_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_bike_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        bike_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_ev_charger_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        ev_charger_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_medical_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        medical_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_hangang_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        hangang_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_academy_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        academy_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_school_environment_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        school_environment_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_culture_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        culture_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_fire_station_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        fire_station_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_nightlife_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        nightlife_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_commercial_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        commercial_info,
        apartment,
    )

    category_summaries, preference_tags, domain_summaries = apply_shopping_baseline_to_ui(
        category_summaries,
        preference_tags,
        domain_summaries,
        shopping_info,
        apartment,
    )

    normalize_summary_sources(category_summaries, domain_summaries)

    apply_result_percentile_labels(
        category_summaries,
        preference_tags,
        domain_summaries,
        apartment.get("district", ""),
    )

    enhance_category_summaries(category_summaries)

    insight = build_apartment_insight(
        apartment,
        category_summaries,
        preference_tags,
        complex_info,
    )
    insight = build_score_based_insight(apartment, category_summaries, insight)

    try:
        transaction_summary = get_transaction_summary(apartment)
    except Exception as exc:
        print(f"[TRANSACTION] result integration failed: {exc}")
        transaction_summary = empty_transaction_summary("integration_failed")

    lifestyle_summary = (
        build_lifestyle_summary(category_summaries) if entry_src == "explore" else None
    )

    # 카테고리 상세 카드를 가치판단 중요도 순으로 정렬(지하철·버스·교육·학원 …).
    category_summaries = sort_category_summaries(category_summaries)

    return render_template(
        "result.html",
        apartment=apartment,
        scores=scores,
        preferences=preferences,
        preference_score=preference_score,
        top_apartments=top_apartments,
        entry_src=entry_src,
        representative_score=representative_score,
        domain_profile=domain_profile,
        recommendations=recommendations,
        recommendations_title=recommendations_title,
        recommendations_note=recommendations_note,
        lifestyle_summary=lifestyle_summary,
        preference_tags=preference_tags,
        category_summaries=category_summaries,
        pois=pois,
        kakao_javascript_key=KAKAO_JAVASCRIPT_KEY,
        domain_summaries=domain_summaries,
        school_zone=school_zone,
        complex_info=complex_info,
        insight=insight,
        bus_info=bus_info,
        bike_info=bike_info,
        ev_charger_info=ev_charger_info,
        medical_info=medical_info,
        hangang_info=hangang_info,
        commercial_info=commercial_info,
        shopping_info=shopping_info,
        nightlife_info=nightlife_info,
        academy_info=academy_info,
        school_environment_info=school_environment_info,
        culture_info=culture_info,
        fire_station_info=fire_station_info,
        transaction_summary=transaction_summary,
    )


if __name__ == "__main__":
    app.run(debug=True)

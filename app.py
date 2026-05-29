import json
import csv
import sys
import re

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

KAKAO_RESULT_FALLBACK_CATEGORIES = (
    "cafe",
    "convenience",
    "mart",
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
    "mart",
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
    "cctv": "🛡️",
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
        name = hangang_park_name(text)
        return f"🌊 {name}" if name else ""
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
    list_icon_keys = {"hangang"}

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
        features.append({
            "icon": NEAREST_ICON_BY_CATEGORY.get(summary.get("key"), "•"),
            "label": f"{compact_label(summary.get('label'))} {suffix}",
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
        return ""

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


def build_subway_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(subway_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("subway_items_json", "[]")
    items_500m_raw = row.get("subway_items_500m_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"
    if items_500m_raw is None or isinstance(items_500m_raw, float):
        items_500m_raw = "[]"

    try:
        items = json.loads(str(items_raw))
    except Exception:
        items = []
    try:
        items_500m = json.loads(str(items_500m_raw))
    except Exception:
        items_500m = []

    try:
        items = sorted(
            items,
            key=lambda item: int(float(item.get("distance", 999999)))
        )
    except Exception:
        pass
    try:
        items_500m = sorted(
            items_500m,
            key=lambda item: int(float(item.get("distance", 999999)))
        )
    except Exception:
        pass

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

    bus_items_raw = row.get("bus_items_json", "[]")

    if bus_items_raw is None:
        bus_items_raw = "[]"

    if isinstance(bus_items_raw, float):
        bus_items_raw = "[]"

    try:
        bus_items = json.loads(str(bus_items_raw))
    except:
        bus_items = []
    
    try:
        bus_items = sorted(
            bus_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except:
        pass

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

    for name, count in chip_sources:
        try:
            count = int(float(count))
        except:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
        "seoul_percentile": get_baseline_percentile(row, "bus_stop_count_500m_seoul_percentile"),
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


def get_primary_bus_subtype(routes):
    subtype_priority = ["광역", "간선", "지선", "마을", "심야", "공항", "기타"]
    subtype_set = {
        BUS_TYPE_LABELS.get(classify_bus_route_type(route), "기타")
        for route in routes
    }

    for subtype in subtype_priority:
        if subtype in subtype_set:
            return subtype

    return "기타"


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
        subtype = get_primary_bus_subtype(routes)
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

    items_raw = row.get("hangang_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        hangang_items = json.loads(str(items_raw))
    except Exception:
        hangang_items = []

    try:
        hangang_items = sorted(
            hangang_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

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
    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not hangang_info:
        return []

    map_pois = []

    for item in hangang_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = str(item.get("park_name") or item.get("label", "한강공원")).replace("🌊", "").strip()

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "hangang",
            "label": f"🌊 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": item.get("subtype", "한강공원"),
            "source": "서울시 한강공원 시설현황",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "hangang"
    ]

    if hangang_summary:
        result = []
        inserted = False

        for summary in category_summaries:
            result.append(summary)

            if summary.get("key") == "park":
                result.append(hangang_summary)
                inserted = True

        if not inserted:
            result.append(hangang_summary)

        category_summaries = result

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "hangang"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "hangang"
        ]

    if not hangang_info or not hangang_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "hangang",
        "label": "🌊 한강공원",
        "value": old_hangang_tag.get("value", 3) if old_hangang_tag else 3,
        "level": old_hangang_tag.get("level", "보통") if old_hangang_tag else "보통",
        "level_class": old_hangang_tag.get("level_class", "level-normal") if old_hangang_tag else "level-normal",
        "radius": 3000,
        "count": hangang_info.get("hangang_count_3km", 0),
        "percentile": None,
        "seoul_percentile": hangang_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🌊 {hangang_info.get('nearest_name', '')}" if hangang_info.get("nearest_name") else "",
        "nearest_distance": hangang_info.get("nearest_distance", None),
    })

    rest_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "rest"
        ),
        None
    )

    if rest_domain:
        result = []
        inserted = False

        for summary in rest_domain.get("categories", []):
            result.append(summary)

            if summary.get("key") == "park":
                result.append(hangang_summary)
                inserted = True

        if not inserted:
            result.append(hangang_summary)

        rest_domain["categories"] = result
        try:
            rest_domain["poi_count"] = int(rest_domain.get("poi_count", 0)) + int(hangang_info.get("hangang_count_3km", 0))
        except Exception:
            rest_domain["poi_count"] = hangang_info.get("hangang_count_3km", 0)
    else:
        rest_domain = {
            "key": "rest",
            "label": "☕ 휴식/여가",
            "description": "카페, 공원, 한강 등 휴식 요소",
            "initial_load": True,
            "category_count": 1,
            "poi_count": hangang_info.get("hangang_count_3km", 0),
            "categories": [hangang_summary],
            "max_score": 0,
        }
        domain_summaries.append(rest_domain)

    return category_summaries, preference_tags, domain_summaries

def build_bike_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(bike_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("bike_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        bike_items = json.loads(str(items_raw))
    except Exception:
        bike_items = []

    try:
        bike_items = sorted(
            bike_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

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
    if not bike_info:
        return []

    map_pois = []

    for item in bike_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = str(item.get("label", "따릉이 대여소")).replace("🚲", "").strip()

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "bike",
            "label": f"🚲 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": "따릉이",
            "source": "서울시 공공자전거 따릉이 대여소 마스터 정보",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "bike"
    ]

    if bike_summary:
        result = []
        inserted = False

        for summary in category_summaries:
            result.append(summary)

            if summary.get("key") == "bus-baseline":
                result.append(bike_summary)
                inserted = True

        if not inserted:
            result.append(bike_summary)

        category_summaries = result

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "bike"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "bike"
        ]

    if not bike_info or not bike_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "bike",
        "label": "🚲 따릉이",
        "value": old_bike_tag.get("value", 3) if old_bike_tag else 3,
        "level": old_bike_tag.get("level", "보통") if old_bike_tag else "보통",
        "level_class": old_bike_tag.get("level_class", "level-normal") if old_bike_tag else "level-normal",
        "radius": 500,
        "count": bike_info.get("station_count_500m", 0),
        "percentile": None,
        "seoul_percentile": bike_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🚲 {bike_info.get('nearest_station', '')}" if bike_info.get("nearest_station") else "",
        "nearest_distance": bike_info.get("nearest_distance", None),
    })

    transport_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "transport"
        ),
        None
    )

    if transport_domain:
        result = []
        inserted = False

        for summary in transport_domain.get("categories", []):
            result.append(summary)

            if summary.get("key") == "bus-baseline":
                result.append(bike_summary)
                inserted = True

        if not inserted:
            result.append(bike_summary)

        transport_domain["categories"] = result
        try:
            transport_domain["poi_count"] = int(transport_domain.get("poi_count", 0)) + int(bike_info.get("station_count_500m", 0))
        except Exception:
            transport_domain["poi_count"] = bike_info.get("station_count_500m", 0)

    return category_summaries, preference_tags, domain_summaries


def build_ev_charger_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(ev_charger_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("ev_charger_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        items = json.loads(str(items_raw))
    except Exception:
        items = []

    try:
        items = sorted(items, key=lambda item: int(item.get("distance", 999999)))
    except Exception:
        pass

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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "ev-charger"
    ]

    if ev_summary:
        result = []
        inserted = False

        for summary in category_summaries:
            result.append(summary)

            if summary.get("key") == "convenience":
                result.append(ev_summary)
                inserted = True

        if not inserted:
            result.append(ev_summary)

        category_summaries = result

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "ev-charger"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "ev-charger"
        ]

    if not ev_charger_info or not ev_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "ev-charger",
        "label": "⚡ 전기차 충전",
        "value": old_tag.get("value", 3) if old_tag else 3,
        "level": old_tag.get("level", ev_charger_info.get("level", "보통")) if old_tag else ev_charger_info.get("level", "보통"),
        "level_class": old_tag.get("level_class", "level-normal") if old_tag else "level-normal",
        "radius": 1000,
        "count": ev_charger_info.get("count_1km", 0),
        "percentile": None,
        "seoul_percentile": ev_charger_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"⚡ {ev_charger_info.get('nearest_name', '')}" if ev_charger_info.get("nearest_name") else "",
        "nearest_distance": ev_charger_info.get("nearest_distance", None),
    })

    convenience_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "convenience"
        ),
        None
    )

    if convenience_domain:
        result = []
        inserted = False

        for summary in convenience_domain.get("categories", []):
            result.append(summary)

            if summary.get("key") == "convenience":
                result.append(ev_summary)
                inserted = True

        if not inserted:
            result.append(ev_summary)

        convenience_domain["categories"] = result
        try:
            convenience_domain["poi_count"] = int(convenience_domain.get("poi_count", 0)) + int(ev_charger_info.get("count_1km", 0))
        except Exception:
            convenience_domain["poi_count"] = ev_charger_info.get("count_1km", 0)
    else:
        domain_summaries.append({
            "key": "convenience",
            "label": "생활편의",
            "description": "마트, 편의점, 전기차 충전 등 일상 편의시설",
            "initial_load": True,
            "category_count": 1,
            "poi_count": ev_charger_info.get("count_1km", 0),
            "categories": [ev_summary],
            "max_score": ev_charger_info.get("score", 0),
        })

    return category_summaries, preference_tags, domain_summaries


def build_medical_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(medical_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    def parse_items(column_name):
        items_raw = row.get(column_name, "[]")
        if items_raw is None or isinstance(items_raw, float):
            items_raw = "[]"

        try:
            items = json.loads(str(items_raw))
        except Exception:
            items = []

        try:
            items = sorted(items, key=lambda item: int(float(item.get("distance", 999999))))
        except Exception:
            pass

        return items

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
            "description": "반경 500m 기준 병원 접근성과 1km 내 진료과 분포입니다.",
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
        medical_domain["poi_count"] = medical_info.get("medical_count_1km", 0)
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
            "poi_count": medical_info.get("medical_count_1km", 0),
            "categories": medical_summaries,
            "max_score": to_int(medical_info.get("medical_count_1km"), 0),
        })

    return category_summaries, preference_tags, domain_summaries

def build_commercial_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(commercial_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("commercial_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        commercial_items = json.loads(str(items_raw))
    except Exception:
        commercial_items = []

    try:
        commercial_items = sorted(
            commercial_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

    type_chips = []
    chip_sources = [
        ("골목", row.get("alley_count", 0)),
        ("대형상권", row.get("developed_count", 0)),
        ("시장", row.get("market_count", 0)),
        ("관광특구", row.get("tourism_count", 0)),
    ]

    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not commercial_info:
        return []

    map_pois = []

    for item in commercial_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = item.get("label", "상권")
        subtype = item.get("subtype", "기타")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "commercial",
            "label": f"🌃 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울시 상권분석서비스",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "commercial"
    ]

    if commercial_summary:
        category_summaries.append(commercial_summary)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "commercial"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "commercial"
        ]

    if not commercial_info or not commercial_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "commercial",
        "label": "🌃 상권",
        "value": 3,
        "level": "보통",
        "level_class": "level-normal",
        "radius": 1000,
        "count": commercial_info.get("commercial_count_1km", 0),
        "percentile": None,
        "seoul_percentile": commercial_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🌃 {commercial_info.get('nearest_name', '')}",
        "nearest_distance": commercial_info.get("nearest_distance", None),
    })

    activity_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "activity"
        ),
        None
    )

    if activity_domain:
        activity_domain["categories"].append(commercial_summary)
        try:
            activity_domain["poi_count"] = int(activity_domain.get("poi_count", 0)) + int(commercial_info.get("commercial_count_1km", 0))
        except Exception:
            activity_domain["poi_count"] = commercial_info.get("commercial_count_1km", 0)
    else:
        activity_domain = {
            "key": "activity",
            "label": "🌃 상권",
            "description": "유흥시설, 상권 밀집도",
            "initial_load": False,
            "category_count": 1,
            "poi_count": commercial_info.get("commercial_count_1km", 0),
            "categories": [commercial_summary],
            "max_score": 0,
        }
        domain_summaries.append(activity_domain)


    return category_summaries, preference_tags, domain_summaries



def build_shopping_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(shopping_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("shopping_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        shopping_items = json.loads(str(items_raw))
    except Exception:
        shopping_items = []

    try:
        shopping_items = sorted(
            shopping_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

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
    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

    return {
        "shopping_count_3km": len(shopping_items),
        "nearest_name": clean_text(row.get("nearest_shopping_name", "")),
        "nearest_subtype": clean_text(row.get("nearest_shopping_subtype", "")),
        "nearest_distance": clean_text(row.get("nearest_shopping_distance", "")),
        "items": shopping_items,
        "type_chips": type_chips,
        "seoul_percentile": get_baseline_percentile(row, "shopping_count_3km_seoul_percentile"),
    }

    return None

def build_shopping_map_pois(shopping_info):
    if not shopping_info:
        return []

    map_pois = []

    for item in shopping_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = str(item.get("label", "쇼핑시설")).replace("🛍", "").strip()
        subtype = item.get("subtype", "기타쇼핑")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "shopping",
            "label": f"🛍️ {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울시 대규모점포 인허가 정보",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "shopping"
    ]

    if shopping_summary:
        result = []
        inserted = False

        for summary in category_summaries:
            result.append(summary)

            if summary.get("key") == "commercial":
                result.append(shopping_summary)
                inserted = True

        if not inserted:
            result.append(shopping_summary)

        category_summaries = result

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "shopping"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "shopping"
        ]

    if not shopping_info or not shopping_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "shopping",
        "label": "🛍️ 쇼핑",
        "value": 3,
        "level": "보통",
        "level_class": "level-normal",
        "radius": 3000,
        "count": shopping_info.get("shopping_count_3km", 0),
        "percentile": None,
        "seoul_percentile": shopping_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🛍️ {shopping_info.get('nearest_name', '')}" if shopping_info.get("nearest_name") else "",
        "nearest_distance": shopping_info.get("nearest_distance", None),
    })

    activity_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "activity"
        ),
        None
    )

    if activity_domain:
        result = []
        inserted = False

        for summary in activity_domain.get("categories", []):
            result.append(summary)

            if summary.get("key") == "commercial":
                result.append(shopping_summary)
                inserted = True

        if not inserted:
            result.append(shopping_summary)

        activity_domain["categories"] = result
        try:
            activity_domain["poi_count"] = int(activity_domain.get("poi_count", 0)) + int(shopping_info.get("shopping_count_3km", 0))
        except Exception:
            activity_domain["poi_count"] = shopping_info.get("shopping_count_3km", 0)
    else:
        activity_domain = {
            "key": "activity",
            "label": "🌃 상권/활기",
            "description": "상권, 쇼핑, 야간상권 등 활동 인프라",
            "initial_load": False,
            "category_count": 1,
            "poi_count": shopping_info.get("shopping_count_3km", 0),
            "categories": [shopping_summary],
            "max_score": 0,
        }
        domain_summaries.append(activity_domain)

    return category_summaries, preference_tags, domain_summaries

def build_nightlife_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(nightlife_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("nightlife_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        nightlife_items = json.loads(str(items_raw))
    except Exception:
        nightlife_items = []

    try:
        nightlife_items = sorted(
            nightlife_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

    chip_sources = [
        ("룸살롱", row.get("room_salon_count", 0)),
        ("바/주점", row.get("bar_count", 0)),
        ("클럽/나이트", row.get("club_count", 0)),
        ("기타", row.get("etc_count", 0)),
    ]

    type_chips = []
    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not nightlife_info:
        return []

    map_pois = []

    for item in nightlife_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = item.get("label", "유흥주점")
        subtype = item.get("subtype", "기타")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "nightlife",
            "label": f"🍺 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울열린데이터광장",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "nightlife"
    ]

    if nightlife_summary:
        category_summaries.append(nightlife_summary)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "nightlife"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "nightlife"
        ]

    if not nightlife_info or not nightlife_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "nightlife",
        "label": "🍺 유흥주점",
        "value": old_nightlife_tag.get("value", 3) if old_nightlife_tag else 3,
        "level": old_nightlife_tag.get("level", "보통") if old_nightlife_tag else "보통",
        "level_class": old_nightlife_tag.get("level_class", "level-normal") if old_nightlife_tag else "level-normal",
        "radius": 500,
        "count": nightlife_info.get("nightlife_count_500m", 0),
        "percentile": None,
        "seoul_percentile": None,
        "gu_percentile": None,
        "display_percentile": False,
        "district": apartment.get("district", ""),
        "nearest_name": f"🍺 {nightlife_info.get('nearest_name', '')}" if nightlife_info.get("nearest_name") else "",
        "nearest_distance": nightlife_info.get("nearest_distance", None),
    })

    activity_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "activity"
        ),
        None
    )

    if activity_domain:
        activity_domain["categories"].append(nightlife_summary)
        try:
            activity_domain["poi_count"] = int(activity_domain.get("poi_count", 0)) + int(nightlife_info.get("nightlife_count_500m", 0))
        except Exception:
            activity_domain["poi_count"] = nightlife_info.get("nightlife_count_500m", 0)
    else:
        activity_domain = {
            "key": "activity",
            "label": "🌃 상권/활기",
            "description": "유흥시설, 상권 밀집도",
            "initial_load": False,
            "category_count": 1,
            "poi_count": nightlife_info.get("nightlife_count_500m", 0),
            "categories": [nightlife_summary],
            "max_score": 0,
        }
        domain_summaries.append(activity_domain)

    return category_summaries, preference_tags, domain_summaries



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

    items_raw = row.get("academy_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        academy_items = json.loads(str(items_raw))
    except Exception:
        academy_items = []

    try:
        academy_items = sorted(
            academy_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

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

    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not academy_info:
        return []

    map_pois = []

    for item in academy_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = str(item.get("label", "학원")).replace("🏫", "").strip()
        subtype = item.get("subtype", "기타")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "academy",
            "label": f"🏫 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울시 학원교습소 정보",
        })

    return map_pois



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


def insert_before_category(summaries, target_key, new_summary):
    if not new_summary:
        return summaries

    cleaned = [
        summary for summary in summaries
        if summary.get("key") != new_summary.get("key")
    ]

    result = []
    inserted = False

    for summary in cleaned:
        if summary.get("key") == target_key and not inserted:
            result.append(new_summary)
            inserted = True

        result.append(summary)

    if not inserted:
        result.append(new_summary)

    return result


def apply_school_environment_to_ui(category_summaries, preference_tags, domain_summaries, school_environment_info, apartment):
    school_summary = build_school_environment_category_summary(school_environment_info)

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "school-environment"
    ]

    category_summaries = insert_before_category(
        category_summaries,
        "academy",
        school_summary
    )

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "school-environment"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "school-environment"
        ]

    if not school_environment_info or not school_summary:
        return category_summaries, preference_tags, domain_summaries

    assigned_school_name = school_environment_info.get("assigned_school_name", "")

    preference_tags.append({
        "key": "school-environment",
        "label": "🏫 교육환경",
        "value": 3,
        "level": "정보",
        "level_class": "level-normal",
        "radius": SCHOOL_ENVIRONMENT_RADIUS,
        "count": school_summary.get("count", 0),
        "percentile": None,
        "seoul_percentile": None,
        "gu_percentile": None,
        "display_percentile": False,
        "district": apartment.get("district", ""),
        "nearest_name": f"🏫 {assigned_school_name}" if assigned_school_name else "",
        "nearest_distance": school_environment_info.get("assigned_distance", None),
    })

    education_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "education"
        ),
        None
    )

    if education_domain:
        education_domain["categories"] = insert_before_category(
            education_domain.get("categories", []),
            "academy",
            school_summary
        )
        try:
            education_domain["poi_count"] = int(education_domain.get("poi_count", 0)) + int(school_summary.get("count", 0))
        except Exception:
            education_domain["poi_count"] = school_summary.get("count", 0)
    else:
        education_domain = {
            "key": "education",
            "label": "🏫 교육",
            "description": "학교, 학원 등 교육 인프라",
            "initial_load": False,
            "category_count": 1,
            "poi_count": school_summary.get("count", 0),
            "categories": [school_summary],
            "max_score": 0,
        }
        domain_summaries.append(education_domain)

    return category_summaries, preference_tags, domain_summaries


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "academy"
    ]

    if academy_summary:
        category_summaries.append(academy_summary)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "academy"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "academy"
        ]

    if not academy_info or not academy_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "academy",
        "label": "✏️ 학원",
        "value": old_academy_tag.get("value", 3) if old_academy_tag else 3,
        "level": old_academy_tag.get("level", "보통") if old_academy_tag else "보통",
        "level_class": old_academy_tag.get("level_class", "level-normal") if old_academy_tag else "level-normal",
        "radius": 1000,
        "count": academy_info.get("academy_count_1000m", 0),
        "percentile": None,
        "seoul_percentile": academy_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"✏️ {academy_info.get('nearest_name', '')}" if academy_info.get("nearest_name") else "",
        "nearest_distance": academy_info.get("nearest_distance", None),
    })

    education_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "education"
        ),
        None
    )

    if education_domain:
        education_domain["categories"].append(academy_summary)
        try:
            education_domain["poi_count"] = int(education_domain.get("poi_count", 0)) + int(academy_info.get("academy_count_1000m", 0))
        except Exception:
            education_domain["poi_count"] = academy_info.get("academy_count_1000m", 0)
    else:
        education_domain = {
            "key": "education",
            "label": "🏫 교육",
            "description": "학원, 교육 인프라",
            "initial_load": False,
            "category_count": 1,
            "poi_count": academy_info.get("academy_count_1000m", 0),
            "categories": [academy_summary],
            "max_score": 0,
        }
        domain_summaries.append(education_domain)

    return category_summaries, preference_tags, domain_summaries


def build_culture_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(culture_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("culture_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        culture_items = json.loads(str(items_raw))
    except Exception:
        culture_items = []

    try:
        culture_items = sorted(
            culture_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

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
    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not culture_info:
        return []

    map_pois = []

    for item in culture_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = item.get("label", "문화생활")
        subtype = item.get("subtype", "기타")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "culture",
            "label": f"🎭 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울시 공공서비스예약",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "culture"
    ]

    if culture_summary:
        category_summaries.append(culture_summary)

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "culture"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "culture"
        ]

    if not culture_info or not culture_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "culture",
        "label": "🎭 문화생활",
        "value": old_culture_tag.get("value", 3) if old_culture_tag else 3,
        "level": old_culture_tag.get("level", "보통") if old_culture_tag else "보통",
        "level_class": old_culture_tag.get("level_class", "level-normal") if old_culture_tag else "level-normal",
        "radius": 1500,
        "count": culture_info.get("culture_count_1500m", 0),
        "percentile": None,
        "seoul_percentile": culture_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🎭 {culture_info.get('nearest_name', '')}" if culture_info.get("nearest_name") else "",
        "nearest_distance": culture_info.get("nearest_distance", None),
    })

    culture_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "culture"
        ),
        None
    )

    if culture_domain:
        culture_domain["categories"].append(culture_summary)
        try:
            culture_domain["poi_count"] = int(culture_info.get("culture_count_1500m", 0))
        except Exception:
            culture_domain["poi_count"] = culture_info.get("culture_count_1500m", 0)
    else:
        culture_domain = {
            "key": "culture",
            "label": "🎭 문화생활",
            "description": "공연, 전시, 체육, 체험 등 활동형 여가",
            "initial_load": False,
            "category_count": 1,
            "poi_count": culture_info.get("culture_count_1500m", 0),
            "categories": [culture_summary],
            "max_score": 0,
        }
        domain_summaries.append(culture_domain)

    return category_summaries, preference_tags, domain_summaries


def build_fire_station_info(apartment_name, gu=None, dong=None):
    row = get_indexed_baseline_row(fire_station_baseline_index, apartment_name, gu, dong)

    if not row:
        return None

    items_raw = row.get("fire_station_items_json", "[]")

    if items_raw is None or isinstance(items_raw, float):
        items_raw = "[]"

    try:
        fire_items = json.loads(str(items_raw))
    except Exception:
        fire_items = []

    try:
        fire_items = sorted(
            fire_items,
            key=lambda item: int(item.get("distance", 999999))
        )
    except Exception:
        pass

    type_chips = []
    chip_sources = [
        ("안전센터", row.get("safety_center_count", 0)),
        ("구조대", row.get("rescue_count", 0)),
        ("기타", row.get("fire_etc_count", 0)),
    ]

    for name, count in chip_sources:
        try:
            count = int(float(count))
        except Exception:
            count = 0

        if count > 0:
            type_chips.append({
                "name": name,
                "count": count,
            })

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
    if not fire_station_info:
        return []

    map_pois = []

    for item in fire_station_info.get("items", []):
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue

        label = str(item.get("label", "119안전센터/구조대")).replace("🚒", "").strip()
        subtype = item.get("subtype", "기타")

        map_pois.append({
            "lat": lat,
            "lng": lng,
            "category": "fire-station",
            "label": f"🚒 {label}",
            "name": label,
            "distance": item.get("distance"),
            "subtype": subtype,
            "source": "서울시 119안전센터/구조대 위치정보",
        })

    return map_pois


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

    category_summaries = [
        summary for summary in category_summaries
        if summary.get("key") != "fire-station"
    ]

    if fire_summary:
        result = []
        inserted = False

        for summary in category_summaries:
            result.append(summary)

            if summary.get("key") == "cctv":
                result.append(fire_summary)
                inserted = True

        if not inserted:
            result.append(fire_summary)

        category_summaries = result

    preference_tags = [
        tag for tag in preference_tags
        if tag.get("key") != "fire-station"
    ]

    for domain in domain_summaries:
        domain["categories"] = [
            summary for summary in domain.get("categories", [])
            if summary.get("key") != "fire-station"
        ]

    if not fire_station_info or not fire_summary:
        return category_summaries, preference_tags, domain_summaries

    preference_tags.append({
        "key": "fire-station",
        "label": "🚒 119안전센터/구조대",
        "value": old_fire_tag.get("value", 3) if old_fire_tag else 3,
        "level": old_fire_tag.get("level", "보통") if old_fire_tag else "보통",
        "level_class": old_fire_tag.get("level_class", "level-normal") if old_fire_tag else "level-normal",
        "radius": 1500,
        "count": fire_station_info.get("fire_station_count_1500m", 0),
        "percentile": None,
        "seoul_percentile": fire_station_info.get("seoul_percentile"),
        "gu_percentile": None,
        "district": apartment.get("district", ""),
        "nearest_name": f"🚒 {fire_station_info.get('nearest_name', '')}" if fire_station_info.get("nearest_name") else "",
        "nearest_distance": fire_station_info.get("nearest_distance", None),
    })

    safety_domain = next(
        (
            domain for domain in domain_summaries
            if domain.get("key") == "safety"
        ),
        None
    )

    if safety_domain:
        result = []
        inserted = False

        for summary in safety_domain.get("categories", []):
            result.append(summary)

            if summary.get("key") == "cctv":
                result.append(fire_summary)
                inserted = True

        if not inserted:
            result.append(fire_summary)

        safety_domain["categories"] = result
        try:
            safety_domain["poi_count"] = int(safety_domain.get("poi_count", 0)) + int(fire_station_info.get("fire_station_count_1500m", 0))
        except Exception:
            safety_domain["poi_count"] = fire_station_info.get("fire_station_count_1500m", 0)
    else:
        safety_domain = {
            "key": "safety",
            "label": "🛡 안전",
            "description": "CCTV, 119안전센터 등 안전 인프라",
            "initial_load": False,
            "category_count": 1,
            "poi_count": fire_station_info.get("fire_station_count_1500m", 0),
            "categories": [fire_summary],
            "max_score": 0,
        }
        domain_summaries.append(safety_domain)

    return category_summaries, preference_tags, domain_summaries


def get_preferences():
    preferences = {}

    for key in PREFERENCE_KEYS:
        value = request.args.get(key, "3")

        try:
            preferences[key] = int(value)
        except ValueError:
            preferences[key] = 3

    return preferences


def calculate_personal_score(scores, preferences):
    total_weight = 0
    weighted_sum = 0

    for key in PREFERENCE_KEYS:
        weight = preferences.get(key, 0)

        if weight <= 0:
            continue

        score = scores.get(key, 0)

        if key == "nightlife":
            score = 100 - score

        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0

    return round(weighted_sum / total_weight)


def make_result_url(apartment_name, preferences, gu="", dong=""):
    # Always carry gu/dong so links resolve the exact complex, not the first
    # name match. Names collide across Seoul (e.g. 신동아아파트 x3).
    params = {"apartment": apartment_name}

    if gu:
        params["gu"] = gu
    if dong:
        params["dong"] = dong

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


def build_explore_results(filters, limit=10):
    selected_features = filters.get("features", [])
    gu_filter = clean_text(filters.get("gu", ""))
    dong_filter = clean_text(filters.get("dong", ""))
    line_filter = clean_text(filters.get("line", ""))
    station_filter = clean_text(filters.get("station", "")).replace("역", "")
    query = clean_text(filters.get("q", ""))

    results = []

    for apartment in apartment_data:
        name = clean_text(apartment.get("name", ""))
        gu = clean_text(apartment.get("gu", ""))
        dong = clean_text(apartment.get("dong", ""))

        if gu_filter and gu_filter != gu:
            continue
        if dong_filter and dong_filter != dong:
            continue
        if query and query not in name:
            continue

        rows = get_baseline_rows_for_apartment(name)
        subway = rows.get("subway") or {}
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

        failed = False
        for feature in selected_features:
            if has_feature_from_rows(feature, rows):
                label = next((item["label"] for item in FEATURE_OPTIONS if item["key"] == feature), feature)
                matched.append(label)
                score += 2
            else:
                failed = True
                break

        if failed:
            continue

        subway_distance = insight_to_number(subway.get("subway_distance"))
        if subway_distance is not None and subway_distance <= 800:
            score += 1

        medical = rows.get("medical") or {}
        if insight_to_number(medical.get("nearest_emergency_distance")) is not None:
            score += 1

        results.append({
            "name": name,
            "gu": gu,
            "dong": dong,
            "score": score,
            "matched_features": matched[:5] or ["생활 균형형"],
            "url": make_result_url(name, get_preferences(), gu, dong),
        })

    results.sort(key=lambda item: (-item["score"], item["gu"], item["dong"], item["name"]))
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
    filters = {
        "q": request.args.get("q", ""),
        "gu": request.args.get("gu", ""),
        "dong": request.args.get("dong", ""),
        "line": request.args.get("line", ""),
        "station": request.args.get("station", ""),
        "features": request.args.getlist("feature"),
    }
    gu_options = sorted({clean_text(item.get("gu", "")) for item in apartment_data if clean_text(item.get("gu", ""))})
    dong_options = sorted({
        clean_text(item.get("dong", ""))
        for item in apartment_data
        if clean_text(item.get("dong", ""))
        and (not filters["gu"] or clean_text(item.get("gu", "")) == filters["gu"])
    })

    results = build_explore_results(filters)

    return render_template(
        "explore.html",
        feature_options=FEATURE_OPTIONS,
        filters=filters,
        results=results,
        gu_options=gu_options,
        dong_options=dong_options,
        subway_line_options=get_subway_line_options(),
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
        )
    else:
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

    if ranking_apartment:
        preference_score = calculate_weighted_score(
            ranking_apartment["category_scores"],
            preferences
        )
    else:
        preference_score = 0
    
    top_apartments = get_top_apartments(preferences)
    apartment_with_real_pois = {
        **apartment,
        "pois": pois,
    }

    category_summaries = get_category_summaries(
        apartment_with_real_pois,
        PREFERENCE_KEYS
    )

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

    return render_template(
        "result.html",
        apartment=apartment,
        scores=scores,
        preferences=preferences,
        preference_score=preference_score,
        top_apartments=top_apartments,
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

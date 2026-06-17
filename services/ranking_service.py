"""Apartment ranking / preference scoring.

Single source of truth: the baked `{primary_metric}_seoul_score` columns
produced by scripts/enrich_baseline_percentiles.py from BASELINE_METRIC_CONFIG.
Ranking no longer recomputes percentiles with its own (divergent) metrics —
it reads the same scores the detail cards and admin debug show, so the
recommendation engine and the per-category cards can never disagree.
"""

import math

from services import preload_service
from scripts.baseline_metric_config import BASELINE_METRIC_CONFIG, score_column


# preference key -> (BASELINE_METRIC_CONFIG key, preload_service data attribute)
#
# Only categories that are (a) loaded into memory, (b) ranking_enabled in the
# config, and (c) map to a user preference key participate in weighting.
# Direction (higher/lower better) is already encoded in the baked score, so no
# per-category inversion is needed here (e.g. nightlife LOWER_BETTER -> a high
# baked score already means "few nightlife venues").
RANKING_SOURCES = {
    "subway": ("subway", "subway_baseline_data"),
    "bus": ("bus", "bus_baseline_data"),
    "bike": ("bike", "bike_baseline_data"),
    "convenience": ("convenience", "convenience_baseline_data"),
    "large_mart": ("large_mart", "mart_baseline_data"),
    "super_mart": ("super_mart", "mart_baseline_data"),
    "warehouse_mart": ("warehouse_mart", "mart_baseline_data"),
    "cafe": ("cafe", "cafe_baseline_data"),
    "hospital": ("medical", "medical_baseline_data"),
    "academy": ("academy", "academy_baseline_data"),
    "culture": ("culture", "culture_baseline_data"),
    "shopping": ("shopping", "shopping_baseline_data"),
    "commercial": ("commercial", "commercial_baseline_data"),
    "nightlife": ("nightlife", "nightlife_baseline_data"),
    "hangang": ("hangang", "hangang_baseline_data"),
    "fire-station": ("fire_station", "fire_station_baseline_data"),
    "ev-charger": ("ev_charger", "ev_charger_baseline_data"),
    "cctv": ("cctv", "cctv_baseline_data"),
}

# Home/Explore 랭킹이 실제로 사용하는 baseline metric(config) 키 집합 = 단일 기준.
# ranking-debug 화면도 이 집합만 노출해 Home/Explore 와 metric 기준을 일치시킨다.
# (park/school_zone 처럼 BASELINE_METRIC_CONFIG 엔 있으나 랭킹 브리지에 없는 metric은 제외)
RANKING_METRIC_KEYS = {config_key for config_key, _data_attr in RANKING_SOURCES.values()}

_APARTMENT_INDEX_CACHE = None


def to_number(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def get_row_key(row):
    return (
        row.get("name"),
        row.get("gu"),
        row.get("dong"),
    )


def build_apartment_index():
    global _APARTMENT_INDEX_CACHE

    if _APARTMENT_INDEX_CACHE is not None:
        return _APARTMENT_INDEX_CACHE

    apartment_index = {}

    for pref_key, (config_key, data_attr) in RANKING_SOURCES.items():
        config = BASELINE_METRIC_CONFIG.get(config_key)
        if not config:
            continue

        rows = getattr(preload_service, data_attr, None) or []
        col = score_column(config["primary_metric"])

        for row in rows:
            key = get_row_key(row)

            entry = apartment_index.get(key)
            if entry is None:
                entry = {
                    "name": row.get("name"),
                    "district": row.get("gu"),
                    "dong": row.get("dong"),
                    "category_scores": {},
                    "category_percentiles": {},
                }
                apartment_index[key] = entry

            score = to_number(row.get(col))
            if score is None:
                continue

            entry["category_scores"][pref_key] = score
            entry["category_percentiles"][pref_key] = to_number(
                row.get(f"{config['primary_metric']}_seoul_percentile")
            )

    _APARTMENT_INDEX_CACHE = apartment_index

    return _APARTMENT_INDEX_CACHE


def reset_apartment_index_cache():
    """Allow rebuilding after baselines are reloaded/re-baked."""
    global _APARTMENT_INDEX_CACHE
    _APARTMENT_INDEX_CACHE = None


def calculate_weighted_score(category_scores, preferences):
    total_weight = 0
    weighted_sum = 0

    for category, weight in preferences.items():
        try:
            weight = float(weight)
        except Exception:
            continue

        if weight <= 0:
            continue

        score = category_scores.get(category)

        if score is None:
            continue

        total_weight += weight
        weighted_sum += score * weight

    if total_weight == 0:
        return 0

    return round(weighted_sum / total_weight)


def get_ranked_apartments(preferences, limit=5):
    apartment_index = build_apartment_index()

    ranked = []

    for apartment in apartment_index.values():
        score = calculate_weighted_score(
            apartment["category_scores"],
            preferences
        )

        ranked.append({
            "name": apartment["name"],
            "district": apartment["district"],
            "dong": apartment["dong"],
            "score": score,
            "category_scores": apartment["category_scores"],
            "category_percentiles": apartment["category_percentiles"],
        })

    ranked.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return ranked[:limit]

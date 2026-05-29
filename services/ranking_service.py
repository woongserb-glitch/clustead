from services.preload_service import (
    subway_baseline_data,
    cctv_baseline_data,
    convenience_baseline_data,
    mart_baseline_data,
    cafe_baseline_data,
    nightlife_baseline_data,
    academy_baseline_data,
    culture_baseline_data,
    ev_charger_baseline_data,
)


CATEGORY_CONFIG = {
    "subway": {
        "data": subway_baseline_data,
        "metric": "subway_distance",
        "type": "distance",
    },
    "cctv": {
        "data": cctv_baseline_data,
        "metric": "cctv_count_500m",
        "type": "density",
    },
    "convenience": {
        "data": convenience_baseline_data,
        "metric": "convenience_count_500m",
        "type": "density",
    },
    "mart": {
        "data": mart_baseline_data,
        "metric": "mart_count_1500m",
        "type": "density",
    },
    "cafe": {
        "data": cafe_baseline_data,
        "metric": "cafe_count_500m",
        "type": "density",
    },
    "nightlife": {
        "data": nightlife_baseline_data,
        "metric": "nightlife_count_500m",
        "type": "inverse_density",
    },
    "academy": {
        "data": academy_baseline_data,
        "metric": "academy_count_1000m",
        "type": "density",
    },
    "culture": {
        "data": culture_baseline_data,
        "metric": "culture_count_1500m",
        "type": "density",
    },
    "ev-charger": {
        "data": ev_charger_baseline_data,
        "metric": "ev_charger_score",
        "type": "density",
    },
}

_APARTMENT_INDEX_CACHE = None


def to_number(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except:
        return None


def clean_numeric_values(values):
    """Pre-extract valid numbers once so callers avoid re-parsing per row."""
    cleaned = []
    for item in values:
        number = to_number(item)
        if number is not None:
            cleaned.append(number)
    return cleaned


def calculate_top_percent(value, valid_values, metric_type):
    """Mid-rank percentile of `value` within `valid_values` (already cleaned).

    Ties contribute half their count (standard percentile-rank), which keeps
    the modal value from being unfairly pushed to one extreme — the same
    zero-inflation distortion fixed in enrich_baseline_percentiles.py.
    Lower return = better.
    """
    value = to_number(value)

    if value is None or not valid_values:
        return None

    if metric_type in ["distance", "inverse_density"]:
        strictly_better = sum(1 for item in valid_values if item < value)
    else:
        strictly_better = sum(1 for item in valid_values if item > value)

    ties = sum(1 for item in valid_values if item == value)

    top_percent = (strictly_better + 0.5 * ties) / len(valid_values) * 100

    return max(1, round(top_percent))


def top_percent_to_score(top_percent):
    if top_percent is None:
        return 0

    score = 101 - top_percent

    return max(0, min(100, score))


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

    for category, config in CATEGORY_CONFIG.items():
        rows = config["data"]
        metric = config["metric"]
        metric_type = config["type"]

        # Extract & clean the column once per category (was re-built for every
        # row -> O(N^2) per category, ~17s startup for 2,873 complexes x 9).
        valid_values = clean_numeric_values(
            row.get(metric) for row in rows
        )

        for row in rows:
            key = get_row_key(row)

            if key not in apartment_index:
                apartment_index[key] = {
                    "name": row.get("name"),
                    "district": row.get("gu"),
                    "dong": row.get("dong"),
                    "category_scores": {},
                    "category_percentiles": {},
                }

            top_percent = calculate_top_percent(
                row.get(metric),
                valid_values,
                metric_type
            )

            score = top_percent_to_score(top_percent)

            apartment_index[key]["category_scores"][category] = score
            apartment_index[key]["category_percentiles"][category] = top_percent

    _APARTMENT_INDEX_CACHE = apartment_index

    return _APARTMENT_INDEX_CACHE


def calculate_weighted_score(category_scores, preferences):
    total_weight = 0
    weighted_sum = 0

    for category, weight in preferences.items():
        try:
            weight = float(weight)
        except:
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

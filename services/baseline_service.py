from services.preload_service import subway_baseline_data
from services.preload_service import cctv_baseline_data
from services.preload_service import convenience_baseline_data
from services.preload_service import mart_baseline_data
from services.preload_service import cafe_baseline_data


def to_number(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except:
        return None
    

def _mid_rank_top_percent(current, values, lower_is_better):
    """Mid-rank percentile (lower return = better).

    Ties count as half, matching enrich_baseline_percentiles.py and
    ranking_service.py so all three percentile paths agree on method and
    don't penalise the modal value (e.g. zero-inflated metrics).
    """
    current = to_number(current)

    if current is None or not values:
        return None

    valid = [number for number in (to_number(v) for v in values) if number is not None]

    if not valid:
        return None

    if lower_is_better:
        strictly_better = sum(1 for v in valid if v < current)
    else:
        strictly_better = sum(1 for v in valid if v > current)

    ties = sum(1 for v in valid if v == current)

    top_percent = (strictly_better + 0.5 * ties) / len(valid) * 100

    return max(1, round(top_percent))


def calculate_distance_top_percent(current_distance, distances):
    # Distance: smaller is better.
    return _mid_rank_top_percent(current_distance, distances, lower_is_better=True)


def calculate_density_top_percent(current_value, values):
    # Density/count: larger is better.
    return _mid_rank_top_percent(current_value, values, lower_is_better=False)


def get_subway_percentiles(current_distance, gu):
    seoul_distances = []
    gu_distances = []

    for item in subway_baseline_data:
        distance = item.get("subway_distance")

        if distance is None:
            continue

        seoul_distances.append(distance)

        if item.get("gu") == gu:
            gu_distances.append(distance)

    return {
        "seoul": calculate_distance_top_percent(current_distance, seoul_distances),
        "gu": calculate_distance_top_percent(current_distance, gu_distances),
    }


def get_cctv_percentiles(current_count, gu):
    seoul_values = []
    gu_values = []

    for item in cctv_baseline_data:
        value = item.get("cctv_count_500m")

        if value is None:
            continue

        seoul_values.append(value)

        if item.get("gu") == gu:
            gu_values.append(value)

    return {
        "seoul": calculate_density_top_percent(current_count, seoul_values),
        "gu": calculate_density_top_percent(current_count, gu_values),
    }


def get_convenience_percentiles(
    current_count,
    gu
):
    seoul_values = []
    gu_values = []

    for item in convenience_baseline_data:

        value = item.get(
            "convenience_count_500m"
        )

        if value is None:
            continue

        seoul_values.append(value)

        if item.get("gu") == gu:
            gu_values.append(value)

    return {
        "seoul": (
            calculate_density_top_percent(
                current_count,
                seoul_values
            )
        ),

        "gu": (
            calculate_density_top_percent(
                current_count,
                gu_values
            )
        ),
    }


def get_mart_percentiles(current_count, gu):
    seoul_values = []
    gu_values = []

    for item in mart_baseline_data:
        value = item.get("mart_count_1500m")

        if value is None:
            continue

        seoul_values.append(value)

        if item.get("gu") == gu:
            gu_values.append(value)

    return {
        "seoul": calculate_density_top_percent(current_count, seoul_values),
        "gu": calculate_density_top_percent(current_count, gu_values),
    }


def get_cafe_percentiles(current_count, gu):
    seoul_values = []
    gu_values = []

    for item in cafe_baseline_data:
        value = item.get("cafe_count_500m")

        if value is None:
            continue

        seoul_values.append(value)

        if item.get("gu") == gu:
            gu_values.append(value)

    return {
        "seoul": calculate_density_top_percent(current_count, seoul_values),
        "gu": calculate_density_top_percent(current_count, gu_values),
    }
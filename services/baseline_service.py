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
    

def calculate_distance_top_percent(current_distance, distances):
    current_distance = to_number(current_distance)

    if current_distance is None or not distances:
        return None

    valid_distances = []

    for distance in distances:
        distance = to_number(distance)

        if distance is not None:
            valid_distances.append(distance)

    if not valid_distances:
        return None

    better_or_equal_count = 0

    for distance in valid_distances:
        if distance <= current_distance:
            better_or_equal_count += 1

    top_percent = (better_or_equal_count / len(valid_distances)) * 100

    return max(1, round(top_percent))


def calculate_density_top_percent(current_value, values):
    current_value = to_number(current_value)

    if current_value is None or not values:
        return None

    valid_values = []

    for value in values:
        value = to_number(value)

        if value is not None:
            valid_values.append(value)

    if not valid_values:
        return None

    better_or_equal_count = 0

    for value in valid_values:
        if value >= current_value:
            better_or_equal_count += 1

    top_percent = (better_or_equal_count / len(valid_values)) * 100

    return max(1, round(top_percent))


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
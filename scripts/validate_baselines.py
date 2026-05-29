import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from baseline_metric_config import BASELINE_METRIC_CONFIG


csv.field_size_limit(sys.maxsize)

SEOUL_LAT_RANGE = (37.35, 37.75)
SEOUL_LNG_RANGE = (126.75, 127.25)
REPORT_DIR = Path("data/validation")
HANGANG_RAW_PATH = Path("data/hangang/hangang_facilities.csv")
HANGANG_MASTER_PATH = Path("data/hangang/hangang_park_master.csv")
HANGANG_LAT_RANGE = (37.45, 37.70)
HANGANG_LNG_RANGE = (126.75, 127.20)


class ValidationReporter:
    def __init__(self):
        self.errors = 0
        self.warnings = 0
        self.checked = 0

    def ok(self, message):
        print(f"[OK] {message}")

    def warning(self, message):
        self.warnings += 1
        print(f"[WARNING] {message}")

    def error(self, message):
        self.errors += 1
        print(f"[ERROR] {message}")

    def summary(self):
        print("-" * 60)
        print(
            f"[SUMMARY] baselines={self.checked} "
            f"errors={self.errors} warnings={self.warnings}"
        )


def to_number(value):
    try:
        if value is None:
            return None

        text = str(value).strip()

        if not text or text.lower() in {"nan", "none", "null"}:
            return None

        number = float(text)

        if math.isnan(number):
            return None

        return number
    except Exception:
        return None


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader), list(reader.fieldnames or [])


def read_rows_with_fallback(path):
    for encoding in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            with path.open("r", encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)
                return list(reader), list(reader.fieldnames or []), encoding
        except UnicodeDecodeError:
            continue

    raise RuntimeError(f"CSV encoding not readable: {path}")


def normalize_hangang_park_key(value):
    return str(value or "").strip().replace("한강공원", "").strip()


def is_count_column(column):
    return "_count" in column or column.endswith("_count")


def is_distance_column(column):
    return "distance" in column or column.endswith("_distance")


def validate_required_columns(reporter, file_name, columns, required_columns):
    missing = [
        column for column in required_columns
        if column not in columns
    ]

    if missing:
        reporter.error(f"{file_name} missing required columns={missing}")
    else:
        reporter.ok(f"{file_name} required columns present")


def validate_duplicate_names(reporter, file_name, rows):
    key_field = "name"

    if rows and key_field not in rows[0] and "apartment_name" in rows[0]:
        key_field = "apartment_name"

    names = [
        str(row.get(key_field, "")).strip()
        for row in rows
        if str(row.get(key_field, "")).strip()
    ]
    duplicates = [
        name for name, count in Counter(names).items()
        if count > 1
    ]

    if duplicates:
        reporter.warning(
            f"{file_name} duplicate {key_field} count={len(duplicates)} "
            f"sample={duplicates[:3]}"
        )
    else:
        reporter.ok(f"{file_name} duplicate names none")


def validate_lat_lng(reporter, file_name, rows, columns, required_columns):
    requires_lat_lng = "lat" in required_columns or "lng" in required_columns

    if "lat" not in columns or "lng" not in columns:
        if requires_lat_lng:
            reporter.error(f"{file_name} missing lat/lng columns")
        else:
            reporter.warning(f"{file_name} lat/lng not configured; skipped lat/lng validation")
        return

    invalid = 0
    out_of_seoul = 0

    for row in rows:
        lat = to_number(row.get("lat"))
        lng = to_number(row.get("lng"))

        if lat is None or lng is None:
            invalid += 1
            continue

        if not (SEOUL_LAT_RANGE[0] <= lat <= SEOUL_LAT_RANGE[1]) or not (
            SEOUL_LNG_RANGE[0] <= lng <= SEOUL_LNG_RANGE[1]
        ):
            out_of_seoul += 1

    if invalid:
        reporter.error(f"{file_name} invalid lat/lng rows={invalid}")
    else:
        reporter.ok(f"{file_name} lat/lng numeric")

    if out_of_seoul:
        reporter.warning(f"{file_name} lat/lng outside Seoul bounds rows={out_of_seoul}")
    else:
        reporter.ok(f"{file_name} lat/lng Seoul bounds")


def validate_json_columns(reporter, file_name, rows, json_columns):
    for column in json_columns:
        failed = 0
        empty = 0

        for row in rows:
            raw = row.get(column, "")

            if raw is None or str(raw).strip() == "":
                empty += 1
                continue

            try:
                json.loads(raw)
            except Exception:
                failed += 1

        if failed:
            reporter.error(f"{file_name} {column} parse failed rows={failed}")
        elif empty:
            reporter.warning(f"{file_name} {column} empty rows={empty}")
        else:
            reporter.ok(f"{file_name} {column} JSON parse")


def validate_negative_numbers(reporter, file_name, rows, columns):
    negative_counts = 0
    negative_distances = 0

    for row in rows:
        for column in columns:
            value = to_number(row.get(column))

            if value is None or value >= 0:
                continue

            if is_count_column(column):
                negative_counts += 1
            elif is_distance_column(column):
                negative_distances += 1

    if negative_counts:
        reporter.error(f"{file_name} negative count values={negative_counts}")
    else:
        reporter.ok(f"{file_name} negative count values none")

    if negative_distances:
        reporter.error(f"{file_name} negative distance values={negative_distances}")
    else:
        reporter.ok(f"{file_name} negative distance values none")


def validate_radius_rules(reporter, file_name, rows, radius_rules):
    for smaller, larger in radius_rules:
        invalid = 0

        for row in rows:
            smaller_value = to_number(row.get(smaller))
            larger_value = to_number(row.get(larger))

            if smaller_value is None or larger_value is None:
                continue

            if smaller_value > larger_value:
                invalid += 1

        if invalid:
            reporter.warning(
                f"{file_name} radius order failed {smaller}<={larger} rows={invalid}"
            )
        else:
            reporter.ok(f"{file_name} radius order {smaller}<={larger}")


def validate_range_column(reporter, file_name, rows, column, label):
    if not rows or column not in rows[0]:
        reporter.warning(f"{file_name} {label} column missing: {column}")
        return

    invalid = 0
    empty = 0

    for row in rows:
        value = to_number(row.get(column))

        if value is None:
            empty += 1
            continue

        if value < 0 or value > 100:
            invalid += 1

    if invalid:
        reporter.error(f"{file_name} {column} out of 0~100 range rows={invalid}")
    elif empty:
        reporter.warning(f"{file_name} {column} empty rows={empty}")
    else:
        reporter.ok(f"{file_name} {column} 0~100 range")


def validate_primary_metric(reporter, file_name, rows, primary_metric):
    invalid = 0
    empty = 0

    for row in rows:
        raw = row.get(primary_metric)
        value = to_number(raw)

        if raw is None or str(raw).strip() == "":
            empty += 1
        elif value is None:
            invalid += 1

    if invalid:
        reporter.error(f"{file_name} primary metric {primary_metric} invalid rows={invalid}")
    elif empty:
        reporter.warning(f"{file_name} primary metric {primary_metric} empty rows={empty}")
    else:
        reporter.ok(f"{file_name} primary metric {primary_metric} numeric")


def validate_hangang_master(reporter):
    print("\n" + "=" * 60)
    print("[VALIDATE] hangang master reference")

    if not HANGANG_RAW_PATH.exists():
        reporter.warning(f"hangang raw missing path={HANGANG_RAW_PATH}")
        return

    if not HANGANG_MASTER_PATH.exists():
        reporter.error(f"hangang master missing path={HANGANG_MASTER_PATH}")
        return

    try:
        raw_rows, raw_columns, raw_encoding = read_rows_with_fallback(HANGANG_RAW_PATH)
        master_rows, master_columns, master_encoding = read_rows_with_fallback(HANGANG_MASTER_PATH)
    except Exception as exc:
        reporter.error(f"hangang master validation read failed: {exc}")
        return

    raw_park_column = "한강공원명"
    if raw_park_column not in raw_columns:
        reporter.error(f"hangang raw missing park column={raw_park_column}")
        return

    required_master_columns = ["park_key", "park_name", "lat", "lng"]
    missing_master_columns = [
        column for column in required_master_columns
        if column not in master_columns
    ]

    if missing_master_columns:
        reporter.error(f"hangang master missing columns={missing_master_columns}")
        return

    raw_keys = {
        normalize_hangang_park_key(row.get(raw_park_column))
        for row in raw_rows
        if normalize_hangang_park_key(row.get(raw_park_column))
        and normalize_hangang_park_key(row.get(raw_park_column)) != "hangangrv_park_nm"
    }
    master_keys = {
        normalize_hangang_park_key(row.get("park_key"))
        for row in master_rows
        if normalize_hangang_park_key(row.get("park_key"))
    }

    missing_in_master = sorted(raw_keys - master_keys)
    missing_in_raw = sorted(master_keys - raw_keys)

    reporter.ok(
        f"hangang raw parks={len(raw_keys)} master parks={len(master_keys)} "
        f"raw_encoding={raw_encoding} master_encoding={master_encoding}"
    )

    if missing_in_master:
        reporter.warning(f"hangang master missing parks={missing_in_master}")
    else:
        reporter.ok("hangang master covers all raw parks")

    if missing_in_raw:
        reporter.warning(f"hangang raw missing parks={missing_in_raw}")
    else:
        reporter.ok("hangang raw covers all master parks")

    invalid_lat_lng = 0
    out_of_range = 0

    for row in master_rows:
        lat = to_number(row.get("lat"))
        lng = to_number(row.get("lng"))

        if lat is None or lng is None:
            invalid_lat_lng += 1
            continue

        if not (HANGANG_LAT_RANGE[0] <= lat <= HANGANG_LAT_RANGE[1]) or not (
            HANGANG_LNG_RANGE[0] <= lng <= HANGANG_LNG_RANGE[1]
        ):
            out_of_range += 1

    if invalid_lat_lng:
        reporter.error(f"hangang master invalid lat/lng rows={invalid_lat_lng}")
    else:
        reporter.ok("hangang master lat/lng numeric")

    if out_of_range:
        reporter.warning(f"hangang master lat/lng outside Hangang bounds rows={out_of_range}")
    else:
        reporter.ok("hangang master lat/lng Hangang bounds")


def validate_baseline(reporter, key, config, expected_row_count):
    path = Path(config["path"])
    file_name = config["file"]

    print("\n" + "=" * 60)
    print(f"[VALIDATE] {key} ({file_name})")

    reporter.checked += 1

    if not path.exists():
        reporter.error(f"{file_name} missing path={path}")
        return

    try:
        rows, columns = read_rows(path)
    except Exception as exc:
        reporter.error(f"{file_name} read failed: {exc}")
        return

    if not rows:
        reporter.error(f"{file_name} rows=0")
        return

    if expected_row_count is not None and len(rows) != expected_row_count:
        reporter.warning(
            f"{file_name} rows={len(rows)} differs from max_rows={expected_row_count}"
        )
    else:
        reporter.ok(f"{file_name} rows={len(rows)}")

    validate_required_columns(
        reporter,
        file_name,
        columns,
        config["required_columns"],
    )
    validate_duplicate_names(reporter, file_name, rows)
    validate_lat_lng(
        reporter,
        file_name,
        rows,
        columns,
        config["required_columns"],
    )
    validate_json_columns(
        reporter,
        file_name,
        rows,
        config["json_columns"],
    )
    validate_negative_numbers(reporter, file_name, rows, columns)
    validate_radius_rules(
        reporter,
        file_name,
        rows,
        config["radius_rules"],
    )
    validate_primary_metric(
        reporter,
        file_name,
        rows,
        config["primary_metric"],
    )
    if config.get("percentile_enabled", True):
        validate_range_column(
            reporter,
            file_name,
            rows,
            config["primary_percentile_column"],
            "percentile",
        )
        validate_range_column(
            reporter,
            file_name,
            rows,
            config["primary_score_column"],
            "score",
        )
    else:
        reporter.ok(f"{file_name} percentile validation skipped")


def collect_expected_row_count():
    counts = []

    for config in BASELINE_METRIC_CONFIG.values():
        path = Path(config["path"])

        if not path.exists():
            continue

        try:
            rows, _ = read_rows(path)
            counts.append(len(rows))
        except Exception:
            continue

    if not counts:
        return None

    return max(counts)


def run_validation():
    reporter = ValidationReporter()
    expected_row_count = collect_expected_row_count()

    print(f"[INFO] expected row count baseline=max_rows={expected_row_count}")

    for key, config in BASELINE_METRIC_CONFIG.items():
        if not config.get("validation_enabled", True):
            print("\n" + "=" * 60)
            print(f"[VALIDATE] {key} ({config.get('file', '')})")
            reporter.ok(f"{config.get('file', key)} validation skipped")
            continue

        validate_baseline(reporter, key, config, expected_row_count)

        if key == "hangang":
            validate_hangang_master(reporter)

    reporter.summary()
    return reporter


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"validation_report_v3_6_{timestamp}.txt"

    original_stdout = sys.stdout

    with report_path.open("w", encoding="utf-8") as file:
        sys.stdout = file
        reporter = run_validation()
        sys.stdout = original_stdout

    with report_path.open("r", encoding="utf-8") as file:
        print(file.read())

    print(f"[DONE] validation report saved: {report_path}")

    return 1 if reporter.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

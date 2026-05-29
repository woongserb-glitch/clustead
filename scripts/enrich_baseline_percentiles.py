import csv
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from baseline_metric_config import (
    BASELINE_METRIC_CONFIG,
    HIGHER_BETTER,
    LOWER_BETTER,
)


csv.field_size_limit(sys.maxsize)

BASE_DIR = Path(__file__).resolve().parents[1]
PIPELINE_RUN_DIR = BASE_DIR / "data" / "registry" / "pipeline_runs"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def get_meta_path(path):
    return path.with_name(f"{path.stem}.meta.json")


def count_csv_rows(path):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return max(sum(1 for _ in file) - 1, 0)
    except Exception:
        return None


def update_enrich_meta(path, report):
    metadata = load_json(get_meta_path(path), {})
    metadata.update({
        "last_enriched_at": report.get("enrich_finished_at"),
        "last_enrich_status": report.get("enrich_status"),
        "last_enrich_elapsed_seconds": report.get("enrich_elapsed_seconds"),
        "percentile_columns": report.get("percentile_columns", []),
        "score_columns": report.get("score_columns", []),
        "percentile_columns_added": bool(report.get("columns_added")),
        "baseline_row_count": count_csv_rows(path),
        "updated_by": "enrich",
    })
    save_json(get_meta_path(path), metadata)


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


def clamp_0_100(value):
    return max(0, min(100, value))


def format_percentile_value(value):
    value = clamp_0_100(value)
    return f"{value:.2f}"


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader), list(reader.fieldnames or [])


def write_rows(path, rows, fieldnames):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def better_or_equal_count(values, target, direction):
    if direction == HIGHER_BETTER:
        return sum(1 for value in values if value >= target)

    if direction == LOWER_BETTER:
        return sum(1 for value in values if value <= target)

    raise ValueError(f"Unknown metric direction: {direction}")


def calculate_percentile_and_score(values, target, direction):
    if target is None or not values:
        return "", ""

    better_count = better_or_equal_count(values, target, direction)
    top_percent = better_count / len(values) * 100
    top_percent = clamp_0_100(top_percent)
    score = clamp_0_100(100 - top_percent)

    return format_percentile_value(top_percent), format_percentile_value(score)


def enrich_baseline(key, config):
    path = Path(config["path"])
    started_at = time.time()
    started_iso = now_iso()
    report = {
        "key": key,
        "file": config["file"],
        "path": str(path.relative_to(BASE_DIR)) if path.is_absolute() else str(path),
        "enrich_started_at": started_iso,
        "enrich_status": "not_run",
        "percentile_columns": [],
        "score_columns": [],
        "columns_added": [],
        "columns_updated": [],
    }

    if not config.get("percentile_enabled", True):
        print(f"[SKIP] {config['file']} percentile disabled")
        report.update({
            "enrich_status": "skipped_percentile_disabled",
            "enrich_finished_at": now_iso(),
            "enrich_elapsed_seconds": round(time.time() - started_at, 1),
        })
        return 0, 0, report

    if not path.exists():
        print(f"[ERROR] {config['file']} missing path={path}")
        report.update({
            "enrich_status": "missing_baseline",
            "enrich_finished_at": now_iso(),
            "enrich_elapsed_seconds": round(time.time() - started_at, 1),
        })
        return 0, 0, report

    rows, fieldnames = read_rows(path)

    if not rows:
        print(f"[WARNING] {config['file']} has no rows")
        report.update({
            "enrich_status": "warning_empty_baseline",
            "enrich_finished_at": now_iso(),
            "enrich_elapsed_seconds": round(time.time() - started_at, 1),
        })
        return 0, 1, report

    warning_count = 0

    for metric, direction in config["metrics"].items():
        metric_started_at = time.time()
        percentile_col = f"{metric}_seoul_percentile"
        score_col = f"{metric}_seoul_score"
        report["percentile_columns"].append(percentile_col)
        report["score_columns"].append(score_col)

        if metric not in fieldnames:
            print(f"[ERROR] {config['file']} missing metric={metric}")
            report.update({
                "enrich_status": "failed_missing_metric",
                "enrich_finished_at": now_iso(),
                "enrich_elapsed_seconds": round(time.time() - started_at, 1),
                "error": f"missing metric={metric}",
            })
            return 1, warning_count, report

        for col in [percentile_col, score_col]:
            if col not in fieldnames:
                fieldnames.append(col)
                report["columns_added"].append(col)
            else:
                report["columns_updated"].append(col)

        print(f"[ENRICH] {config['file']} percentile update started metric={metric}")
        print("[ENRICH] columns:")
        print(f"  - {percentile_col}")
        print(f"  - {score_col}")

        valid_values = [
            to_number(row.get(metric))
            for row in rows
        ]
        valid_values = [
            value for value in valid_values
            if value is not None
        ]

        if not valid_values:
            print(f"[WARNING] {config['file']} metric={metric} has no valid numeric values")
            warning_count += 1

        valid_count = 0
        empty_count = 0

        for row in rows:
            target = to_number(row.get(metric))
            percentile, score = calculate_percentile_and_score(
                valid_values,
                target,
                direction,
            )

            if percentile == "":
                empty_count += 1
            else:
                valid_count += 1

            row[percentile_col] = percentile
            row[score_col] = score

        write_rows(path, rows, fieldnames)

        status = "OK" if empty_count == 0 else "WARNING"
        if empty_count:
            warning_count += 1

        print(
            f"[{status}] {config['file']} enriched "
            f"metric={metric} direction={direction} "
            f"rows={len(rows)} valid={valid_count} empty={empty_count}"
        )
        print(
            f"[ENRICH] {config['file']} metric={metric} "
            f"completed in {round(time.time() - metric_started_at, 1)}s"
        )

    report.update({
        "enrich_status": "success" if warning_count == 0 else "success_with_warnings",
        "enrich_finished_at": now_iso(),
        "enrich_elapsed_seconds": round(time.time() - started_at, 1),
        "row_count": len(rows),
        "warning_count": warning_count,
    })
    update_enrich_meta(path, report)

    print(
        f"[ENRICH] {config['file']} completed in "
        f"{report['enrich_elapsed_seconds']}s"
    )

    return 0, warning_count, report


def main():
    error_count = 0
    warning_count = 0
    reports = []

    for key, config in BASELINE_METRIC_CONFIG.items():
        errors, warnings, report = enrich_baseline(key, config)
        error_count += errors
        warning_count += warnings
        reports.append(report)

    print("-" * 60)
    print(
        f"[SUMMARY] enrich complete "
        f"errors={error_count} warnings={warning_count}"
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = PIPELINE_RUN_DIR / f"enrich_baseline_percentiles_{stamp}.json"
    save_json(report_path, {
        "status": "failed" if error_count else "success",
        "error_count": error_count,
        "warning_count": warning_count,
        "generated_at": now_iso(),
        "items": reports,
    })
    print(f"[SUMMARY] enrich report saved: {report_path}")

    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

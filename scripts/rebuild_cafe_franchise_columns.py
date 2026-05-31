"""Derive cafe franchise columns from the existing cafe_items_json.

The cafe count (cafe_count_500m) saturates at 45 because the Kakao Local
category API returns at most 45 results (15/page x 3 pages); ~36% of complexes
hit that ceiling, destroying discrimination in dense areas. This rebuilds a
franchise-based metric instead, classifying the *already collected* item
labels into the 10 major coffee franchises — no Kakao re-fetch, so it is
deterministic and free of the 45-cap drift (franchise counts are far below 45).

Writes per-brand `{brand}_count_500m` (10) and `franchise_total_500m` into
data/baseline/cafe_baseline.csv. Idempotent. The brand keyword rules are the
single source of truth in services.poi_service.SUBTYPE_RULES["cafe"].

Usage:
    python scripts/rebuild_cafe_franchise_columns.py            # dry-run report
    python scripts/rebuild_cafe_franchise_columns.py --apply    # write columns
"""

import csv
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
csv.field_size_limit(10 ** 7)

from services.poi_service import SUBTYPE_RULES  # noqa: E402

CAFE_CSV = BASE_DIR / "data" / "baseline" / "cafe_baseline.csv"
RADIUS = 500
CAFE_RULES = SUBTYPE_RULES["cafe"]
BRANDS = [rule["name"] for rule in CAFE_RULES]  # 10 franchises, priority order
BRAND_COLS = [f"{name}_count_500m" for name in BRANDS]
TOTAL_COL = "franchise_total_500m"


def classify(item):
    """Same matching as poi_service.get_subtype_chips: case-insensitive
    substring over name+label+subtype, rules in priority order, first wins."""
    haystack = " ".join([
        str(item.get("name", "")),
        str(item.get("label", "")),
        str(item.get("subtype", "")),
    ]).lower()
    for rule in CAFE_RULES:
        for keyword in rule["keywords"]:
            if keyword.lower() in haystack:
                return rule["name"]
    return None


def franchise_counts(items_json):
    counts = {name: 0 for name in BRANDS}
    try:
        items = json.loads(items_json) if items_json and items_json != "[]" else []
    except Exception:
        items = []
    for item in items:
        try:
            if float(item.get("distance", 999999)) > RADIUS:
                continue
        except Exception:
            pass
        brand = classify(item)
        if brand is not None:
            counts[brand] += 1
    return counts


def main():
    apply = "--apply" in sys.argv[1:]

    with CAFE_CSV.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    for col in BRAND_COLS + [TOTAL_COL]:
        if col not in fieldnames:
            fieldnames.append(col)

    totals = []
    brand_coverage = {name: 0 for name in BRANDS}
    for row in rows:
        counts = franchise_counts(row.get("cafe_items_json", ""))
        total = sum(counts.values())
        totals.append(total)
        for name in BRANDS:
            row[f"{name}_count_500m"] = counts[name]
            if counts[name] > 0:
                brand_coverage[name] += 1
        row[TOTAL_COL] = total

    if apply:
        with CAFE_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    n = len(rows)
    totals_sorted = sorted(totals)
    print("=" * 56)
    print(f"mode: {'APPLY (written)' if apply else 'DRY-RUN'}  rows={n}")
    print(f"brands ({len(BRANDS)}): {BRANDS}")
    print(f"franchise_total_500m: max={max(totals)} mean={sum(totals)/n:.2f} "
          f"median={totals_sorted[n//2]} #at_max={totals.count(max(totals))}")
    print("brand coverage (complexes with >=1):")
    for name in BRANDS:
        print(f"   {name}: {brand_coverage[name]} ({100*brand_coverage[name]/n:.0f}%)")
    if not apply:
        print("\n(dry-run) re-run with --apply to write columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

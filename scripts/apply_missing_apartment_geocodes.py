"""Fill missing apartment coordinates from an approved geocode override file.

Reproducible patch for the 40 apartments that had blank 좌표X/좌표Y in
data/apartment/seoul_apartments.csv (which is gitignored). The approved
coordinates live in a TRACKED file
(scripts/manual_overrides/missing_apartment_geocodes_approved.csv) so the
data fill can always be re-derived from version control.

Precision-first policy:
  * Only rows in the approved file are touched (HIGH-confidence Kakao address
    matches: gu+dong match, single result, within Seoul bounds).
  * Only cells that are currently BLANK are filled — never overwrite an
    existing coordinate. So the script is idempotent and safe to re-run.
  * MEDIUM/LOW rows are intentionally NOT here; see
    missing_apartment_geocodes_manual_review.csv.

Usage:
    python scripts/apply_missing_apartment_geocodes.py            # dry-run report
    python scripts/apply_missing_apartment_geocodes.py --apply    # write coords
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
APPROVED = BASE_DIR / "scripts" / "manual_overrides" / "missing_apartment_geocodes_approved.csv"
MASTER_ENCODING = "cp949"

NAME_COL, GU_COL, DONG_COL = "k-아파트명", "주소(시군구)", "주소(읍면동)"
X_COL, Y_COL = "좌표X", "좌표Y"  # X = longitude, Y = latitude


def key(name, gu, dong):
    return (str(name or "").strip(), str(gu or "").strip(), str(dong or "").strip())


def coord_blank(row):
    return not str(row.get(X_COL, "")).strip() or not str(row.get(Y_COL, "")).strip()


def main():
    apply = "--apply" in sys.argv[1:]

    with APPROVED.open(encoding="utf-8-sig", newline="") as f:
        approved = list(csv.DictReader(f))
    # key -> (lng, lat)  (Kakao approved file stores lat/lng)
    overrides = {key(a["name"], a["gu"], a["dong"]): (a["lng"].strip(), a["lat"].strip())
                 for a in approved}
    print(f"approved overrides: {len(overrides)}")

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    blank_before = sum(1 for r in rows if coord_blank(r))

    # duplicate-key analysis among master rows targeted by overrides
    from collections import Counter
    key_counts = Counter(key(r.get(NAME_COL), r.get(GU_COL), r.get(DONG_COL)) for r in rows)
    dup_keys_in_overrides = [k for k in overrides if key_counts.get(k, 0) > 1]

    applied = 0
    applied_rows = 0
    matched_keys = set()
    for r in rows:
        k = key(r.get(NAME_COL), r.get(GU_COL), r.get(DONG_COL))
        if k in overrides and coord_blank(r):
            lng, lat = overrides[k]
            if apply:
                r[X_COL] = lng
                r[Y_COL] = lat
            applied_rows += 1
            matched_keys.add(k)

    applied = len(matched_keys)
    unmatched = [k for k in overrides if k not in matched_keys]
    blank_after = blank_before - (applied_rows if apply else 0)

    if apply:
        with MASTER.open("w", encoding=MASTER_ENCODING, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print("=" * 56)
    print(f"mode:                 {'APPLY (written)' if apply else 'DRY-RUN (no write)'}")
    print(f"blank-coord BEFORE:   {blank_before}")
    print(f"override keys matched:{applied} (rows filled: {applied_rows})")
    print(f"blank-coord AFTER:    {blank_after}")
    print(f"overrides unmatched:  {len(unmatched)}  {unmatched if unmatched else ''}")
    print(f"duplicate-key impact: {len(dup_keys_in_overrides)} override key(s) match >1 master row "
          f"{dup_keys_in_overrides if dup_keys_in_overrides else '(none)'}")
    if not apply:
        print("\n(dry-run) re-run with --apply to write coordinates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

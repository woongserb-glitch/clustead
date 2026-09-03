"""Fill missing apartment household counts from an approved override file.

Sibling of apply_missing_apartment_geocodes.py. The source (서울시 공동주택
아파트 정보) ships 0 for a handful of complexes -- newly registered ones in
particular -- and 0 is a missing value, not a real count. The page renders "-"
for those, but where a trustworthy figure exists it is better to carry it.

The approved counts live in a TRACKED file
(scripts/manual_overrides/missing_apartment_households_approved.csv) because the
master itself is gitignored, so the fill can always be re-derived.

Policy, mirroring the geocode overrides:
  * Only rows listed in the approved file are touched.
  * Only cells that are currently blank or 0 are filled -- an existing positive
    count is never overwritten. So the script is idempotent.
  * Identity is checked before writing: the master row must still carry the
    동수/주차대수 recorded at approval time. If the master has changed, the row
    is reported as STALE and skipped rather than silently clobbered.
  * Complexes that should NOT be filled (e.g. duplicate registrations) live in
    missing_apartment_households_manual_review.csv and are intentionally absent
    from the approved file.

Usage:
    python scripts/apply_missing_apartment_households.py            # dry-run
    python scripts/apply_missing_apartment_households.py --apply    # write
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
APPROVED = BASE_DIR / "scripts" / "manual_overrides" / "missing_apartment_households_approved.csv"
MASTER_ENCODING = "cp949"

CODE_COL, NAME_COL, GU_COL = "k-아파트코드", "k-아파트명", "주소(시군구)"
HOUSEHOLD_COL, DONG_COL, PARKING_COL = "k-전체세대수", "k-전체동수", "주차대수"


def text(value):
    value = "" if value is None else str(value).strip()
    if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
        value = value[:-2]
    return value


def is_missing(value):
    return text(value) in ("", "0")


def same(a, b):
    """승인 시점 식별값과 현재 값이 같은지 (숫자면 숫자로 비교)."""
    a, b = text(a), text(b)
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def main():
    apply_changes = "--apply" in sys.argv[1:]

    with APPROVED.open(encoding="utf-8-sig", newline="") as handle:
        approved = {row["apt_code"].strip(): row for row in csv.DictReader(handle)}
    print(f"approved households: {len(approved)}")

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)

    filled, stale, skipped, unmatched = [], [], [], set(approved)
    for row in rows:
        code = text(row.get(CODE_COL))
        entry = approved.get(code)
        if entry is None:
            continue
        unmatched.discard(code)
        label = f"{row.get(GU_COL)} {row.get(NAME_COL)}"

        if not is_missing(row.get(HOUSEHOLD_COL)):
            skipped.append((label, text(row.get(HOUSEHOLD_COL))))
            continue
        if not same(row.get(DONG_COL), entry.get("dong_count")) or not same(
            row.get(PARKING_COL), entry.get("parking")
        ):
            stale.append(
                (
                    label,
                    f"동 {text(row.get(DONG_COL))}/주차 {text(row.get(PARKING_COL))}",
                    f"승인시 동 {entry.get('dong_count')}/주차 {entry.get('parking')}",
                )
            )
            continue

        row[HOUSEHOLD_COL] = text(entry["households"])
        filled.append((label, row[HOUSEHOLD_COL], entry.get("source", "")))

    for label, value, source in filled:
        print(f"  FILL  {label}: {value}세대  ({source})")
    for label, value in skipped:
        print(f"  SKIP  {label}: 이미 {value}세대")
    for label, now, then in stale:
        print(f"  STALE {label}: {now} != {then} -> 건너뜀")
    for code in sorted(unmatched):
        print(f"  MISS  {code}: 마스터에 없음")

    print(f"\nfilled={len(filled)} skipped={len(skipped)} stale={len(stale)} unmatched={len(unmatched)}")

    if not apply_changes:
        print("dry-run 입니다. 반영하려면 --apply 를 붙이세요.")
        return
    if not filled:
        print("변경 없음.")
        return

    staged = MASTER.with_suffix(".csv.hh_new")
    with staged.open("w", encoding=MASTER_ENCODING, errors="replace", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    staged.replace(MASTER)
    print(f"[OK] {len(filled)}건 반영")


if __name__ == "__main__":
    main()

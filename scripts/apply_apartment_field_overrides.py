"""Apply approved per-field corrections to the apartment master.

Third sibling of the geocode/household override scripts, and the general one:
it patches an arbitrary column of an arbitrary row instead of a fixed field.
Use it for source defects that are not "missing value" but "wrong value" --
two complexes sharing one name, an address pointing at the neighbouring block,
a row that carries the summed figures of two 단지.

The corrections live in a TRACKED file
(scripts/manual_overrides/apartment_field_overrides.csv) because the master
itself is gitignored, so every edit stays auditable and re-derivable.

Safety, same shape as fix_wrong_apartment_geocodes.py:
  * A cell is rewritten only when it still holds `expected_current`. If the
    source has changed the value since approval, the row is reported as STALE
    and skipped -- so the script is idempotent and safe to re-run after every
    master refresh.
  * A cell that already holds the new value is reported as DONE, not an error.

Usage:
    python scripts/apply_apartment_field_overrides.py            # dry-run
    python scripts/apply_apartment_field_overrides.py --apply    # write
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
APPROVED = BASE_DIR / "scripts" / "manual_overrides" / "apartment_field_overrides.csv"
MASTER_ENCODING = "cp949"
CODE_COL, NAME_COL = "k-아파트코드", "k-아파트명"


def text(value):
    value = "" if value is None else str(value).strip()
    if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
        value = value[:-2]
    return value


def same(a, b):
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
        entries = [row for row in csv.DictReader(handle)]
    print(f"approved field overrides: {len(entries)}")

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)

    by_code = {}
    for row in rows:
        by_code.setdefault(text(row.get(CODE_COL)), row)

    applied, done, stale, missing = [], [], [], []
    for entry in entries:
        code = entry["apt_code"].strip()
        column = entry["column"].strip()
        row = by_code.get(code)
        if row is None:
            missing.append((code, column, "마스터에 코드 없음"))
            continue
        if column not in columns:
            missing.append((code, column, "마스터에 컬럼 없음"))
            continue

        current = row.get(column)
        if same(current, entry["new_value"]):
            done.append((code, row.get(NAME_COL), column))
            continue
        if not same(current, entry["expected_current"]):
            stale.append((code, row.get(NAME_COL), column, text(current), entry["expected_current"]))
            continue

        row[column] = entry["new_value"]
        applied.append((code, row.get(NAME_COL), column, entry["expected_current"], entry["new_value"]))

    for code, name, column, old, new in applied:
        print(f"  SET   {code} {name} .{column}: {old or '(빈값)'} -> {new}")
    for code, name, column in done:
        print(f"  DONE  {code} {name} .{column}: 이미 반영됨")
    for code, name, column, now, expected in stale:
        print(f"  STALE {code} {name} .{column}: 현재 {now or '(빈값)'} != 승인시 {expected or '(빈값)'} -> 건너뜀")
    for code, column, why in missing:
        print(f"  MISS  {code} .{column}: {why}")

    print(f"\napplied={len(applied)} done={len(done)} stale={len(stale)} missing={len(missing)}")

    if not apply_changes:
        print("dry-run 입니다. 반영하려면 --apply 를 붙이세요.")
        return
    if not applied:
        print("변경 없음.")
        return

    staged = MASTER.with_suffix(".csv.field_new")
    with staged.open("w", encoding=MASTER_ENCODING, errors="replace", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
    staged.replace(MASTER)
    print(f"[OK] {len(applied)}건 반영")


if __name__ == "__main__":
    main()

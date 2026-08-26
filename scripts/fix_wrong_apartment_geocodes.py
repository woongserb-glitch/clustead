"""Correct apartments whose coordinates were copied from a DIFFERENT complex.

Companion to apply_missing_apartment_geocodes.py. That script only ever fills
BLANK cells and never overwrites — a deliberate safety policy. These 6 rows,
however, hold a *wrong* non-blank coordinate: each had inherited another
complex's point (verified 2026-08-25 by finding coordinate collisions whose
members sit in different 구, then re-geocoding both sides by road address).
Overwriting therefore needs its own explicit, auditable path.

Safety: a row is rewritten only when its current coordinate still equals the
old_lat/old_lng recorded at approval time. If the master has changed since,
the row is reported as STALE and skipped rather than silently clobbered — so
the script stays idempotent and safe to re-run.

Usage:
    python scripts/fix_wrong_apartment_geocodes.py            # dry-run report
    python scripts/fix_wrong_apartment_geocodes.py --apply    # write coords
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
APPROVED = BASE_DIR / "scripts" / "manual_overrides" / "wrong_apartment_geocodes_approved.csv"
MASTER_ENCODING = "cp949"

NAME_COL, GU_COL, DONG_COL = "k-아파트명", "주소(시군구)", "주소(읍면동)"
X_COL, Y_COL = "좌표X", "좌표Y"  # X = longitude, Y = latitude

# 승인 시점 좌표와 현재 좌표가 이 이상 어긋나면 마스터가 바뀐 것으로 보고 건너뛴다.
STALE_TOLERANCE_DEG = 1e-4  # 약 10m


def key(name, gu, dong):
    return (str(name or "").strip(), str(gu or "").strip(), str(dong or "").strip())


def close(a, b):
    try:
        return abs(float(a) - float(b)) <= STALE_TOLERANCE_DEG
    except (TypeError, ValueError):
        return False


def main():
    apply = "--apply" in sys.argv[1:]

    with APPROVED.open(encoding="utf-8-sig", newline="") as f:
        approved = {key(a["name"], a["gu"], a["dong"]): a for a in csv.DictReader(f)}
    print(f"approved corrections: {len(approved)}")

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixed, stale, unmatched = [], [], set(approved)
    for r in rows:
        k = key(r.get(NAME_COL), r.get(GU_COL), r.get(DONG_COL))
        a = approved.get(k)
        if not a:
            continue
        unmatched.discard(k)
        if not (close(r.get(Y_COL), a["old_lat"]) and close(r.get(X_COL), a["old_lng"])):
            stale.append((k, r.get(Y_COL), r.get(X_COL)))
            continue
        if apply:
            r[X_COL] = a["lng"]
            r[Y_COL] = a["lat"]
        fixed.append((k[0], a["old_lat"], a["old_lng"], a["lat"], a["lng"], a["reason"]))

    if apply and fixed:
        with MASTER.open("w", encoding=MASTER_ENCODING, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print("=" * 72)
    print(f"mode:                 {'APPLY (written)' if apply else 'DRY-RUN (no write)'}")
    print(f"corrected:            {len(fixed)}")
    for name, oy, ox, ny, nx, reason in fixed:
        print(f"  {name}")
        print(f"      {oy},{ox}  ->  {ny},{nx}")
        print(f"      사유: {reason}")
    print(f"stale (skipped):      {len(stale)}  {stale if stale else ''}")
    print(f"unmatched overrides:  {len(unmatched)}  {sorted(unmatched) if unmatched else ''}")
    if not apply:
        print("\n(dry-run) re-run with --apply to write coordinates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

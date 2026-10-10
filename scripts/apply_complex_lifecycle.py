"""재건축이 끝난 옛 단지를 현재 마스터에서 뺀다.

refresh_apartment_master.py 는 월간 병합 때 같은 목록(complex_lifecycle_approved.csv,
status=rebuilt)을 걸러 내지만, 병합 없이 지금 마스터에 바로 반영할 때 이 스크립트를 쓴다.

안전장치: 새 단지(successor_code)가 마스터에 있을 때만 옛 단지를 뺀다. 새 단지가 없으면
옛 단지를 남기고 SKIP 으로 보고한다(둘 다 잃지 않도록). 이미 빠진 행은 그대로 둔다(멱등).

Usage:
    python scripts/apply_complex_lifecycle.py            # dry-run report
    python scripts/apply_complex_lifecycle.py --apply    # 마스터에서 제거
"""

import csv
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
LIFECYCLE = BASE_DIR / "scripts" / "manual_overrides" / "complex_lifecycle_approved.csv"
MASTER_ENCODING = "cp949"
CODE_COL, NAME_COL = "k-아파트코드", "k-아파트명"


def main():
    apply = "--apply" in sys.argv[1:]
    with LIFECYCLE.open(encoding="utf-8-sig", newline="") as handle:
        # merged(같은 단지 중복 행)도 같은 규칙: 남길 행이 마스터에 있을 때만 뺀다.
        rebuilt = [r for r in csv.DictReader(handle) if r.get("status") in ("rebuilt", "merged")]

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    codes = {r.get(CODE_COL, "").strip() for r in rows}

    drop, skipped, absent = set(), [], []
    for entry in rebuilt:
        old, new = entry["code"].strip(), entry.get("successor_code", "").strip()
        if old not in codes:
            absent.append(entry["name"])
        elif new not in codes:
            skipped.append((entry["name"], entry.get("successor_name", "")))
        else:
            drop.add(old)
            print(f"  제거: {entry['gu']} {entry['name']} -> {entry.get('successor_name', '')}")

    print(f"재건축 옛 단지·중복 행 {len(rebuilt)}건: 제거 {len(drop)} / 이미 없음 {len(absent)} / 보류 {len(skipped)}")
    for name, succ in skipped:
        print(f"  [보류] {name}: 새 단지 {succ} 가 마스터에 없음")

    if apply and drop:
        kept = [r for r in rows if r.get(CODE_COL, "").strip() not in drop]
        with MASTER.open("w", encoding=MASTER_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(kept)
        print(f"[OK] 마스터 {len(rows)} -> {len(kept)}건")
    elif not apply:
        print("\n(dry-run) --apply 로 마스터에 반영합니다.")


if __name__ == "__main__":
    main()

"""Refresh data/apartment/seoul_apartments.csv from the Seoul Open API.

The apartment master is the ROOT of the whole pipeline: 12 baseline builders,
the transaction mapping and preload_service all read it. Replacing it forces a
full baseline rebuild and a golden-master re-save, so it is deliberately kept
OUT of the monthly auto-download in data_sources.json (registered there with
check_mode=manual, i.e. detect-only). This script is the apply path.

Source: 서울열린데이터광장 "서울시 공동주택 아파트 정보", service OpenAptInfo.
The API carries the same 47 columns as the master plus one extra
(APT_STDG_ADDR) that the master has never stored.

MERGE, not replace. Verified 2026-09-03: the live API blanks 세대수 for 62
complexes that the current master has values for (타워팰리스1차 1297, 센트라스
2097 ...). A straight overwrite would silently degrade the service. So each
field takes the API value only when the API value is non-blank, and otherwise
keeps what the master already holds. New complexes are appended; disappearing
complexes are reported and kept (they are only dropped with --drop-removed).

Coordinates: the API still serves the wrong points for the 53 rows corrected in
scripts/manual_overrides/. Those overrides are re-applied after the merge --
run both override scripts with --apply, or pass --run-overrides here.

Usage:
    python scripts/refresh_apartment_master.py             # dry-run report
    python scripts/refresh_apartment_master.py --apply     # merge + write
    python scripts/refresh_apartment_master.py --apply --run-overrides
"""

import csv
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASTER = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
MASTER_ENCODING = "cp949"
REJECTED = BASE_DIR / "scripts" / "manual_overrides" / "duplicate_apartments_rejected.csv"
API_BASE = "http://openapi.seoul.go.kr:8088"
SERVICE = "OpenAptInfo"
PAGE_SIZE = 1000
API_ONLY_COLUMN = "APT_STDG_ADDR"  # 마스터에 없는 유일한 API 컬럼
CODE_COL, NAME_COL, GU_COL = "k-아파트코드", "k-아파트명", "주소(시군구)"
HOUSEHOLD_COL, X_COL, Y_COL = "k-전체세대수", "좌표X", "좌표Y"

# 위치 기반 매핑이 어긋나지 않았는지 확인하는 고정점.
ANCHORS = {
    CODE_COL: "APT_CD",
    NAME_COL: "APT_NM",
    GU_COL: "SGG_ADDR",
    HOUSEHOLD_COL: "TNOHSH",
    "주차대수": "PRK_CNTOM",
    X_COL: "XCRD",
    Y_COL: "YCRD",
}

# 단지 수가 이 비율 이상 줄면 소스 사고로 보고 중단한다.
SHRINK_ABORT_RATIO = 0.01


def load_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def fetch_rows():
    load_env()
    service_key = os.getenv("SEOUL_OPEN_DATA_KEY")
    if not service_key:
        sys.exit("SEOUL_OPEN_DATA_KEY is required (.env).")

    rows, start, total = [], 1, None
    while True:
        end = start + PAGE_SIZE - 1
        url = f"{API_BASE}/{service_key}/json/{SERVICE}/{start}/{end}/"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        body = payload.get(SERVICE) or {}
        code = (body.get("RESULT") or {}).get("CODE")
        if code and code not in ("INFO-000",):
            sys.exit(f"API error {code}: {(body.get('RESULT') or {}).get('MESSAGE')}")
        page = body.get("row") or []
        if isinstance(page, dict):
            page = [page]
        rows.extend(page)
        if total is None:
            total = int(body.get("list_total_count") or len(page))
        if len(rows) >= total or not page:
            break
        start = end + 1
    return rows, total


def text(value):
    """API의 float 표기(183.0)를 마스터의 정수 표기(183)로 맞춘다."""
    if value is None:
        return ""
    value = str(value).strip()
    if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
        value = value[:-2]
    return value


def same_number(a, b):
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def build_mapping(csv_columns, api_columns):
    usable = [c for c in api_columns if c != API_ONLY_COLUMN]
    if len(usable) != len(csv_columns):
        sys.exit(
            f"컬럼 수 불일치: 마스터 {len(csv_columns)} vs API-1 {len(usable)}. "
            "API 스키마가 바뀌었으니 매핑을 다시 확인하세요."
        )
    mapping = dict(zip(csv_columns, usable))
    for csv_col, expected in ANCHORS.items():
        if mapping.get(csv_col) != expected:
            sys.exit(f"매핑 고정점 실패: {csv_col} -> {mapping.get(csv_col)} (기대 {expected})")
    return mapping


def zero_over_positive(new_value, old_value):
    """양수였던 수치를 API가 0으로 되돌리는 경우 (소스 품질 저하)."""
    try:
        return float(new_value) == 0 and float(old_value) != 0
    except (TypeError, ValueError):
        return False


def merge_row(current, api_row, mapping):
    """API 값이 비었거나 양수를 0으로 지우는 경우엔 현재 값을 지킨다.

    숫자가 같으면 현재 표기를 유지해 불필요한 diff를 만들지 않는다.
    """
    merged, changes, protected = dict(current), [], []
    for csv_col, api_col in mapping.items():
        new_value = text(api_row.get(api_col))
        old_value = text(current.get(csv_col))
        if not new_value:
            continue
        if new_value == old_value or same_number(new_value, old_value):
            continue
        if zero_over_positive(new_value, old_value):
            protected.append((csv_col, old_value))
            continue
        merged[csv_col] = new_value
        changes.append((csv_col, old_value, new_value))
    return merged, changes, protected


def blank(value):
    return text(value) in ("", "0")


def load_rejected():
    """같은 단지가 코드 두 개로 수록된 경우의 껍데기 행 목록.

    소스가 계속 내려보내므로 병합 때마다 걸러야 한다. 유지할 실체 행의 코드를
    함께 적어 두고, 그 행이 사라지면 제외를 멈춘다(둘 다 잃지 않도록).
    """
    if not REJECTED.exists():
        return {}
    with REJECTED.open(encoding="utf-8-sig", newline="") as handle:
        return {row["reject_code"].strip(): row for row in csv.DictReader(handle)}


def main():
    args = sys.argv[1:]
    apply_changes = "--apply" in args
    run_overrides = "--run-overrides" in args
    drop_removed = "--drop-removed" in args

    with MASTER.open(encoding=MASTER_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames)
        current_rows = list(reader)

    api_rows, total = fetch_rows()
    print(f"API {SERVICE}: {len(api_rows)}건 수집 (list_total_count={total})")
    if not api_rows:
        sys.exit("API가 0건을 반환했습니다. 중단합니다.")

    mapping = build_mapping(columns, list(api_rows[0].keys()))
    print(f"컬럼 매핑 확인 완료 ({len(mapping)}열, API 전용 {API_ONLY_COLUMN} 제외)")

    by_code = {text(row.get(CODE_COL)): row for row in current_rows}
    api_by_code = {text(row.get("APT_CD")): row for row in api_rows}

    rejected = load_rejected()
    # 유지 대상이 실제로 살아 있을 때만 껍데기를 버린다.
    active_rejects = {
        code: entry
        for code, entry in rejected.items()
        if entry.get("keep_code", "").strip() in api_by_code
    }
    for code, entry in rejected.items():
        if code not in active_rejects:
            print(f"  [주의] 중복 제외 보류: {code} {entry.get('reject_name')} "
                  f"(유지 대상 {entry.get('keep_code')} 가 소스에 없음)")
    for code in active_rejects:
        api_by_code.pop(code, None)

    added = [code for code in api_by_code if code not in by_code]
    removed = [code for code in by_code if code not in api_by_code]

    merged_rows, changed, household_saved = [], [], []
    dropped = []
    for row in current_rows:
        code = text(row.get(CODE_COL))
        if code in active_rejects:
            dropped.append((row.get(GU_COL), row.get(NAME_COL), active_rejects[code]))
            continue
        api_row = api_by_code.get(code)
        if api_row is None:
            merged_rows.append(row)
            continue
        merged, changes, protected = merge_row(row, api_row, mapping)
        merged_rows.append(merged)
        if protected:
            household_saved.append((row.get(GU_COL), row.get(NAME_COL), protected))
        # k-수정일자는 거의 전 행이 바뀌므로 변경 리포트에서 제외한다.
        real = [c for c in changes if c[0] != "k-수정일자"]
        if real:
            changed.append((row.get(GU_COL), row.get(NAME_COL), real))

    next_no = max((int(text(r.get(columns[0])) or 0) for r in current_rows), default=0)
    new_rows = []
    for code in added:
        next_no += 1
        api_row = api_by_code[code]
        row = {csv_col: text(api_row.get(api_col)) for csv_col, api_col in mapping.items()}
        row[columns[0]] = str(next_no)
        new_rows.append(row)
    new_rows.sort(key=lambda r: (r.get(GU_COL, ""), r.get(NAME_COL, "")))
    merged_rows.extend(new_rows)

    if drop_removed and removed:
        merged_rows = [r for r in merged_rows if text(r.get(CODE_COL)) not in set(removed)]

    print()
    print(f"신규 {len(added)}건 / 소멸 {len(removed)}건 / 속성 변경 {len(changed)}건")
    print(f"중복 제외 {len(active_rejects)}건 (마스터에서 제거 {len(dropped)}건)")
    for gu, name, entry in dropped:
        print(f"    제외: {gu} {name} -> {entry.get('keep_name')} 로 통합")
    print(f"수치 보호(API가 0/빈값으로 지우려 한 값 유지) {len(household_saved)}건")
    for gu, name, protected in household_saved[:6]:
        detail = ", ".join(f"{col}={value}" for col, value in protected[:3])
        print(f"    지킴: {gu} {name} -> {detail}")
    print()
    for row in new_rows:
        print(
            f"  + {row.get(GU_COL):6} {str(row.get(NAME_COL))[:24]:26} "
            f"{text(row.get(HOUSEHOLD_COL)) or '?':>6}세대  "
            f"준공 {str(row.get('k-사용검사일-사용승인일'))[:10]}"
        )
    for code in removed:
        row = by_code[code]
        print(f"  - {row.get(GU_COL)} {row.get(NAME_COL)} ({'삭제' if drop_removed else '유지'})")

    # 검증 게이트
    before, after = len(current_rows), len(merged_rows)
    coord_before = sum(1 for r in current_rows if blank(r.get(X_COL)) or blank(r.get(Y_COL)))
    coord_after = sum(1 for r in merged_rows if blank(r.get(X_COL)) or blank(r.get(Y_COL)))
    hh_before = sum(1 for r in current_rows if blank(r.get(HOUSEHOLD_COL)))
    hh_after = sum(1 for r in merged_rows if blank(r.get(HOUSEHOLD_COL)))
    print()
    print(f"검증: 단지 {before} -> {after} / 좌표결측 {coord_before} -> {coord_after} / 세대수결측 {hh_before} -> {hh_after}")

    problems = []
    if after < before - len(dropped) - max(1, before * SHRINK_ABORT_RATIO):
        problems.append(f"단지 수가 {before - after}건 줄었습니다.")
    if coord_after > coord_before + len(added):
        problems.append(f"좌표 결측이 {coord_after - coord_before}건 늘었습니다.")
    if hh_after > hh_before + len(added):
        problems.append(f"세대수 결측이 {hh_after - hh_before}건 늘었습니다.")
    if problems:
        for problem in problems:
            print(f"  [ABORT] {problem}")
        sys.exit(1)
    print("  [OK] 게이트 통과")

    if not apply_changes:
        print()
        print("dry-run 입니다. 반영하려면 --apply 를 붙이세요.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = MASTER.with_suffix(f".csv.bak.{stamp}")
    backup.write_bytes(MASTER.read_bytes())
    staged = MASTER.with_suffix(".csv.new")
    with staged.open("w", encoding=MASTER_ENCODING, errors="replace", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(merged_rows)
    staged.replace(MASTER)
    print()
    print(f"[OK] 마스터 갱신 {before} -> {after}건 (백업 {backup.name})")

    if run_overrides:
        for script in (
            "apply_missing_apartment_geocodes.py",
            "fix_wrong_apartment_geocodes.py",
            "apply_missing_apartment_households.py",
            "apply_apartment_field_overrides.py",
        ):
            print(f"\n--- {script} --apply ---")
            subprocess.run([sys.executable, str(BASE_DIR / "scripts" / script), "--apply"], check=True)
    else:
        print("override를 다시 적용하세요:")
        print("  python scripts/apply_missing_apartment_geocodes.py --apply")
        print("  python scripts/fix_wrong_apartment_geocodes.py --apply")
        print("  python scripts/apply_missing_apartment_households.py --apply")
        print("  python scripts/apply_apartment_field_overrides.py --apply")


if __name__ == "__main__":
    main()

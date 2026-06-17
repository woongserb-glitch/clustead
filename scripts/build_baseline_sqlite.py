"""인덱스 조회 전용 baseline CSV들을 SQLite DB로 변환(메모리 절감).

배경: 1GB 서버에서 baseline 전체를 dict-of-str로 상주시키면 RAM이 부족하다.
medical(180MB)·academy(128MB) 등 '인덱스 조회 전용' baseline은 메모리에 들고
있을 필요 없이 SQLite 인덱스 조회로 대체한다. 스캔되는 thin baseline
(subway/cctv/convenience/mart/cafe/school_zone)은 메모리에 그대로 둔다.

설계(바이트 동일성 유지):
- 원본 CSV 문자열을 그대로 TEXT로 저장한다. 런타임에서 parse_csv_row를 적용하면
  기존 인메모리 dict와 값·타입이 동일해진다.
- preload_service.rebuild_baseline_index 의 키 규칙을 그대로 재현한 보조 컬럼을 둔다:
    _ck = composite key = norm(name) US norm(gu) US norm(dong)   (US=\x1f)
    _nk = name-only key = norm(name)
  name 은 (name, apartment_name) 중 첫 비어있지 않은 값. norm 은 strip.
  → 런타임 .get(composite_tuple)=_ck 조회(rowid DESC, last-wins),
     .get(name)=_nk 조회(rowid ASC, first-wins) 로 기존 dict 인덱스 의미와 일치.

stdlib(csv, sqlite3)만 사용 → 런타임 의존(requirements.txt)으로 1GB 서버에서도 실행 가능.

사용:
    python scripts/build_baseline_sqlite.py
출력:
    data/baseline.db   (preload_service 가 읽는다)
"""

import csv
import os
import sqlite3
import sys

# 거대 셀(POI 목록 등) 대응 — pandas엔 없던 csv 필드 한도 제거.
csv.field_size_limit(2**31 - 1)

KEY_SEP = "\x1f"

# SQLite로 옮길 '인덱스 조회 전용' baseline (테이블명 = 카테고리 키).
# 스캔되는 subway/cctv/convenience/mart/cafe/school_zone 은 제외(메모리 유지).
INDEXED_BASELINES = [
    "academy", "medical", "ev_charger", "shopping", "culture",
    "bus", "commercial", "bike", "fire_station", "nightlife", "hangang",
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "baseline.db")


def norm(value):
    return str(value or "").strip()


def row_keys(row):
    """rebuild_baseline_index 와 동일한 (composite, name-only) 키."""
    name = norm(row.get("name")) or norm(row.get("apartment_name"))
    gu = norm(row.get("gu"))
    dong = norm(row.get("dong"))
    ck = KEY_SEP.join((name, gu, dong))
    return ck, name


def read_csv_rows(path, encodings=("utf-8-sig", "cp949")):
    last_err = None
    for enc in encodings:
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                return reader.fieldnames, list(reader)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return None, []


def build_table(conn, category):
    csv_path = os.path.join(ROOT, "data", "baseline", f"{category}_baseline.csv")
    if not os.path.exists(csv_path):
        print(f"[SKIP] {category}: 파일 없음 {csv_path}")
        return 0

    fieldnames, rows = read_csv_rows(csv_path)
    if not fieldnames:
        print(f"[SKIP] {category}: 헤더 없음")
        return 0

    cols = [c for c in fieldnames if c is not None]
    # 보조 키 컬럼은 별도로 추가(원본 컬럼과 충돌 방지를 위해 언더스코어 접두).
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols) + ', "_ck" TEXT, "_nk" TEXT'

    conn.execute(f'DROP TABLE IF EXISTS "{category}"')
    conn.execute(f'CREATE TABLE "{category}" ({col_defs})')

    placeholders = ", ".join(["?"] * (len(cols) + 2))
    insert_cols = ", ".join(f'"{c}"' for c in cols) + ', "_ck", "_nk"'
    insert_sql = f'INSERT INTO "{category}" ({insert_cols}) VALUES ({placeholders})'

    payload = []
    for row in rows:
        ck, nk = row_keys(row)
        values = [row.get(c, "") for c in cols] + [ck, nk]
        payload.append(values)

    conn.executemany(insert_sql, payload)
    conn.execute(f'CREATE INDEX "ix_{category}_ck" ON "{category}" ("_ck")')
    conn.execute(f'CREATE INDEX "ix_{category}_nk" ON "{category}" ("_nk")')
    conn.commit()

    print(f"[OK] {category}: {len(payload)}행, {len(cols)}컬럼")
    return len(payload)


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    total = 0
    for category in INDEXED_BASELINES:
        total += build_table(conn, category)
    conn.close()

    size_mb = os.path.getsize(DB_PATH) / 1024 / 1024
    print("-" * 50)
    print(f"완료: {DB_PATH}  ({size_mb:.1f} MB, 총 {total}행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

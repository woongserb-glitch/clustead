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
    # 2026-08-26 추가. 런타임이 CSV 를 통째로 인메모리에 들고 있었고(RAM 961MB 서버에
    # 약 50MB), /admin/ranking-debug 는 아예 CSV 파일을 다시 열어 두 달 묵은 값을
    # 보여줬다. db 로 옮겨 지연 조회로 바꾼다.
    "subway", "cctv", "cafe", "mart", "convenience", "school_zone", "park",
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



def _create_ranking_index(conn, category, cols):
    """admin 랭킹용 커버링 인덱스.

    SQLite 는 레코드 뒤쪽 컬럼을 읽으려면 앞쪽 컬럼 데이터를 건너뛰어야 하고,
    medical 처럼 items_json(59MB) 이 앞에 있으면 백분위 컬럼 하나를 읽자고
    행마다 오버플로 페이지를 훑는다. 콜드 캐시인 서버에서 60초를 넘겨
    gunicorn 이 워커를 죽였다. 필요한 컬럼만 담은 커버링 인덱스를 두면
    SCAN ... USING COVERING INDEX 로 바뀌어 테이블 행에 접근하지 않는다
    (실측 122ms -> 3ms).
    """
    try:
        from baseline_metric_config import BASELINE_METRIC_CONFIG
    except Exception:
        return

    wanted = []
    for config in BASELINE_METRIC_CONFIG.values():
        if os.path.basename(config.get("file", "")) != f"{category}_baseline.csv":
            continue
        for column in (
            config.get("primary_metric"),
            config.get("primary_percentile_column"),
            config.get("primary_score_column"),
            *config.get("debug_columns", []),
        ):
            if column and column in cols and column not in wanted:
                wanted.append(column)

    if not wanted:
        return

    index_cols = ["name", "gu", "dong"] + wanted
    index_cols = [c for c in dict.fromkeys(index_cols) if c in cols]
    col_sql = ", ".join(f'"{c}"' for c in index_cols)
    conn.execute(f'DROP INDEX IF EXISTS "ix_{category}_rank"')
    conn.execute(f'CREATE INDEX "ix_{category}_rank" ON "{category}" ({col_sql})')


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
    _create_ranking_index(conn, category, cols)
    conn.commit()

    print(f"[OK] {category}: {len(payload)}행, {len(cols)}컬럼")
    return len(payload)


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 새 DB 를 옆에 만들고 다 만든 뒤에 바꿔 끼운다. 기존 파일부터 지우면 도중에
    # 한 카테고리라도 실패했을 때 멀쩡하던 DB 가 사라지고 빈 DB 만 남는다.
    tmp_path = DB_PATH + ".new"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    conn = sqlite3.connect(tmp_path)
    total = 0
    try:
        for category in INDEXED_BASELINES:
            total += build_table(conn, category)
    except BaseException:
        conn.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print("[FAIL] 빌드 중단 — 기존 baseline.db 는 그대로 둡니다.")
        raise
    conn.close()

    os.replace(tmp_path, DB_PATH)

    size_mb = os.path.getsize(DB_PATH) / 1024 / 1024
    print("-" * 50)
    print(f"완료: {DB_PATH}  ({size_mb:.1f} MB, 총 {total}행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

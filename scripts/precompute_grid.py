"""무거운 격자 연산을 빌드 시점에 미리 계산해 grid.db 에 굽는다.

왜
    서버(1코어 / RAM 961MB)에서 미캐시 클러스터 조합이 실측 58초 걸린다.
    gunicorn timeout 이 60초이고 워커는 2개뿐이라, 그 시간 동안 처리 능력의
    절반이 묶인다. 설정 파일 주석의 2026-07-28 '워커 스파이럴' 과 같은 조건이다.

    빌드 때 계산해두면 런타임은 단순 SELECT 다. 빌드는 월 1회고 서버 부하와
    무관하다.

무엇을
    화면에서 실제로 고를 수 있는 조합만 굽는다. 서브타입을 끼우면 경우의 수가
    무한해지므로 서브타입 없는 기본 조합만 대상으로 한다. 나머지는 런타임
    계산으로 남고, heavy_slot 이 동시 실행을 막는다.

      scale        레이어 x 모드 x 확대배수
      clusters     레이어 순서쌍 x 임계값
      transit_gap  거리 기준

사용:
    python scripts/precompute_grid.py            # 전체
    python scripts/precompute_grid.py --scale    # 일부만
"""

import json
import os
import sqlite3
import sys
import time
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import grid_service as grid

GRID_DB_PATH = grid.GRID_DB_PATH

# 화면이 제공하는 선택지와 일치시킨다(templates/admin_grid.html).
CLUSTER_THRESHOLDS = (30, 40, 50, 60)
TRANSIT_DISTANCES = (600, 800, 1000, 1500)

SCHEMA = """
CREATE TABLE IF NOT EXISTS precomputed (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    computed_at TEXT
) WITHOUT ROWID;
"""


def store(connection, rows):
    connection.executemany(
        "INSERT OR REPLACE INTO precomputed (key, kind, payload, computed_at) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    connection.commit()


def build_scales(connection, stamp):
    layers = [entry["layer"] for entry in grid.get_meta()["layers"]]
    rows = []
    started = time.time()

    for layer in layers:
        for mode in grid.MODES:
            for factor in grid.FACTORS:
                payload = grid.get_scale(layer, mode, factor=factor)
                rows.append((
                    grid.precompute_key(
                        "scale", layer=layer, mode=mode, factor=factor,
                        subtypes=(), core=False, per_hh=False,
                    ),
                    "scale", json.dumps(payload), stamp,
                ))

    store(connection, rows)
    print(f"[SCALE] {len(rows)}건 {time.time() - started:.0f}s")


def build_clusters(connection, stamp):
    layers = [entry["layer"] for entry in grid.get_meta()["layers"]]
    rows = []
    started = time.time()
    total = len(layers) * (len(layers) - 1) * len(CLUSTER_THRESHOLDS)
    done = 0

    for a in layers:
        for b in layers:
            if a == b:
                continue

            for threshold in CLUSTER_THRESHOLDS:
                payload = grid.query_clusters(a, b, threshold=threshold)
                rows.append((
                    grid.precompute_key(
                        "clusters", a=a, b=b, threshold=threshold,
                        sa=(), sb=(), core=False, min_cells=10, limit=40,
                        per_hh=False,
                    ),
                    "clusters", json.dumps(payload), stamp,
                ))
                done += 1

                if done % 30 == 0:
                    elapsed = time.time() - started
                    print(f"  {done}/{total} ({elapsed:.0f}s, "
                          f"남은 예상 {elapsed / done * (total - done):.0f}s)")

            # 캐시가 무한정 커지지 않게 주기적으로 비운다.
            grid._cluster_cache.clear()

    store(connection, rows)
    print(f"[CLUSTERS] {len(rows)}건 {time.time() - started:.0f}s")


def build_transit_gap(connection, stamp):
    rows = []
    started = time.time()

    for distance in TRANSIT_DISTANCES:
        payload = grid.query_transit_gap(min_distance_m=distance)
        rows.append((
            grid.precompute_key(
                "transit_gap", distance=distance, bus=50,
                min_cells=20, limit=30, core=False, brt=True,
            ),
            "transit_gap", json.dumps(payload), stamp,
        ))

    store(connection, rows)
    print(f"[TRANSIT] {len(rows)}건 {time.time() - started:.0f}s")


def main():
    if not os.path.exists(GRID_DB_PATH):
        print(f"[ERROR] {GRID_DB_PATH} 가 없습니다. build_grid_index.py 를 먼저 실행하세요.")
        return 1

    args = sys.argv[1:]
    want = {a.lstrip("-") for a in args if a.startswith("--")} or {
        "scale", "clusters", "transit"
    }

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    started = time.time()

    with closing(sqlite3.connect(GRID_DB_PATH)) as connection:
        connection.executescript(SCHEMA)

        # 이전 회차 결과가 남아 새 격자와 섞이면 안 된다.
        connection.execute("DELETE FROM precomputed")
        connection.commit()

        if "scale" in want:
            build_scales(connection, stamp)
        if "clusters" in want:
            build_clusters(connection, stamp)
        if "transit" in want:
            build_transit_gap(connection, stamp)

        count = connection.execute(
            "SELECT COUNT(*) FROM precomputed"
        ).fetchone()[0]

    size = os.path.getsize(GRID_DB_PATH) / 1e6
    print(f"[DONE] 사전계산 {count:,}건, grid.db {size:.1f}MB, "
          f"{time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

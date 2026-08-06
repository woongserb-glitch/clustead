"""격자 시계열 스냅샷 — 인프라가 늘었나 줄었나.

지금 격자는 전부 현재 스냅샷이다. 갱신 이력을 쌓아두면 "이 지역 인프라가
늘었나 줄었나", "새 노선 개통 전후로 무엇이 달라졌나" 를 볼 수 있다.
**지금 안 쌓으면 소급이 불가능하고**, 비용은 거의 없다.

무엇을 저장하나
    grid.db 전체(126MB)를 매달 복사하면 1년에 1.5GB 다. 대신 변화 탐지에
    실제로 필요한 것만 담는다.

      snapshot_cell   시설이 '위치한' 셀 (grid_cell, 레이어별 합)
      snapshot_layer  레이어별 총량·점유셀

    영향권(coverage)은 위치에서 다시 계산되는 파생물이라 담지 않는다.
    한 스냅샷이 약 5만행 / 2MB 라 1년치가 25MB 다.

사용
    python scripts/snapshot_grid.py              # 오늘자 스냅샷 적재
    python scripts/snapshot_grid.py --list       # 목록
    python scripts/snapshot_grid.py --diff       # 최근 두 스냅샷 비교
    python scripts/snapshot_grid.py --diff A B   # 특정 두 스냅샷 비교
"""

import os
import sqlite3
import sys
import time
from contextlib import closing

GRID_DB_PATH = "data/grid.db"
HISTORY_DB_PATH = "data/grid_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_on TEXT NOT NULL UNIQUE,
    grid_built_at TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS snapshot_layer (
    snapshot_id INTEGER NOT NULL,
    layer TEXT NOT NULL,
    label TEXT,
    radius_m INTEGER,
    poi_count INTEGER,
    located_cells INTEGER,
    total_count REAL,
    PRIMARY KEY (snapshot_id, layer)
);

CREATE TABLE IF NOT EXISTS snapshot_cell (
    snapshot_id INTEGER NOT NULL,
    layer TEXT NOT NULL,
    i INTEGER NOT NULL,
    j INTEGER NOT NULL,
    count REAL NOT NULL,
    PRIMARY KEY (snapshot_id, layer, i, j)
) WITHOUT ROWID;
"""


def open_history():
    connection = sqlite3.connect(HISTORY_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def take_snapshot(note=""):
    if not os.path.exists(GRID_DB_PATH):
        print(f"[ERROR] {GRID_DB_PATH} 가 없습니다. build_grid_index.py 를 먼저 실행하세요.")
        return 1

    today = time.strftime("%Y-%m-%d")

    with closing(open_history()) as history:
        existing = history.execute(
            "SELECT id FROM snapshot WHERE taken_on = ?", (today,)
        ).fetchone()

        if existing:
            print(f"[SKIP] {today} 스냅샷이 이미 있습니다 (id={existing['id']}).")
            print("       다시 담으려면 해당 행을 지우고 실행하세요.")
            return 0

        with closing(sqlite3.connect(f"file:{GRID_DB_PATH}?mode=ro", uri=True)) as grid:
            grid.row_factory = sqlite3.Row

            built_at = grid.execute(
                "SELECT value FROM grid_meta WHERE key = 'built_at'"
            ).fetchone()

            cursor = history.execute(
                "INSERT INTO snapshot (taken_on, grid_built_at, note) VALUES (?, ?, ?)",
                (today, built_at["value"] if built_at else None, note),
            )
            snapshot_id = cursor.lastrowid

            layers = grid.execute(
                "SELECT layer, label, radius_m, poi_count FROM layer_meta"
            ).fetchall()

            cells = grid.execute(
                "SELECT layer, i, j, SUM(count) AS count "
                "FROM grid_cell GROUP BY layer, i, j"
            ).fetchall()

        history.executemany(
            "INSERT INTO snapshot_cell VALUES (?, ?, ?, ?, ?)",
            [
                (snapshot_id, row["layer"], row["i"], row["j"], row["count"])
                for row in cells
            ],
        )

        history.executemany(
            "INSERT INTO snapshot_layer VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    snapshot_id, row["layer"], row["label"], row["radius_m"],
                    row["poi_count"],
                    sum(1 for c in cells if c["layer"] == row["layer"]),
                    sum(c["count"] for c in cells if c["layer"] == row["layer"]),
                )
                for row in layers
            ],
        )

        history.commit()

    size = os.path.getsize(HISTORY_DB_PATH) / 1e6
    print(f"[DONE] {today} 스냅샷 적재 — 셀 {len(cells):,}행, "
          f"레이어 {len(layers)}종, 누적 {size:.1f}MB")
    return 0


def list_snapshots():
    with closing(open_history()) as history:
        rows = history.execute(
            "SELECT s.id, s.taken_on, s.grid_built_at, s.note, "
            "COUNT(l.layer) AS layers, SUM(l.poi_count) AS pois "
            "FROM snapshot s LEFT JOIN snapshot_layer l ON l.snapshot_id = s.id "
            "GROUP BY s.id ORDER BY s.taken_on"
        ).fetchall()

    if not rows:
        print("스냅샷이 없습니다.")
        return 0

    print(f"{'날짜':<12}{'레이어':>6}{'POI':>10}  빌드시각")
    for row in rows:
        print(f"{row['taken_on']:<12}{row['layers']:>6}{row['pois'] or 0:>10,}  "
              f"{row['grid_built_at'] or '-'}")
    return 0


def diff_snapshots(first=None, second=None):
    with closing(open_history()) as history:
        dates = [
            row["taken_on"]
            for row in history.execute(
                "SELECT taken_on FROM snapshot ORDER BY taken_on"
            )
        ]

        if len(dates) < 2:
            print(f"비교하려면 스냅샷이 2개 이상 필요합니다 (현재 {len(dates)}개).")
            return 0

        first = first or dates[-2]
        second = second or dates[-1]

        print(f"{first} → {second}")
        print()
        print(f"{'레이어':<16}{'이전':>9}{'이후':>9}{'증감':>9}")

        rows = history.execute(
            "SELECT a.label, a.total_count AS before, b.total_count AS after "
            "FROM snapshot_layer a "
            "JOIN snapshot sa ON sa.id = a.snapshot_id AND sa.taken_on = ? "
            "JOIN snapshot sb ON sb.taken_on = ? "
            "JOIN snapshot_layer b ON b.snapshot_id = sb.id AND b.layer = a.layer "
            "ORDER BY a.label",
            (first, second),
        ).fetchall()

        for row in rows:
            delta = (row["after"] or 0) - (row["before"] or 0)
            mark = "" if delta == 0 else ("  ▲" if delta > 0 else "  ▼")
            print(f"{row['label']:<16}{row['before']:>9,.0f}"
                  f"{row['after']:>9,.0f}{delta:>+9,.0f}{mark}")

        # 셀 단위로 늘거나 준 곳.
        # FULL OUTER JOIN 은 SQLite 3.39+ 전용이라 UNION 으로 키를 모은다.
        changed = history.execute(
            "WITH a AS (SELECT layer, i, j, count FROM snapshot_cell "
            "           WHERE snapshot_id = (SELECT id FROM snapshot WHERE taken_on = ?)), "
            "     b AS (SELECT layer, i, j, count FROM snapshot_cell "
            "           WHERE snapshot_id = (SELECT id FROM snapshot WHERE taken_on = ?)), "
            "     k AS (SELECT layer, i, j FROM a UNION SELECT layer, i, j FROM b) "
            "SELECT k.layer, k.i, k.j, "
            "       COALESCE(b.count, 0) - COALESCE(a.count, 0) AS delta "
            "FROM k "
            "LEFT JOIN a ON a.layer = k.layer AND a.i = k.i AND a.j = k.j "
            "LEFT JOIN b ON b.layer = k.layer AND b.i = k.i AND b.j = k.j "
            "WHERE COALESCE(a.count, 0) != COALESCE(b.count, 0)",
            (first, second),
        ).fetchall()

    if not changed:
        print()
        print("셀 단위 변화 없음.")
        return 0

    by_layer = {}

    for row in changed:
        entry = by_layer.setdefault(row["layer"], [0, 0.0])
        entry[0] += 1
        entry[1] += row["delta"]

    print()
    print("변화가 있었던 셀")
    for layer, (cells, delta) in sorted(
        by_layer.items(), key=lambda x: -abs(x[1][1])
    ):
        print(f"  {layer:<14}{cells:>6}칸  {delta:>+9,.0f}")

    # 어디서 바뀌었는지. grid.db 가 있으면 구/동을 붙인다.
    places = {}

    if os.path.exists(GRID_DB_PATH):
        with closing(
            sqlite3.connect(f"file:{GRID_DB_PATH}?mode=ro", uri=True)
        ) as grid:
            places = {
                (row[0], row[1]): (row[2], row[3])
                for row in grid.execute("SELECT i, j, gu, dong FROM grid_zone")
            }

    top = sorted(changed, key=lambda r: -abs(r["delta"]))[:10]

    print()
    print("변화가 큰 지점")
    for row in top:
        gu, dong = places.get((row["i"], row["j"]), ("?", "?"))
        print(f"  {row['layer']:<14}{row['delta']:>+7,.0f}  {gu} {dong}"
              f"  (셀 {row['i']},{row['j']})")

    return 0


def main():
    args = sys.argv[1:]

    if "--list" in args:
        return list_snapshots()

    if "--diff" in args:
        rest = [a for a in args if not a.startswith("--")]
        return diff_snapshots(*rest[:2]) if rest else diff_snapshots()

    note = " ".join(a for a in args if not a.startswith("--"))
    return take_snapshot(note)


if __name__ == "__main__":
    raise SystemExit(main())

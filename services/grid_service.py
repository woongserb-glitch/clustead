"""아파트 생활권 격자 조회 (scripts/build_grid_index.py 산출물).

grid.db 는 읽기 전용이고 요청마다 커넥션을 새로 연다. 격자 데이터는 정적이라
쓰기 경합이 없고, 워커별 장기 커넥션을 들고 있을 이유도 없다.

세 지표의 집계 규칙이 서로 다르다. 섞으면 조용히 틀린 숫자가 나간다.
    point    POI 가 위치한 셀      → 거친 격자로 낮출 때 SUM
    coverage POI 가 영향을 주는 셀 → 이웃 셀에 중복 계산되므로 AVG
    nearest  최근접 거리           → MIN
"""

import os
import sqlite3

GRID_DB_PATH = "data/grid.db"

MODES = ("point", "coverage", "nearest")

_MODE_TABLE = {
    "point": ("grid_cell", "SUM(count)"),
    "coverage": ("grid_coverage", "AVG(count)"),
    "nearest": ("grid_nearest", "MIN(distance_m)"),
}

# 확대 수준별 집계 배수. 100m 셀 9개가 정확히 300m 셀 1개가 된다.
FACTORS = (1, 3, 9)

MAX_CELLS = 20000


def grid_available():
    return os.path.exists(GRID_DB_PATH)


def _connect():
    connection = sqlite3.connect(f"file:{GRID_DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_meta():
    """격자 원점·셀크기 등. 클라이언트가 셀 ID ↔ 위경도를 직접 계산한다."""
    if not grid_available():
        return None

    with _connect() as connection:
        meta = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM grid_meta")
        }

        layers = [
            dict(row)
            for row in connection.execute(
                "SELECT layer, label, trust, note, poi_count, radius_m "
                "FROM layer_meta ORDER BY label"
            )
        ]

        for layer in layers:
            layer["subtypes"] = [
                row["subtype"]
                for row in connection.execute(
                    "SELECT DISTINCT subtype FROM grid_coverage "
                    "WHERE layer = ? ORDER BY subtype",
                    (layer["layer"],),
                )
            ]
            layer["has_nearest"] = bool(
                connection.execute(
                    "SELECT 1 FROM grid_nearest WHERE layer = ? LIMIT 1",
                    (layer["layer"],),
                ).fetchone()
            )

    meta["layers"] = layers
    return meta


def _cell_bounds(meta, min_lat, min_lng, max_lat, max_lng):
    cell_size = float(meta["cell_size_m"])
    lat_origin = float(meta["lat_origin"])
    lng_origin = float(meta["lng_origin"])
    d_lat = cell_size / float(meta["lat_m_per_deg"])
    d_lng = cell_size / float(meta["lng_m_per_deg"])

    return (
        int((min_lat - lat_origin) / d_lat),
        int((max_lat - lat_origin) / d_lat),
        int((min_lng - lng_origin) / d_lng),
        int((max_lng - lng_origin) / d_lng),
    )


def query_cells(layer, mode, bounds, factor=1, subtypes=None, core_only=False):
    """뷰포트 내 셀 값. bounds = (min_lat, min_lng, max_lat, max_lng)."""
    if mode not in _MODE_TABLE:
        raise ValueError(f"알 수 없는 mode: {mode}")

    if factor not in FACTORS:
        factor = 1

    meta = get_meta()

    if meta is None:
        return {"cells": [], "truncated": False}

    table, aggregate = _MODE_TABLE[mode]
    min_i, max_i, min_j, max_j = _cell_bounds(meta, *bounds)

    where = [
        "layer = ?",
        "i BETWEEN ? AND ?",
        "j BETWEEN ? AND ?",
    ]
    params = [layer, min_i, max_i, min_j, max_j]

    # nearest 는 서브타입이 없다.
    if subtypes and mode != "nearest":
        where.append(
            "subtype IN (" + ",".join("?" * len(subtypes)) + ")"
        )
        params.extend(subtypes)

    if core_only:
        where.append(
            "EXISTS (SELECT 1 FROM grid_zone z "
            "WHERE z.i = t.i AND z.j = t.j AND z.in_core = 1)"
        )

    # 거친 격자는 자식 셀을 묶어 재집계한다. coverage 는 합이 아니라 평균이다.
    sql = (
        f"SELECT i / {factor} AS gi, j / {factor} AS gj, "
        f"{aggregate} AS value "
        f"FROM {table} AS t "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY gi, gj "
        f"LIMIT {MAX_CELLS + 1}"
    )

    with _connect() as connection:
        rows = connection.execute(sql, params).fetchall()

    truncated = len(rows) > MAX_CELLS

    return {
        "cells": [
            [row["gi"], row["gj"], round(row["value"], 2)]
            for row in rows[:MAX_CELLS]
        ],
        "truncated": truncated,
    }


def query_points(layer, bounds, subtypes=None, limit=2000):
    """최대 확대에서의 개별 시설 위치. 위치 집계 셀의 중심을 좌표로 돌려준다."""
    meta = get_meta()

    if meta is None:
        return {"points": [], "truncated": False}

    min_i, max_i, min_j, max_j = _cell_bounds(meta, *bounds)

    where = ["layer = ?", "i BETWEEN ? AND ?", "j BETWEEN ? AND ?"]
    params = [layer, min_i, max_i, min_j, max_j]

    if subtypes:
        where.append("subtype IN (" + ",".join("?" * len(subtypes)) + ")")
        params.extend(subtypes)

    with _connect() as connection:
        rows = connection.execute(
            f"SELECT i, j, subtype, count FROM grid_cell "
            f"WHERE {' AND '.join(where)} LIMIT {limit + 1}",
            params,
        ).fetchall()

    cell_size = float(meta["cell_size_m"])
    lat_origin = float(meta["lat_origin"])
    lng_origin = float(meta["lng_origin"])
    d_lat = cell_size / float(meta["lat_m_per_deg"])
    d_lng = cell_size / float(meta["lng_m_per_deg"])

    return {
        "points": [
            {
                "lat": lat_origin + (row["i"] + 0.5) * d_lat,
                "lng": lng_origin + (row["j"] + 0.5) * d_lng,
                "subtype": row["subtype"],
                "count": row["count"],
            }
            for row in rows[:limit]
        ],
        "truncated": len(rows) > limit,
    }


def get_cell_detail(i, j):
    """셀 하나의 전 레이어 값. 지도에서 칸을 클릭했을 때 쓴다."""
    if not grid_available():
        return None

    with _connect() as connection:
        zone = connection.execute(
            "SELECT in_core, apartment_count FROM grid_zone WHERE i = ? AND j = ?",
            (i, j),
        ).fetchone()

        coverage = [
            dict(row)
            for row in connection.execute(
                "SELECT layer, subtype, count FROM grid_coverage "
                "WHERE i = ? AND j = ? ORDER BY layer, subtype",
                (i, j),
            )
        ]

        nearest = {
            row["layer"]: row["distance_m"]
            for row in connection.execute(
                "SELECT layer, distance_m FROM grid_nearest WHERE i = ? AND j = ?",
                (i, j),
            )
        }

        apartments = [
            dict(row)
            for row in connection.execute(
                "SELECT a.name, a.gu, a.dong, ga.in_core "
                "FROM grid_apartment ga JOIN apartment a ON a.id = ga.apartment_id "
                "WHERE ga.i = ? AND ga.j = ? "
                "ORDER BY ga.in_core DESC, a.name LIMIT 30",
                (i, j),
            )
        ]

    return {
        "in_core": bool(zone["in_core"]) if zone else False,
        "apartment_count": zone["apartment_count"] if zone else 0,
        "coverage": coverage,
        "nearest": nearest,
        "apartments": apartments,
    }

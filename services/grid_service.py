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
from contextlib import closing

GRID_DB_PATH = "data/grid.db"

MODES = ("point", "coverage", "nearest")

# (테이블, 값컬럼, 셀 안 집계, 자식셀 간 집계)
#
# 두 단계를 구분해야 한다. 한 셀 안에는 서브타입별로 행이 여러 개 있고,
# 거친 격자에서는 그런 셀이 여러 개 묶인다.
#   coverage 셀 안=SUM(서브타입 합) / 셀 간=AVG(중복 계산이라 합산 불가)
#   point    셀 안=SUM / 셀 간=SUM (POI 실개수라 합산이 맞다)
#   nearest  서브타입 없음. 셀 안=MIN / 셀 간=MIN
_MODE_TABLE = {
    "point": ("grid_cell", "count", "SUM", "SUM"),
    "coverage": ("grid_coverage", "count", "SUM", "AVG"),
    "nearest": ("grid_nearest", "distance_m", "MIN", "MIN"),
}

# 확대 수준별 집계 배수. 100m 셀 9개가 정확히 300m 셀 1개가 된다.
FACTORS = (1, 3, 9)

MAX_CELLS = 20000

# 절대 색상 스케일용 분위 경계 개수(p0..p100).
SCALE_STEPS = 100

# 격자 데이터는 정적이라 프로세스 내내 유효하다. 서브타입 조합이 임의라
# 미리 구울 수 없어 요청 시 계산하고(50~200ms) 선택 단위로 캐시한다.
# 뷰포트가 아니라 '선택'이 키라, 지도를 옮겨도 다시 계산하지 않는다.
_scale_cache = {}
_SCALE_CACHE_MAX = 200

# get_meta() 결과 캐시(리스트 1칸). 격자 데이터는 정적이다.
_meta_cache = []

# 클러스터는 서울 전체를 훑고 연결요소까지 계산해 1초 이상 걸린다.
# 뷰포트와 무관한 결과라 선택 단위로 캐시하면 재계산이 없다.
_cluster_cache = {}
_CLUSTER_CACHE_MAX = 60


def grid_available():
    return os.path.exists(GRID_DB_PATH)


def _connect():
    """호출부는 반드시 closing() 으로 감쌀 것.

    `with sqlite3.connect(...)` 는 트랜잭션 컨텍스트일 뿐 연결을 닫지 않는다.
    그대로 두면 요청마다 연결이 쌓인다.
    """
    connection = sqlite3.connect(f"file:{GRID_DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_meta():
    """격자 원점·셀크기 등. 클라이언트가 셀 ID ↔ 위경도를 직접 계산한다.

    레이어별 서브타입 목록을 뽑느라 DISTINCT 스캔이 들어가 요청마다 부르면
    수백 ms 가 든다. 격자 데이터는 정적이라 프로세스 단위로 캐시한다.
    """
    if _meta_cache:
        return _meta_cache[0]

    if not grid_available():
        return None

    with closing(_connect()) as connection:
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
    _meta_cache.append(meta)
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


def _cell_value_sql(layer, mode, factor, subtypes, core_only,
                    extra_where=None, extra_params=(), limit=None):
    """(SQL, params). 셀 안 집계 → 자식셀 간 집계 2단계로 만든다."""
    table, column, inner, outer = _MODE_TABLE[mode]

    where = ["layer = ?"]
    params = [layer]

    # nearest 는 서브타입이 없다.
    if subtypes and mode != "nearest":
        where.append("subtype IN (" + ",".join("?" * len(subtypes)) + ")")
        params.extend(subtypes)

    if core_only:
        where.append(
            "EXISTS (SELECT 1 FROM grid_zone z "
            "WHERE z.i = t.i AND z.j = t.j AND z.in_core = 1)"
        )

    if extra_where:
        where.extend(extra_where)
        params.extend(extra_params)

    inner_sql = (
        f"SELECT i / {factor} AS gi, j / {factor} AS gj, "
        f"{inner}({column}) AS cell_value "
        f"FROM {table} AS t "
        f"WHERE {' AND '.join(where)} "
        f"GROUP BY i, j"
    )

    sql = (
        f"SELECT gi, gj, {outer}(cell_value) AS value "
        f"FROM ({inner_sql}) GROUP BY gi, gj"
    )

    if limit is not None:
        sql += f" LIMIT {limit}"

    return sql, params


def _zone_cell_count(connection, factor, core_only):
    sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM grid_zone "
    if core_only:
        sql += "WHERE in_core = 1 "
    sql += f"GROUP BY i / {factor}, j / {factor})"

    return connection.execute(sql).fetchone()[0]


def _breaks_from(values, steps=SCALE_STEPS):
    """정렬된 값에서 p0..p100 경계를 뽑는다."""
    if not values:
        return []

    last = len(values) - 1

    return [
        values[min(last, int(round(last * step / steps)))]
        for step in range(steps + 1)
    ]


def get_scale(layer, mode, factor=1, subtypes=None, core_only=False):
    """서울 아파트 생활권 전체 분포 기준 분위 경계.

    뷰포트 최소~최대로 색을 칠하면 지도를 옮길 때마다 같은 값의 색이 달라져
    비교가 불가능하다. 절대 스케일은 화면과 무관하게 고정된 기준을 준다.

    coverage/point 는 값이 없는 셀이 곧 0 이므로, 테이블에 없는 셀을 0 으로
    채워 넣어야 분포가 정직하다(CCTV 는 22% 가 0). nearest 는 값이 없으면
    '3km 밖'이라는 별도 범주라 채우지 않는다.
    """
    if mode not in _MODE_TABLE:
        raise ValueError(f"알 수 없는 mode: {mode}")

    if factor not in FACTORS:
        factor = 1

    key = (layer, mode, factor, tuple(sorted(subtypes or ())), core_only)

    if key in _scale_cache:
        return _scale_cache[key]

    sql, params = _cell_value_sql(layer, mode, factor, subtypes, core_only)

    with closing(_connect()) as connection:
        rows = connection.execute(sql, params).fetchall()
        total_cells = _zone_cell_count(connection, factor, core_only)

    values = sorted(row["value"] for row in rows)
    measured = len(values)

    if mode != "nearest":
        missing = max(0, total_cells - measured)
        values = [0] * missing + values

    scale = {
        "breaks": [round(v, 2) for v in _breaks_from(values)],
        "cells": len(values),
        "measured": measured,
        "zero_cells": sum(1 for v in values if v == 0) if mode != "nearest" else None,
        "beyond_range": (total_cells - measured) if mode == "nearest" else None,
    }

    if len(_scale_cache) >= _SCALE_CACHE_MAX:
        _scale_cache.clear()

    _scale_cache[key] = scale
    return scale


def query_cells(layer, mode, bounds, factor=1, subtypes=None, core_only=False):
    """뷰포트 내 셀 값. bounds = (min_lat, min_lng, max_lat, max_lng)."""
    if mode not in _MODE_TABLE:
        raise ValueError(f"알 수 없는 mode: {mode}")

    if factor not in FACTORS:
        factor = 1

    meta = get_meta()

    if meta is None:
        return {"cells": [], "truncated": False}

    min_i, max_i, min_j, max_j = _cell_bounds(meta, *bounds)

    sql, params = _cell_value_sql(
        layer, mode, factor, subtypes, core_only,
        extra_where=["i BETWEEN ? AND ?", "j BETWEEN ? AND ?"],
        extra_params=(min_i, max_i, min_j, max_j),
        limit=MAX_CELLS + 1,
    )

    with closing(_connect()) as connection:
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

    with closing(_connect()) as connection:
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


def _percentile_of(value, breaks):
    """값 → 백분위(0~100). 클라이언트의 percentileOf 와 같은 규칙."""
    if not breaks:
        return 0

    if value <= breaks[0]:
        return 0

    if value >= breaks[-1]:
        return 100

    lo, hi = 0, len(breaks) - 1

    while lo < hi:
        mid = (lo + hi + 1) // 2

        if breaks[mid] <= value:
            lo = mid
        else:
            hi = mid - 1

    return lo


def query_compare(layer_a, layer_b, bounds, factor=1,
                  subtypes_a=None, subtypes_b=None, core_only=False):
    """두 레이어의 불균형. 값 = A백분위 - B백분위 (-100 ~ +100).

    원시 비율(A/B)은 분모가 0 이면 폭발하고 단위가 달라 비교가 성립하지 않는다.
    각각을 서울 생활권 분포의 백분위로 바꾼 뒤 빼면 순위 기반 잔차가 되어
    "학원은 상위 82% 인데 CCTV 는 31%" 라는 방어 가능한 문장이 나온다.

    두 레이어 모두 coverage(영향권) 기준이다. 개수와 거리를 섞으면 해석이
    불가능해서 mode 는 고정한다.
    """
    meta = get_meta()

    if meta is None:
        return {"cells": [], "truncated": False}

    scale_a = get_scale(layer_a, "coverage", factor, subtypes_a, core_only)
    scale_b = get_scale(layer_b, "coverage", factor, subtypes_b, core_only)

    min_i, max_i, min_j, max_j = _cell_bounds(meta, *bounds)
    extra = ["i BETWEEN ? AND ?", "j BETWEEN ? AND ?"]
    extra_params = (min_i, max_i, min_j, max_j)

    def fetch(layer, subtypes):
        sql, params = _cell_value_sql(
            layer, "coverage", factor, subtypes, core_only,
            extra_where=extra, extra_params=extra_params,
            limit=MAX_CELLS + 1,
        )
        with closing(_connect()) as connection:
            return {
                (row["gi"], row["gj"]): row["value"]
                for row in connection.execute(sql, params)
            }

    values_a = fetch(layer_a, subtypes_a)
    values_b = fetch(layer_b, subtypes_b)

    cells = []

    # 양쪽 모두 값이 없는 칸은 차이가 0 이라 굳이 내려보내지 않는다.
    for key in set(values_a) | set(values_b):
        pa = _percentile_of(values_a.get(key, 0), scale_a["breaks"])
        pb = _percentile_of(values_b.get(key, 0), scale_b["breaks"])
        cells.append([key[0], key[1], pa - pb, pa, pb])

    truncated = len(cells) > MAX_CELLS

    return {
        "cells": cells[:MAX_CELLS],
        "truncated": truncated,
        "scale_a": scale_a,
        "scale_b": scale_b,
    }


def query_clusters(layer_a, layer_b, threshold=40, subtypes_a=None,
                   subtypes_b=None, core_only=False, min_cells=10, limit=40):
    """인접한 불균형 칸을 묶어 실체로 만든다.

    뷰포트가 아니라 서울 생활권 전체에서 계산한다. 화면을 옮길 때마다 덩어리가
    달라지면 '이 지역은 불균형하다'는 진술이 성립하지 않기 때문이다.

    기본 100m 격자에서만 묶는다. 거친 격자로 묶으면 경계가 뭉개져 면적과
    관련 단지 수가 부정확해진다.

    threshold 는 A백분위 - B백분위 기준. 양수면 'A 는 높은데 B 가 낮은' 칸.
    """
    meta = get_meta()

    if meta is None:
        return {"clusters": []}

    # 아래 루프가 key 를 셀 좌표로 재사용하므로 이름을 분리해 둔다.
    cache_key = (
        layer_a, layer_b, threshold,
        tuple(sorted(subtypes_a or ())), tuple(sorted(subtypes_b or ())),
        core_only, min_cells, limit,
    )

    if cache_key in _cluster_cache:
        return _cluster_cache[cache_key]

    scale_a = get_scale(layer_a, "coverage", 1, subtypes_a, core_only)
    scale_b = get_scale(layer_b, "coverage", 1, subtypes_b, core_only)

    def fetch(layer, subtypes):
        sql, params = _cell_value_sql(layer, "coverage", 1, subtypes, core_only)
        with closing(_connect()) as connection:
            return {
                (row["gi"], row["gj"]): row["value"]
                for row in connection.execute(sql, params)
            }

    values_a = fetch(layer_a, subtypes_a)
    values_b = fetch(layer_b, subtypes_b)

    flagged = {}

    for cell in set(values_a) | set(values_b):
        pa = _percentile_of(values_a.get(cell, 0), scale_a["breaks"])
        pb = _percentile_of(values_b.get(cell, 0), scale_b["breaks"])
        diff = pa - pb

        if diff >= threshold:
            flagged[cell] = diff

    # 4-이웃 연결요소. 8-이웃은 모서리만 닿은 덩어리까지 붙여 과대집계된다.
    seen = set()
    clusters = []

    for start in flagged:
        if start in seen:
            continue

        stack = [start]
        seen.add(start)
        members = []

        while stack:
            cell = stack.pop()
            members.append(cell)
            i, j = cell

            for nb in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if nb in flagged and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)

        if len(members) >= min_cells:
            clusters.append(members)

    clusters.sort(key=len, reverse=True)
    clusters = clusters[:limit]

    result = _describe_clusters(meta, clusters, flagged)

    if len(_cluster_cache) >= _CLUSTER_CACHE_MAX:
        _cluster_cache.clear()

    _cluster_cache[cache_key] = result
    return result


def _describe_clusters(meta, clusters, flagged):
    cell_size = float(meta["cell_size_m"])
    lat_origin = float(meta["lat_origin"])
    lng_origin = float(meta["lng_origin"])
    d_lat = cell_size / float(meta["lat_m_per_deg"])
    d_lng = cell_size / float(meta["lng_m_per_deg"])
    cell_area_km2 = (cell_size / 1000.0) ** 2

    described = []

    with closing(_connect()) as connection:
        connection.execute(
            "CREATE TEMP TABLE cluster_cell (cid INTEGER, i INTEGER, j INTEGER)"
        )
        connection.executemany(
            "INSERT INTO cluster_cell VALUES (?, ?, ?)",
            [
                (cid, i, j)
                for cid, members in enumerate(clusters)
                for i, j in members
            ],
        )
        connection.execute("CREATE INDEX tmp_cc ON cluster_cell (i, j)")

        apartment_counts = dict(
            connection.execute(
                "SELECT cc.cid, COUNT(DISTINCT ga.apartment_id) "
                "FROM cluster_cell cc "
                "JOIN grid_apartment ga ON ga.i = cc.i AND ga.j = cc.j "
                "GROUP BY cc.cid"
            )
        )

        places = {}

        for cid, gu, dong, n in connection.execute(
            "SELECT cc.cid, a.gu, a.dong, COUNT(DISTINCT a.id) n "
            "FROM cluster_cell cc "
            "JOIN grid_apartment ga ON ga.i = cc.i AND ga.j = cc.j "
            "JOIN apartment a ON a.id = ga.apartment_id "
            "GROUP BY cc.cid, a.gu, a.dong ORDER BY n DESC"
        ):
            places.setdefault(cid, []).append({"gu": gu, "dong": dong, "count": n})

    for cid, members in enumerate(clusters):
        lats = [i for i, _ in members]
        lngs = [j for _, j in members]
        diffs = [flagged[cell] for cell in members]

        described.append({
            "id": cid,
            "cells": len(members),
            "area_km2": round(len(members) * cell_area_km2, 3),
            "mean_diff": round(sum(diffs) / len(diffs), 1),
            "max_diff": max(diffs),
            "apartment_count": apartment_counts.get(cid, 0),
            "places": (places.get(cid) or [])[:3],
            "bounds": {
                "min_lat": lat_origin + min(lats) * d_lat,
                "max_lat": lat_origin + (max(lats) + 1) * d_lat,
                "min_lng": lng_origin + min(lngs) * d_lng,
                "max_lng": lng_origin + (max(lngs) + 1) * d_lng,
            },
        })

    return {"clusters": described}


def get_cell_detail(i, j):
    """셀 하나의 전 레이어 값. 지도에서 칸을 클릭했을 때 쓴다."""
    if not grid_available():
        return None

    with closing(_connect()) as connection:
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

        # 지도에 마커로 찍어야 해서 좌표까지 함께 준다.
        apartments = [
            dict(row)
            for row in connection.execute(
                "SELECT a.id, a.name, a.gu, a.dong, a.lat, a.lng, ga.in_core "
                "FROM grid_apartment ga JOIN apartment a ON a.id = ga.apartment_id "
                "WHERE ga.i = ? AND ga.j = ? "
                "ORDER BY ga.in_core DESC, a.name LIMIT 60",
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

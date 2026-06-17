"""사용자 행동 분석 로깅 — SQLite(WAL) + 워커별 비동기 writer 스레드.

설계 원칙(OCI 단일 VM / gunicorn preload_app=True / 워커 2개 기준):

- 요청 핸들러는 dict 하나를 큐에 put_nowait 만 한다(논블로킹). 실제 DB 쓰기는
  워커별 데몬 스레드가 배치로 commit → 본 서비스 응답 지연 0에 수렴.
- preload_app=True 라 import 시점(=마스터)에 스레드/커넥션을 만들면 fork 후
  워커에 상속되지 않는다. 따라서 첫 track() 호출 때 lazy 로 워커 안에서 시작한다.
- 분석 로깅 실패가 본 서비스를 절대 망가뜨리지 않는다. 모든 경로 try/except 격리,
  큐가 가득 차면 조용히 drop.
- 개인정보 최소수집: IP 원문 저장 금지. visitor_hash = sha256(IP+UA+일일솔트)[:16].
  일일 솔트 회전으로 날짜가 바뀌면 동일인 재식별 불가(당일 순방문자 집계만 가능).
"""

import hashlib
import json
import os
import queue
import sqlite3
import threading
from datetime import datetime, timezone, timedelta

# KST(UTC+9). 서버 TZ 무관하게 'day' 비정규화 컬럼을 한국 날짜로 고정.
_KST = timezone(timedelta(hours=9))

# 마스터 스위치. 0 이면 완전 무동작(track 은 즉시 return).
ENABLED = os.getenv("CLUSTEAD_ANALYTICS", "1") == "1"

# DB 경로 — 영속 볼륨(./data:/app/data) 밑에 둬야 컨테이너 재생성에도 생존.
_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "analytics", "analytics.db",
)
DB_PATH = os.getenv("CLUSTEAD_ANALYTICS_DB", _DEFAULT_DB)

# 해시 솔트 시드. 미설정 시 부팅 랜덤(재시작마다 끊김 — 추적 방지엔 더 안전).
_SALT_SEED = os.getenv("CLUSTEAD_ANALYTICS_SALT", "") or os.urandom(16).hex()

# 큐 상한. 가득 차면 drop(분석보다 본 서비스 보호 우선).
_MAX_QUEUE = 10000
# writer 가 한 번에 모아 commit 할 최대 배치 크기.
_BATCH = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS event (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             TEXT    NOT NULL,
  day            TEXT    NOT NULL,
  event_type     TEXT    NOT NULL,
  path           TEXT,
  visitor_hash   TEXT    NOT NULL,
  apartment      TEXT,
  apartment_gu   TEXT,
  apartment_dong TEXT,
  src            TEXT,
  combo_key      TEXT,
  combo_json     TEXT,
  result_count   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_event_type_day ON event(event_type, day);
CREATE INDEX IF NOT EXISTS idx_event_apartment ON event(apartment);
CREATE INDEX IF NOT EXISTS idx_event_combo     ON event(combo_key);
CREATE INDEX IF NOT EXISTS idx_event_visitor   ON event(visitor_hash, day);
"""

_queue = None          # queue.Queue, lazy
_worker = None         # threading.Thread, lazy
_lock = threading.Lock()
_init_failed = False   # init 한 번 실패하면 더 시도 안 함(로그 폭주 방지)

_COLUMNS = (
    "ts", "day", "event_type", "path", "visitor_hash",
    "apartment", "apartment_gu", "apartment_dong", "src",
    "combo_key", "combo_json", "result_count",
)


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _ensure_started():
    """첫 호출 시 워커 안에서 스레드·스키마를 lazy 초기화. fork-safe."""
    global _queue, _worker, _init_failed
    if _init_failed or (_worker is not None and _worker.is_alive()):
        return _queue is not None
    with _lock:
        if _init_failed or (_worker is not None and _worker.is_alive()):
            return _queue is not None
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            conn = _connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()
            _queue = queue.Queue(maxsize=_MAX_QUEUE)
            _worker = threading.Thread(
                target=_writer_loop, name="analytics-writer", daemon=True
            )
            _worker.start()
            return True
        except Exception:
            # init 실패 시 본 서비스는 그대로 동작. 분석만 비활성.
            _init_failed = True
            return False


def _writer_loop():
    conn = None
    try:
        conn = _connect()
    except Exception:
        return
    while True:
        try:
            first = _queue.get()  # 블로킹 — 이벤트 올 때까지 대기
        except Exception:
            continue
        batch = [first]
        # 대기 중인 것들을 추가로 모아 한 번에 commit.
        for _ in range(_BATCH - 1):
            try:
                batch.append(_queue.get_nowait())
            except queue.Empty:
                break
        try:
            conn.executemany(
                "INSERT INTO event (%s) VALUES (%s)"
                % (", ".join(_COLUMNS), ", ".join("?" for _ in _COLUMNS)),
                [tuple(row.get(c) for c in _COLUMNS) for row in batch],
            )
            conn.commit()
        except Exception:
            # 쓰기 실패해도 루프는 계속(다음 배치 시도).
            try:
                conn.rollback()
            except Exception:
                pass


def _daily_salt():
    day = datetime.now(_KST).strftime("%Y-%m-%d")
    return "%s|%s" % (_SALT_SEED, day)


def visitor_hash(ip, user_agent):
    """IP+UA+일일솔트 → 16자 해시. 원문 저장 금지, 날짜 넘어가면 재식별 불가."""
    raw = "%s|%s|%s" % (ip or "", user_agent or "", _daily_salt())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def track(event_type, ip=None, user_agent=None, path=None,
          apartment=None, apartment_gu=None, apartment_dong=None, src=None,
          combo_key=None, combo=None, result_count=None):
    """이벤트 1건 비동기 기록. 절대 예외를 밖으로 던지지 않는다."""
    if not ENABLED:
        return
    try:
        if not _ensure_started():
            return
        now = datetime.now(_KST)
        row = {
            "ts": now.astimezone(timezone.utc).isoformat(),
            "day": now.strftime("%Y-%m-%d"),
            "event_type": event_type,
            "path": path,
            "visitor_hash": visitor_hash(ip, user_agent),
            "apartment": apartment,
            "apartment_gu": apartment_gu,
            "apartment_dong": apartment_dong,
            "src": src,
            "combo_key": combo_key,
            "combo_json": (
                json.dumps(combo, ensure_ascii=False, separators=(",", ":"))
                if combo else None
            ),
            "result_count": result_count,
        }
        _queue.put_nowait(row)
    except queue.Full:
        pass  # 큐 포화 — drop(본 서비스 보호 우선)
    except Exception:
        pass  # 어떤 이유로든 분석 로깅은 본 서비스를 방해하지 않는다


def build_weight_combo(preferences, default=3):
    """가중치 dict → (combo_key, combo). 기본값(3) 아닌 항목만 정렬해 정규화."""
    items = sorted(
        (k, v) for k, v in (preferences or {}).items() if v != default
    )
    combo_key = ";".join("%s=%s" % (k, v) for k, v in items)
    return combo_key, (dict(items) if items else None)


def _read_connect():
    """조회 전용 커넥션. DB 없으면 None(아직 이벤트 0건)."""
    if not os.path.exists(DB_PATH):
        return None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _day_floor(days):
    """오늘(KST)에서 days-1 일 전 'YYYY-MM-DD'. days<=0 이면 None(전체)."""
    if not days or days <= 0:
        return None
    return (datetime.now(_KST) - timedelta(days=days - 1)).strftime("%Y-%m-%d")


def query_analytics(days=30, top=20):
    """admin/analytics 대시보드용 집계 일괄 조회. 단일 read 커넥션 재사용.

    days: 최근 N일(KST, 오늘 포함). 0/None 이면 전체 기간.
    반환 dict 구조는 템플릿이 그대로 소비.
    """
    empty = {
        "available": False, "days": days,
        "kpi": {"page_views": 0, "result_views": 0, "explore_searches": 0,
                "unique_visitors": 0},
        "daily": [], "top_apartments": [], "top_weight_combos": [],
        "top_filter_combos": [], "src_dist": [], "explore_sizes": {},
    }
    conn = _read_connect()
    if conn is None:
        return empty
    floor = _day_floor(days)
    where = "WHERE day >= ?" if floor else ""
    params = (floor,) if floor else ()
    try:
        def q(sql, extra=()):
            return conn.execute(sql, params + extra).fetchall()

        # KPI — 이벤트 타입별 건수 + 순방문자.
        type_counts = {
            r["event_type"]: r["n"] for r in q(
                "SELECT event_type, COUNT(*) n FROM event %s GROUP BY event_type"
                % where)
        }
        uniq = q(
            "SELECT COUNT(DISTINCT visitor_hash) n FROM event %s" % where
        )[0]["n"]

        # 일별 추이 — 방문(page_view) 수 + 일별 순방문자.
        daily = [
            {"day": r["day"], "page_views": r["pv"], "unique_visitors": r["uv"],
             "searches": r["sv"]}
            for r in q(
                "SELECT day, "
                "SUM(event_type='page_view') pv, "
                "COUNT(DISTINCT visitor_hash) uv, "
                "SUM(event_type IN ('result_view','explore_search')) sv "
                "FROM event %s GROUP BY day ORDER BY day" % where)
        ]

        # 자주 검색된 아파트 — result_view 기준.
        top_apartments = [
            {"apartment": r["apartment"], "gu": r["apartment_gu"],
             "count": r["n"], "visitors": r["uv"]}
            for r in q(
                "SELECT apartment, apartment_gu, COUNT(*) n, "
                "COUNT(DISTINCT visitor_hash) uv FROM event "
                "%s %s event_type='result_view' AND apartment IS NOT NULL "
                "GROUP BY apartment, apartment_gu ORDER BY n DESC LIMIT ?"
                % (where, "AND" if where else "WHERE"), (top,))
        ]

        # 자주 쓰인 가중치 조합 — result_view. combo_key='' 은 '기본값 그대로'.
        top_weight_combos = [
            {"combo_key": r["combo_key"] or "(기본값)", "count": r["n"],
             "visitors": r["uv"], "sample": r["sample"]}
            for r in q(
                "SELECT combo_key, COUNT(*) n, COUNT(DISTINCT visitor_hash) uv, "
                "MAX(combo_json) sample FROM event "
                "%s %s event_type='result_view' "
                "GROUP BY combo_key ORDER BY n DESC LIMIT ?"
                % (where, "AND" if where else "WHERE"), (top,))
        ]

        # 자주 쓰인 검색 필터 조합 — explore_search.
        top_filter_combos = [
            {"combo_key": r["combo_key"] or "(필터없음)", "count": r["n"],
             "visitors": r["uv"], "sample": r["sample"],
             "avg_results": round(r["avg_r"], 1) if r["avg_r"] is not None else None}
            for r in q(
                "SELECT combo_key, COUNT(*) n, COUNT(DISTINCT visitor_hash) uv, "
                "MAX(combo_json) sample, AVG(result_count) avg_r FROM event "
                "%s %s event_type='explore_search' "
                "GROUP BY combo_key ORDER BY n DESC LIMIT ?"
                % (where, "AND" if where else "WHERE"), (top,))
        ]

        # 진입경로(src) 분포 — result_view.
        src_dist = [
            {"src": r["src"] or "(미상)", "count": r["n"]}
            for r in q(
                "SELECT src, COUNT(*) n FROM event "
                "%s %s event_type='result_view' "
                "GROUP BY src ORDER BY n DESC"
                % (where, "AND" if where else "WHERE"))
        ]

        # explore 결과 규모 — 필터가 너무 좁은지(0건 비율) 진단.
        sz = q(
            "SELECT COUNT(*) n, AVG(result_count) avg_r, "
            "SUM(result_count=0) zero FROM event "
            "%s %s event_type='explore_search'"
            % (where, "AND" if where else "WHERE"))[0]
        explore_sizes = {
            "searches": sz["n"] or 0,
            "avg_results": round(sz["avg_r"], 1) if sz["avg_r"] is not None else None,
            "zero_result_count": sz["zero"] or 0,
            "zero_result_pct": (
                round(100.0 * (sz["zero"] or 0) / sz["n"], 1) if sz["n"] else None),
        }

        return {
            "available": True, "days": days,
            "kpi": {
                "page_views": type_counts.get("page_view", 0),
                "result_views": type_counts.get("result_view", 0),
                "explore_searches": type_counts.get("explore_search", 0),
                "unique_visitors": uniq,
            },
            "daily": daily,
            "top_apartments": top_apartments,
            "top_weight_combos": top_weight_combos,
            "top_filter_combos": top_filter_combos,
            "src_dist": src_dist,
            "explore_sizes": explore_sizes,
        }
    except Exception:
        return empty
    finally:
        conn.close()


def build_filter_combo(filters):
    """explore 필터 dict → (combo_key, combo). 활성 필터만 정렬해 정규화."""
    flat = {}
    for k, v in (filters or {}).items():
        if v in (None, "", [], ()):
            continue
        if k == "priorities":
            # [(category, subtype), ...] → 'category:subtype' 정렬 리스트
            vals = sorted(
                "%s:%s" % (c, s) for c, s in v if c and s
            )
            if vals:
                flat[k] = vals
        elif isinstance(v, (list, tuple)):
            vals = sorted(str(x) for x in v if str(x))
            if vals:
                flat[k] = vals
        else:
            flat[k] = v
    combo_key = ";".join(
        "%s=%s" % (k, ",".join(flat[k]) if isinstance(flat[k], list) else flat[k])
        for k in sorted(flat)
    )
    return combo_key, (flat if flat else None)

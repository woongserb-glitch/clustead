"""워커별 '현재 처리 중인 요청' 추적 (진단용).

목적: 워커가 gunicorn 타임아웃(60s)으로 강제종료될 때, 어떤 요청 URL 에 묶여
있었는지 gunicorn `worker_abort` 훅에서 남기기 위함. 2026-07-28 healthz FAIL
스파이럴(자원은 정상인데 워커만 60s 블로킹)의 범인 URL 을 다음 발생 때 특정한다.

설계:
- 동기(sync) 워커는 프로세스당 한 번에 한 요청만 처리하므로, 프로세스 전역
  단일 슬롯(`_CURRENT`)이면 충분하다(스레드 로컬 불필요).
- 인메모리라 요청당 디스크 I/O 가 없다(이 서버는 I/O 에 민감).
- 분석/진단 코드가 본 서비스를 절대 깨뜨리지 않도록 전 경로 try/except.
"""

import time

_CURRENT = {}


def begin(method, path, ip=""):
    try:
        _CURRENT["r"] = {
            "method": method,
            "path": path,
            "ip": ip,
            "start": time.time(),
        }
    except Exception:
        pass


def end():
    try:
        _CURRENT.pop("r", None)
    except Exception:
        pass


def snapshot():
    """현재 처리 중인 요청 정보(+경과초). 없으면 None."""
    try:
        r = _CURRENT.get("r")
        if not r:
            return None
        out = dict(r)
        out["elapsed"] = round(time.time() - r["start"], 1)
        return out
    except Exception:
        return None

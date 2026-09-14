"""Gunicorn 설정 — Clustead 소규모 외부 공개(A안) / OCI 단일 VPS.

핵심: 1.4GB 데이터를 preload로 마스터에서 1회 적재한 뒤 워커를 fork한다.
리눅스 copy-on-write 덕분에 워커들이 메모리를 대부분 공유 → 워커×1.4GB
중복 적재(OOM)를 피한다. preload가 이 배포의 메모리 생존선이다.
"""
import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# 워커 수: 소규모라 보수적으로 2. preload로 메모리는 대부분 공유되지만,
# 요청 중 생성되는 객체는 워커별로 쌓이므로 RAM 여유를 보며 WEB_CONCURRENCY로 조정.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))

# /result 가 Kakao API를 동기 호출 → 느릴 수 있어 타임아웃을 넉넉히(nginx와 맞춤).
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

# 마스터에서 앱(=데이터)을 1회 적재 후 fork. 워커 재활용 시에도 재적재 없음.
preload_app = True

# 점진적 메모리 증가 방어용 워커 재활용. 0 이면 비활성(gunicorn 기본값).
#
# 주의(2026-07-19): 호스트 RAM 이 1GB 뿐이라 앱 메모리 상당량이 스왑에 나가 있다.
# 이 상태에서 워커를 재활용하면 새 워커가 CoW 페이지를 스왑에서 되읽어야 해
# 콜드스타트가 매우 길어진다(07-19 01:13 재활용 시 부팅에 52초 소요). preload_app
# 이라 재활용해도 데이터 재적재 이득은 없고 지연만 생기므로 기본을 0(비활성)으로 둔다.
# 메모리 누수 징후가 보이면 GUNICORN_MAX_REQUESTS 로 다시 켤 수 있다.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100")) if max_requests else 0

# 컨테이너 표준출력으로 로깅(docker logs / nginx와 분리).
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")


def post_fork(server, worker):
    """fork 직후, 이 워커가 첫 요청을 받기 전에 뜨거운 페이지를 스왑에서 되읽는다.

    preload_app 으로 부모가 적재한 페이지를 워커는 CoW 로 물려받는데, 호스트
    RAM 이 961MB 뿐이라 그 상당량이 스왑에 나가 있다(2026-09-10 실측: 마스터
    245MB, 워커당 ~119MB 스왑). 워커가 그 페이지를 처음 만지는 순간이 하필
    사용자 요청 안이면 50~60 초가 걸려 timeout=60 에 걸린다.

    2026-09-07~09-09 사이 워커 강제종료 10 건 중 4 건이 이것이었고, 멈춘 워커는
    모두 부팅 5 분 이내의 새 워커였다(1분35초~5분10초). 그 URL 들을 나중에 다시
    재 보면 0.16~0.25 초다 — 페이지가 느린 게 아니라 워커가 차가웠다.

    되읽기를 여기서 끝내면 같은 비용이 "사용자가 60 초 기다리다 502" 대신
    "워커가 조용히 늦게 뜸" 이 된다. gunicorn 은 post_fork 동안 이 워커에
    요청을 넣지 않는다.

    주의: 오래 걸리면 마스터가 heartbeat 가 멎은 줄 알고 이 워커를 죽인다.
    처음엔 단계 사이에만 notify() 했는데, 한 단계가 통째로 60 초를 넘기면
    그 안에서 죽었다(2026-09-12·09-13 에 3 회, [WARM] 로그도 못 남기고 사라짐).
    그래서 예열 동안 별도 스레드가 주기적으로 갱신한다. 예산을 넘기면 남은
    단계는 건너뛰되, 진행 중인 단계는 끝까지 두고 heartbeat 로 버틴다.
    """
    import threading
    import time

    budget = float(os.getenv("GUNICORN_WARM_BUDGET", "40"))
    started = time.perf_counter()

    def beat():
        try:
            worker.tmp.notify()
        except Exception:
            pass

    # 한 단계가 timeout 보다 오래 걸려도 마스터가 죽이지 않도록 계속 살아있음을
    # 알린다. 데몬이라 워커가 요청 루프에 들어가기 전에 반드시 정리된다.
    stop_beating = threading.Event()

    def keep_alive():
        while not stop_beating.wait(5.0):
            beat()

    heart = threading.Thread(target=keep_alive, name="warm-heartbeat", daemon=True)
    heart.start()

    def spent():
        return time.perf_counter() - started

    try:
        import app as clustead

        steps = []

        def step(name, fn):
            steps.append((name, fn))

        # 단지 마스터 — 모든 화면이 가장 먼저 만진다.
        step("apartments", lambda: sum(
            1 for row in clustead.apartment_data if row.get("name")
        ))
        # 점수 인덱스 — 상세·탐색·지역 공통.
        step("ranking-index", lambda: len(clustead.build_apartment_index()))
        # 상세 한 장을 실제로 렌더해 result 경로의 페이지를 모두 만진다.
        step("result", lambda: clustead.app.test_client().get(
            "/result?apartment=%ED%97%AC%EB%A6%AC%EC%98%A4%EC%8B%9C%ED%8B%B0"
            "&gu=%EC%86%A1%ED%8C%8C%EA%B5%AC&dong=%EA%B0%80%EB%9D%BD%EB%8F%99"
        ).status_code)
        # 폰 진입점.
        step("explore", lambda: clustead.app.test_client().get("/explore").status_code)

        for name, fn in steps:
            if spent() > budget:
                worker.log.info("[WARM] 예산 초과 — %s 이후 건너뜀 (%.1fs)", name, spent())
                break
            beat()
            try:
                fn()
            except Exception as exc:
                worker.log.info("[WARM] %s 실패: %s", name, exc)
            beat()

        worker.log.info("[WARM] 워커 %s 예열 완료 %.1fs", worker.pid, spent())
    except Exception as exc:
        # 예열은 최적화일 뿐이다. 실패해도 워커는 정상 기동해야 한다.
        worker.log.info("[WARM] 예열 건너뜀: %s", exc)
    finally:
        stop_beating.set()
        heart.join(timeout=1.0)
        beat()


def worker_abort(worker):
    """워커가 타임아웃(timeout=60s)으로 강제종료되기 직전 호출된다(해당 워커
    프로세스 안에서). 그 순간 처리 중이던 요청 URL 을 남겨, 자원은 정상인데
    워커만 묶이는 스파이럴(2026-07-28)의 범인 URL 을 특정한다. 앱이 인메모리로
    기록해 둔 현재요청을 읽는다(services/request_tracker). 실패해도 무해."""
    try:
        from services.request_tracker import snapshot
        snap = snapshot()
        if snap:
            worker.log.critical(
                "[WORKER STUCK] %ss %s %s ip=%s",
                snap.get("elapsed"), snap.get("method"),
                snap.get("path"), snap.get("ip"),
            )
        else:
            worker.log.critical("[WORKER STUCK] (처리 중 요청 없음 — 요청 밖에서 멈춤)")
    except Exception:
        pass

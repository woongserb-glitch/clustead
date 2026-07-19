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

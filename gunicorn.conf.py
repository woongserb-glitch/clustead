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

# 점진적 메모리 증가 방어: 일정 요청마다 워커 재활용(jitter로 동시 재활용 분산).
max_requests = 1000
max_requests_jitter = 100

# 컨테이너 표준출력으로 로깅(docker logs / nginx와 분리).
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")

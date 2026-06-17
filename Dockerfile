# Clustead — 소규모 외부 공개(A안) / OCI Ubuntu VPS · Docker · Gunicorn · Nginx
# 데이터(1.4GB)는 이미지에 굽지 않는다. 런타임에 ./data 를 /app/data 로 마운트.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pandas/pyproj 등은 manylinux 휠로 설치되어 보통 빌드툴이 불필요하다.
# 특정 패키지가 소스 빌드를 요구하면 아래 줄의 주석을 해제한다.
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# 코드만 복사(data/ 는 .dockerignore 로 제외 → 볼륨 마운트).
COPY . .

# 비루트 사용자로 구동. 단, data/cache(Kakao 캐시 write)는 마운트 볼륨이라
# 호스트 측 권한과 맞아야 한다(DEPLOY.md 참고).
RUN useradd -m -u 10001 appuser
USER appuser

EXPOSE 8000

# 설정은 gunicorn.conf.py(preload·workers·timeout) 참조.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]

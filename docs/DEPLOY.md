# LiveFit 배포 가이드 (소규모 외부 공개 / OCI Ubuntu VPS)

스택: **OCI Ubuntu VPS 1대 · Docker · Gunicorn · Nginx**
구성: 인터넷 → Nginx(80) → Gunicorn(app:8000, 컨테이너 내부) → Flask 앱
데이터(1.4GB)는 이미지에 굽지 않고 **호스트 볼륨**(`./data`)으로 마운트한다.

---

## 0. 사전 점검 (보안 게이트)

외부 공개 전 반드시 확인:

- [ ] `.env` 에 `FLASK_DEBUG` 미설정(=OFF). **디버거 켜면 RCE.**
- [ ] `.env` 에 `LIVEFIT_ADMIN_TOKEN` 을 강한 랜덤값으로 설정(`/admin/*` 보호).
- [ ] Kakao 콘솔에서 `KAKAO_JAVASCRIPT_KEY` 의 **플랫폼 도메인 화이트리스트** 등록(키 도용 방지).
- [ ] 레이트리밋 활성(기본 ON). `compose` 가 `LIVEFIT_TRUST_PROXY=1` 주입(아래 참고).

---

## 1. OCI 인스턴스 / 네트워크

1. Ubuntu 22.04+ 인스턴스 생성(Always Free ARM Ampere A1 권장 — RAM 여유).
2. **인그레스 개방**: OCI 콘솔 → VCN → Security List 에 80(필요 시 443) TCP 허용.
3. 호스트 방화벽(우분투는 기본 `iptables`/`netfilter-persistent` 사용 주의):
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo netfilter-persistent save
   ```
   (ufw 사용 환경이면 `sudo ufw allow 80/tcp`.)

## 2. Docker 설치

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 재로그인 후 적용
```
`docker compose`(v2 플러그인)가 함께 설치된다.

## 3. 코드 + 데이터 배치

```bash
git clone <REPO_URL> livefit && cd livefit
cp .env.example .env && nano .env     # 0번 체크리스트대로 채운다
```

데이터(`data/`, 1.4GB)는 git 추적 대상이 아니다. 빌드/수집 머신에서 전송:
```bash
rsync -avz --progress ./data/ <user>@<vps>:~/livefit/data/
```

**권한**: 컨테이너는 비루트(uid 10001)로 구동된다. Kakao 캐시 write(`data/cache/`)를 위해:
```bash
sudo chown -R 10001:10001 data
```

## 4. 빌드 & 기동

```bash
docker compose up -d --build
docker compose ps             # app=healthy 될 때까지 ~1분(부팅 워밍업)
docker compose logs -f app    # [PRELOAD]/[BASELINE] 적재 로그 확인
```

확인:
```bash
curl -s http://localhost/healthz      # {"status":"ok",...}
curl -s -o /dev/null -w "%{http_code}" http://<공인IP>/   # 200
```

## 5. 운영 메모

### 메모리 (가장 큰 함정)
- 앱은 부팅 시 1.4GB를 메모리에 적재한다. Gunicorn `preload_app=True`(이미 설정)로 **마스터가 1회 적재 후 fork** → 워커들이 copy-on-write로 공유한다.
- 워커 수는 `WEB_CONCURRENCY`(기본 2). **RAM이 빠듯하면 1로 낮춘다.** 늘릴 땐 요청 중 생성 객체가 워커별로 쌓이는 점을 감안(메모리 우선, CPU 다음).
- 부팅 8~17초 동안은 healthcheck `start_period`(60s)가 unhealthy 판정을 막는다.

### 레이트리밋
- `/result` 30/분, `/result/export.xlsx` 10/분 (IP 기준, Kakao 유료쿼터 방어).
- **주의**: 메모리 스토리지는 워커별 카운트라 워커 2개면 실질 한도가 ~2배가 된다. 전역 일치가 필요하면 Redis 사용:
  - `compose` 에 redis 서비스 추가 + `LIVEFIT_RATELIMIT_STORAGE=redis://redis:6379`.

### 로그 / 헬스
```bash
docker compose logs -f app          # gunicorn 액세스/에러 + 앱 로그
docker inspect --format '{{.State.Health.Status}}' $(docker compose ps -q app)
```

## 6. 재배포 (코드 갱신)

```bash
git pull
docker compose up -d --build        # 무중단은 아님(소규모 A안). 재시작 시 ~수십초 워밍업.
```
데이터만 갱신 시 컨테이너 재시작으로 재적재:
```bash
docker compose restart app
```

## 7. 도메인 연결 + HTTPS (clustead.com)

서버 구성은 이미 HTTPS-ready 다(443 포트·certbot 서비스·SSL conf 포함). 순서대로:

### 7-1. DNS — clustead.com → VM 공인 IP
도메인 레지스트라(또는 OCI DNS)에서 A 레코드:
```
clustead.com        A   <VM_PUBLIC_IP>
www.clustead.com    A   <VM_PUBLIC_IP>
```
전파 확인(VM에서): `dig +short clustead.com` 가 VM IP를 반환할 때까지 대기(수 분~수십 분).
⚠️ OCI Security List + 호스트 iptables 에 **443 도 개방**해야 한다(§1 의 80 과 동일하게 dport 443).

### 7-2. HTTP로 먼저 기동 (인증서 발급 준비)
부트스트랩 conf(livefit.conf)는 인증서를 참조하지 않으므로 바로 뜬다:
```bash
docker compose up -d --build      # http://clustead.com 로 접속되면 정상
```

### 7-3. 인증서 1회 발급 (webroot 방식)
```bash
docker compose run --rm --entrypoint certbot certbot \
  certonly --webroot -w /var/www/certbot \
  -d clustead.com -d www.clustead.com \
  --email <your-email> --agree-tos --no-eff-email
```
성공 시 `deploy/certbot/conf/live/clustead.com/` 에 인증서 생성.

### 7-4. nginx 를 HTTPS conf 로 전환
`docker-compose.yml` 의 nginx default.conf 마운트를 SSL conf 로 변경:
```yaml
      - ./deploy/nginx/livefit-ssl.conf:/etc/nginx/conf.d/default.conf:ro
```
적용:
```bash
docker compose up -d nginx        # 이제 https://clustead.com (80→443 자동 리다이렉트)
```

### 7-5. 자동 갱신
`certbot` 서비스가 12시간마다 `renew` 시도(만료 30일 이내만 실제 갱신). 갱신된 인증서를
nginx 가 읽도록 주기적 reload 가 필요하다(예: cron 으로 주 1회):
```bash
docker compose exec nginx nginx -s reload
```

> Kakao 콘솔의 JavaScript 키 플랫폼 도메인에 `https://clustead.com` 도 등록할 것(지도 로드).

---

## 부록: 남은 운영 과제 (A안 이후)
- 에러 트래킹(Sentry) · 메트릭 연동.
- CI/CD: `tests/snapshot_result.py check` + `tests/test_correctness.py` 를 머지 게이트로 자동화.
- 데이터 갱신 파이프라인 cron 화(현재 수동).
- 워드마크 폰트(Jost) self-host 로 로고 렌더 정밀도 향상(현재 시스템 지오메트릭 폴백).

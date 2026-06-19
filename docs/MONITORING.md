# Clustead 모니터링 & 장애 대응 런북

> 대상 인프라: NCP Ubuntu 24.04 1 vCPU / 1GB RAM + 2GB swap, host **nginx**(80/443) →
> **Docker** `clustead-app-1`(gunicorn, `127.0.0.1:8000`), 앞단 **Cloudflare**(orange proxy).
> 데이터는 `./data` 볼륨 마운트(baseline.db ~390MB, 실거래 master ~252MB).

---

## 1. 장애 시나리오 분석 (현재 자동복구 상태)

| 시나리오 | 자동 복구? | 근거 / 설정 | 탐지 경로 |
|---|---|---|---|
| **앱 컨테이너 다운** | ✅ 자동재시작 | compose `restart: unless-stopped` | 외부(UptimeRobot) 사이트 다운, healthz 실패 |
| **Gunicorn 워커 죽음** | ✅ 자동 | 마스터가 워커 재생성 + `max_requests=1000`로 주기적 재활용(메모리 누수 방어) | healthz/외부 |
| **Gunicorn 마스터 죽음** | ✅ 간접 | 컨테이너 exit → docker가 재시작 | 외부 |
| **Nginx 다운** | ✅ 자동(신규) | systemd `Restart=on-failure`(이번에 추가) + 부팅 `enabled` | 외부(전체 다운) |
| **서버 재부팅** | ✅ 복구(신규) | **`systemctl enable docker`(이번에 수정)** + `restart: unless-stopped` → 부팅 시 컨테이너 자동 기동. nginx도 enabled | 외부(워밍업 ~50초간 502 후 정상) |
| **메모리 부족(OOM)** | ✅ 격리 | compose `mem_limit: 768m` → 폭주 시 **컨테이너만** OOM-kill, 호스트 보호. 이후 자동재시작 | 서버 스크립트(OOMKilled 플래그/가용메모리), 외부(일시 5xx) |
| **디스크 부족** | ❌ 수동 | 현재 **93%**(여유 ~684MB) — 데이터 footprint(transactions 626M+baseline 437M+db 372M)가 9.8G 디스크에 빡빡. 임박 시 SQLite/로그/캐시 쓰기 실패 | **서버 스크립트(디스크 임계 알림)** ← 외부 모니터로는 안 보임 |
| **Cloudflare 뒤 origin 장애** | 시나리오별 | origin 다운 시 CF가 **522/523/521** 표시. CF 자체 장애는 드묾 | 외부 모니터를 **CF 통과 URL**(`https://clustead.com/...`)로 두면 origin·CF 경로 모두 감시 |
| **Kakao 지도 키/도메인 문제** | ❌ 수동 | 키 만료·도메인 미등록 시 지도만 안 뜸(사이트는 정상) | 육안/사용자 제보 (외부 모니터 미탐지) |

**요점**: 이번 작업으로 *재부팅·nginx 크래시*의 자동복구 구멍을 메웠다. 남는 수동 리스크는 **디스크**(현재 95%로 가장 임박)와 Kakao 키.

---

## 2. 무료 업타임 모니터링 비교

| 서비스 | 무료 한도 | 체크 주기(무료) | 알림 | 특징 | Clustead 적합도 |
|---|---|---|---|---|---|
| **UptimeRobot** | 모니터 50개 | **5분** | 이메일·Slack·Telegram·Webhook | 가장 단순·관대, keyword 모니터 지원 | ⭐ 외부 감시 1순위 |
| **Better Stack (Uptime)** | 모니터 10개 | **3분** | 이메일·Slack·전화(유료)·상태페이지 | UI/인시던트·상태페이지 우수, 3분 주기 | 상태페이지 원하면 |
| **Healthchecks.io** | 체크 20개 | (heartbeat) | 이메일·Slack·Webhook | **dead-man's-switch**(핑이 끊기면 알림) — cron/백업 감시용 | 서버 cron 감시 보완용 |
| **Cloudflare Health Checks** | — | 유료(노티피케이션) | — | CF Pro+ 필요 | ❌ 비용 |

**결론**
- **외부 가용성**: **UptimeRobot 무료**가 가장 적합(50 모니터·5분·keyword·다양한 알림). 5분 주기면 1인 운영 사이트엔 충분.
- **더 짧은 주기/상태페이지**가 필요하면 Better Stack(3분) 병행.
- **내부 지표(디스크/메모리)**: 외부 모니터로는 안 보이므로 **서버 cron 스크립트**(아래 4-B)로 보완.

---

## 3. 권장 아키텍처

```
[UptimeRobot] --5분--> https://clustead.com/healthz  (keyword: "ok")   ─┐
[UptimeRobot] --5분--> https://clustead.com/          (HTTP 200)        ─┤→ 이메일/Slack/텔레그램
                                                                        │   (사이트·502·컨테이너·재부팅·CF origin 감지)
[서버 cron 5분] server_health_check.sh ─→ 디스크/메모리/컨테이너/OOM ──┘→ Webhook(Slack/Discord)
                                                                            (외부가 못 보는 내부 신호)
```

- **2겹 구성**: 외부(UptimeRobot)는 "밖에서 안 보임"을, 내부(cron)는 "곧 죽을 신호"를 잡는다.
- healthz는 데이터 적재 완료 시 `{"status":"ok"}` 200, 워밍업/이상 시 503 → keyword `ok` 감시로 "떠 있지만 준비 안 됨"까지 구분.

---

## 4. 적용 방법

### A. UptimeRobot (외부, ~5분 / 사용자 작업)
1. https://uptimerobot.com 가입(무료).
2. **Add New Monitor**:
   - Monitor Type: **Keyword**, URL: `https://clustead.com/healthz`, Keyword: `ok`, "Alert when keyword *not* exists", 주기 5분.
   - (추가) Monitor Type: **HTTP(s)**, URL: `https://clustead.com/`, 주기 5분.
3. **My Settings → Alert Contacts**: 이메일은 기본. 원하면 Telegram/Slack 추가(즉시성↑).
4. (선택) **Status Page** 생성 → 공개 상태페이지 URL 확보.

> Cloudflare 뒤라도 `clustead.com`(CF 통과) URL로 두면 origin 다운(522 등)도 감지된다.
> CF가 봇을 막지 않도록, 차단되면 UptimeRobot User-Agent를 WAF 예외 처리.

### B. 서버 자가 점검 (내부, cron / 코드 포함)
스크립트: [`scripts/server_health_check.sh`](../scripts/server_health_check.sh) (레포 포함, 서버 git pull 시 반영).

```bash
# 1) 알림 채널 설정 (Slack/Discord 웹훅 1분이면 생성)
sudo tee /etc/clustead-monitor.env >/dev/null <<'EOF'
CLUSTEAD_ALERT_WEBHOOK="https://discord.com/api/webhooks/XXXX"   # 또는 Slack Incoming Webhook
CLUSTEAD_DISK_MAX_PCT=90
CLUSTEAD_MEM_MIN_MB=80
EOF

# 2) 실행 권한 + cron 등록(5분 간격)
chmod +x /root/clustead/scripts/server_health_check.sh
( crontab -l 2>/dev/null; echo "*/5 * * * * /root/clustead/scripts/server_health_check.sh" ) | crontab -

# 3) 동작 확인
/root/clustead/scripts/server_health_check.sh; tail -n 3 /var/log/clustead-monitor.log
```
- 웹훅 미설정이어도 `/var/log/clustead-monitor.log`에 기록은 남는다(알림만 생략).
- 알림은 **상태 변화 시에만**(이상 발생/내용변경/복구) → 스팸 없음.

---

## 5. 예상 비용

| 항목 | 비용 |
|---|---|
| UptimeRobot 무료 | **0원** (모니터 50개·5분) |
| Better Stack 무료(선택) | **0원** (모니터 10개·3분) |
| 서버 cron 스크립트 | **0원** (기존 서버 자원) |
| Slack/Discord 웹훅 알림 | **0원** |
| **합계** | **0원** |

> 더 짧은 주기(1분)·전화 알림·SMS는 대부분 유료. 1인 운영 단계에선 불필요.

---

## 6. 운영 체크리스트

**일/주 단위 (대부분 UptimeRobot이 대신함)**
- [ ] UptimeRobot 대시보드 가동률(uptime %) 확인
- [ ] 디스크 여유 확인 — 현재 **93%**(임계 95% 설정). 9.8G로 빡빡해 증설 검토 여지. `df -h /` 모니터링

**배포/데이터 갱신 시**
- [ ] 재배포 후 `https://clustead.com/healthz` 200·`ok` 확인
- [ ] raw 데이터 갱신은 **전체 체인** 실행: `python scripts/rebuild_data_full.py` → `data/baseline.db` 전송 → 컨테이너 재시작 (enrich/sqlite 누락 방지)
- [ ] `docker compose ... up -d --build` 후 디스크 잔량 확인(빌드 캐시 누적)

**정기 점검(월)**
- [ ] `systemctl is-enabled docker nginx` 둘 다 `enabled` 인지
- [ ] Kakao JavaScript SDK 도메인에 `https://clustead.com` 등록 유지
- [ ] `docker system prune -af` 로 빌드 캐시 정리(디스크)

---

## 7. 상황별 대응 (확인 명령어)

> SSH 접속: 로컬에서 `ssh -i ~/.ssh/clustead_deploy root@211.188.48.124`

### 공통: 빠른 전체 상태
```bash
systemctl is-active docker nginx                  # 데몬 살아있나
docker ps --format '{{.Names}} {{.Status}}'       # 컨테이너 상태/업타임
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/healthz   # 앱 준비됐나(200)
df -h / ; free -m                                 # 디스크/메모리
```

### A. 사이트 접속 안 됨
```bash
curl -I https://clustead.com                      # CF 통과 상태(521/522/523=origin 문제)
curl -I http://127.0.0.1:8000/healthz             # origin 자체는 살아있나
systemctl status nginx --no-pager | tail -20      # nginx 죽었나
docker ps -a | grep clustead                      # 컨테이너 Exited인가
```
- nginx 죽음 → `systemctl restart nginx` (이제 자동복구되지만 수동도 가능)
- 컨테이너 Exited → `cd /root/clustead && docker compose -f docker-compose.app-only.yml up -d`

### B. 502 / 503 / 504 발생
```bash
docker logs --tail 80 clustead-app-1              # 앱 로그(트레이스백)
docker inspect -f '{{.State.Health.Status}} restarts={{.RestartCount}} oom={{.State.OOMKilled}}' clustead-app-1
```
- 배포/재시작 직후라면 **워밍업(~50초)** 정상 — 잠시 후 200.
- 계속 502면 로그의 예외 확인 후 `docker compose ... up -d --force-recreate`.

### C. 컨테이너 다운/계속 재시작(restart loop)
```bash
docker ps -a | grep clustead                      # 상태/재시작 횟수
docker logs --tail 120 clustead-app-1             # 크래시 원인
docker inspect -f '{{.State.OOMKilled}}' clustead-app-1   # OOM이면 true
```
- OOM이면 → 메모리 항목(D) 참고. 코드 예외면 마지막 배포 롤백(`git log`→이전 커밋 `up -d --build`).

### D. 메모리 부족(OOM)
```bash
free -m ; docker stats --no-stream clustead-app-1     # 사용량/상한(768m)
dmesg -T | grep -i -E 'oom|killed process' | tail     # 커널 OOM 기록
```
- 컨테이너만 죽고 자동재시작됨(호스트 보호). 빈번하면 워커 수↓(`WEB_CONCURRENCY=1`) 또는 실거래 상세 드릴다운 트래픽 점검(detail master 수백MB 적재).

### E. 디스크 부족
```bash
df -h / ; du -sh /root/clustead/data/* 2>/dev/null | sort -h | tail
docker system df                                      # 도커가 먹는 용량
docker system prune -af && docker builder prune -af   # 미사용 이미지/빌드캐시 정리(안전)
```
- 그래도 빡빡하면: 오래된 로그(`/var/log/clustead-monitor.log`) 로테이트, 또는 디스크 증설 검토.

### F. 서버 재부팅 후
```bash
systemctl is-active docker nginx                  # 둘 다 active 여야(이제 enabled)
docker ps | grep clustead                         # 자동 기동됐나
```
- 안 떠 있으면: `systemctl start docker && cd /root/clustead && docker compose -f docker-compose.app-only.yml up -d`

### 로그 위치 요약
| 대상 | 명령 |
|---|---|
| 앱(gunicorn/Flask) | `docker logs --tail 100 -f clustead-app-1` |
| nginx 접근/오류 | `tail -f /var/log/nginx/access.log /var/log/nginx/error.log` |
| 서버 자가점검 | `tail -f /var/log/clustead-monitor.log` |
| 커널/OOM | `dmesg -T | grep -i oom` |
| 분석 대시보드 | `https://clustead.com/admin/analytics?admin_token=...` |

---

## 8. 이번 작업으로 적용된 것 (요약)
- ✅ `systemctl enable docker` — 재부팅 시 컨테이너 자동 기동(이전: disabled → 재부팅 시 수동 복구 필요했음)
- ✅ nginx `Restart=on-failure` drop-in — nginx 크래시 자가복구
- ✅ 디스크 정리: docker prune(215M) + 스테일 raw_backup 스냅샷(195M) 제거 → 97%→**93%**
- ✅ `scripts/server_health_check.sh` 서버 배포 + **cron 5분 등록 완료** + `/etc/clustead-monitor.env` 생성(임계 디스크 95%/메모리 80MB). 첫 실행 `[OK]` 확인.
- ✅ 런북(이 문서)
- ⬜ (사용자) ① UptimeRobot 가입·모니터 2개 등록(4-A), ② `/etc/clustead-monitor.env` 의 `CLUSTEAD_ALERT_WEBHOOK` 에 Slack/Discord 웹훅 채우기(현재 빈 값 → 로그만, 알림 미발송)

> 디스크는 9.8G로 구조적으로 빡빡(데이터 ~1.4GB). 임계 95%로 두어 '추가 증가'만 알린다.
> 더 늘면 `data/transactions/raw`(193M, master 재빌드용) 정리 또는 디스크 증설 검토.

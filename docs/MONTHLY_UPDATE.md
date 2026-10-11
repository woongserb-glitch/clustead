# Clustead 월간 데이터 갱신 A to Z

매달 한 번, 단지 마스터부터 서버 배포까지 **빠짐없이** 돌리기 위한 절차서다. 회차마다 겪은 함정은
맨 아래 "함정 모음"에 모았다. 한 단계라도 건너뛰면 그 이유를 갱신 기록(7장)에 남긴다.

- 언제: 매월 1~5일(실거래 전월분 신고가 어느 정도 쌓인 뒤). 화면의 "데이터 기준 YYYY년 M월"은 **전월**이다.
- 걸리는 시간: 로컬 작업 반나절 + 카카오 3종 2~3일(하루 한도 때문에 나눔, 그동안 다른 단계 진행) + 배포 30분.
- 어디서: 워크트리 `C:/Users/hyr19/clustead-main`(브랜치 main). `data/`는 원래 폴더
  `C:/Users/hyr19/OneDrive/Desktop/apartment-life-score/data`로 연결(junction)돼 있다.
  **원래 폴더는 Codex가 feature/ai-search로 쓰고 있어 브랜치를 바꾸지 않는다.**
- 키: 원래 폴더의 `.env`(KAKAO_REST_API_KEY, VWORLD_API_KEY, SEOUL_OPEN_DATA_KEY, PUBLIC_DATA_SERVICE_KEY).
  워크트리에는 .env 가 없으니 스크립트를 돌릴 때 이 파일을 환경변수로 올린다(값은 출력하지 않는다).
  ```bash
  set -a; . /c/Users/hyr19/OneDrive/Desktop/apartment-life-score/.env; set +a
  ```

---

## 0. 한눈에 보는 순서

| # | 단계 | 명령(요약) | 결과물 |
|---|---|---|---|
| 1 | 준비·백업 | 미리보기 서버 끄기, 백업 폴더 | `C:/Users/hyr19/clustead-backups/YYYYMMDD/` |
| 2 | 원천 점검 | `update_data_pipeline.py --check-only` | 갱신된 원천 목록 |
| 3 | 단지 마스터 | `refresh_apartment_master.py` → 보정 4종 | `data/apartment/seoul_apartments.csv` |
| 4 | 단지 상태 점검 | 재건축·통용명·좌표 감사 | `scripts/manual_overrides/*.csv` |
| 5 | 브이월드 원천 | 통학구역·공원·전통시장·학교군 | `data/school/zone/`, `data/park/`, `data/derived/vworld/` |
| 6 | 동 건물 매칭 | (신규 단지 많을 때만) v5 파이프라인 | `complex_buildings_v5.jsonl` |
| 7 | 서울시·공공 rawdata | `update_data_pipeline.py --download-updated` | `data/<원천>/` |
| 8 | 실거래 | 국토부 xlsx 수동 → master → mapping → summary | `data/transactions/`, `transaction_summary.csv` |
| 9 | baseline 18종 | `build_all_baselines`(카카오 3종 제외) | `data/baseline/*.csv` |
| 10 | 카카오 3종 | 편의점·슈퍼(1일차) / 카페(2일차) | cafe·convenience·mart baseline |
| 11 | 동별 정보 | `scripts/vworld/build_dong_level.py` | `data/derived/vworld/dong_level.json` |
| 12 | 백분위·DB·검사 | `rebuild_data_full.py --skip-build` | `data/baseline.db` |
| 13 | 홈 순위 | `build_home_rankings.py` | `data/derived/home_rankings.json` |
| 14 | 격자 지도 | `build_grid_index` → `precompute_grid` → `snapshot_grid` | `data/grid.db` |
| 15 | 기준월 표기 | 푸터·홈 data_month | 코드 커밋 |
| 16 | 검증 | 변경 범위·0 붕괴·골든·pytest·화면 | — |
| 17 | 배포 | 코드 push → 데이터 전송·교체 → 재시작 → 빌드 | 서버 |
| 18 | 사후 | CF Purge, AI 검색 목록, 블로그 숫자, 기록 | — |

---

## 1. 준비·백업

1. 로컬 미리보기 서버를 끈다. 켜 둔 채면 `baseline.db` 를 붙들고 있어 12단계 sqlite 교체가 `WinError 5` 로 실패한다.
2. 백업(마스터·baseline·DB는 gitignore라 git으로 되돌릴 수 없다):
   ```bash
   B=C:/Users/hyr19/clustead-backups/$(date +%Y%m%d); mkdir -p $B
   cd C:/Users/hyr19/clustead-main
   cp data/apartment/seoul_apartments.csv data/baseline.db data/grid.db $B/
   cp -r data/baseline $B/baseline
   cp -r data/derived $B/derived          # home_rankings.json(13단계 --previous 로 씀), vworld/
   cp data/transactions/*.csv $B/ ; cp -r data/registry $B/registry
   ```
3. 골든마스터가 지금 코드·데이터와 맞는지 먼저 확인: `python tests/snapshot_result.py check` → PASS가 아니면 원인부터.
4. 서버 디스크 여유 확인(배포 전 1.8GB 이상 필요, 17장).

## 2. 원천 점검

```bash
env -u PYTHONIOENCODING python scripts/update_data_pipeline.py --check-only
```
- 결과는 `data/registry/pipeline_runs/update_check_*.json`. `update_available` 인 원천만 7단계에서 받는다.
- **이 점검이 다루지 않는 것**(매달 따로 확인): 단지 마스터(3장), 실거래(8장), 브이월드 레이어(5장),
  카카오 3종(10장), 한강 출입구(분기, 6장 표).

## 3. 단지 마스터 — 모든 데이터의 기준

```bash
set -a; . <.env>; set +a
PYTHONIOENCODING=utf-8 python scripts/refresh_apartment_master.py          # 인자 없음 = dry-run 보고
```
1. 보고서에서 **신규·삭제·속성 변경**을 읽는다. 신규 단지는 이름·주소·세대수·좌표를, 삭제는 재건축 여부를 본다.
2. 반영: `python scripts/refresh_apartment_master.py --apply --run-overrides`
3. 보정(모두 `scripts/manual_overrides/`, 근거·출처 열을 반드시 채움):
   - 세대수 0인 신규 단지 → `missing_apartment_households_approved.csv` → `python scripts/apply_missing_apartment_households.py --apply`
     (`dong_count` 열은 K-apt 현재값과 같아야 한다. 다르면 STALE 로 건너뜀)
   - 좌표 없는 단지 → `apply_missing_apartment_geocodes.py`
   - 잘못된 대표좌표 → `wrong_apartment_geocodes_approved.csv` → `python scripts/fix_wrong_apartment_geocodes.py --apply`
   - 재건축이 끝난 옛 단지·중복 행 → `complex_lifecycle_approved.csv`(status rebuilt/merged) → `python scripts/apply_complex_lifecycle.py --apply`
     (새 단지가 마스터에 있을 때만 옛 행을 뺀다. 2단계 refresh 도 같은 목록을 매달 자동으로 거른다)
4. 결과 단지 수를 적어 둔다(예: 2,861행, 런타임 2,860곳 — 좌표 없는 일원대우 1곳 차이).

## 4. 단지 상태 점검(재건축·통용명·좌표)

마스터가 흔들리면 모든 지표가 흔들린다. 신규·변경 단지를 중심으로 매달 본다.

| 점검 | 방법 | 반영 |
|---|---|---|
| 대표좌표 감사 | `python scripts/vworld/coord_audit.py` → `data/derived/vworld/coord_audit.json` 에서 단지 건물과 100m 넘게 떨어진 곳 | 카카오 단지 장소·도로명 지오코딩·동 건물과 맞으면 `wrong_apartment_geocodes_approved.csv` |
| 재건축 신호 | 실거래 매핑이 **다른 단지 이름**을 가리킴(예: 상계주공8단지→포레나노원), 2025년 이후 거래 0건, 카카오 장소명에 "(YYYY년MM월예정)" | 끝남 → `rebuilt` + 새 단지, 공사 중 → `rebuilding` + planned_name |
| 중복 행 | 같은 세대수·동수, 좌표 수십 m, 한쪽은 주소·사용승인일 없음 | `merged` + 남길 행 |
| 통용명 | 현장·실거래 이름이 마스터와 다름(임대 관리 단위는 분양 단지 이름) | `complex_common_names_approved.csv` |
| 동별 매칭 오류 | 동 건물이 남의 건물을 잡음(카카오 "OO아파트 101동" 장소와 대조) | `dong_buildings_rejected.csv`(동별 계산에서 빼고 대표좌표) |

판정에 쓰는 조회 도구는 2026-10-10 기록 참고(카카오 키워드·coord2address 주변 아파트·실거래 매핑·마스터 중복 대조).
근거가 약한 판정은 evidence 열에 "추정"이라고 적는다.

## 5. 브이월드 원천(매월 자동)

```bash
set -a; . <.env>; set +a
python scripts/fetch_school_zones_vworld.py        # 초등 통학구역 → data/school/zone/vworld_desch.geojson
python scripts/vworld/collect_layers.py            # 공원(UPISUQ153)·전통시장·중/고 학교군 → data/derived/vworld/
python scripts/build_park_source_vworld.py         # 조성 공원 → data/park/vworld_parks.geojson (이름: 괄호→주요공원→카카오)
```
- 통학구역은 예전 SHP(교육시설안전원, 3·9월 수동 교체)와 같은 데이터다. vworld 파일이 있으면 빌더가 이것을 쓴다.
- 레이어 수가 지난달보다 크게 줄면(예: 공원 2,689 → 1,000) 9단계 전에 멈추고 원인을 본다. 수집기는 0개면 기존 파일을 지키지만, 일부만 받힌 경우는 막지 못한다.

## 6. 동 건물 매칭(v5) — 필요할 때만

`data/derived/vworld/complex_buildings_v5.jsonl` 은 단지마다 동 건물 윤곽이다. 동별 등급(지하철·버스·교육환경·한강·공원·병원·약국·학원·편의점·카페·슈퍼)이 모두 이걸 쓴다.
- **신규 단지는 v5에 없으면 자동으로 대표좌표 기준**이 된다. 그러니 매달 다시 만들 필요는 없다.
- 신규·재건축 단지가 많이 쌓였거나(대략 20곳 이상) 대단지가 새로 들어오면 파이프라인을 다시 돌린다:
  `scripts/vworld/pipeline/README.md` 순서(SPBD → 카카오 동번호 → 통용명 → BLDGINFO → match_v5 → 유령·지점 보완 → 동번호 판정 → 원장).

| 주기 | 작업 |
|---|---|
| 분기 1회 | 한강 출입구 `python scripts/vworld/collect_hangang_access.py`(나들목·경사로·계단, 카카오) |
| 필요 시 | v5 파이프라인, 통용명 재수집 |

## 7. 서울시·공공 rawdata

```bash
env -u PYTHONIOENCODING python scripts/update_data_pipeline.py --download-updated
```
- `update_available` 인 원천만 내려받고 해당 baseline 을 다시 빌드한다(그때 percentile 칸이 빠진다 → 12단계가 채움).
- 한강(OA-id 없음)·국토부 실거래(수동)는 자동 대상이 아니다.
- **반드시 `PYTHONIOENCODING` 을 빼고** 돌린다(함정 1).

## 8. 실거래(국토부, 수동)

1. https://rt.molit.go.kr 에서 서울 아파트 매매·전월세를 연도별 xlsx로 받아 `data/transactions/raw/molit/`(trade_YYYY.xlsx, rent_YYYY.xlsx)에 둔다.
2. ```bash
   python scripts/build_molit_transaction_master.py
   python scripts/build_transaction_mapping.py
   python scripts/build_transaction_summary.py
   ```
3. 확인: 전월 거래 건수, 연결 단지 수(예: 2,531), 신규 단지의 매핑, `apartment_transaction_mapping_manual.csv` 보정.
   DEPLOY.md "동(洞) 불일치 점검표"도 본다.

## 9. baseline 18종(카카오 3종 제외)

```bash
# .env 를 올리고, 카카오 캐시는 만료시키지 않는다(TTL=0) — 동 위치·좌표가 바뀐 곳만 새로 조회
set -a; . <.env>; set +a
CLUSTEAD_KAKAO_CACHE_TTL=0 CLUSTEAD_BASELINE_SKIP=cafe,convenience,mart python -m scripts.build_all_baselines
```
- 약 25분. 오래 걸리니 Start-Process(PowerShell)나 백그라운드로 돌린다.
- 동별 원칙: `scripts/dong_points.py`(등급 = 중간 동, 목록 = 동 전체 합침, 동 건물 2개 미만은 대표좌표).

## 10. 카카오 3종(편의점·카페·슈퍼) — 이틀에 나눠서

카카오 로컬 API는 하루 10만 회 한도. 동이 150m 넘게 퍼진 단지(약 416곳)는 동을 150m 격자로 묶은 지점(약 2,700곳)마다 조회한다(`scripts/kakao_dong.py`).
캐시는 30일이 지나면 만료되므로, **매달 새로 받으면** 대표좌표 2,860곳 + 동별 2,700곳을 다시 부른다.

| 날 | 대상 | 호출(대략) |
|---|---|---|
| 1일차 | 편의점 + 슈퍼 | 약 5~6만 |
| 2~3일차(자정 이후) | 카페(브랜드 10종 키워드 검색) | 약 9만 — 하루 한도에 걸려 멈출 수 있음, 다음 날 같은 명령으로 이어감 |

```bash
set -a; . <.env>; set +a
CLUSTEAD_BASELINE_ONLY=convenience,mart python -m scripts.build_all_baselines   # 1일차
CLUSTEAD_BASELINE_ONLY=cafe python -m scripts.build_all_baselines              # 2일차
```
- 캐시를 새로 받지 않고 지난 값을 그대로 쓸 때(좌표·마스터만 바뀐 달)는 `CLUSTEAD_KAKAO_CACHE_TTL=0` 을 붙여 하루에 다 돌려도 된다.
- **API 실패가 한 번이라도 나면 빌더가 멈춘다**(빈 결과가 '0곳'으로 기록되는 사고 방지). 한도면 다음 날 같은 명령을 다시 돌린다. 이미 받은 조회는 캐시라 다시 부르지 않는다.
- 끝나면 `convenience_count_500m` 등 주요 칸이 전부 0이 아닌지 본다(12단계 validate도 잡는다).

## 11. 동별 정보

```bash
python scripts/vworld/build_dong_level.py     # 배정초·역·한강 나들목·학교군 → data/derived/vworld/dong_level.json
```
마스터·통학구역·학교군·한강 출입구가 바뀐 뒤에 돈다. 결과 페이지의 동별 주석(배정초 갈림 등)이 이걸 읽는다.

## 12. 백분위·DB·검사

```bash
python scripts/rebuild_data_full.py --skip-build     # enrich percentiles → baseline.db → validate
```
- validate `errors=0` 이면 통과(경고 40~50건은 기존 양성).
- 큰 CSV(medical 230MB)를 쓸 때 OneDrive 락으로 `PermissionError` 가 나면 그대로 다시 돌린다(파일은 안 깨짐).
- baseline.db 만 두고 CSV 백분위만 살리려면 `python scripts/enrich_baseline_percentiles.py`.

## 13. 홈 순위

```bash
python scripts/build_home_rankings.py --data-month YYYY-MM \
  --source-dates outputs/clustead-home-billboard/source_dates.json \
  --previous <1단계 백업>/derived/home_rankings.json \
  --prev-master <1단계 백업>/seoul_apartments.csv \
  --prev-medical <1단계 백업>/baseline/medical_baseline.csv
```
- `--data-month` 는 전월. `source_dates.json` 의 수집일을 이번 달 근거로 고친다(추론 금지, 파일 note 참고).
- `--previous` 계열을 빼면 "직전 달과 비교"가 미비교로 나온다.

## 14. 격자 지도

```bash
python scripts/build_grid_index.py     # 약 40초
python scripts/precompute_grid.py      # 약 5분(서버 부하 대책의 핵심 — 빼먹지 말 것)
python scripts/snapshot_grid.py "YYYY년 M월 정기갱신"
```
신규 단지가 격자에 들어간다(2026-10 기준 오래 재생성하지 않아 어긋나 있었다).

## 15. 기준월 표기

- `templates/_legal_footer.html` "데이터 기준: YYYY년 M월 (정기 갱신)"
- 홈 전광판은 13단계 `--data-month` 를 따른다.
- 블로그·문서에 적힌 비교 단지 수(예: 2,860곳)도 바뀌면 같이 고친다.

## 16. 검증(배포 전)

1. **변경 범위**: 백업 대비 baseline 원시 지표가 바뀐 단지가 이번 달 원천·마스터 변화로 설명되는지.
   설명 안 되는 대량 변경은 비결정성(동점 순서 등)이나 사고다. 2026-10-10 `verify_rebuild*.py` 참고.
2. **0 붕괴**: 주요 count 칸이 전 단지 0이 아닌지(카카오 3종, 함정 3).
3. **골든**: `python tests/snapshot_result.py check` → 차이를 하나씩 읽고, 의도한 변화면 `save`.
4. **테스트**: `python -m pytest -q tests`(약 3~7분, 2,860개 페이지 렌더 포함).
5. **화면**: 헬리오시티·파크리오·은마·신규 단지 1곳·재건축 301 1곳·통용명 1곳을 미리보기로 연다.

## 17. 배포

DEPLOY.md 6장과 같다. 이번 달 순서(디스크 사고를 피하는 순서):
1. 코드: 서비스워커 `static/sw.js` 의 `CACHE_VERSION` 을 올리고(필요하면 `style.css?v=`), 커밋·`git push origin main`.
2. 서버 디스크 확보(여유 1.8GB 이상): `docker builder prune -af`, `apt-get clean`, 필요하면 옛 커널 정리.
3. 보낼 파일 고르기: `python scripts/verify_deployed_data.py` → "다름" 목록이 곧 보낼 목록.
4. 스테이징·전송:
   ```bash
   S=<스크래치패드>; cd C:/Users/hyr19/clustead-main
   md5sum <파일들> > $S/deploy.md5; tar --force-local -czf $S/deploy.tgz <파일들>
   ssh -i ~/.ssh/clustead_deploy root@211.188.48.124 "rm -rf /root/_stage && mkdir -p /root/_stage"
   scp -i ~/.ssh/clustead_deploy $S/deploy.tgz $S/deploy.md5 root@211.188.48.124:/root/_stage/
   # 서버: 풀고 md5sum -c → mv -f 로 /root/clustead/<경로> 교체 → chown 10001:10001 → restart app → rm -rf _stage
   ```
   detail_index 는 폴더째 교체(고아 파일 제거).
5. `docker compose -f docker-compose.app-only.yml restart app` → healthz 200(2~10분, 느린 워밍업은 멈춤이 아님).
6. 코드: 서버 `git pull origin main` → `setsid nohup docker compose ... build app &` → `up -d app` → healthz → `docker image prune -f`.
7. `python scripts/verify_deployed_data.py` 전 항목 일치, 화면 확인(16단계 5번 단지들).
8. 사용자: Cloudflare "Purge Everything".

## 18. 사후

- AI 검색(feature/ai-search, Codex) 지역·단지 목록: 신규 동·단지, 재건축·통용명 반영 여부를 Codex에 알린다.
- 블로그 게시글 숫자·등급이 사이트와 달라졌는지(단지분석 글).
- 이 문서 7장 기록에 한 줄 남기고, 새 함정은 아래 함정 모음에 더한다.

---

## 함정 모음

1. **`PYTHONIOENCODING=utf-8` 금지(7단계)** — update_data_pipeline 이 자식 출력을 cp949로 읽어 UnicodeDecodeError. `env -u PYTHONIOENCODING`.
2. **tar 경로** — `C:/...` 는 원격 호스트로 해석된다. 항상 `tar --force-local`. OneDrive 락을 피하려면 스크래치패드로 복사한 뒤 묶는다.
3. **카카오 0 붕괴** — 키 없음·한도·캐시 만료가 겹치면 빈 결과가 '0곳'으로 기록되고 빌더는 성공으로 끝난다. 빌더 첫 단지 프리플라이트 + API 실패 시 중단으로 막아 두었다. 그래도 12단계 validate와 0 붕괴 확인은 한다.
4. **rawdata 재빌드 중단 시 등급 전부 D** — percentile 칸이 빠진 CSV가 남는다. `enrich_baseline_percentiles.py` 로 복구.
5. **배포 누락** — CSV를 직접 읽는 baseline(subway·cctv·convenience·mart·cafe·school_zone)과 실거래 mapping 을 빠뜨린 적이 있다. verify_deployed_data 목록을 따른다.
6. **`.new` 로 올리고 교체를 빠뜨림** — md5까지 맞추고 mv를 안 했다. 교체 후 서버 경로에서 md5 재확인.
7. **코드와 데이터 따로 배포** — DB 인덱스·칸이 바뀌면 코드도 같이 나가야 한다.
8. **서버 디스크 100%** — 데이터를 풀어 둔 채 빌드하다 찼다. 데이터 교체 → restart(옛 DB FD 해제) → 빌드 순서.
9. **미리보기 서버가 DB 잠금** — 12단계 전 끄기.
10. **동점·집합 순서 비결정성** — set 순서로 고르면 빌드마다 값이 바뀐다(버스 최근접 정류장, 학원 목록 순서). 빌더에 동점 규칙을 둔다.
11. **이름만 보고 재건축 후속 단지 판정 금지** — 신반포15차→아크로리버파크 오판 사례. 옛 위치에 지금 서 있는 단지로 판정.
12. **압구정 한양처럼 K-apt 단지 번호 ≠ 현장 차수** — 실거래·카카오로 실제 자리를 확인.
13. **/admin/ranking-debug 는 서버 워커를 죽인다** — 검증에 쓰지 않는다.

---

## 갱신 기록

| 월 | 날짜 | 담당 | 메모 |
|---|---|---|---|
| 2026-09 기준 | 2026-10-01 | Claude | 신규 7곳, 실거래 529,619행. 마스터 미리보기 누락 사고 → 3장 신설 계기 |
| (보정) | 2026-10-10~11 | Claude | 좌표 92곳 수정, 재건축 23·중복 3 정리, 통용명 71, 동별 등급 11종, 브이월드 원천 전환 |

# Clustead

서울시 아파트 단지 주변 **생활 인프라**를 서울시 전체와 비교해 점수화하는 Flask 웹서비스.
(브랜드: Clustead = Cluster + Stead, clustead.com)

집값·브랜드가 아니라 *실제로 누리는 생활 인프라*(교통·생활편의·의료·교육·안전·문화·상권 등)를
**서울시 상대평가(percentile)** 로 평가한다. 비싼 단지라고 점수가 높지 않으며, 사용자가 설정한
가중치(선호도)에 따라 추천 단지가 달라진다.

---

## 홈 전광판 개편 — 사용자 확인이 필요한 결정

아래 네 항목은 구현 전에 기록한 질문이며 아직 확정되지 않았다. 로컬 검토를 위한
임시 기본값만 적용한다. `outputs/clustead-home-billboard/compute_home_preview.py`의
집계 대상·반경·필터·동률 정렬은 변경하지 않는다.

1. **기존 d3 그래프를 전광판 아래에 둘까요, `/graph` 별도 메뉴로 둘까요?**
   임시로 별도 `/graph` 메뉴에 보존한다. `CLUSTEAD_HOME_GRAPH_ENABLED=0`이면
   메뉴와 경로를 끈다. `CLUSTEAD_HOME_BILLBOARD_ENABLED=0`이면 기존 홈으로 돌아간다.
2. **휴대폰도 전광판 홈을 볼까요, 기존처럼 Explore로 보낼까요?**
   개편안은 모바일 접근성과 검색의 동일 콘텐츠 노출을 위해 새 홈을 기본으로 한다
   (`CLUSTEAD_HOME_MOBILE_ENABLED=1`). `0`이면 기존 Explore 이동을 복원한다.
   설정이 `0`인 환경의 로컬 시안 검토는 `/?home=billboard`로 이동을 우회한다.
3. **카카오 로컬 데이터의 스세권·편세권 순위를 공개할까요?**
   재가공·순위 공개 가능 여부와 사용자 기본값 결정 전까지
   `CLUSTEAD_HOME_KAKAO_RANKINGS_ENABLED=0`으로 홈·개별 페이지·사이트맵에서 제외한다.
   검토 후 `1`로 켤 수 있다. 이 설정은 원본 데이터나 집계 정의를 바꾸지 않는다.
4. **순위 URL을 `/rankings/<slug>`로 하고 TOP 몇 개를 공개할까요?**
   임시로 해당 URL과 TOP 30을 사용한다. `CLUSTEAD_HOME_RANKING_PAGES_ENABLED=0`이면
   순위 페이지·전체 보기 링크·사이트맵 등록을 끈다. `CLUSTEAD_HOME_RANKING_LIMIT`은
   20~50 범위로 설정한다. 홈 TOP 5와 산정 정의는 그대로 유지한다.

### 개편안: 질문에 답하는 생활 인프라 전광판

Clustead의 강점은 여러 원천의 단지 좌표·시설 위치·법정동 주소·거래 조건을
연결해 **같은 기준의 비교 결과**를 만드는 데 있다. 홈은 이 결과를 질문으로
발견하고, 숫자로 비교하고, 근거를 확인한 뒤 단지 탐색으로 이어지는 입구다.

| 영역 | 사용자에게 하는 일 | 읽을 수 있는 콘텐츠 |
|---|---|---|
| 소개·집계 범위 | 어떤 데이터인지 바로 이해 | 기준월, 단지 수, 구 수, 집계 방식 |
| 전광판·질문 목차 | 지금 궁금한 질문을 발견 | 1위 이름·숫자·반경·주제별 순위 링크 |
| 학원가와 동네 | 단지 반경과 법정동을 구분해 비교 | 단지 TOP 5, 동 TOP 5, 구별 25개 동 |
| 가격과 이동 | 여러 조건을 함께 만족하는 곳 탐색 | 가격·세대수·역 조건, 학원 수, 지하철 노선 |
| 매일의 생활 | 가까운 시설과 주변환경 확인 | 편의·의료·유흥주점 거리 (공개 설정 적용) |
| 월간 기록·숫자 읽는 법 | 변화와 숫자의 한계 이해 | 스냅샷 비교 여부, 기준 설명, 질문·답 |
| 개별 순위 페이지 | 답을 자세히 확인하고 인용 | 완결된 답문장, TOP N, 전체 산정 기준·출처 |

본문·숫자·링크를 서버 렌더링하고, 모바일에도 같은 정보를 제공한다. 모든 주제를
관심사별 앵커로 연결하며 JS 필터로 숨기지 않는다. 홈페이지 CollectionPage와
순위 ItemList는 화면의 내용과 URL에 맞춘다. canonical은 쿼리 없는 주소이고
사이트맵의 홈·순위 갱신일은 해당 JSON 산출일을 사용한다.

이 방향은 [Google의 AI 검색 가이드](https://developers.google.com/search/docs/appearance/ai-features)의
읽을 수 있는 텍스트, 내부 링크, 화면과 일치하는 구조화 데이터 원칙을 따른다.
별도의 AI 전용 문서나 특수 스키마를 붙이는 것을 목표로 삼지 않는다.
검색 노출·유입 증가는 아직 측정하지 않았으며 보장하지 않는다. 공개 후에는
홈→순위→단지 이동, 모바일 이탈, 순위 URL의 검색 노출·클릭을 비교한다.

### 로컬 실행과 화면 확인

이 기능은 `main`에서 만든 별도 `feature/home-billboard` worktree에서 개발한다.
원래 `feature/ai-search` 체크아웃과 원본 데이터는 변경하지 않는다. 인계 자료는
`outputs/clustead-home-billboard/`에 원문 그대로 보관했다. 원본 재현 스크립트의
`REPO`는 인계 당시 절대 경로이며, 새 산출기는 `--data-dir`로 경로를 받는다.

```powershell
# 별도 worktree에서 실행. data는 원본 데이터 폴더를 가리키는 junction이다.
# 결과는 Git에서 제외한 로컬 폴더에 저장하므로 원본 data는 읽기만 한다.
python scripts/build_home_rankings.py --data-month 2026-09 --source-dates outputs/clustead-home-billboard/source_dates.json --output outputs/local-home/home_rankings.json
$env:CLUSTEAD_HOME_RANKINGS_PATH = 'outputs/local-home/home_rankings.json'
$env:CLUSTEAD_ANALYTICS = '0'
$env:CLUSTEAD_KAKAO_RESULT_MODE = 'off'
python -m flask --app app run --host 127.0.0.1 --port 5057 --no-reload
```

- `/`: 전광판과 주제별 TOP 5. 모바일 검토는 `/?home=billboard`.
- `/graph`: 기존 d3 탐색 화면. `/explore`, `/compare`는 기존 메뉴로 연결.
- `/rankings/academy-apartments`, `/rankings/academy-neighborhoods`: 학원 순위.
- `/rankings/value-transit-academy`, `/rankings/subway-lines`: 조합·지하철 순위.
- `/rankings/quiet-large-complexes`, `/rankings/emergency-facilities`: 대단지·응급실 순위.
- `/rankings/district-academy-winners`: 구별 1위 동 전체 25개(구 이름순).
- `/rankings/monthly-changes`: 저장된 신규 단지·배정초 변경 목록.
- `/rankings/starbucks`, `/rankings/convenience-stores`: 카카오 순위를 켰을 때만 제공.

설정 예시는 `.env.example`에 있다. JSON은 경로별 프로세스 캐시로 한 번 읽고,
파일 누락·스키마 오류 시 홈에 준비 중 상태를 표시한다. 갱신 후 앱 프로세스를
재시작해야 한다. 서버 요청 중 CSV를 열거나 순위를 다시 계산하지 않는다.

### 월간 갱신 절차

기존 데이터 파이프라인을 완료한 뒤 아래 한 줄을 추가한다. `--data-month`는
게시 기준월이고, `--source-dates`에는 해당 갱신의 출처·실제 수집일을 기록한다.
이 저장소의 `source_dates.json`은 이번 인계 데이터의 근거 기록이므로 다음 달에
날짜만 일괄 치환하지 않는다. 거래 계약 기간도 실제 요약 집계 범위를 확인한다.

```bash
python scripts/build_home_rankings.py --data-month YYYY-MM --source-dates path/to/current-source-dates.json --previous path/to/previous-home_rankings.json
```

기본 출력은 `data/derived/home_rankings.json`이다. 직전 JSON의 단지 코드·배정초
원문 스냅샷으로 차이를 계산하고 결과 자체도 저장하므로 웹서버에 지난 파일을
보관할 필요는 없다. 같은 기준월 재실행은 저장된 월간 차이를 유지한다.
최초에는 `--prev-master`와 `--prev-school`로 직전 CSV를 각각 지정할 수 있다.
비교 자료가 없는 항목은 미비교로 명시하며, 0건으로 표시하거나 시안의 변경 목록을
현재 계산 결과로 간주하지 않는다. 원본 CSV/DB를 재생성하거나 수정하지 않는다.

`scripts/verify_deployed_data.py`의 배포 대상에 산출 JSON을 포함했다.
`python scripts/verify_deployed_data.py --list`는 서버 접속 없이 목록 self-check를
실행한다. 이번 작업에서는 push·배포·Cloudflare 설정 변경을 하지 않는다.

### 시안과 달라진 점

- 숫자·산정 기준·전체 보기 링크·전광판의 모든 주제를 Jinja로 서버 렌더링한다.
- 자동 회전은 마우스·키보드 포커스·수동 일시정지·동작 줄이기 설정에 대응한다.
  JS가 없으면 산정 기준을 본문에 펼쳐 표시한다.
- 질문 목차·관심사별 섹션·1위 강조와 가까운 출처 표시로 읽는 순서를 만든다.
  개별 순위는 기준월·대상·숫자를 포함한 한 문장 답으로 시작한다.
- 카카오 순위는 임시로 비공개이며, 그래프와 모바일 진입은 위 설정을 따른다.
- 신고 평균이 10억 미만인 조건을 반올림으로 혼동하지 않도록 조합 가격을 만원으로
  표시한다. 계산 값·필터·정렬은 원본과 같다.
- 동률의 마지막 처리(원본 입력순)와 법정동 미확인 제외 수를 명시한다.
  유흥주점 0곳은 반경 500m 조건으로 표시하며 소음 수준으로 해석하지 않는다.
- 수집일과 원천 갱신일을 구분한다. 확인할 수 없는 수집일은 기록 없음으로 표시한다.
- 순위 페이지는 임시 TOP 30(20~50 설정), 홈은 TOP 5이며 구별 동은 전체를 표시한다.

검증 명령:

```bash
python -m pytest tests/test_home_rankings_builder.py tests/test_home_billboard.py tests/test_correctness.py
python tests/snapshot_result.py check
python scripts/verify_deployed_data.py --list
```

---

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env        # 키 채우기 (아래 환경변수 참고)
python app.py               # http://127.0.0.1:5000
```

> 앱은 import 시점에 `data/` 의 베이스라인 CSV를 전부 메모리에 적재한다(현재 ~9초).

### 환경변수 (`.env`)

| 변수 | 용도 |
|---|---|
| `KAKAO_JAVASCRIPT_KEY` | 결과 페이지 지도(JS SDK) |
| `KAKAO_REST_API_KEY` | POI 검색(REST) |
| `SEOUL_OPEN_DATA_KEY` / `PUBLIC_DATA_SERVICE_KEY` | 데이터 수집 파이프라인 |

런타임 토글(선택):

| 변수 | 기본 | 설명 |
|---|---|---|
| `CLUSTEAD_KAKAO_RESULT_MODE` | (fallback) | `off`=결과 페이지 Kakao 호출 안 함, `all`=전 카테고리, 미설정=cafe/convenience/mart만 |
| `CLUSTEAD_KAKAO_CACHE` | `1` | Kakao POI 캐시 사용(`0`=끔) |
| `CLUSTEAD_KAKAO_CACHE_TTL` | `2592000`(30일) | 캐시 TTL(초) |
| `CLUSTEAD_PRELOAD_VERBOSE` | `0` | 적재 로그 출력 |
| `CLUSTEAD_DEBUG` | `0` | 디버그 로그 |

---

## 구조

```
app.py                  라우트 + 카테고리별 결과 조립 (대형)
services/
  preload_service.py    CSV 적재 + 베이스라인 인덱스(복합키 name,gu,dong)
  ranking_service.py    추천/가중점수 — baked 점수를 단일 정본으로 사용
  baseline_service.py   실시간 POI 개수를 베이스라인 분포에 위치(mid-rank)
  poi_service.py        카테고리 요약/도메인 구성
  kakao_local_service.py Kakao POI 검색 + 캐시(메모리+디스크)
  transaction_service.py / insight_service.py / geo_service.py
scripts/
  baseline_metric_config.py   카테고리별 metric/방향(HIGHER/LOWER_BETTER) 정본 config
  build_*_baseline.py         원천 데이터 → 베이스라인 CSV
  build_all_baselines.py      baseline_config.BASELINE_JOBS에 등록된 전체 베이스라인 일괄 실행
  enrich_baseline_percentiles.py  베이스라인에 *_seoul_percentile / *_seoul_score 컬럼 굽기
  validate_baselines.py       검증
templates/  result.html(메인) 등
static/     style.css, script.js
data/        CSV/캐시/거래내역 (1.6GB, git 미추적 — .gitignore)
tests/       test_correctness.py, snapshot_result.py
```

### 점수 산출 (단일 정본)

1. `scripts/build_*_baseline.py` 가 단지별 metric(예: 500m 내 카페 수)을 계산해 베이스라인 CSV 생성.
2. `enrich_baseline_percentiles.py` 가 `BASELINE_METRIC_CONFIG.primary_metric` 기준으로
   **mid-rank percentile**(동점은 0.5로 계산)과 `100 - percentile` 점수를 CSV에 컬럼으로 굽는다.
   방향(`HIGHER_BETTER`/`LOWER_BETTER`)이 점수에 반영된다 — 유흥처럼 적을수록 좋은 항목은 적을수록 고득점.
3. 런타임은 이 **baked 점수**를 읽는다. `ranking_service`(추천·가중점수)와 결과 카드가 같은 값을 사용.

### 데이터 파이프라인 재생성

```bash
python -m scripts.build_all_baselines        # 베이스라인 재생성
cd scripts && python enrich_baseline_percentiles.py   # 점수/percentile 재-bake
python scripts/validate_baselines.py          # 검증
```

`scripts.build_all_baselines`는 전체 baseline 재생성의 정본 진입점이다. 새 `build_*_baseline.py`
스크립트를 추가하거나 percentile/validation 대상 baseline을 추가할 때는 반드시
`scripts/baseline_config.py`의 `BASELINE_JOBS`에도 등록해야 한다.

---

## 테스트

```bash
python tests/test_correctness.py     # 정합성(매칭·점수·캐시) — "옳음" 검증
python tests/snapshot_result.py save # /result HTML 골든 스냅샷 캡처
python tests/snapshot_result.py check# 리팩토링 후 바이트 동일성 검증
```

- **test_correctness.py**: 동명 단지 매칭, mid-rank 점수, 랭킹=baked 일치, Kakao 캐시 동작을 단언.
- **snapshot_result.py**: Kakao off로 결정적 렌더링한 9개 단지 HTML을 고정. 리팩토링 안전망.
  (골든 HTML은 `data/`처럼 gitignore — `save`로 재생성)

---

## 남은 기술 부채 (로드맵)

`docs/REFACTOR_LOG.md` 참고. 요약:

- **P2 유지보수성**: `build_X_info`/`build_X_map_pois`/`build_X_category_summary` 트리오(13×) 복붙,
  특수 apply 6개(subway/bus/medical/ev/hangang/school) 미통합, `/result` 갓-함수(~350줄).
- **점수 통합 잔여**: cctv/convenience/mart/cafe 카드는 아직 실시간 Kakao 개수를 사용(나머지는 baked).
- **확장성**: 전 데이터 메모리 적재(1.6GB) → 전국 확장 시 DB(DuckDB/SQLite) 전환 필요.
- **죽은 코드**: `app.calculate_personal_score`, `baseline_service.get_subway_percentiles`.

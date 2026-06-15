# Clustead

서울시 아파트 단지 주변 **생활 인프라**를 서울시 전체와 비교해 점수화하는 Flask 웹서비스.
(브랜드: Clustead = Cluster + Stead, clustead.com)

집값·브랜드가 아니라 *실제로 누리는 생활 인프라*(교통·생활편의·의료·교육·안전·문화·상권 등)를
**서울시 상대평가(percentile)** 로 평가한다. 비싼 단지라고 점수가 높지 않으며, 사용자가 설정한
가중치(선호도)에 따라 추천 단지가 달라진다.

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
| `LIVEFIT_KAKAO_RESULT_MODE` | (fallback) | `off`=결과 페이지 Kakao 호출 안 함, `all`=전 카테고리, 미설정=cafe/convenience/mart만 |
| `LIVEFIT_KAKAO_CACHE` | `1` | Kakao POI 캐시 사용(`0`=끔) |
| `LIVEFIT_KAKAO_CACHE_TTL` | `2592000`(30일) | 캐시 TTL(초) |
| `LIVEFIT_PRELOAD_VERBOSE` | `0` | 적재 로그 출력 |
| `LIVEFIT_DEBUG` | `0` | 디버그 로그 |

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
python -m scripts.validate_baselines          # 검증
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

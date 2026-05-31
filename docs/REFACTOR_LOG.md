# LiveFit 감사 & 리팩토링 로그

2026-05-29 CTO 종합 감사 후 수행한 작업 기록. 모든 변경은 git 커밋으로 추적되며,
점수/매칭 로직은 `tests/`로 보호된다.

## 감사 요약 (시작 시점)

종합 완성도 ~45/100. 가장 위험했던 것:

1. **오(誤)단지 표시** — `get_apartment`이 부분 문자열 + 첫 매치, 베이스라인 인덱스가 이름 단독 키.
   서울에 동명 단지가 다수(베이스라인 9건, 마스터 9건) → 남의 단지 데이터를 표시.
2. **점수 3중화 + 동점 왜곡** — percentile을 enrich(baked)/ranking/baseline_service 세 곳에서
   따로 계산(서로 다른 metric). 동점을 `>=`/`<=`로 세어 제로팽창 분포에서 점수 붕괴
   (유흥 0개 단지가 30점/'부족' — 철학과 정반대).
3. **성능** — `build_apartment_index` O(N²)로 부팅 17초; `/result`마다 Kakao 동기 호출 3회.
4. **테스트 0개, git 미사용**(폴더 복사로 수동 백업).

## 변경 이력 (커밋 순)

| 커밋 | 분류 | 내용 |
|---|---|---|
| `198cc58` | chore | git init, `data/`(1.6GB) gitignore — 코드만 추적 |
| `28a0676` | **P0** | `get_apartment(name,gu,dong)` 정확매칭 + 복합키 인덱스. 오단지 버그 박멸. 미존재 시 404 |
| `c7eb4ec` | **P1** | 동점 mid-rank 보정(3 시스템 일괄) + `build_apartment_index` O(N²)→O(N). 부팅 17→8.7초 |
| `becc1d1` | **P1** | ranking을 baked 점수 단일 정본으로 통합. 커버리지 9→16 카테고리 |
| `e8dbee5` | test | 골든마스터 하네스(9개 단지, Kakao off, 결정적) |
| `1f809f9` | **P2** | `apply_baseline_category_to_ui` 헬퍼 추출 + 7개 마이그레이션. app.py 5919→5467줄 |
| `f11232a` | test | 정합성 단위테스트(매칭·mid-rank·랭킹=baked) |
| `40e4b7e` | UX | 결과 페이지 점수 의미 범례 + 메인점수 부라벨 |
| `ec19945` | **perf** | Kakao POI 캐시(메모리+디스크, 성공만 캐시) |

### 핵심 수치

- 부팅: **17초 → 8.7초**
- 랭킹 커버리지: **9 → 16** 카테고리
- nightlife=0 점수: **30 → 65**(제로질량의 중앙, 순서 보존)
- app.py: **5919 → 5467줄**
- 테스트: **0 → 11** 정합성 + 9 골든 스냅샷

## 검증 방법

```bash
python tests/test_correctness.py        # 정합성 (옳음 검증)
python tests/snapshot_result.py check    # 리팩토링 회귀 (바이트 동일)
```

## 남은 작업 (우선순위)

**P2 유지보수성 (사용자 영향 없음, 작업량 큼)**
- apply_X 통합: **10/13 완료**(commercial, nightlife, academy, culture, bike, shopping,
  fire-station, hangang, ev_charger, school). 헬퍼 `apply_baseline_category_to_ui`는
  anchor/insert_position(after|before)/poi_count_mode(increment|set)/domain_template 지원.
  **의도적 제외 3개**(억지 통합 시 특수 파라미터만 늘고 위험):
  - subway: 최상단 prepend(insert 0), summary 없을 때 strip 안 함, 도메인 라벨 fallback 매칭
  - bus: 이중 키(bus/bus-baseline), tag 키가 bus-baseline, 도메인을 subway 포함여부로 매칭
  - medical: 다중 요약(여러 summary 생성/삽입)
- build_X 트리오 공통화: **취약 중복 블록만 추출 완료**(줄수 감소 아님이 목표).
  - `parse_baseline_items(row, col, float_distance)` — items_json 파싱+정렬, 13개 전부(예외 포함) 재사용. 커밋 17f8d7e.
  - `build_simple_map_pois(info, …, label_fn, subtype_fn)` — 표준 map_pois 8개. subway/bus/medical/ev 제외. 커밋 de0eaf3.
  - `build_count_chips(chip_sources)` — count→chip 루프 8개. 커밋 4a53e17.
  - **`build_baseline_info` 전체 통합은 보류(결정).** 표준 6개라도 info의 *return dict* 가 카테고리별로 다름:
    count 키 이름(station_count_500m / hangang_count_3km / commercial_count_1km …),
    nearest 키(bike=nearest_station vs 나머지=nearest_name), extra 필드(nearest_facility_tags,
    nearest_type, alley/developed/market/tourism_count …), label 변환(prefix/park_name/strip/full_label/none).
    downstream(summary·apply)이 이 카테고리별 키를 직접 읽으므로, spec로 묶으면 return dict를
    config-DSL로 옮기는 셈 → 가독성 악화(유지보수성 기준에서 손해). summary 보류와 같은 이유.
- `/result` 갓-함수(~350줄) → 카테고리 등록 루프화.

**점수 통합 잔여**
- cctv/convenience/mart/cafe 카드는 아직 `baseline_service`로 실시간 Kakao 개수를 사용.
  나머지 14개처럼 baked로 흡수하려면 `build_X_category_summary` 추가 필요(위 트리오 작업과 함께).

**확장성 (전국 확장 시)**
- 전 데이터 메모리 적재(1.6GB) → DuckDB/SQLite 전환. percentile은 SQL 윈도우 함수로.
- `data/` 를 코드 리포에서 완전 분리(DVC 등).

**위생**
- 죽은 코드 제거: `app.calculate_personal_score`, `baseline_service.get_subway_percentiles`.
- 베이스라인 일부 CSV의 깨진 컬럼명/인코딩(cp949 혼재) 정리.

## 2026-06-01 데이터 빌드 정본 보정

- `scripts.build_all_baselines`가 README의 "전체 baseline 일괄 실행" 설명과 다르게
  `bus`, `school_zone`, `medical`, `lifestyle_food`를 실행하지 않던 문제를 확인.
- 네 builder를 `scripts/baseline_config.py`의 `BASELINE_JOBS`에 등록해 전체 재빌드 대상과
  percentile/validation 대상의 불일치를 제거.
- `cafe` 빌더가 `cafe_access_score_raw`를 직접 생성하도록 맞춰 별도 보정 스크립트 없이도
  `build_all_baselines -> enrich -> validate` 흐름이 통과하도록 정리.
- rawdata 다운로드 없이 기존 rawdata와 보강된 아파트 좌표 기준으로 baseline 재생성 및 검증.

> 원칙: 빅뱅 금지. 리팩토링은 반드시 골든마스터 `check` 통과를 확인하며 한 번에 하나씩.

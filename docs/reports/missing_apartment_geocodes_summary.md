# 좌표 누락 단지 지오코딩 보강 — 요약

`data/`는 git 미추적이므로, 좌표 보강은 **추적되는 패치 구조**로 남긴다.

## 배경
`data/apartment/seoul_apartments.csv`(master) 2,873행 중 **40행이 좌표(좌표X/Y) 빈값**.
좌표 의존(거리·반경 POI) 베이스라인이 이 40개를 제외해 행수 불일치(2,833 vs 2,873) 발생.

## 지오코딩 (Kakao 주소 API, precision 우선)
`kapt도로명주소` 기준 지오코딩 후 신뢰도 분류:

| confidence | 건수 | 처리 |
|---|---|---|
| HIGH | 28 | 자동 반영 (구+동 일치·단일 결과·도로명주소 보유·서울 경계 내) |
| MEDIUM | 1 | 수동 검수 |
| LOW (도로명주소 없음) | 11 | 수동 처리 |

## 추적 파일 (재현 가능)
- `scripts/manual_overrides/missing_apartment_geocodes_approved.csv` — HIGH 28건 승인 좌표
- `scripts/manual_overrides/missing_apartment_geocodes_manual_review.csv` — MEDIUM+LOW 12건
- `scripts/apply_missing_apartment_geocodes.py` — 승인 좌표를 master의 **빈 좌표만** 채움(멱등, `--apply` 필요)

## 적용 결과 (apply_missing_apartment_geocodes.py --apply)
- 빈 좌표 BEFORE: **40**
- 반영(채움): **28**
- 빈 좌표 AFTER: **12** (MEDIUM 1 + LOW 11)
- 중복키 영향: **0** (28개 키 모두 master에서 단일 행과 매칭)
- 멱등성: 재실행 시 0건 추가(기존 좌표 미덮어씀)
- 회귀: 9개 골든 0 diff, test_correctness PASS (28건은 골든 표본 밖)

## 재현 방법
```
python scripts/apply_missing_apartment_geocodes.py            # dry-run 보고
python scripts/apply_missing_apartment_geocodes.py --apply    # master에 좌표 기입
```

## 남은 작업
- 12건(MEDIUM 1 + LOW 11): master에 도로명주소가 없어 지번/명칭 기반 수동 지오코딩 필요.
- 28건을 거리 베이스라인에 반영하려면 베이스라인 재빌드 필요(범위/네트워크 영향은 별도 결정).

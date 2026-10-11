# v5 동 건물 매칭 파이프라인

단지 마스터(K-apt) 한 줄마다 실제 동 건물 윤곽을 붙여 `data/derived/vworld/complex_buildings_v5.jsonl` 을 만든다.
동별 등급(지하철·버스·교육환경·한강·공원·병원·약국·학원·편의점·카페·슈퍼)과 동별 정보(`build_dong_level`)가 모두 이 파일을 쓴다.
2026-10-09~10 세션에서 만들었고, 2026-10-12 저장소로 옮겼다(그 전에는 백업 폴더에만 있었다).

**언제 돌리나:** 매달은 아니다. 신규·재건축 단지가 20곳 넘게 쌓였거나 대단지가 새로 들어왔을 때.
v5 에 없는 단지는 자동으로 대표좌표 기준이 되므로 미루어도 화면이 깨지지는 않는다(docs/MONTHLY_UPDATE.md 6장).

**키:** `_paths.py` 가 저장소 `.env` → (워크트리면) data 가 가리키는 원래 폴더 `.env` → 환경변수 순으로 읽는다.
`VWORLD_API_KEY`(브이월드, 도메인 https://clustead.com 등록), `KAKAO_REST_API_KEY`.

**실행 위치:** 저장소 루트에서 `python scripts/vworld/pipeline/<파일>.py`. 산출물·캐시는 모두 `data/derived/vworld/`.

## 순서

| # | 스크립트 | 입력 → 출력 | 비고 |
|---|---|---|---|
| 1 | `collect_buildings.py` | 마스터 → `complex_buildings.jsonl` | 도로명주소 건물(LT_C_SPBD)을 주소·이름·근접으로. 이어받기 가능(이미 있는 단지 건너뜀) |
| 2 | `collect_buildings_pass2.py` | → `complex_buildings_v2.jsonl` | 1에서 못 찾은 단지 보완 |
| 3 | `kakao_fill.py` | v2 → `complex_buildings_v3.jsonl`, `kakao_fill_report.json` | 카카오 "OO아파트 101동" 장소로 동번호 |
| 4 | `kakao_fill2.py` | v3 → `complex_buildings_v4.jsonl` | 동번호 검증·충돌 보완 |
| 5 | `common_names.py` | v4 → `complex_common_names.json` | 현장 통용명(카카오·브이월드 건물명) |
| 6 | `collect_bldginfo.py` | → `bldginfo_apt.geojson` | 건축물정보(LT_C_BLDGINFO, 공동주택 `usability:=:02000`) 서울 전체. 오래 걸림 |
| 7 | `match_v5.py` | v4 + bldginfo + 캐시들 → `complex_buildings_v5.jsonl`, `match_v5_report.json` | SPBD + 건축물정보 + 좌표 지점 통합 |
| 8 | `exist_check.py` | v5 → `exist_cache.json` | 대장에만 남은 철거 건물(유령) 판정용 SPBD 겹침 |
| 9 | `point_match.py` | v5 → `point_cache.json` | 1~2동 주상복합: 단지명 장소·주소 좌표가 가리키는 건물. `--redo` |
| 10 | `match_v5.py` 다시 | 캐시 반영 → v5 | |
| 11 | `label_arbiter.py` | v5 → v5(덮어씀) | 동번호 충돌을 카카오로 판정 |
| 12 | `check_v5.py [N]` | 확인만 | 상태별 개수, 단지끼리 건물 공유(0이어야 함) |
| 13 | `last_trade.py` → `build_ledger.py` | → `last_trade.json`, `complex_status_ledger.json/csv` | 단지 상태 원장(normal·split_rental·rebuilt_old·rebuilding·alias…) |

그다음(저장소 쪽):
- `python scripts/vworld/coord_audit.py` → `coord_fix_candidates.py`(이 폴더) → 승인분을 `scripts/manual_overrides/wrong_apartment_geocodes_approved.csv`
- 원장의 rebuilt_old·rebuilding·alias 는 사람이 확인해 `complex_lifecycle_approved.csv`·`complex_common_names_approved.csv`
- 남의 건물을 잡은 단지는 `dong_buildings_rejected.csv`
- `python scripts/vworld/build_dong_level.py` → baseline 재생성(docs/MONTHLY_UPDATE.md 9~12장)

## 분석 도구
- `analyze_v5.py [N]`: diff(동 수 불일치) 표본
- `weak_check.py <단지목록.txt>`: 근거가 약한 단지를 건축물대장과 대조
- `building_match_report.py`: 주거동 판별 규칙(`residential`, `NON_RES`) — 다른 스크립트가 import

## 함정(2026-10 실전)
- `[가-하]` 정규식은 한글 전체를 잡는다 — 동 이름 글자는 명시 목록으로(kakao_fill2 의 LETTERS).
- 건축물대장에는 철거 건물이 남아 있다 → SPBD 겹침(8번)으로 유령을 거른다.
- 사용승인일이 같은 이웃 단지 건물이 섞인다 → 단지 윤곽(hull) 제한 + 다른 단지 소유 건물 제외.
- 후속 단지는 이름 유사도로 고르면 틀린다(신반포15차→아크로리버파크 오판). 옛 위치에 지금 서 있는 단지로(20년 이상 차이, 30% 이상 덮음).
- 마스터 단지명 앞뒤 공백 → strip.
- 재건축·중복으로 마스터에서 빠진 단지가 v5 에 남는다 — 분석 스크립트는 마스터에 있는 단지만 본다.

# scripts/vworld — 브이월드·카카오 기반 월간 갱신 보조 스크립트

| 스크립트 | 산출물 | 언제 |
|---|---|---|
| `coord_audit.py` | `data/derived/vworld/coord_audit.json` | 마스터 갱신 후. 대표좌표가 단지 건물에서 벗어난 곳을 찾는다(교정은 `scripts/manual_overrides/wrong_apartment_geocodes_approved.csv`) |
| `collect_hangang_access.py` | `data/derived/hangang_access_points.json` | 분기 1회 정도. 한강 나들목·경사로·계단 출입구(카카오) |
| `build_dong_level.py` | `data/derived/vworld/dong_level.json` | `complex_buildings_v5.jsonl`·통학구역·역 갱신 후. 결과 페이지 동별 주석·카드 |
| `../fetch_school_zones_vworld.py` | `data/school/zone/vworld_desch.geojson` | 매월(통학구역 원천) |
| `../build_park_source_vworld.py` | `data/park/vworld_parks.geojson` | 매월(공원 원천, LT_C_UPISUQ153 재수집 후) |

동 건물 매칭 v5(`complex_buildings_v5.jsonl`) 자체를 다시 만드는 파이프라인(SPBD·BLDGINFO 수집, 카카오 동번호, 매칭·원장)은
아직 저장소 밖 `C:/Users/hyr19/clustead-backups/vworld_pipeline_scripts/`(README 에 순서)에 있다. 마스터가 크게 바뀐 달에만 돌린다.

키는 환경변수 또는 저장소 `.env` 의 `KAKAO_REST_API_KEY`, `VWORLD_API_KEY`(이 워크트리에는 .env 가 없으니 원래 폴더 .env 를 로드해서 실행). baseline 빌더의 동별 계산 원칙은 `scripts/dong_points.py` 참고.

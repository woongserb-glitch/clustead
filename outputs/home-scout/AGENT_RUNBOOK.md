# 월간 홈 아이템 스카우트 실행 지시서

매달 데이터 갱신이 끝난 뒤, 배포 전에 실행한다. 목적은 데이터에 숨은 새 질문·순위·변화를 찾아 사용자에게 보고하는 것이다. 사용자가 선택한 제안만 별도 승인 범위에서 홈에 구현한다.

## 1. 작업 범위

- 보조 에이전트를 띄우지 않고 혼자 순서대로 진행한다.
- `scripts/scout_home_items.py`는 기존 파일을 읽고 `outputs/home-scout/YYYY-MM/`에만 결과와 비교용 사본을 쓴다. LLM·네트워크 호출은 없다.
- 원본 데이터 재빌드·수정, 푸시·배포, main 병합, Cloudflare 변경, 가격 등 기존 정의의 임의 변경을 하지 않는다.
- 사용자에게 한국어로 보고한다. “학군”이라는 표현을 쓰지 않는다. 학원 수를 교육 성과로 해석하지 않는다.
- 작업 A는 완료됐다. 가격은 기존 `home_price_trend.collect_trades()`·`build_price_trend()`만 호출한다. 가격 주제나 UI를 다시 구현하지 않는다.

## 2. 입력 준비

1. 현재 `data/`: 단지 마스터, baseline, 학원 주소 원본, 거래 마스터·매핑·국토부 매매 원본 엑셀, 현재 `derived/home_rankings.json`과 snapshot.
2. `--prev-dir`: 갱신 **전**에 보관한 폴더. `baseline/*_baseline.csv`와 `apartment/seoul_apartments.csv` 또는 루트의 `seoul_apartments.csv`가 있어야 한다. 폴더 이름만 보고 자료의 시점을 추정하지 말고 갱신 기록·메타데이터를 대조한다. `stage`·재빌드 후 사본을 직전 자료로 사용하지 않는다.
3. 직전 순위는 기본적으로 `outputs/home-scout/<직전 월>/home_rankings.json`을 읽는다. 다른 위치는 `--previous-rankings`로 지정한다. 직전 월 자료가 없거나 기준월이 다르면 **미비교**다.
4. 분석 DB는 별도로 받은 **서버 사본**만 `--analytics-db`로 지정한다. 옵션이 없거나 사본이 없으면 **미집계**다. 개발 PC의 `data/analytics/`는 옵션으로 지정해도 거부한다. 환경변수 `CLUSTEAD_ANALYTICS_DB`도 사용하지 않는다.

### 서버 분석 DB 사본 받기 — 사용자가 직접 수행

에이전트는 서버에 접속하지 않는다. 서버 운영자가 원본을 읽기 전용으로 열어 SQLite backup 기능으로 일관된 독립 사본을 만든다. WAL 모드의 실행 중 DB 파일 하나를 그대로 scp하면 최근 이벤트가 빠질 수 있으므로 아래처럼 사본을 먼저 만든다. 경로·계정·호스트는 실제 운영 환경에 맞게 사용자가 확인한다.

서버 운영자가 실행할 예시(Linux):

```bash
sqlite3 -readonly /actual/server/path/analytics.db ".backup '/tmp/home-scout-analytics-YYYY-MM.db'"
chmod 400 /tmp/home-scout-analytics-YYYY-MM.db
```

사용자가 개발 PC에서 실행할 예시(PowerShell):

```powershell
New-Item -ItemType Directory -Force outputs/home-scout/server-copies
scp USER@HOST:/tmp/home-scout-analytics-YYYY-MM.db outputs/home-scout/server-copies/analytics-YYYY-MM.db
Set-ItemProperty -LiteralPath outputs/home-scout/server-copies/analytics-YYYY-MM.db -Name IsReadOnly -Value $true
```

원본 권한·저널 모드는 바꾸지 않는다. 서버 임시 사본의 보관·삭제는 운영자가 관리한다. 사본 폴더는 Git에서 제외한다. 스크립트도 `mode=ro&immutable=1`과 `query_only`로 열어 DB와 WAL/SHM을 쓰지 않는다. WAL·journal이 남아 있는 사본은 미집계로 처리한다. 개인 방문자 식별자는 보고서에 저장하지 않는다.

인기 집계는 기준월 말일까지 30일(KST)의 `home_topic_click`·`ranking_view`다. `analytics_service.topic_interest()`와 같은 `COUNT(DISTINCT visitor_hash || '|' || day)` 정의를 쓴다. 과거 보고서의 재현성과 읽기 전용 연결을 위해 날짜를 고정한 별도 SELECT를 사용한다. 같은 방문자의 하루 반복은 1이며 날짜가 다르면 다시 센다. **노출 수나 30일 전체 순방문자 수가 아니다.** 사본 누락·조회 실패를 인기 0으로 바꾸지 않는다. 0~1 방문자-일인 질문은 노출 기회와 집계 시작일도 확인한다.

## 3. 실행

이 작업의 승인된 실행(서버 사본 없음):

```powershell
$env:PYTHONIOENCODING = 'utf-8'
python scripts/scout_home_items.py --data-month 2026-09 --prev-dir C:/Users/hyr19/clustead-backups/20261001
```

일반 월간 실행:

```powershell
python scripts/scout_home_items.py --data-month YYYY-MM --prev-dir C:/path/to/pre-refresh-backup --analytics-db outputs/home-scout/server-copies/analytics-YYYY-MM.db
```

기준월은 현재 `home_rankings.json`의 `data_month`와 같아야 한다. 다르면 실행이 멈춘다. 올바른 기존 사본을 `--rankings`로 지정하고, 스카우트 수행 중 재빌드하지 않는다. 테스트나 별도 자료 검토에는 `--data-dir`, `--output-root`를 쓸 수 있으나 data·백업·입력 파일 안으로 출력하는 경로는 거부한다(심볼릭 링크·junction 해석 후 검사).

2026-09 보고서는 10월 1일 갱신된 시설 자료와 갱신 전 백업을 비교한다. 이를 “9월에 개업·폐업한 시설”로 단정하지 않는다. 가격은 승인된 정의에 따라 2026-03~08 대 2025-09~2026-02이며, 2026-09 계약은 제외한다. 매매 직거래 판별용 원본 엑셀 조회에 시간이 걸릴 수 있다.

## 4. 산출물과 다음 달 비교

매 실행 시 해당 월 폴더에 다음 파일을 저장한다. 같은 입력으로 다시 실행하면 같은 결과가 나온다.

| 파일 | 내용 |
|---|---|
| `report.md` | 첫 화면 상위 10개, 펼쳐 보는 질문 제안·검증·전체 목록 |
| `candidates.json` | 모든 후보의 수치·영향 단지·근거 파일과 키·점검 상태, 인기 집계 |
| `home_rankings.json` | 현재 월 원본 순위 사본. 다음 달 TOP 5 비교의 기준 |
| `home_rankings.snapshot.json` | 원본 비교 snapshot 사본. 원본이 없으면 미보관 상태 기록 |
| `academy_address_counts.json` | 개원 중 입시/보습·수학·영어 학원의 원본 행 번호·지정번호·이름·주소·법정동과 집계. 지정번호 중복 제거, 주소 미확인 수 기록 |

이번 달 학원 변화 후보는 `academy_count_1000m`의 단지별 증가(1곳 이상)만 계산한다. 동별 증가 계산은 아직 하지 않는다. 다음 달에는 이번 주소 집계 사본과 동일 정의의 새 사본을 대조해 동별 변화 검토에 사용할 수 있다. 원천 주소·지정번호가 함께 있어 주소 변경과 중복을 검증할 수 있다.

후보는 영향 **고유 단지 수 내림차순**이다. 동률은 학원 증가 수, 가격 순위, 종류·제목·ID로 고정한다. 시설은 시설별 추가·소실 영향 단지, 신규 단지·가격·학원 증가는 각 단지 1곳이다. 동별 순위는 영향 단지 수를 임의로 추정하지 않는다. TOP 5 밖으로 나간 항목의 순위는 미상이다. 구별 1위 목록은 서울 전체 순위가 아니므로 TOP 5 비교에서 제외한다.

응급실 1km, 종합병원급 3km, 대형마트 3km, 지하철역 500m, 스타벅스 500m를 비교한다. 개수 컬럼이 요구하는 수만큼 가까운 항목을 고른다. 항목 목록이 부족한 단지는 제외하고 `invalid_current`·`invalid_previous`에 기록한다. 이름 공백을 제거하며 이전과 같은 코드·이름·구·동의 서비스 대상 단지만 비교한다. 추가·소실 후보는 실제 신설·폐업 확인 전까지 공개 확정 문구를 쓰지 않는다.

지하철은 양쪽 자료에 `build_subway_baseline.canonical_line()`·`station_key()`를 적용한다. 옛 개수만큼 항목을 선택한 **뒤** 같은 역을 묶어 노선 집합을 합친다. 서울역/서울, 경부선/1호선, 경원선 구간 차이를 새 역으로 세지 않는다. 역 묶음의 대표 좌표가 달라져 500m 경계를 넘더라도 다른 달의 넓은 역 목록에 이미 있는 역이면 신설·폐업 후보에서 제외한다. 제외 쌍 수는 `subway_existing_station_radius_changes_excluded`에 남긴다. 신규 노선·기존 역 접근성 변화는 이 후보의 범위 밖이다.

## 5. 상위 후보 원천 대조 — 매달 필수

다음은 실제로 밟은 비교 함정이다.

1. **기관명 띄어쓰기 변경.** 원천 데이터가 이름 띄어쓰기만 바꾸는 달이 있다(2026-10: 중앙보훈병원·한일병원·안암병원·양지병원). 공백을 빼고 비교한다.
   - 이를 안 하면 51곳이 106곳으로 부풀었다.
2. **단지 이름 변경.** 이름이 바뀐 단지(2026-10 목동성원 계열)는 직전 달 키가 없다. "직전 달에 없던 단지"는 변화 비교에서 뺀다.
3. **경계값 반올림.** 1km 경계에서 항목 거리(m 반올림)와 개수 컬럼이 1건 어긋난다. 개수 컬럼을 기준으로 삼는다.
4. **신고 기한.** 최신 월 실거래는 신고 기한 30일 때문에 일부만 들어 있다. 2026-09는 13,226건이고, 평월은 약 23,000~28,000건이다.

상위 10개 각각의 `evidence.file`·`key`·`record`·`column`을 원본과 직접 대조한다. `record`는 헤더를 제외한 CSV 논리 행 번호이고 실제 텍스트 줄 번호와 다를 수 있다. 기관/점포 이름·주소·좌표가 같은지, 동명 기관·누락 수집·좌표 정정으로 생긴 차이인지 확인한다. 영향 단지 목록은 중복 없이 세고, 경계 단지를 따로 확인한다. 수치 검증과 실제 개업·폐업 확인을 구분한다. 원천 조회나 외부 확인을 하지 않았다면 `source_confirmation`은 검증 대기로 남긴다.

신규 단지의 코드 추가를 실제 입주로 표현하지 않는다. 대단지는 1,000세대 이상·기준월 사용승인인 경우만 별도 표시하며 실제 입주일은 확인이 필요하다. 가격 후보는 같은 면적·기간별 건수·직거래 제외·매핑을 원천과 대조한다. 새 가격 정의를 만들지 않는다.

## 6. 사용자 보고와 승인

1. `report.md`의 상위 10개와 미비교·미집계 범위를 보여 준다.
2. 후보 중 질문 3~5개를 제안한다. 질문 문장, 1위 답 후보, 산정 기준(기준점·반경·방식·출처), 위험 요소를 붙인다. 반경처럼 해당하지 않는 기준은 줄을 생략한다. 근거가 부족하면 개수를 채우기 위해 제안을 만들지 않는다.
3. 새 변화 주제는 `CHANGE_KINDS`의 heading·icon·color·label·radius·empty·uncompared 설정도 제안한다. 제안된 아이콘 키는 현재 `_billboard_macros.html`의 `CHANGE_ICONS`에 존재한다. 실제 구현 시 필요한 아이콘이 달라지면 두 설정을 함께 검토한다.
4. 사용자 승인을 받은 제안만 빌더·서비스·템플릿에 구현한다. 보고서 생성 승인을 홈 자동 반영이나 배포 승인으로 해석하지 않는다.
5. 검증 명령은 `python -m pytest tests -q`다. 단지 상세 골든마스터를 갱신하지 않는다. 승인된 별도 배포가 끝난 뒤 운영 화면 수치와 보고서 수치를 대조한다.

코드 검증·원천 수치 검증 결과와 아직 사용자 판단이 필요한 내용을 구분해 최종 보고한다.

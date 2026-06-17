# Icon Mapping Validation

검증일: 2026-06-07

대상 파일: `docs/icon_mapping_proposal.json`

검증 기준: `https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{icon}.svg` 경로에 HTTP HEAD 요청을 보내 공식 Lucide SVG 존재 여부를 확인했습니다.

## 결과 요약

| 항목 | 수량 |
| --- | ---: |
| 최초 Lucide 후보 | 73 |
| 최초 유효 후보 | 70 |
| 최초 404 후보 | 3 |
| 교체 후 후보 | 73 |
| 교체 후 미검증/무효 후보 | 0 |

## 교체 내역

| 기존 후보 | 교체 후보 | 적용 위치 | 판단 |
| --- | --- | --- | --- |
| `circle-help` | `circle-question-mark` | 기타, 기타쇼핑 칩 | Lucide 공식 SVG가 없어서, 같은 의미의 유효한 물음표 원형 아이콘으로 교체 |
| `tooth` | `smile-plus` | 치과 칩 | Lucide 공식 SVG가 없어서, 치과/구강 관리 느낌이 가장 가까운 유효 아이콘으로 교체 |
| `waves` | `droplets` | 한강공원 카테고리/칩 | Lucide 공식 SVG가 없어서, 수변 의미를 유지하면서 수영장처럼 보이지 않는 유효 아이콘으로 교체 |

## 대체 후보 메모

- `circle-help` 대안으로 `badge-question-mark`, `ellipsis`도 유효하지만, 칩 안에서 가장 직관적인 `circle-question-mark`를 우선 추천합니다.
- `tooth` 대안으로 `smile`, `badge-plus`, `cross`도 유효합니다. 다만 `cross`는 의료 일반과 겹치고, `smile-plus`가 치과 맥락에 더 가깝습니다.
- `waves` 대안으로 `sailboat`, `waves-ladder`, `ship-wheel`도 유효합니다. `waves-ladder`는 수영장 느낌이 강해 한강공원에는 `droplets`가 더 안정적입니다.

## 이번 단계에서 제외한 것

- 브랜드 로고 파일 존재 여부와 라이선스/상표 사용 조건은 아직 확인하지 않았습니다.
- 실제 UI 파일에는 아이콘 변경을 적용하지 않았습니다.
- 지도 마커, 칩, 버튼 컴포넌트의 렌더링 방식은 다음 구현 단계에서 정리합니다.

## 다음 단계 제안

1. 브랜드 서브타입 로고 검증: 공식 BI, Simple Icons fallback, 모노그램 fallback 순으로 확인합니다.
2. `static/icons/` 구조 확정: `lucide/`, `brands/`, `generated/`처럼 역할별로 나눕니다.
3. 아이콘 레지스트리 구현: JSON 매핑을 앱에서 읽기 쉬운 Python/JS 공용 구조로 변환합니다.
4. Explore/Result에 작게 적용: 칩과 지도 토글부터 교체하고 시각 QA를 진행합니다.

# 2026-09 월간 홈 아이템 스카우트

총 **1,195개 후보**. 영향 단지 수가 큰 순서이며 첫 화면에는 상위 10개만 표시합니다.
시설 추가·소실은 데이터에서 발견한 후보입니다. 실제 신설·폐업은 검증 대기입니다.

| 순서 | 후보 | 영향 단지 |
|---:|---|---:|
| 1 | 서울고든병원 · 응급실 추가 후보 | 51 |
| 2 | 스타벅스 목동오목로점 · 스타벅스 소실 후보 | 9 |
| 3 | 스타벅스 강동경희대병원점 · 스타벅스 추가 후보 | 6 |
| 4 | 스타벅스 외대정문점 · 스타벅스 추가 후보 | 6 |
| 5 | 스타벅스 서초역라이프재단점 · 스타벅스 추가 후보 | 5 |
| 6 | 롯데캐슬헤론 · 1km 학원 8곳 증가 | 1 |
| 7 | 반포힐스테이트 · 1km 학원 8곳 증가 | 1 |
| 8 | 송파레이크파크 호반 써밋2 · 1km 학원 8곳 증가 | 1 |
| 9 | 송파레이크힐아파트 · 1km 학원 8곳 증가 | 1 |
| 10 | 송파위례리슈빌 · 1km 학원 8곳 증가 | 1 |

- TOP 5 변동: **미비교** — 직전 월 home_rankings.json 사본 없음
- 질문 인기: **미집계** — --analytics-db 서버 사본을 지정하지 않음
- 동 단위 학원 증가: 이번 달 미비교. 주소 집계 사본을 저장해 다음 달 비교 기준으로 사용합니다.
- 상세 수치·영향 단지·근거 행·점검 결과: [candidates.json](candidates.json)

<details>
<summary>질문 제안·산정 기준·위험 요소·변화 주제 설정</summary>

### 이번 갱신에서 주변 응급실 정보가 추가된 단지는?

1위 답 후보: 서울고든병원: 51개 단지, 가장 가까운 곳은 등촌태영(51m)

- 기준점: 단지 대표 좌표
- 반경: 직선거리 1,000m
- 방식: 동일 단지의 직전·현재 시설 목록을 이름 공백 정규화 후 비교, 개수 컬럼 우선
- 출처: 서울시 병의원 위치 정보

위험 요소: 데이터 추가·소실이며 실제 신설·폐업은 기관 공지와 원천 이력으로 확인해야 합니다. / 동명 기관·좌표 이동·수집 범위 변경 여부를 확인해야 합니다.

`CHANGE_KINDS` 제안(사용자 선택 후 구현, 아이콘은 기존 `CHANGE_ICONS` 키):

```json
{
  "color": "#e5484d",
  "empty": "이번 달 응급실 추가 후보가 없습니다.",
  "heading": "주변 응급실 추가 후보",
  "icon": "cross",
  "key": "emergency_added",
  "label": "응급실 추가 후보",
  "radius": "반경 1,000m",
  "uncompared": "직전 달 응급실 정보가 없어 비교하지 않았습니다."
}
```

### 이번 갱신에서 주변 스타벅스 정보가 소실된 단지는?

1위 답 후보: 스타벅스 목동오목로점: 9개 단지, 가장 가까운 곳은 목동성원(목동서로)(95m)

- 기준점: 단지 대표 좌표
- 반경: 직선거리 500m
- 방식: 동일 단지의 직전·현재 시설 목록을 이름 공백 정규화 후 비교, 개수 컬럼 우선
- 출처: kakao map 기준

위험 요소: 데이터 추가·소실이며 실제 신설·폐업은 기관 공지와 원천 이력으로 확인해야 합니다. / 동명 기관·좌표 이동·수집 범위 변경 여부를 확인해야 합니다.

`CHANGE_KINDS` 제안(사용자 선택 후 구현, 아이콘은 기존 `CHANGE_ICONS` 키):

```json
{
  "color": "#15803d",
  "empty": "이번 달 스타벅스 소실 후보가 없습니다.",
  "heading": "주변 스타벅스 소실 후보",
  "icon": "store",
  "key": "starbucks_removed",
  "label": "스타벅스 소실 후보",
  "radius": "반경 500m",
  "uncompared": "직전 달 스타벅스 정보가 없어 비교하지 않았습니다."
}
```

### 1km 안 학원 수가 가장 많이 늘어난 아파트는?

1위 답 후보: 롯데캐슬헤론: 239곳 → 247곳(+8곳)

- 기준점: 단지 대표 좌표
- 반경: 직선거리 1,000m
- 방식: 같은 단지 주변 전체 학원 개수의 직전 대비 증가(1곳 이상)
- 출처: 서울시 학원·교습소 정보

위험 요소: 학원 개수 증가이며 교육 성과를 뜻하지 않습니다. 좌표·분류·등록 변경을 확인해야 합니다.

`CHANGE_KINDS` 제안(사용자 선택 후 구현, 아이콘은 기존 `CHANGE_ICONS` 키):

```json
{
  "color": "#7c3aed",
  "empty": "이번 달 학원이 늘어난 단지가 없습니다.",
  "heading": "주변 학원이 늘어난 단지",
  "icon": "pin",
  "key": "academy_growth",
  "label": "학원 수 증가",
  "radius": "반경 1km",
  "uncompared": "직전 학원 정보가 없어 비교하지 않았습니다."
}
```

### 이번 갱신에서 새로 등록된 아파트는?

1위 답 후보: 강변역센트럴아이파크: 215세대, 사용승인 2026-08-25

- 기준점: 단지 코드
- 방식: 직전 마스터에 없던 코드, 1,000세대 이상·기준월 사용승인 별도 표시
- 출처: 서울시 공동주택 아파트 정보

위험 요소: 신규 등록이 입주 시작을 뜻하지 않습니다. 실제 입주일을 확인해야 합니다.

`CHANGE_KINDS` 제안(사용자 선택 후 구현, 아이콘은 기존 `CHANGE_ICONS` 키):

```json
{
  "color": "#2563eb",
  "empty": "신규 등록 단지가 없습니다.",
  "heading": "새로 등록된 단지",
  "icon": "pin",
  "key": "new_complex",
  "label": "신규 등록",
  "radius": "",
  "uncompared": "직전 단지 정보가 없어 비교하지 않았습니다."
}
```

### 최근 6개월, 매매가가 가장 많이 내린 아파트는?

1위 답 후보: 은마 84㎡: -7.9%

- 기준점: 같은 단지·같은 전용면적(㎡ 정수)
- 방식: 2026-03~2026-08와 2025-09~2026-02 매매 중앙값 비교, 분양·300세대 이상·기간별 5건 이상·직거래 제외
- 출처: 국토교통부 아파트 매매 실거래가

위험 요소: 면적 정수 안의 층·동·수리 상태 차이와 표본 구성 변화는 남습니다.

</details>

<details>
<summary>비교 범위·점검 결과·질문 인기</summary>

## 비교 기준

- 보고서 기준월과 원천 수집일은 다릅니다. 기준월 라벨을 시설 개업월로 해석하지 않습니다.
- 현재 데이터: `C:\Users\hyr19\OneDrive\Desktop\apartment-life-score\data`
- 직전 자료: `C:\Users\hyr19\clustead-backups\20261001`
- 가격: 2026-03~2026-08 대 2025-09~2026-02
- 가격 비교 가능 단지·면적 조합: 986, 직거래 제외 1,231건

## 필수 점검

1. 기관명 공백을 제거한 뒤 비교합니다(중앙보훈·한일·안암·양지병원 사례).
2. 직전 달에 없던 단지 키와 코드가 바뀐 단지는 시설 변화에서 제외합니다(목동성원 사례).
3. 반올림 거리 대신 개수 컬럼을 우선합니다. 개수에 맞는 항목이 없으면 제외합니다.
4. 가격은 신고 기한 30일을 고려해 기준월을 제외합니다(2026-09 부분 신고 사례).
5. 지하철은 양쪽에 canonical_line·station_key를 적용하고 기존 역의 반경 변화를 제외합니다.

| 영역 | 상태 | 비교 단지 / 제외 |
|---|---|---|
| emergency | 비교 | 2873 / 14 |
| hospital | 비교 | 2873 / 14 |
| mart | 비교 | 2875 / 11 |
| subway | 비교 | 2875 / 11 |
| starbucks | 비교 | 2875 / 11 |
| academy_growth | 비교 | — / — |
| new_complex | 비교 | — / — |
| top5 | 미비교 | — / — |

### 질문 인기

기간(KST): 2026-09-01 이상 ~ 2026-10-01 미만.
같은 방문자의 하루 반복을 1로 세는 방문자-일입니다. 노출 수나 기간 전체 순방문자 수가 아닙니다.

미집계: --analytics-db 서버 사본을 지정하지 않음. 0건으로 간주하지 않습니다.

</details>

<details>
<summary>전체 후보 목록</summary>

| 순서 | 후보 | 영향 단지 | 후보 ID |
|---:|---|---:|---|
| 1 | 서울고든병원 · 응급실 추가 후보 | 51 | emergency-1d0cc11cfe65 |
| 2 | 스타벅스 목동오목로점 · 스타벅스 소실 후보 | 9 | starbucks-313925667f0f |
| 3 | 스타벅스 강동경희대병원점 · 스타벅스 추가 후보 | 6 | starbucks-18e74c74f555 |
| 4 | 스타벅스 외대정문점 · 스타벅스 추가 후보 | 6 | starbucks-db1216a18e7c |
| 5 | 스타벅스 서초역라이프재단점 · 스타벅스 추가 후보 | 5 | starbucks-d81e8ed318d7 |
| 6 | 롯데캐슬헤론 · 1km 학원 8곳 증가 | 1 | academy_growth-08756719b1f4 |
| 7 | 반포힐스테이트 · 1km 학원 8곳 증가 | 1 | academy_growth-761574e45424 |
| 8 | 송파레이크파크 호반 써밋2 · 1km 학원 8곳 증가 | 1 | academy_growth-652e0fc2b7b1 |
| 9 | 송파레이크힐아파트 · 1km 학원 8곳 증가 | 1 | academy_growth-98e159a47a94 |
| 10 | 송파위례리슈빌 · 1km 학원 8곳 증가 | 1 | academy_growth-07779904fe2f |
| 11 | 쌍용예가클래식 · 1km 학원 8곳 증가 | 1 | academy_growth-517a456d4280 |
| 12 | 위례2차아이파크아파트 · 1km 학원 8곳 증가 | 1 | academy_growth-3618ff5ddcd0 |
| 13 | 이수교스위첸 · 1km 학원 8곳 증가 | 1 | academy_growth-c11fe222f4e0 |
| 14 | 포레나송파 · 1km 학원 8곳 증가 | 1 | academy_growth-f02131f54c24 |
| 15 | 거여4단지 · 1km 학원 7곳 증가 | 1 | academy_growth-bf59505df51b |
| 16 | 거여5단지 · 1km 학원 7곳 증가 | 1 | academy_growth-c8f7c7e4d137 |
| 17 | 거여6단지 · 1km 학원 7곳 증가 | 1 | academy_growth-a2f293eda60d |
| 18 | 동작금강KCC · 1km 학원 7곳 증가 | 1 | academy_growth-e5eb8982affd |
| 19 | 래미안 원페를라 · 1km 학원 7곳 증가 | 1 | academy_growth-24d3865aa557 |
| 20 | 방배3차e편한세상 · 1km 학원 7곳 증가 | 1 | academy_growth-87111f4fca7a |
| 21 | 방배신삼호 · 1km 학원 7곳 증가 | 1 | academy_growth-534a68012377 |
| 22 | 방배아크로리버 · 1km 학원 7곳 증가 | 1 | academy_growth-f2df99e20dc9 |
| 23 | 삼호 · 1km 학원 7곳 증가 | 1 | academy_growth-401d751aec93 |
| 24 | 쌍용대치1차 · 1km 학원 7곳 증가 | 1 | academy_growth-f5da897923ec |
| 25 | 아크로리버파크 · 1km 학원 7곳 증가 | 1 | academy_growth-36050ba568f9 |
| 26 | 위례 송파푸르지오 · 1km 학원 7곳 증가 | 1 | academy_growth-16bb1df04f66 |
| 27 | 이수스위첸포레힐즈아파트 · 1km 학원 7곳 증가 | 1 | academy_growth-d1bfd9a5663d |
| 28 | 이수힐스테이트 · 1km 학원 7곳 증가 | 1 | academy_growth-78692895f6e0 |
| 29 | 현대멤피스아파트 · 1km 학원 7곳 증가 | 1 | academy_growth-55754777a42d |
| 30 | 래미안 원펜타스 · 1km 학원 6곳 증가 | 1 | academy_growth-263b24256136 |
| 31 | 래미안장위포레카운티아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-c2833c62763f |
| 32 | 목동3단지 · 1km 학원 6곳 증가 | 1 | academy_growth-7d64edac6fa2 |
| 33 | 반포래미안트리니원 · 1km 학원 6곳 증가 | 1 | academy_growth-47ff2561d8b5 |
| 34 | 반포본동아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-c9f598c82e39 |
| 35 | 방배롯데캐슬아르떼 · 1km 학원 6곳 증가 | 1 | academy_growth-dfd9cb450736 |
| 36 | 방배한신트리플 · 1km 학원 6곳 증가 | 1 | academy_growth-533ffcd33b29 |
| 37 | 송파더센트레아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-f0a2cf23091e |
| 38 | 신반포15차아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-adbae574b003 |
| 39 | 위례아이파크아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-d201769c6f9b |
| 40 | 장위지웰에스테이트 · 1km 학원 6곳 증가 | 1 | academy_growth-a11693925a1f |
| 41 | 힐스테이트 송파위례아파트 · 1km 학원 6곳 증가 | 1 | academy_growth-2ce28086fcf5 |
| 42 | e편한세상화랑대아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-14fcd62211f3 |
| 43 | 거여1단지 · 1km 학원 5곳 증가 | 1 | academy_growth-2e8b94d15304 |
| 44 | 거여3단지 · 1km 학원 5곳 증가 | 1 | academy_growth-dae7a13783db |
| 45 | 공릉2-6 · 1km 학원 5곳 증가 | 1 | academy_growth-af9a8475b454 |
| 46 | 공릉두산힐스빌 · 1km 학원 5곳 증가 | 1 | academy_growth-30a51e44e037 |
| 47 | 공릉비선 · 1km 학원 5곳 증가 | 1 | academy_growth-034409d0d0a9 |
| 48 | 공릉삼익2차 · 1km 학원 5곳 증가 | 1 | academy_growth-aec50000f587 |
| 49 | 공릉신성미소지움 · 1km 학원 5곳 증가 | 1 | academy_growth-590546317033 |
| 50 | 공릉우방4단지 · 1km 학원 5곳 증가 | 1 | academy_growth-bf1db906d35a |
| 51 | 공릉청솔9단지 · 1km 학원 5곳 증가 | 1 | academy_growth-42782b05b617 |
| 52 | 공릉태강 · 1km 학원 5곳 증가 | 1 | academy_growth-b3e23528953d |
| 53 | 공릉태릉우성 · 1km 학원 5곳 증가 | 1 | academy_growth-9280f4c2efcf |
| 54 | 공릉현대 · 1km 학원 5곳 증가 | 1 | academy_growth-7b1b12584184 |
| 55 | 공릉화랑타운 · 1km 학원 5곳 증가 | 1 | academy_growth-78ea9d162afa |
| 56 | 길음뉴타운11단지 롯데캐슬골든힐스아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-e6649247c789 |
| 57 | 길음뉴타운3단지임대 · 1km 학원 5곳 증가 | 1 | academy_growth-0dd8c02d5893 |
| 58 | 길음뉴타운8단지 · 1km 학원 5곳 증가 | 1 | academy_growth-c96ddec7af5a |
| 59 | 꿈의숲아이파크아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-c11ade48a4d8 |
| 60 | 노원프레미어스엠코 · 1km 학원 5곳 증가 | 1 | academy_growth-18b62b12d858 |
| 61 | 동아효성아파트(거여2단지) · 1km 학원 5곳 증가 | 1 | academy_growth-4c087410a9b7 |
| 62 | 둔촌역청구아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-180579abeb4c |
| 63 | 목동4단지 · 1km 학원 5곳 증가 | 1 | academy_growth-d55995ce0573 |
| 64 | 목동금호어울림 · 1km 학원 5곳 증가 | 1 | academy_growth-5709d7e88294 |
| 65 | 목동금호타운아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-2734eadbf088 |
| 66 | 목동트윈빌 · 1km 학원 5곳 증가 | 1 | academy_growth-bfcaa169df2f |
| 67 | 묵동세방 · 1km 학원 5곳 증가 | 1 | academy_growth-5cd34b05c5e6 |
| 68 | 묵동신도1차 · 1km 학원 5곳 증가 | 1 | academy_growth-5db098c0f87e |
| 69 | 브라운스톤태릉 · 1km 학원 5곳 증가 | 1 | academy_growth-a59d219dcf2c |
| 70 | 성내1차e-편한세상 · 1km 학원 5곳 증가 | 1 | academy_growth-221f6d0f50e9 |
| 71 | 송파 와이즈더샵 · 1km 학원 5곳 증가 | 1 | academy_growth-b3ad2eca14b0 |
| 72 | 송파레이크파크호반써밋1차 · 1km 학원 5곳 증가 | 1 | academy_growth-197be769ee9f |
| 73 | 신내4단지 · 1km 학원 5곳 증가 | 1 | academy_growth-ccd30b9ab3b4 |
| 74 | 신내5단지대림두산 · 1km 학원 5곳 증가 | 1 | academy_growth-ba953e5444ea |
| 75 | 신내6단지 · 1km 학원 5곳 증가 | 1 | academy_growth-5f1081c8e7af |
| 76 | 신내글로리움아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-a021a31c284a |
| 77 | 신정동아이파크 · 1km 학원 5곳 증가 | 1 | academy_growth-5b84256294c7 |
| 78 | 오금대림 · 1km 학원 5곳 증가 | 1 | academy_growth-540212d26a77 |
| 79 | 오금현대백조 · 1km 학원 5곳 증가 | 1 | academy_growth-05fdbbf55abc |
| 80 | 오금현대백조(임대) · 1km 학원 5곳 증가 | 1 | academy_growth-8df2554019db |
| 81 | 위례포레샤인13단지아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-4ad8e2038661 |
| 82 | 위례포레샤인18단지 · 1km 학원 5곳 증가 | 1 | academy_growth-88a4ca938040 |
| 83 | 청솔아파트8 · 1km 학원 5곳 증가 | 1 | academy_growth-5f6b35d4ba01 |
| 84 | 태릉해링턴플레이스 · 1km 학원 5곳 증가 | 1 | academy_growth-91a6ea89368f |
| 85 | 태릉현대 · 1km 학원 5곳 증가 | 1 | academy_growth-c1508e653f1f |
| 86 | 화랑해링턴플레이스 · 1km 학원 5곳 증가 | 1 | academy_growth-61c5950d94e8 |
| 87 | 효성아파트 · 1km 학원 5곳 증가 | 1 | academy_growth-a9b58e8c703d |
| 88 | SK허브진주상복합아파트 · 1km 학원 4곳 증가 | 1 | academy_growth-38ab7b7fa7d7 |
| 89 | 공릉해링턴플레이스(구.효성화운트빌) · 1km 학원 4곳 증가 | 1 | academy_growth-797d21d588e8 |
| 90 | 길음SHVILLE · 1km 학원 4곳 증가 | 1 | academy_growth-78cf1b51cc03 |
| 91 | 길음뉴타운 데시앙 · 1km 학원 4곳 증가 | 1 | academy_growth-05de821583bb |
| 92 | 길음뉴타운7단지 · 1km 학원 4곳 증가 | 1 | academy_growth-de2933fed43f |
| 93 | 길음뉴타운7단지제2 · 1km 학원 4곳 증가 | 1 | academy_growth-6ad81158cdb1 |
| 94 | 길음뉴타운8단지제2 · 1km 학원 4곳 증가 | 1 | academy_growth-b6ef1fe3dbf9 |
| 95 | 꿈의숲 SK뷰 아파트 · 1km 학원 4곳 증가 | 1 | academy_growth-7b88d3b76eb0 |
| 96 | 꿈의숲대명루첸 · 1km 학원 4곳 증가 | 1 | academy_growth-0ff08d12cb4c |
| 97 | 당산2차삼성 · 1km 학원 4곳 증가 | 1 | academy_growth-228f5c85a889 |
| 98 | 당산SHVILLE · 1km 학원 4곳 증가 | 1 | academy_growth-8249a2c9ac3a |
| 99 | 당산동부센트레빌 · 1km 학원 4곳 증가 | 1 | academy_growth-a1256b3fccba |
| 100 | 당산반도유보라 · 1km 학원 4곳 증가 | 1 | academy_growth-dbf158d442e0 |
| 101 | 당산브라운스톤아파트 · 1km 학원 4곳 증가 | 1 | academy_growth-1ec18fc55eb0 |
| 102 | 당산한양 · 1km 학원 4곳 증가 | 1 | academy_growth-fcf96ef83705 |
| 103 | 둔촌신동아 · 1km 학원 4곳 증가 | 1 | academy_growth-ae2370018a98 |
| 104 | 둔촌하이츠 · 1km 학원 4곳 증가 | 1 | academy_growth-8bcce26c6548 |
| 105 | 둔촌현대2차 · 1km 학원 4곳 증가 | 1 | academy_growth-f33cbb911de8 |
| 106 | 둔촌현대3차 · 1km 학원 4곳 증가 | 1 | academy_growth-6a080ec1182d |
| 107 | 둔촌현대4차 · 1km 학원 4곳 증가 | 1 | academy_growth-61c8cb584b93 |
| 108 | 래미안트리베라1차 · 1km 학원 4곳 증가 | 1 | academy_growth-9a583f68a875 |
| 109 | 래미안퍼스트하이 · 1km 학원 4곳 증가 | 1 | academy_growth-571cc398a520 |
| 110 | 로프트원 태릉입구역 · 1km 학원 4곳 증가 | 1 | academy_growth-e137dcd7a2d1 |
| 111 | 목동현대하이페리온2차 · 1km 학원 4곳 증가 | 1 | academy_growth-7b9065982f9c |
| 112 | 묵동금호어울림 · 1km 학원 4곳 증가 | 1 | academy_growth-fe8ed9c92627 |
| 113 | 묵동신안1차 · 1km 학원 4곳 증가 | 1 | academy_growth-c6438573a252 |
| 114 | 묵동신안2차 · 1km 학원 4곳 증가 | 1 | academy_growth-eec950ab72b8 |
| 115 | 묵동신안3차 · 1km 학원 4곳 증가 | 1 | academy_growth-92acc2ab7593 |
| 116 | 반포삼호가든맨션5차 · 1km 학원 4곳 증가 | 1 | academy_growth-b4267d8a57a4 |
| 117 | 반포자이 · 1km 학원 4곳 증가 | 1 | academy_growth-824006d8e916 |
| 118 | 방배디오빌 · 1km 학원 4곳 증가 | 1 | academy_growth-d5e6f404bff7 |
| 119 | 방학동부센트레빌 · 1km 학원 4곳 증가 | 1 | academy_growth-90f1cbdcab67 |
| 120 | 성내코오롱 · 1km 학원 4곳 증가 | 1 | academy_growth-03544b4a3719 |
| 121 | 성북역신도브래뉴 · 1km 학원 4곳 증가 | 1 | academy_growth-a8927ec05c3b |
| 122 | 송천센트레빌 · 1km 학원 4곳 증가 | 1 | academy_growth-43958af1c71d |
| 123 | 신내진로아파트 · 1km 학원 4곳 증가 | 1 | academy_growth-92b777d2e9b6 |
| 124 | 신성둔촌미소지움1차 · 1km 학원 4곳 증가 | 1 | academy_growth-7dba02c51efc |
| 125 | 신성둔촌미소지움2차 · 1km 학원 4곳 증가 | 1 | academy_growth-ce3b321cf469 |
| 126 | 압구정하이츠파크 · 1km 학원 4곳 증가 | 1 | academy_growth-fed50db5feee |
| 127 | 압구정한양아파트제1단지 · 1km 학원 4곳 증가 | 1 | academy_growth-af562202305f |
| 128 | 역삼삼익 · 1km 학원 4곳 증가 | 1 | academy_growth-2acf32b1d929 |
| 129 | 영등포경남아너스빌 · 1km 학원 4곳 증가 | 1 | academy_growth-761a8dd62c79 |
| 130 | 올림픽파크포레온 · 1km 학원 4곳 증가 | 1 | academy_growth-037348a89b2e |
| 131 | 올림픽파크한양수자인 · 1km 학원 4곳 증가 | 1 | academy_growth-113ba5c976ac |
| 132 | 이수자이 주상복합 · 1km 학원 4곳 증가 | 1 | academy_growth-77efce15a02c |
| 133 | 이편한세상 길음뉴타운4단지 · 1km 학원 4곳 증가 | 1 | academy_growth-f2c70d6a421e |
| 134 | 잠실 센트럴파크 · 1km 학원 4곳 증가 | 1 | academy_growth-93f8835fa1a9 |
| 135 | 잠실5단지아파트 · 1km 학원 4곳 증가 | 1 | academy_growth-4d05519e6ac2 |
| 136 | 잠원동아 · 1km 학원 4곳 증가 | 1 | academy_growth-5080bc0d479d |
| 137 | 정릉푸른마을동아 · 1km 학원 4곳 증가 | 1 | academy_growth-9cbb3f671e62 |
| 138 | 창동현대4차아이파크 · 1km 학원 4곳 증가 | 1 | academy_growth-37567c613636 |
| 139 | 청광플러스원큐브3차 · 1km 학원 4곳 증가 | 1 | academy_growth-90f685eac3df |
| 140 | 개포자이아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-65be07f6c773 |
| 141 | 갤러리아팰리스 · 1km 학원 3곳 증가 | 1 | academy_growth-ad277d3c2c47 |
| 142 | 거여우방 · 1km 학원 3곳 증가 | 1 | academy_growth-8fb79a24d0d0 |
| 143 | 고덕 온빛채 · 1km 학원 3곳 증가 | 1 | academy_growth-c2d148f4e243 |
| 144 | 고덕리엔파크1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-e39905e59433 |
| 145 | 고덕리엔파크2단지 · 1km 학원 3곳 증가 | 1 | academy_growth-7fc79a4643ff |
| 146 | 고덕센트럴푸르지오 · 1km 학원 3곳 증가 | 1 | academy_growth-d13877ea0a07 |
| 147 | 고덕풍경채어바니티 · 1km 학원 3곳 증가 | 1 | academy_growth-196fffc017f7 |
| 148 | 길음뉴타운 경남아너스빌 · 1km 학원 3곳 증가 | 1 | academy_growth-9e50069e2cb2 |
| 149 | 길음뉴타운푸르지오아파트2,3단지 · 1km 학원 3곳 증가 | 1 | academy_growth-6866304eb1c2 |
| 150 | 길음동부센트레빌 · 1km 학원 3곳 증가 | 1 | academy_growth-37f37edab4a4 |
| 151 | 길음현대 · 1km 학원 3곳 증가 | 1 | academy_growth-c015908da565 |
| 152 | 남현동한일유앤아이 · 1km 학원 3곳 증가 | 1 | academy_growth-3d60362aeaf9 |
| 153 | 남현우림루미아트 · 1km 학원 3곳 증가 | 1 | academy_growth-ee2708ecb3a8 |
| 154 | 논현동현 · 1km 학원 3곳 증가 | 1 | academy_growth-6292d991e52f |
| 155 | 답십리동답한신 · 1km 학원 3곳 증가 | 1 | academy_growth-9936fc4480bf |
| 156 | 답십리동서울한양 · 1km 학원 3곳 증가 | 1 | academy_growth-9b9502992d3e |
| 157 | 답십리래미안임대 · 1km 학원 3곳 증가 | 1 | academy_growth-74f8ce118940 |
| 158 | 답십리우성그린 · 1km 학원 3곳 증가 | 1 | academy_growth-16bb2630b97b |
| 159 | 답십리청솔우성제2 · 1km 학원 3곳 증가 | 1 | academy_growth-4b0655b5c497 |
| 160 | 당산강변래미안3차 · 1km 학원 3곳 증가 | 1 | academy_growth-b11704958dd8 |
| 161 | 당산금호어울림 · 1km 학원 3곳 증가 | 1 | academy_growth-fff2273056e6 |
| 162 | 당산동1차효성아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-5d3c5419bbf7 |
| 163 | 당산롯데캐슬프레스티지 아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-3f5e5438cbd8 |
| 164 | 당산삼익 · 1km 학원 3곳 증가 | 1 | academy_growth-8ee744fd56a9 |
| 165 | 당산상아 · 1km 학원 3곳 증가 | 1 | academy_growth-f4369e1b07ff |
| 166 | 당산센트럴아이파크 · 1km 학원 3곳 증가 | 1 | academy_growth-3e578d86bf15 |
| 167 | 당산쌍용예가클래식 · 1km 학원 3곳 증가 | 1 | academy_growth-7cec39e9a4c4 |
| 168 | 당산푸르지오 · 1km 학원 3곳 증가 | 1 | academy_growth-faf19f5a2686 |
| 169 | 당산현대5차 · 1km 학원 3곳 증가 | 1 | academy_growth-141483e21e78 |
| 170 | 대방2차현대 · 1km 학원 3곳 증가 | 1 | academy_growth-05b6dd1ce117 |
| 171 | 대방주공1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-a0b6a7a6f9b8 |
| 172 | 대원칸타빌(신사동) · 1km 학원 3곳 증가 | 1 | academy_growth-995cae7051b7 |
| 173 | 대치쌍용2차 · 1km 학원 3곳 증가 | 1 | academy_growth-1ffc4b0a3e90 |
| 174 | 더샵둔촌포레 · 1km 학원 3곳 증가 | 1 | academy_growth-471a768b5379 |
| 175 | 더샵파크솔레이유아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-ad08dc0a61ff |
| 176 | 더클래식동작 · 1km 학원 3곳 증가 | 1 | academy_growth-da0b56fb97fd |
| 177 | 도곡1차아이파크 · 1km 학원 3곳 증가 | 1 | academy_growth-7a9c67d45397 |
| 178 | 도곡2차 I-Park · 1km 학원 3곳 증가 | 1 | academy_growth-7b8443abd958 |
| 179 | 도곡3차아이파크 · 1km 학원 3곳 증가 | 1 | academy_growth-d9aedaab0121 |
| 180 | 도곡경남 · 1km 학원 3곳 증가 | 1 | academy_growth-06891718d754 |
| 181 | 도곡삼성 · 1km 학원 3곳 증가 | 1 | academy_growth-c21566324fc1 |
| 182 | 도곡한라비발디아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-8bf8fe6ab726 |
| 183 | 도곡한신 · 1km 학원 3곳 증가 | 1 | academy_growth-2eb945599e85 |
| 184 | 도곡현대 · 1km 학원 3곳 증가 | 1 | academy_growth-dfac783a5748 |
| 185 | 도곡현대그린 · 1km 학원 3곳 증가 | 1 | academy_growth-5abc7cc04b51 |
| 186 | 둔촌현대1차 · 1km 학원 3곳 증가 | 1 | academy_growth-bc84eeb8cd50 |
| 187 | 래미안길음2차아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-2a7381918964 |
| 188 | 래미안로이파크아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-4c604ca17d73 |
| 189 | 래미안엘파인 · 1km 학원 3곳 증가 | 1 | academy_growth-d5088129e713 |
| 190 | 로데오현대아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-eb533a56c4ec |
| 191 | 마곡엠밸리11단지 · 1km 학원 3곳 증가 | 1 | academy_growth-4d23633cbff8 |
| 192 | 목동극동늘푸른 · 1km 학원 3곳 증가 | 1 | academy_growth-e64a72d2d3e6 |
| 193 | 목동금강에스쁘아 · 1km 학원 3곳 증가 | 1 | academy_growth-b47f0fbd6f55 |
| 194 | 목동대원칸타빌 · 1km 학원 3곳 증가 | 1 | academy_growth-3d44ae6763e3 |
| 195 | 목동대원칸타빌2,3단지 · 1km 학원 3곳 증가 | 1 | academy_growth-98277a0c77b7 |
| 196 | 목동부영그린타운3차 · 1km 학원 3곳 증가 | 1 | academy_growth-00267447e043 |
| 197 | 목동삼성래미안 · 1km 학원 3곳 증가 | 1 | academy_growth-414704c0395f |
| 198 | 목동삼성쉐르빌2차 · 1km 학원 3곳 증가 | 1 | academy_growth-d27ac29f11a8 |
| 199 | 목동우성 · 1km 학원 3곳 증가 | 1 | academy_growth-2e3ab325eec8 |
| 200 | 목동트라팰리스 · 1km 학원 3곳 증가 | 1 | academy_growth-8260c636b82c |
| 201 | 목동한신청구 · 1km 학원 3곳 증가 | 1 | academy_growth-3fc2a30d93bf |
| 202 | 목동현대2차 · 1km 학원 3곳 증가 | 1 | academy_growth-495a21aa31b9 |
| 203 | 무학현대 · 1km 학원 3곳 증가 | 1 | academy_growth-1db0b16638f6 |
| 204 | 미성아파트(불광동) · 1km 학원 3곳 증가 | 1 | academy_growth-bbd34fbe21f6 |
| 205 | 미아2동경남아너스빌 · 1km 학원 3곳 증가 | 1 | academy_growth-1b4de8101b96 |
| 206 | 미아동부센트레빌 · 1km 학원 3곳 증가 | 1 | academy_growth-c86eed743547 |
| 207 | 반포리체 · 1km 학원 3곳 증가 | 1 | academy_growth-177ce409fb5a |
| 208 | 반포푸르지오 · 1km 학원 3곳 증가 | 1 | academy_growth-0342485f1034 |
| 209 | 방배1차현대 · 1km 학원 3곳 증가 | 1 | academy_growth-6f5d0e63ac90 |
| 210 | 방이대림가락 · 1km 학원 3곳 증가 | 1 | academy_growth-3ac748cb5f73 |
| 211 | 방이코오롱 · 1km 학원 3곳 증가 | 1 | academy_growth-de53ce57d400 |
| 212 | 방학금광포란재아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-37776b09dcd4 |
| 213 | 방학명품ESA1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-1ff2357ea06b |
| 214 | 방학삼성래미안1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-4d259785d0db |
| 215 | 북한산래미안아파트(임대) · 1km 학원 3곳 증가 | 1 | academy_growth-27caf67eb0e3 |
| 216 | 북한산한신휴플러스 · 1km 학원 3곳 증가 | 1 | academy_growth-25566f255172 |
| 217 | 북한산힐스테이트7차 · 1km 학원 3곳 증가 | 1 | academy_growth-b19ff5eb1eda |
| 218 | 북한산힐스테이트7차제2 (임대) · 1km 학원 3곳 증가 | 1 | academy_growth-1d07d05e76f7 |
| 219 | 사당극동 · 1km 학원 3곳 증가 | 1 | academy_growth-79cfdfbd63ad |
| 220 | 사당롯데캐슬샤인 · 1km 학원 3곳 증가 | 1 | academy_growth-db24ace496aa |
| 221 | 사당삼익그린뷰 · 1km 학원 3곳 증가 | 1 | academy_growth-ca16893dbdc5 |
| 222 | 사당신동아4단지 · 1km 학원 3곳 증가 | 1 | academy_growth-829e6eedb994 |
| 223 | 사당우성(4-3)아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-3136cf195af4 |
| 224 | 사당우성2단지 · 1km 학원 3곳 증가 | 1 | academy_growth-10ba7ac53686 |
| 225 | 삼성쉐르빌1 아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-c71bebccece3 |
| 226 | 상도동 롯데캐슬 비엔 · 1km 학원 3곳 증가 | 1 | academy_growth-694f483065e9 |
| 227 | 상봉우정 · 1km 학원 3곳 증가 | 1 | academy_growth-f8d03c04c494 |
| 228 | 서울숲리버그린동아 · 1km 학원 3곳 증가 | 1 | academy_growth-759fbb0c246e |
| 229 | 서울숲리버뷰자이아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-9ff8c8f530c6 |
| 230 | 서울숲한신더휴아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-46de33bc415f |
| 231 | 석계역 한일노벨리아시티 · 1km 학원 3곳 증가 | 1 | academy_growth-318625b5ab9b |
| 232 | 성내삼성 · 1km 학원 3곳 증가 | 1 | academy_growth-d75b68d63bcf |
| 233 | 성내성안청구 · 1km 학원 3곳 증가 | 1 | academy_growth-9ce6522caa4c |
| 234 | 성현동아 · 1km 학원 3곳 증가 | 1 | academy_growth-fdae3525a53c |
| 235 | 세방하이빌 · 1km 학원 3곳 증가 | 1 | academy_growth-b565a8c55619 |
| 236 | 세양청마루 · 1km 학원 3곳 증가 | 1 | academy_growth-a475ce5eca4f |
| 237 | 송파꿈에그린아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-72111b293276 |
| 238 | 송파파인타운11단지 · 1km 학원 3곳 증가 | 1 | academy_growth-7a90636c68f3 |
| 239 | 송파파인타운1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-5972455c3b39 |
| 240 | 송파파인타운3단지 · 1km 학원 3곳 증가 | 1 | academy_growth-afbc1d90a87b |
| 241 | 송파현대힐스테이트 · 1km 학원 3곳 증가 | 1 | academy_growth-e3b9820c8f41 |
| 242 | 신내8단지두산화성 · 1km 학원 3곳 증가 | 1 | academy_growth-60630ad3efff |
| 243 | 신내9단지 · 1km 학원 3곳 증가 | 1 | academy_growth-7d5289a1b77d |
| 244 | 신동아5 · 1km 학원 3곳 증가 | 1 | academy_growth-9d751f970593 |
| 245 | 신반포4차 · 1km 학원 3곳 증가 | 1 | academy_growth-d7a839243a9f |
| 246 | 아크로타워스퀘어 · 1km 학원 3곳 증가 | 1 | academy_growth-4211ae172e92 |
| 247 | 압구정한양아파트제2단지 · 1km 학원 3곳 증가 | 1 | academy_growth-3162663f647b |
| 248 | 압구정현대8차 · 1km 학원 3곳 증가 | 1 | academy_growth-9dd9c94c8b54 |
| 249 | 양평삼호 · 1km 학원 3곳 증가 | 1 | academy_growth-a2eedc4ae8a3 |
| 250 | 역삼럭키 · 1km 학원 3곳 증가 | 1 | academy_growth-9f3ad8d3dbd3 |
| 251 | 영등포삼환 · 1km 학원 3곳 증가 | 1 | academy_growth-6e71d8dce04c |
| 252 | 오금현대아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-30429184c3c0 |
| 253 | 오티에르반포 · 1km 학원 3곳 증가 | 1 | academy_growth-eceb5cc35fd2 |
| 254 | 올림픽선수기자촌아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-7446631dba4a |
| 255 | 월계동신 · 1km 학원 3곳 증가 | 1 | academy_growth-90e94fe37709 |
| 256 | 월계동현대 · 1km 학원 3곳 증가 | 1 | academy_growth-6d9af6c428a5 |
| 257 | 월계삼창 · 1km 학원 3곳 증가 | 1 | academy_growth-14ee82ee12d6 |
| 258 | 위례중앙푸르지오1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-12a7674045b6 |
| 259 | 위례중앙푸르지오2단지 · 1km 학원 3곳 증가 | 1 | academy_growth-2b633a04a2df |
| 260 | 응봉대림1차 · 1km 학원 3곳 증가 | 1 | academy_growth-c47ff420d75e |
| 261 | 응봉대림강변 · 1km 학원 3곳 증가 | 1 | academy_growth-7b3fb8ff55be |
| 262 | 이수역리가 · 1km 학원 3곳 증가 | 1 | academy_growth-103681f6c7d4 |
| 263 | 잠실동트리지움 · 1km 학원 3곳 증가 | 1 | academy_growth-d83ed74aecf2 |
| 264 | 잠실레이크팰리스 · 1km 학원 3곳 증가 | 1 | academy_growth-99369b7ac975 |
| 265 | 잠실리센츠 · 1km 학원 3곳 증가 | 1 | academy_growth-3e62d7861961 |
| 266 | 잠실엘스아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-d69f4c0a2dce |
| 267 | 잠실현대 · 1km 학원 3곳 증가 | 1 | academy_growth-b4c2939c6794 |
| 268 | 장월SH-VILLE1단지 · 1km 학원 3곳 증가 | 1 | academy_growth-2d0bce2749e5 |
| 269 | 장위우방아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-da2c6646d243 |
| 270 | 장위자이레디언트 · 1km 학원 3곳 증가 | 1 | academy_growth-2c3b9ef8f174 |
| 271 | 장위참누리 · 1km 학원 3곳 증가 | 1 | academy_growth-350d456b7eb6 |
| 272 | 전농SK제2(임대) · 1km 학원 3곳 증가 | 1 | academy_growth-f6c020061fd1 |
| 273 | 전농우성 · 1km 학원 3곳 증가 | 1 | academy_growth-5391da08220f |
| 274 | 정릉힐스테이트 · 1km 학원 3곳 증가 | 1 | academy_growth-77becc0183fe |
| 275 | 중화한신아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-423908f0792b |
| 276 | 창동대림 · 1km 학원 3곳 증가 | 1 | academy_growth-de4473a7a007 |
| 277 | 창동동아그린 · 1km 학원 3곳 증가 | 1 | academy_growth-ec4a2d570afc |
| 278 | 창동동아청솔 · 1km 학원 3곳 증가 | 1 | academy_growth-cac4cd990eb3 |
| 279 | 창동상아1차 · 1km 학원 3곳 증가 | 1 | academy_growth-3488f73aeda9 |
| 280 | 창동상아2차 · 1km 학원 3곳 증가 | 1 | academy_growth-d1ac60adfeae |
| 281 | 창동성원 · 1km 학원 3곳 증가 | 1 | academy_growth-4734ffaddb2f |
| 282 | 창동신도브래뉴 · 1km 학원 3곳 증가 | 1 | academy_growth-786e20ea3e28 |
| 283 | 창동쌍용 · 1km 학원 3곳 증가 | 1 | academy_growth-619536047200 |
| 284 | 타워팰리스1차 · 1km 학원 3곳 증가 | 1 | academy_growth-488a0c6f3aff |
| 285 | 포레나영등포센트럴아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-dc2419351756 |
| 286 | 한강아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-299b987222cb |
| 287 | 한신무학 · 1km 학원 3곳 증가 | 1 | academy_growth-ae32a8111a00 |
| 288 | 한화포레나미아아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-d66df9b7f739 |
| 289 | 행당한신임대 · 1km 학원 3곳 증가 | 1 | academy_growth-93e4bb9110a6 |
| 290 | 현대리버빌2차아파트 · 1km 학원 3곳 증가 | 1 | academy_growth-66619dacbf86 |
| 291 | 호반베르디움 스테이원 · 1km 학원 3곳 증가 | 1 | academy_growth-390c24e5064f |
| 292 | (풍납)대동아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-9de4ede93733 |
| 293 | SH공사대치1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-d530d4c5cc29 |
| 294 | SH황학롯데캐슬베네치아 · 1km 학원 2곳 증가 | 1 | academy_growth-dd8dab8ab8aa |
| 295 | SK북한산시티임대 · 1km 학원 2곳 증가 | 1 | academy_growth-898771236501 |
| 296 | 강동QV2차 · 1km 학원 2곳 증가 | 1 | academy_growth-1cecebc2b809 |
| 297 | 강동역신동아파밀리에 · 1km 학원 2곳 증가 | 1 | academy_growth-f9f65d852660 |
| 298 | 개포대치2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-9161111d38ab |
| 299 | 거여현대1차 · 1km 학원 2곳 증가 | 1 | academy_growth-387a2607382d |
| 300 | 거여현대2차 · 1km 학원 2곳 증가 | 1 | academy_growth-ea2157bad7dc |
| 301 | 경남아너스빌 · 1km 학원 2곳 증가 | 1 | academy_growth-5d315036ae29 |
| 302 | 경향렉스빌아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-b8c8c272d7c6 |
| 303 | 고덕 아르테온 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-cb3348486a20 |
| 304 | 고덕롯데캐슬베네루체 · 1km 학원 2곳 증가 | 1 | academy_growth-514c5864dab6 |
| 305 | 고덕센트럴 아이파크 · 1km 학원 2곳 증가 | 1 | academy_growth-cc6e68c8ec20 |
| 306 | 고덕자이 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-04e3e5e9da6a |
| 307 | 고덕주공6단지 · 1km 학원 2곳 증가 | 1 | academy_growth-ef6115c13499 |
| 308 | 공릉동부 · 1km 학원 2곳 증가 | 1 | academy_growth-61b9eb4b3ece |
| 309 | 공릉현대성우 · 1km 학원 2곳 증가 | 1 | academy_growth-e87eb5b4d30d |
| 310 | 관악동부센트레빌 · 1km 학원 2곳 증가 | 1 | academy_growth-7afb2977a881 |
| 311 | 관악드림타운 · 1km 학원 2곳 증가 | 1 | academy_growth-db7e2d75ffc8 |
| 312 | 관악드림타운제2 · 1km 학원 2곳 증가 | 1 | academy_growth-c121ab5d96a2 |
| 313 | 관악벽산블루밍임대 · 1km 학원 2곳 증가 | 1 | academy_growth-93a4316c379f |
| 314 | 관악우성아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-4e3978322399 |
| 315 | 광운대역 현대프라힐스 · 1km 학원 2곳 증가 | 1 | academy_growth-fcd1d78aac40 |
| 316 | 광화문스페이스본 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-e28b9709f453 |
| 317 | 구로신성미소지움 · 1km 학원 2곳 증가 | 1 | academy_growth-ea1506522404 |
| 318 | 구로중앙하이츠아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-62bd09813b80 |
| 319 | 그란츠 리버파크 · 1km 학원 2곳 증가 | 1 | academy_growth-b19681345c32 |
| 320 | 금호베스트빌임대 · 1km 학원 2곳 증가 | 1 | academy_growth-601ce7f2294e |
| 321 | 길음뉴타운10단지 · 1km 학원 2곳 증가 | 1 | academy_growth-4fdbca95903f |
| 322 | 길음뉴타운4단지임대 · 1km 학원 2곳 증가 | 1 | academy_growth-499c1ed42db3 |
| 323 | 길음뉴타운9단지제2 · 1km 학원 2곳 증가 | 1 | academy_growth-aba31c5b3837 |
| 324 | 길음동부제2 · 1km 학원 2곳 증가 | 1 | academy_growth-6d88172af267 |
| 325 | 길음래미안3차 · 1km 학원 2곳 증가 | 1 | academy_growth-06f82344e26f |
| 326 | 길음서희스타힐스 · 1km 학원 2곳 증가 | 1 | academy_growth-368b8a0e8d66 |
| 327 | 꿈의숲코오롱하늘채아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ef8eadb93bc8 |
| 328 | 남성두산위브트레지움 · 1km 학원 2곳 증가 | 1 | academy_growth-dd350b72c267 |
| 329 | 논현 e편한세상 · 1km 학원 2곳 증가 | 1 | academy_growth-b23f3bef436c |
| 330 | 답십리대림 · 1km 학원 2곳 증가 | 1 | academy_growth-913f6824d73d |
| 331 | 답십리대우 · 1km 학원 2곳 증가 | 1 | academy_growth-147c130d47f6 |
| 332 | 답십리동아 · 1km 학원 2곳 증가 | 1 | academy_growth-4c418c276028 |
| 333 | 답십리청솔우성 · 1km 학원 2곳 증가 | 1 | academy_growth-a55c7ddc5e17 |
| 334 | 당산2가현대 · 1km 학원 2곳 증가 | 1 | academy_growth-ddf4a45cd166 |
| 335 | 당산2차효성타운 · 1km 학원 2곳 증가 | 1 | academy_growth-e055c9513235 |
| 336 | 당산삼성래미안 · 1km 학원 2곳 증가 | 1 | academy_growth-3c1c12cd1b0d |
| 337 | 당산신동아파밀리에 · 1km 학원 2곳 증가 | 1 | academy_growth-1f69d0dac9ea |
| 338 | 대방1차e편한세상 · 1km 학원 2곳 증가 | 1 | academy_growth-bfcbbe40f487 |
| 339 | 대상타운현대 · 1km 학원 2곳 증가 | 1 | academy_growth-f1fc73edc415 |
| 340 | 대우디오빌역삼 · 1km 학원 2곳 증가 | 1 | academy_growth-f1bfe03672f3 |
| 341 | 대청 · 1km 학원 2곳 증가 | 1 | academy_growth-0481d431d92b |
| 342 | 대치미도맨션 · 1km 학원 2곳 증가 | 1 | academy_growth-7de523217aa0 |
| 343 | 더샵강동센트럴시티 · 1km 학원 2곳 증가 | 1 | academy_growth-da68167523be |
| 344 | 도곡대림 · 1km 학원 2곳 증가 | 1 | academy_growth-3c5156a23ce8 |
| 345 | 도곡동 포스코트 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-0457e72d7ee3 |
| 346 | 도곡렉슬 · 1km 학원 2곳 증가 | 1 | academy_growth-e2066e1dda1b |
| 347 | 도곡쌍용예가 · 1km 학원 2곳 증가 | 1 | academy_growth-f4a5478083a6 |
| 348 | 도곡우성아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-bc06008978ab |
| 349 | 도봉서원제2 · 1km 학원 2곳 증가 | 1 | academy_growth-7e95c5512aee |
| 350 | 도봉아테라 · 1km 학원 2곳 증가 | 1 | academy_growth-647cdc1a27fd |
| 351 | 도봉현대성우 · 1km 학원 2곳 증가 | 1 | academy_growth-5389a1f8dada |
| 352 | 돈암범양 · 1km 학원 2곳 증가 | 1 | academy_growth-bf3f58e0af9c |
| 353 | 두산힐스빌아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-d70fdef05b4b |
| 354 | 디에이치반포라클라스 · 1km 학원 2곳 증가 | 1 | academy_growth-06e3eb56598d |
| 355 | 뚝섬중앙하이츠빌 · 1km 학원 2곳 증가 | 1 | academy_growth-41278b51df53 |
| 356 | 라체르보푸르지오써밋 · 1km 학원 2곳 증가 | 1 | academy_growth-cbae55f229a8 |
| 357 | 래미안 크리시엘 · 1km 학원 2곳 증가 | 1 | academy_growth-ccb29d266f95 |
| 358 | 래미안강동팰리스 · 1km 학원 2곳 증가 | 1 | academy_growth-dc2cc329884c |
| 359 | 래미안길음뉴타운9단지 · 1km 학원 2곳 증가 | 1 | academy_growth-2713522de637 |
| 360 | 래미안당산1차아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-1f9b3fd0ccf2 |
| 361 | 래미안미드카운티 · 1km 학원 2곳 증가 | 1 | academy_growth-2aecab90e236 |
| 362 | 래미안미아1차 · 1km 학원 2곳 증가 | 1 | academy_growth-4abbb2748dbe |
| 363 | 래미안상도2차 · 1km 학원 2곳 증가 | 1 | academy_growth-fc41c7bc1266 |
| 364 | 래미안상도3차 · 1km 학원 2곳 증가 | 1 | academy_growth-7f12e39a79c7 |
| 365 | 래미안석관 · 1km 학원 2곳 증가 | 1 | academy_growth-ec21405cfa50 |
| 366 | 래미안신당하이베르 · 1km 학원 2곳 증가 | 1 | academy_growth-9d027838f5a5 |
| 367 | 래미안아름숲 · 1km 학원 2곳 증가 | 1 | academy_growth-7cbe414f776c |
| 368 | 래미안아름숲임대 · 1km 학원 2곳 증가 | 1 | academy_growth-f72d6bd9500f |
| 369 | 래미안아트리치 · 1km 학원 2곳 증가 | 1 | academy_growth-9b182cf6fbd5 |
| 370 | 래미안원베일리 · 1km 학원 2곳 증가 | 1 | academy_growth-9e6db4dab61b |
| 371 | 래미안위브 · 1km 학원 2곳 증가 | 1 | academy_growth-dbbe12d8594e |
| 372 | 래미안크레시티 · 1km 학원 2곳 증가 | 1 | academy_growth-a9b3ba7320ce |
| 373 | 롯데캐슬 · 1km 학원 2곳 증가 | 1 | academy_growth-680d2f57a633 |
| 374 | 롯데캐슬노블레스 · 1km 학원 2곳 증가 | 1 | academy_growth-bd728372cfce |
| 375 | 롯데캐슬루나 · 1km 학원 2곳 증가 | 1 | academy_growth-7c860ecc9db1 |
| 376 | 롯데캐슬리베아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-4958ded6e4f6 |
| 377 | 롯데캐슬베네치아 · 1km 학원 2곳 증가 | 1 | academy_growth-b445ec1470dc |
| 378 | 롯데캐슬클라시아 · 1km 학원 2곳 증가 | 1 | academy_growth-806cd3f665a1 |
| 379 | 마곡엠밸리10단지 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-8e683e77b652 |
| 380 | 마곡엠밸리7단지 · 1km 학원 2곳 증가 | 1 | academy_growth-dcf5728a6465 |
| 381 | 마천금호 · 1km 학원 2곳 증가 | 1 | academy_growth-1f4231102d84 |
| 382 | 목동1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-999c76f99660 |
| 383 | 목동2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-7d895cecdf56 |
| 384 | 목동2차삼성래미안 · 1km 학원 2곳 증가 | 1 | academy_growth-10eab0c5b6e7 |
| 385 | 목동8단지 · 1km 학원 2곳 증가 | 1 | academy_growth-6bf5d56504cd |
| 386 | 목동e-편한세상 · 1km 학원 2곳 증가 | 1 | academy_growth-6b737aeb5dd6 |
| 387 | 목동금호1차 · 1km 학원 2곳 증가 | 1 | academy_growth-7e4c2e8912b8 |
| 388 | 목동대림2차 · 1km 학원 2곳 증가 | 1 | academy_growth-3e1e102f77a0 |
| 389 | 목동부영그린타운2차 · 1km 학원 2곳 증가 | 1 | academy_growth-211596b2d861 |
| 390 | 목동삼익 · 1km 학원 2곳 증가 | 1 | academy_growth-88e0c63127c5 |
| 391 | 목동진도2차 · 1km 학원 2곳 증가 | 1 | academy_growth-de3bcfa3d1f0 |
| 392 | 목동진도아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-82a7e950d3af |
| 393 | 목동현대1차 · 1km 학원 2곳 증가 | 1 | academy_growth-f12a4d076cc1 |
| 394 | 목동현대A · 1km 학원 2곳 증가 | 1 | academy_growth-76d8b29406df |
| 395 | 목동현대아이파크 · 1km 학원 2곳 증가 | 1 | academy_growth-c259aa83e8ad |
| 396 | 목동현대하이페리온 · 1km 학원 2곳 증가 | 1 | academy_growth-3c5eef313344 |
| 397 | 문정3차푸르지오 · 1km 학원 2곳 증가 | 1 | academy_growth-c10bbb962c3b |
| 398 | 문정세양청마루 · 1km 학원 2곳 증가 | 1 | academy_growth-484150eb161f |
| 399 | 반포 르엘 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-a041f27836b4 |
| 400 | 반포경남 · 1km 학원 2곳 증가 | 1 | academy_growth-bd12026adba1 |
| 401 | 반포래미안아이파크 · 1km 학원 2곳 증가 | 1 | academy_growth-b2f94cce0d16 |
| 402 | 반포미도2차 · 1km 학원 2곳 증가 | 1 | academy_growth-7c7f91b25365 |
| 403 | 반포미도아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ab66a07e14ca |
| 404 | 반포한신서래 · 1km 학원 2곳 증가 | 1 | academy_growth-911bb94c832f |
| 405 | 반포한신타워 · 1km 학원 2곳 증가 | 1 | academy_growth-76b35e9a0d10 |
| 406 | 반포현대동궁 · 1km 학원 2곳 증가 | 1 | academy_growth-bb8f35b5cef6 |
| 407 | 방배2차현대홈타운 · 1km 학원 2곳 증가 | 1 | academy_growth-c9d58b7be56c |
| 408 | 방배SH-VILLE · 1km 학원 2곳 증가 | 1 | academy_growth-b94735238722 |
| 409 | 방배래미안 · 1km 학원 2곳 증가 | 1 | academy_growth-c21c752a3709 |
| 410 | 방배우성 · 1km 학원 2곳 증가 | 1 | academy_growth-79090f11367d |
| 411 | 방학4단지신동아 · 1km 학원 2곳 증가 | 1 | academy_growth-ddbef1a77d23 |
| 412 | 방학거성학마을 · 1km 학원 2곳 증가 | 1 | academy_growth-934260574d31 |
| 413 | 방학명품ESA2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-7586bf750c67 |
| 414 | 방학삼성래미안2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-dd36e9d368f3 |
| 415 | 방학삼익세라믹 · 1km 학원 2곳 증가 | 1 | academy_growth-8026ab052f4e |
| 416 | 방학성원 · 1km 학원 2곳 증가 | 1 | academy_growth-ae33bef023ef |
| 417 | 방학신동아1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-e8429a85b039 |
| 418 | 방학지음재힐스 · 1km 학원 2곳 증가 | 1 | academy_growth-2be5997ebbfb |
| 419 | 방학청구 · 1km 학원 2곳 증가 | 1 | academy_growth-3f4989fb2178 |
| 420 | 방학한화성원 · 1km 학원 2곳 증가 | 1 | academy_growth-65b3ccc86d8e |
| 421 | 번동1단지주공아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-434b98d7ca4e |
| 422 | 번동기산그린 · 1km 학원 2곳 증가 | 1 | academy_growth-8bfaedcfa0ef |
| 423 | 번동동문아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-522e56cad021 |
| 424 | 번동솔그린 · 1km 학원 2곳 증가 | 1 | academy_growth-9107665f9235 |
| 425 | 번동신원 · 1km 학원 2곳 증가 | 1 | academy_growth-686cbc5e440f |
| 426 | 번동주공2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-60a9b42aec39 |
| 427 | 번동주공3단지 · 1km 학원 2곳 증가 | 1 | academy_growth-2c5988ae185b |
| 428 | 번동한솔솔파크 · 1km 학원 2곳 증가 | 1 | academy_growth-cde07e4e0be4 |
| 429 | 번동한양 · 1km 학원 2곳 증가 | 1 | academy_growth-da4301ccc1d6 |
| 430 | 번동한진 · 1km 학원 2곳 증가 | 1 | academy_growth-e512c21e7e9f |
| 431 | 벽산라이브파크 · 1km 학원 2곳 증가 | 1 | academy_growth-923f71bf6c1e |
| 432 | 봉천동아제2 · 1km 학원 2곳 증가 | 1 | academy_growth-caf90ecc4fa3 |
| 433 | 봉천벽산타운2차 · 1km 학원 2곳 증가 | 1 | academy_growth-586616e57706 |
| 434 | 북서울자이 폴라리스 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-f5d2935686eb |
| 435 | 북한산래미안임대 · 1km 학원 2곳 증가 | 1 | academy_growth-cf2ad9dc75e6 |
| 436 | 북한산수자인 · 1km 학원 2곳 증가 | 1 | academy_growth-c7ebfcb0682a |
| 437 | 북한산현대홈타운 · 1km 학원 2곳 증가 | 1 | academy_growth-d4914db75145 |
| 438 | 북한산힐스테이트1차 · 1km 학원 2곳 증가 | 1 | academy_growth-78b1f75271f3 |
| 439 | 북한산힐스테이트3차아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-476a852d8a88 |
| 440 | 불광대호2차 · 1km 학원 2곳 증가 | 1 | academy_growth-8ea2c4e86950 |
| 441 | 불광롯데캐슬 · 1km 학원 2곳 증가 | 1 | academy_growth-babe6cad5735 |
| 442 | 브라운스톤 방학아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ddac6a05221c |
| 443 | 사당 대림아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-3e387cbf7cdb |
| 444 | 사당경남아너스빌 · 1km 학원 2곳 증가 | 1 | academy_growth-9904d88a0f27 |
| 445 | 사당대아2차 · 1km 학원 2곳 증가 | 1 | academy_growth-5704af69e76e |
| 446 | 사당동작삼성래미안아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-162b49a7ebe2 |
| 447 | 사당롯데캐슬 · 1km 학원 2곳 증가 | 1 | academy_growth-6ad45a8dc2b2 |
| 448 | 사당유니드 · 1km 학원 2곳 증가 | 1 | academy_growth-45c998a2a848 |
| 449 | 사당진흥아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ee1b7749b067 |
| 450 | 사당현대아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ba385a4cabb0 |
| 451 | 사당휴먼시아 · 1km 학원 2곳 증가 | 1 | academy_growth-2d63d6ff1b57 |
| 452 | 삼익포레스트아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-94f2e147d3a7 |
| 453 | 상계 대창센시티 · 1km 학원 2곳 증가 | 1 | academy_growth-da0e6a4c2e18 |
| 454 | 상계17단지 · 1km 학원 2곳 증가 | 1 | academy_growth-e38401dd22e4 |
| 455 | 상계3차현대아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-e1d3588785ea |
| 456 | 상계대림e-편한세상 · 1km 학원 2곳 증가 | 1 | academy_growth-9a46faf058b6 |
| 457 | 상계주공16단지 · 1km 학원 2곳 증가 | 1 | academy_growth-afe48219ef04 |
| 458 | 상계주공1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-5d28934e1341 |
| 459 | 상계주공2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-68f4baf3b15b |
| 460 | 상계주공3단지 · 1km 학원 2곳 증가 | 1 | academy_growth-64e799cc5a60 |
| 461 | 상계주공4단지 · 1km 학원 2곳 증가 | 1 | academy_growth-c41e3b1b2181 |
| 462 | 상계중앙하이츠아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-29cbf3d979cb |
| 463 | 상계현대1차 · 1km 학원 2곳 증가 | 1 | academy_growth-d7505b72c56d |
| 464 | 상계현대2차 · 1km 학원 2곳 증가 | 1 | academy_growth-5fd64e64554a |
| 465 | 상도 푸르지오 클라베뉴 · 1km 학원 2곳 증가 | 1 | academy_growth-0d5ca8de219c |
| 466 | 상도 휴엔하임 도시형생횔주택 · 1km 학원 2곳 증가 | 1 | academy_growth-23014005755f |
| 467 | 상도1동대림 · 1km 학원 2곳 증가 | 1 | academy_growth-9c06833db8bc |
| 468 | 상도더샵2차 · 1km 학원 2곳 증가 | 1 | academy_growth-19e5544c5bf8 |
| 469 | 상도동원베네스트 · 1km 학원 2곳 증가 | 1 | academy_growth-e4ac6c3b48e9 |
| 470 | 상도동중앙하이츠빌아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-9bada5dd4d2b |
| 471 | 상도래미안1차 · 1km 학원 2곳 증가 | 1 | academy_growth-ecf21e497793 |
| 472 | 상도래미안1차제2 · 1km 학원 2곳 증가 | 1 | academy_growth-840700beba93 |
| 473 | 상도삼호 · 1km 학원 2곳 증가 | 1 | academy_growth-669a75b59f41 |
| 474 | 상도역롯데캐슬파크엘 · 1km 학원 2곳 증가 | 1 | academy_growth-875531e428d7 |
| 475 | 상도파크자이 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-376a8df33a1d |
| 476 | 상도현대 · 1km 학원 2곳 증가 | 1 | academy_growth-78a9d63a0672 |
| 477 | 상도효성해링턴플레이스 · 1km 학원 2곳 증가 | 1 | academy_growth-dc6696c8357a |
| 478 | 서울 왕십리 KCC스위첸아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-f21c7a742859 |
| 479 | 서울대입구삼성아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-f08afc65461c |
| 480 | 서울숲대림아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-ad4a994ff12b |
| 481 | 서울숲더샵 · 1km 학원 2곳 증가 | 1 | academy_growth-660bdfd0b79b |
| 482 | 서울숲아이파크리버포레 · 1km 학원 2곳 증가 | 1 | academy_growth-933daa423976 |
| 483 | 서울숲행당푸르지오 · 1km 학원 2곳 증가 | 1 | academy_growth-7a8ed7e727b3 |
| 484 | 서원아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-5ce98b3afbda |
| 485 | 서초트라팰리스1차 · 1km 학원 2곳 증가 | 1 | academy_growth-59efd51c0a61 |
| 486 | 석계역우남아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-a4a158dada5f |
| 487 | 성내2차e-편한세상 · 1km 학원 2곳 증가 | 1 | academy_growth-254f9aa54302 |
| 488 | 성내현대 · 1km 학원 2곳 증가 | 1 | academy_growth-ccf98077a0a1 |
| 489 | 성동삼성쉐르빌 · 1km 학원 2곳 증가 | 1 | academy_growth-5b86f5b96117 |
| 490 | 성수2차대우 · 1km 학원 2곳 증가 | 1 | academy_growth-5ff51b5d9603 |
| 491 | 성수동아 · 1km 학원 2곳 증가 | 1 | academy_growth-546e85bb15d1 |
| 492 | 성수우방2차 · 1km 학원 2곳 증가 | 1 | academy_growth-b71b826d77b2 |
| 493 | 센트라스 · 1km 학원 2곳 증가 | 1 | academy_growth-1ec5bdc452b7 |
| 494 | 셀립은평 · 1km 학원 2곳 증가 | 1 | academy_growth-42c26d62b4c4 |
| 495 | 송파 시그니처 롯데캐슬아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-bcb9ce28bf5a |
| 496 | 송파레미니스아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-a086c41f89d8 |
| 497 | 송파미성 · 1km 학원 2곳 증가 | 1 | academy_growth-670d56ed46be |
| 498 | 송파해모로아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-1b3e4a5e3750 |
| 499 | 송파현대1차 · 1km 학원 2곳 증가 | 1 | academy_growth-599c716beeac |
| 500 | 송학휴스테이아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-9b9ae5bd80d8 |
| 501 | 신당 파인힐 하나유보라 · 1km 학원 2곳 증가 | 1 | academy_growth-d32f877ec704 |
| 502 | 신당KCC스위첸아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-890983a04f3b |
| 503 | 신동아 · 1km 학원 2곳 증가 | 1 | academy_growth-1f4f8a74ecdf |
| 504 | 신동아파밀리에 · 1km 학원 2곳 증가 | 1 | academy_growth-66af4ee6e48a |
| 505 | 신반포 한신 25,26,27차 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-141f11017390 |
| 506 | 신반포22 · 1km 학원 2곳 증가 | 1 | academy_growth-e28909f1fe28 |
| 507 | 신반포5차 · 1km 학원 2곳 증가 | 1 | academy_growth-9e1cf2a57372 |
| 508 | 신반포7차 · 1km 학원 2곳 증가 | 1 | academy_growth-b4fedc256b14 |
| 509 | 신반포자이아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-fe0e0cf8dc09 |
| 510 | 신반포청구 · 1km 학원 2곳 증가 | 1 | academy_growth-22102951b8e5 |
| 511 | 신반포한신19차 · 1km 학원 2곳 증가 | 1 | academy_growth-bb353132b193 |
| 512 | 신반포한신23차 · 1km 학원 2곳 증가 | 1 | academy_growth-3f77804a4011 |
| 513 | 신반포한신2차 · 1km 학원 2곳 증가 | 1 | academy_growth-64009da12845 |
| 514 | 신설동 지웰홈스 · 1km 학원 2곳 증가 | 1 | academy_growth-705fe4893b27 |
| 515 | 신정대림 · 1km 학원 2곳 증가 | 1 | academy_growth-57b0d17a7551 |
| 516 | 신정명지해드는터 · 1km 학원 2곳 증가 | 1 | academy_growth-286b5ca0c429 |
| 517 | 신정삼성SH임대 · 1km 학원 2곳 증가 | 1 | academy_growth-e356cb0a8b6f |
| 518 | 신정쌍용 · 1km 학원 2곳 증가 | 1 | academy_growth-8e57136aa586 |
| 519 | 신정양천 · 1km 학원 2곳 증가 | 1 | academy_growth-39c4f5e91227 |
| 520 | 신정청구아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-0b8e40b73152 |
| 521 | 신정현대 · 1km 학원 2곳 증가 | 1 | academy_growth-f26d72446aa3 |
| 522 | 신천장미1차2차 · 1km 학원 2곳 증가 | 1 | academy_growth-e0ebc5bd9d4b |
| 523 | 신한토탈아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-8928ed4374ad |
| 524 | 아이파크상도동 · 1km 학원 2곳 증가 | 1 | academy_growth-f7d99cf482a7 |
| 525 | 아크로리버뷰 신반포 · 1km 학원 2곳 증가 | 1 | academy_growth-8c3fdaa05a41 |
| 526 | 압구정 현대(10,13,14차) · 1km 학원 2곳 증가 | 1 | academy_growth-d95c511248e5 |
| 527 | 압구정신현대 · 1km 학원 2곳 증가 | 1 | academy_growth-b08f72f1fae0 |
| 528 | 압구정한양3단지 · 1km 학원 2곳 증가 | 1 | academy_growth-0535bb8ab43e |
| 529 | 양재SK허브프리모 · 1km 학원 2곳 증가 | 1 | academy_growth-fe48843ffd27 |
| 530 | 어바니엘 천호 · 1km 학원 2곳 증가 | 1 | academy_growth-362a9edef1d6 |
| 531 | 역삼개나리 · 1km 학원 2곳 증가 | 1 | academy_growth-ac49f287aa77 |
| 532 | 역삼경남 · 1km 학원 2곳 증가 | 1 | academy_growth-588660edffa9 |
| 533 | 역삼자이아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-e327420ee896 |
| 534 | 왕십리 자이 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-210c320a5c91 |
| 535 | 왕십리주상복합 · 1km 학원 2곳 증가 | 1 | academy_growth-3c05db9f66cf |
| 536 | 왕십리텐즈힐1단지(임대) · 1km 학원 2곳 증가 | 1 | academy_growth-3cfb564ec304 |
| 537 | 왕십리텐즈힐2구역214동 · 1km 학원 2곳 증가 | 1 | academy_growth-cf0894624192 |
| 538 | 우리유앤미 · 1km 학원 2곳 증가 | 1 | academy_growth-fb6492ffe331 |
| 539 | 원에디션강남 · 1km 학원 2곳 증가 | 1 | academy_growth-d20e4beaa9a1 |
| 540 | 월계2차한일 · 1km 학원 2곳 증가 | 1 | academy_growth-fa0acad0734e |
| 541 | 월계극동 · 1km 학원 2곳 증가 | 1 | academy_growth-a0a47cadcf87 |
| 542 | 월계대동 · 1km 학원 2곳 증가 | 1 | academy_growth-e52a74e08137 |
| 543 | 월계서광 · 1km 학원 2곳 증가 | 1 | academy_growth-6c1abf1b006b |
| 544 | 월계시영고층 · 1km 학원 2곳 증가 | 1 | academy_growth-e4c089621a2b |
| 545 | 월계유원 · 1km 학원 2곳 증가 | 1 | academy_growth-76538e2cc6e8 |
| 546 | 월계주공1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-7ac39b9a47dc |
| 547 | 월계주공2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-0d191ea3fc01 |
| 548 | 월계초안산쌍용 · 1km 학원 2곳 증가 | 1 | academy_growth-16ea9ece1ed9 |
| 549 | 월계풍림아이원 · 1km 학원 2곳 증가 | 1 | academy_growth-09dd17ef0be1 |
| 550 | 월계한일1차 · 1km 학원 2곳 증가 | 1 | academy_growth-422d099bac4e |
| 551 | 유원목동 · 1km 학원 2곳 증가 | 1 | academy_growth-31525ad7911e |
| 552 | 응봉금호현대 · 1km 학원 2곳 증가 | 1 | academy_growth-3eb96ea00958 |
| 553 | 응봉대림2차 · 1km 학원 2곳 증가 | 1 | academy_growth-03bb2f36873c |
| 554 | 이문1차푸르지오 · 1km 학원 2곳 증가 | 1 | academy_growth-b65901df655d |
| 555 | 이문쌍용 · 1km 학원 2곳 증가 | 1 | academy_growth-9d96630c8a60 |
| 556 | 이문쌍용임대 · 1km 학원 2곳 증가 | 1 | academy_growth-35b533350b91 |
| 557 | 이문현대 · 1km 학원 2곳 증가 | 1 | academy_growth-8603070c304e |
| 558 | 이문현대임대 · 1km 학원 2곳 증가 | 1 | academy_growth-e090345e7891 |
| 559 | 이수푸르지오더프레티움 · 1km 학원 2곳 증가 | 1 | academy_growth-5feefbad54d9 |
| 560 | 이편한세상 송파파크센트럴 · 1km 학원 2곳 증가 | 1 | academy_growth-4c8687fc6b76 |
| 561 | 잠실아시아선수촌 · 1km 학원 2곳 증가 | 1 | academy_growth-0bd270b7dce8 |
| 562 | 잠실우성4차 · 1km 학원 2곳 증가 | 1 | academy_growth-00fdd955c0eb |
| 563 | 잠실한양3차 · 1km 학원 2곳 증가 | 1 | academy_growth-5619e2a08fdf |
| 564 | 잠원킴스빌리지 · 1km 학원 2곳 증가 | 1 | academy_growth-18709971a016 |
| 565 | 잠원한신그린 · 1km 학원 2곳 증가 | 1 | academy_growth-75e71d59da44 |
| 566 | 잠원한신로얄 · 1km 학원 2곳 증가 | 1 | academy_growth-9e123e6253ac |
| 567 | 장위아트포레아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-b764b713a0e7 |
| 568 | 전농SK · 1km 학원 2곳 증가 | 1 | academy_growth-2d38705e50ca |
| 569 | 전농동신성미소지움아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-b38fe301a99e |
| 570 | 정릉우성 · 1km 학원 2곳 증가 | 1 | academy_growth-3c03c29fe317 |
| 571 | 정릉중앙하이츠빌2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-8021a19dc432 |
| 572 | 정릉힐스테이트1차아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-2252425c2ead |
| 573 | 종로청계힐스테이트 · 1km 학원 2곳 증가 | 1 | academy_growth-d15c39cf4d71 |
| 574 | 중계주공2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-530d3a4976c9 |
| 575 | 중명하니빌 · 1km 학원 2곳 증가 | 1 | academy_growth-abed9fe4300e |
| 576 | 중화극동 · 1km 학원 2곳 증가 | 1 | academy_growth-9146803dcd4f |
| 577 | 창동금호어울림 · 1km 학원 2곳 증가 | 1 | academy_growth-58fb29fc8e3c |
| 578 | 창동대동 · 1km 학원 2곳 증가 | 1 | academy_growth-2e80c1227665 |
| 579 | 창동대우그린아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-3a49e578c57b |
| 580 | 창동동아 · 1km 학원 2곳 증가 | 1 | academy_growth-11f0608bf4ab |
| 581 | 창동북한산아이파크 · 1km 학원 2곳 증가 | 1 | academy_growth-85c133df9377 |
| 582 | 창동삼성 · 1km 학원 2곳 증가 | 1 | academy_growth-329f424abc90 |
| 583 | 창동아이파크(창동2.3차현대) · 1km 학원 2곳 증가 | 1 | academy_growth-8566ae89da52 |
| 584 | 창동주공18단지 · 1km 학원 2곳 증가 | 1 | academy_growth-f4faa27f8521 |
| 585 | 창동주공19단지 · 1km 학원 2곳 증가 | 1 | academy_growth-c5f9efe808bc |
| 586 | 창동주공2단지 · 1km 학원 2곳 증가 | 1 | academy_growth-fc1fc36c841b |
| 587 | 창동주공4단지 · 1km 학원 2곳 증가 | 1 | academy_growth-b38efa5b8d88 |
| 588 | 창동현대 · 1km 학원 2곳 증가 | 1 | academy_growth-5d2773c8854b |
| 589 | 천호두산위브센티움 · 1km 학원 2곳 증가 | 1 | academy_growth-3d5efdcaac5d |
| 590 | 천호역한강청년주택 · 1km 학원 2곳 증가 | 1 | academy_growth-b13ef743120c |
| 591 | 천호코오롱 · 1km 학원 2곳 증가 | 1 | academy_growth-58f36fbc161c |
| 592 | 천호태영 · 1km 학원 2곳 증가 | 1 | academy_growth-965ee9cddcf6 |
| 593 | 천호태영임대 · 1km 학원 2곳 증가 | 1 | academy_growth-3beb721956f5 |
| 594 | 천호현대 · 1km 학원 2곳 증가 | 1 | academy_growth-8a9ad157739c |
| 595 | 천호현대타워 · 1km 학원 2곳 증가 | 1 | academy_growth-d0f8b871db19 |
| 596 | 청계천두산위브더제니스 · 1km 학원 2곳 증가 | 1 | academy_growth-c93749af7762 |
| 597 | 청광플러스원 아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-80be2b5d2138 |
| 598 | 청담2차현대아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-9ee85298e59f |
| 599 | 청담삼환 · 1km 학원 2곳 증가 | 1 | academy_growth-3fc0fa3c5e11 |
| 600 | 테헤란 IPARK · 1km 학원 2곳 증가 | 1 | academy_growth-716641372a92 |
| 601 | 텐즈힐1단지 · 1km 학원 2곳 증가 | 1 | academy_growth-b14d1b41facb |
| 602 | 텐즈힐2구역 · 1km 학원 2곳 증가 | 1 | academy_growth-6f7680942136 |
| 603 | 포레나 당산 · 1km 학원 2곳 증가 | 1 | academy_growth-e89e93a4d8ae |
| 604 | 풍납동아한가람 · 1km 학원 2곳 증가 | 1 | academy_growth-ffda8f81d013 |
| 605 | 풍납쌍용 · 1km 학원 2곳 증가 | 1 | academy_growth-fd7635c5a6ad |
| 606 | 풍납현대 · 1km 학원 2곳 증가 | 1 | academy_growth-efbba57413a6 |
| 607 | 하왕금호베스트빌 · 1km 학원 2곳 증가 | 1 | academy_growth-7c30ff37259a |
| 608 | 한양현대아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-fd83b3da4570 |
| 609 | 한진해모로 · 1km 학원 2곳 증가 | 1 | academy_growth-a25e554ad9d5 |
| 610 | 행당대림 · 1km 학원 2곳 증가 | 1 | academy_growth-26afa8f34e63 |
| 611 | 행당대림제2 · 1km 학원 2곳 증가 | 1 | academy_growth-2cd6ec9ae088 |
| 612 | 행당두산위브아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-2bd001a8bfac |
| 613 | 행당두산위브임대 · 1km 학원 2곳 증가 | 1 | academy_growth-e2897bb7d70a |
| 614 | 행당브라운스톤 · 1km 학원 2곳 증가 | 1 | academy_growth-d1d7a4327384 |
| 615 | 행당푸르지오임대 · 1km 학원 2곳 증가 | 1 | academy_growth-48bc38f1edcb |
| 616 | 행당한진타운 · 1km 학원 2곳 증가 | 1 | academy_growth-1be897c46780 |
| 617 | 헬리오시티아파트 · 1km 학원 2곳 증가 | 1 | academy_growth-9a58959eda5d |
| 618 | 현대비전21 · 1km 학원 2곳 증가 | 1 | academy_growth-00cf78ad10e4 |
| 619 | 황학아크로타워 · 1km 학원 2곳 증가 | 1 | academy_growth-c2712d5b9804 |
| 620 | 황학코아루 · 1km 학원 2곳 증가 | 1 | academy_growth-a609b660ac2d |
| 621 | 흑석동양 · 1km 학원 2곳 증가 | 1 | academy_growth-1ee30c4f1d51 |
| 622 | 힐스테이트 천호역 젠트리스 · 1km 학원 2곳 증가 | 1 | academy_growth-a8b9f0ddb76f |
| 623 | 힐스테이트관악센트씨엘 · 1km 학원 2곳 증가 | 1 | academy_growth-1bbc7f6560fb |
| 624 | 힐스테이트상도센트럴파크 · 1km 학원 2곳 증가 | 1 | academy_growth-5a84d91e3d4a |
| 625 | 힐스테이트상도프레스티지 · 1km 학원 2곳 증가 | 1 | academy_growth-cc98181600b2 |
| 626 | H하우스 대림 뉴스테이 · 1km 학원 1곳 증가 | 1 | academy_growth-5c71fdf9a148 |
| 627 | SK북한산시티아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-29a1a6193b10 |
| 628 | e편한세상 청계 센트럴포레 · 1km 학원 1곳 증가 | 1 | academy_growth-9bdc9559c871 |
| 629 | e편한세상마포리버파크 · 1km 학원 1곳 증가 | 1 | academy_growth-0c589a18c2c4 |
| 630 | e편한세상서울대입구1단지아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-4e21f626486e |
| 631 | 가락삼익맨숀 · 1km 학원 1곳 증가 | 1 | academy_growth-8feef4a9c840 |
| 632 | 가락프라자 · 1km 학원 1곳 증가 | 1 | academy_growth-d435bb3a9b21 |
| 633 | 가락한신 · 1km 학원 1곳 증가 | 1 | academy_growth-6325ca68439b |
| 634 | 가산두산위브 · 1km 학원 1곳 증가 | 1 | academy_growth-f413a0d80e1c |
| 635 | 가산삼익아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-97f93e42a3bb |
| 636 | 강동중흥S-클래스 · 1km 학원 1곳 증가 | 1 | academy_growth-65a5bc326167 |
| 637 | 강변건영 · 1km 학원 1곳 증가 | 1 | academy_growth-93c617c1c348 |
| 638 | 강일리버파크10단지 · 1km 학원 1곳 증가 | 1 | academy_growth-dae196403936 |
| 639 | 강일리버파크11단지 · 1km 학원 1곳 증가 | 1 | academy_growth-a4ab48d3d3b2 |
| 640 | 강일리버파크6단지 · 1km 학원 1곳 증가 | 1 | academy_growth-2aaf8971be67 |
| 641 | 강일리버파크8단지 · 1km 학원 1곳 증가 | 1 | academy_growth-ead3976cf074 |
| 642 | 강일리버파크9단지 · 1km 학원 1곳 증가 | 1 | academy_growth-aa40af1e622a |
| 643 | 개봉대상아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-7ce5d3d405a5 |
| 644 | 개봉한진 · 1km 학원 1곳 증가 | 1 | academy_growth-69486341affd |
| 645 | 개포2차 현대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-92696f28dbb8 |
| 646 | 개포7차우성 · 1km 학원 1곳 증가 | 1 | academy_growth-9757157d2569 |
| 647 | 개포경남아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-df6ddb71298a |
| 648 | 개포상록스타힐스 · 1km 학원 1곳 증가 | 1 | academy_growth-8c595e4c7d28 |
| 649 | 개포우성5차 · 1km 학원 1곳 증가 | 1 | academy_growth-dd7ed4fadf82 |
| 650 | 개포우성8차 · 1km 학원 1곳 증가 | 1 | academy_growth-9c5823164d58 |
| 651 | 개포주공4단지 · 1km 학원 1곳 증가 | 1 | academy_growth-dd6bcd58fd19 |
| 652 | 개포주공6단지 · 1km 학원 1곳 증가 | 1 | academy_growth-1a1671dfd671 |
| 653 | 개포주공7단지 · 1km 학원 1곳 증가 | 1 | academy_growth-2fb77491a703 |
| 654 | 거여현대3차 · 1km 학원 1곳 증가 | 1 | academy_growth-b9c352647433 |
| 655 | 거평 · 1km 학원 1곳 증가 | 1 | academy_growth-195f48e46797 |
| 656 | 거평프리젠 · 1km 학원 1곳 증가 | 1 | academy_growth-a996d917d7bf |
| 657 | 경희궁 롯데캐슬아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-ce23e7b213c3 |
| 658 | 경희궁 유보라 · 1km 학원 1곳 증가 | 1 | academy_growth-7ee31fc2dd94 |
| 659 | 경희궁의아침3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-79b4df845ff7 |
| 660 | 경희궁자이1단지(임대아파트) · 1km 학원 1곳 증가 | 1 | academy_growth-fe2d12771f14 |
| 661 | 경희궁자이2단지 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-271ccee3b174 |
| 662 | 경희궁자이3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-c9955b67f677 |
| 663 | 경희궁자이4단지주상복합 · 1km 학원 1곳 증가 | 1 | academy_growth-8f16ba99d42d |
| 664 | 고덕숲아이파크아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-2ee4ba15b282 |
| 665 | 고덕아이파크아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-d43f12357123 |
| 666 | 공덕SK리더스뷰 1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-fdb2dba03836 |
| 667 | 공덕동 크로시티 행복주택 · 1km 학원 1곳 증가 | 1 | academy_growth-cbf3966a0963 |
| 668 | 공덕아이파크 · 1km 학원 1곳 증가 | 1 | academy_growth-5e842a060ed3 |
| 669 | 공릉1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-a02b873c1c00 |
| 670 | 공릉2단지라이프 · 1km 학원 1곳 증가 | 1 | academy_growth-9242374043b4 |
| 671 | 공릉2차신도브래뉴아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-4e9b2a10637b |
| 672 | 공릉3단지라이프 · 1km 학원 1곳 증가 | 1 | academy_growth-84ccd70e6cc5 |
| 673 | 공릉건영장미 · 1km 학원 1곳 증가 | 1 | academy_growth-1d7051fd2014 |
| 674 | 공릉대동1차 · 1km 학원 1곳 증가 | 1 | academy_growth-9cb955c4da3d |
| 675 | 공릉대동2차 · 1km 학원 1곳 증가 | 1 | academy_growth-9d6b07c07fc3 |
| 676 | 공릉대아2차 · 1km 학원 1곳 증가 | 1 | academy_growth-366f004852c5 |
| 677 | 공릉대주파크빌 · 1km 학원 1곳 증가 | 1 | academy_growth-9ad54fb4fdc1 |
| 678 | 공릉동신 · 1km 학원 1곳 증가 | 1 | academy_growth-119a7799a70d |
| 679 | 공릉삼익4단지 · 1km 학원 1곳 증가 | 1 | academy_growth-f6a450df3955 |
| 680 | 공릉신도1차 · 1km 학원 1곳 증가 | 1 | academy_growth-5ae4a569fd58 |
| 681 | 공릉신원 · 1km 학원 1곳 증가 | 1 | academy_growth-be89feff6805 |
| 682 | 공릉우성 · 1km 학원 1곳 증가 | 1 | academy_growth-9f26a2608aee |
| 683 | 공릉풍림아이원 · 1km 학원 1곳 증가 | 1 | academy_growth-35b5a2a858cf |
| 684 | 공릉한보아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-103b2af236c0 |
| 685 | 관악벽산블루밍 · 1km 학원 1곳 증가 | 1 | academy_growth-596669eccde6 |
| 686 | 관악월드메르디앙아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-d1d7decca218 |
| 687 | 구로우방 · 1km 학원 1곳 증가 | 1 | academy_growth-842a7e20cc97 |
| 688 | 구로우성 · 1km 학원 1곳 증가 | 1 | academy_growth-0a4f03877fc9 |
| 689 | 구로월드 · 1km 학원 1곳 증가 | 1 | academy_growth-bf930ab59e60 |
| 690 | 구로주공 · 1km 학원 1곳 증가 | 1 | academy_growth-37ae4885cdfa |
| 691 | 구로현대상선 · 1km 학원 1곳 증가 | 1 | academy_growth-7adb7fc65fe2 |
| 692 | 구로현대연예인 · 1km 학원 1곳 증가 | 1 | academy_growth-99d5c58b84c6 |
| 693 | 그랑빌 · 1km 학원 1곳 증가 | 1 | academy_growth-f92c91488ff8 |
| 694 | 금호벽산 · 1km 학원 1곳 증가 | 1 | academy_growth-5642b0c892c9 |
| 695 | 금호벽산(임대) · 1km 학원 1곳 증가 | 1 | academy_growth-1f74dfaa0761 |
| 696 | 금호어울림 · 1km 학원 1곳 증가 | 1 | academy_growth-3353e2cefb02 |
| 697 | 금호어울림(삼성동) · 1km 학원 1곳 증가 | 1 | academy_growth-736d5d57e34f |
| 698 | 길음삼부 · 1km 학원 1곳 증가 | 1 | academy_growth-f5959bee0cf3 |
| 699 | 길음역 롯데캐슬 트윈골드 · 1km 학원 1곳 증가 | 1 | academy_growth-fb3b6702c753 |
| 700 | 남서울럭키아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-51b900481cfb |
| 701 | 남서울힐스테이트 · 1km 학원 1곳 증가 | 1 | academy_growth-9074206ce29f |
| 702 | 냉천동부센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-eb60348dbcd1 |
| 703 | 논현동부센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-ac999fa5759c |
| 704 | 논현베르빌 · 1km 학원 1곳 증가 | 1 | academy_growth-ffbbdbf81192 |
| 705 | 논현쌍용 · 1km 학원 1곳 증가 | 1 | academy_growth-9d45f75dbb55 |
| 706 | 답십리두산 · 1km 학원 1곳 증가 | 1 | academy_growth-341708a18bb2 |
| 707 | 답십리두산제2 · 1km 학원 1곳 증가 | 1 | academy_growth-3bf42307bcf0 |
| 708 | 당산디오빌 · 1km 학원 1곳 증가 | 1 | academy_growth-d22a08d84a6c |
| 709 | 당산성원아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-cd6c9492dd03 |
| 710 | 당산유원제일1차 · 1km 학원 1곳 증가 | 1 | academy_growth-ae68e6032332 |
| 711 | 당산유원제일2차 · 1km 학원 1곳 증가 | 1 | academy_growth-edf72b9558dd |
| 712 | 당산진로 · 1km 학원 1곳 증가 | 1 | academy_growth-75b3c12a7aad |
| 713 | 당산현대3차 · 1km 학원 1곳 증가 | 1 | academy_growth-7ae5417a3cff |
| 714 | 대림아파트201동 · 1km 학원 1곳 증가 | 1 | academy_growth-93cf8370ff39 |
| 715 | 대망드림힐 · 1km 학원 1곳 증가 | 1 | academy_growth-3f5168e981d2 |
| 716 | 대방경남아너스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-ef51cabcb3fd |
| 717 | 대방동신일해피트리 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-ced6f7bb869d |
| 718 | 대방성원 · 1km 학원 1곳 증가 | 1 | academy_growth-3aa25d40f13b |
| 719 | 대방우정 · 1km 학원 1곳 증가 | 1 | academy_growth-72849ba87376 |
| 720 | 대방주공2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-d15af4786ad7 |
| 721 | 대방현대1차 · 1km 학원 1곳 증가 | 1 | academy_growth-1d9e570fb366 |
| 722 | 대우디오빌플러스 · 1km 학원 1곳 증가 | 1 | academy_growth-75f116ecaedd |
| 723 | 대우월드마크용산 · 1km 학원 1곳 증가 | 1 | academy_growth-975e9702dab7 |
| 724 | 대우한강베네시티 · 1km 학원 1곳 증가 | 1 | academy_growth-1b96a64c0a84 |
| 725 | 대원그린아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-c8b694a14030 |
| 726 | 덕수궁롯데캐슬아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-560ff741f46c |
| 727 | 도곡개포한신아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-9b107eeeba05 |
| 728 | 도곡동양재디오빌 · 1km 학원 1곳 증가 | 1 | academy_growth-19d775cf5bc9 |
| 729 | 도곡삼성래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-6aa74575fd2e |
| 730 | 도봉래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-50d667cc84c9 |
| 731 | 도봉럭키 · 1km 학원 1곳 증가 | 1 | academy_growth-2b54420cdecd |
| 732 | 도봉삼환 · 1km 학원 1곳 증가 | 1 | academy_growth-b9e4e8c8ffd9 |
| 733 | 도봉서광 · 1km 학원 1곳 증가 | 1 | academy_growth-1e60ff98d7cc |
| 734 | 도원삼성래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-e9dd30585fb9 |
| 735 | 도원삼성제2 · 1km 학원 1곳 증가 | 1 | academy_growth-0d78b61b25f0 |
| 736 | 도화현대 · 1km 학원 1곳 증가 | 1 | academy_growth-30a66783a1a8 |
| 737 | 도화현대1차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-a9f204be4bba |
| 738 | 도화현대2차아파트(임대) · 1km 학원 1곳 증가 | 1 | academy_growth-89c597021080 |
| 739 | 도화현대홈타운 · 1km 학원 1곳 증가 | 1 | academy_growth-da23ed1e9351 |
| 740 | 독립문극동 · 1km 학원 1곳 증가 | 1 | academy_growth-b78ee9c33e6d |
| 741 | 독립문극동임대 · 1km 학원 1곳 증가 | 1 | academy_growth-06742bdcec79 |
| 742 | 독립문삼호 · 1km 학원 1곳 증가 | 1 | academy_growth-b496f829eeb7 |
| 743 | 독립문파크빌 · 1km 학원 1곳 증가 | 1 | academy_growth-a2a523ce239b |
| 744 | 독산동한양수자인아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-186fb67939eb |
| 745 | 독산신도브래뉴 · 1km 학원 1곳 증가 | 1 | academy_growth-da8f11255352 |
| 746 | 돈암동부센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-af7279e9f99f |
| 747 | 돈암현대 · 1km 학원 1곳 증가 | 1 | academy_growth-644ce2b47a10 |
| 748 | 돈의문센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-b3f4225f8d14 |
| 749 | 동대문더퍼스트데시앙아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-19caf61ef77b |
| 750 | 동대문와이즈캐슬 · 1km 학원 1곳 증가 | 1 | academy_growth-33a52c08d1a4 |
| 751 | 동부아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-ec31b7518c0f |
| 752 | 동익빌라 · 1km 학원 1곳 증가 | 1 | academy_growth-11f9002ad2c1 |
| 753 | 동일하이빌뉴시티 · 1km 학원 1곳 증가 | 1 | academy_growth-9181592ed436 |
| 754 | 동작상떼빌주상복합 · 1km 학원 1곳 증가 | 1 | academy_growth-8bac8e460ed3 |
| 755 | 동진신안 · 1km 학원 1곳 증가 | 1 | academy_growth-da317a38fe65 |
| 756 | 두산아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-b8e075f0af2e |
| 757 | 라봄성동청년안심주택 · 1km 학원 1곳 증가 | 1 | academy_growth-d52219cc048b |
| 758 | 라이프미성 · 1km 학원 1곳 증가 | 1 | academy_growth-5f0630a1fef5 |
| 759 | 래미안길음1차 · 1km 학원 1곳 증가 | 1 | academy_growth-8dc67e59502a |
| 760 | 래미안길음센터피스 · 1km 학원 1곳 증가 | 1 | academy_growth-08eec1329b5e |
| 761 | 래미안대치하이스턴 · 1km 학원 1곳 증가 | 1 | academy_growth-ff87ad08aa5f |
| 762 | 래미안마포리버웰 · 1km 학원 1곳 증가 | 1 | academy_growth-99e9334e51cf |
| 763 | 래미안삼성1차103단지 · 1km 학원 1곳 증가 | 1 | academy_growth-09f8ade71cc5 |
| 764 | 래미안삼성1차104단지 · 1km 학원 1곳 증가 | 1 | academy_growth-fbcdf0438cab |
| 765 | 래미안세레니티 · 1km 학원 1곳 증가 | 1 | academy_growth-81715f9eb05f |
| 766 | 래미안송파파인탑 · 1km 학원 1곳 증가 | 1 | academy_growth-8c926771fa4a |
| 767 | 래미안신당하이베르임대 · 1km 학원 1곳 증가 | 1 | academy_growth-677f3da88ff5 |
| 768 | 래미안용강아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-fc9a4ddf37b2 |
| 769 | 래미안트리베라2차 · 1km 학원 1곳 증가 | 1 | academy_growth-2414838e4cbe |
| 770 | 래미안퍼스티지 · 1km 학원 1곳 증가 | 1 | academy_growth-63180f3a83ad |
| 771 | 롯데캐슬 리버파크 시그니처 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-12e03009485f |
| 772 | 롯데캐슬갤럭시아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-5fbaed9e00e6 |
| 773 | 롯데캐슬골드 · 1km 학원 1곳 증가 | 1 | academy_growth-055052e0de8e |
| 774 | 롯데캐슬노블 · 1km 학원 1곳 증가 | 1 | academy_growth-34e821a67568 |
| 775 | 롯데캐슬천지인 · 1km 학원 1곳 증가 | 1 | academy_growth-24dc22119a9e |
| 776 | 롯데캐슬클래식 · 1km 학원 1곳 증가 | 1 | academy_growth-15a9b63b0271 |
| 777 | 루미노816청년안심주택 · 1km 학원 1곳 증가 | 1 | academy_growth-f1321985dd5c |
| 778 | 리버뷰신안인스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-2ae1cf4d801d |
| 779 | 리첸시아용산 · 1km 학원 1곳 증가 | 1 | academy_growth-443adb10801d |
| 780 | 마곡 한진해모로 · 1km 학원 1곳 증가 | 1 | academy_growth-05c34e7823b9 |
| 781 | 마곡삼성 · 1km 학원 1곳 증가 | 1 | academy_growth-38b5b2148fbd |
| 782 | 마곡서광2차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-24534030e694 |
| 783 | 마곡수명산파크3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-75a5f34286b9 |
| 784 | 마곡신안 · 1km 학원 1곳 증가 | 1 | academy_growth-127f5e0d7fc3 |
| 785 | 마곡신안네트빌(1단지) · 1km 학원 1곳 증가 | 1 | academy_growth-7ac7f8449390 |
| 786 | 마곡엠밸리12단지 · 1km 학원 1곳 증가 | 1 | academy_growth-6c975df7f47a |
| 787 | 마곡엠밸리14단지 · 1km 학원 1곳 증가 | 1 | academy_growth-27e1626e1159 |
| 788 | 마곡엠밸리1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-b468631386d8 |
| 789 | 마곡엠밸리2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-288c5a77de8d |
| 790 | 마곡엠밸리3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-306d50d359af |
| 791 | 마곡엠밸리4단지 · 1km 학원 1곳 증가 | 1 | academy_growth-eb14eb91716f |
| 792 | 마곡엠밸리5단지 · 1km 학원 1곳 증가 | 1 | academy_growth-0aa88b2d79e6 |
| 793 | 마곡엠밸리6단지 · 1km 학원 1곳 증가 | 1 | academy_growth-15c30da99122 |
| 794 | 마곡엠밸리8단지 · 1km 학원 1곳 증가 | 1 | academy_growth-2d2f965ff678 |
| 795 | 마곡엠밸리9단지 · 1km 학원 1곳 증가 | 1 | academy_growth-f684142061e4 |
| 796 | 마곡우림필유아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-6868c6b5f819 |
| 797 | 마곡푸르지오 · 1km 학원 1곳 증가 | 1 | academy_growth-1890b751e904 |
| 798 | 마곡한솔솔파크 · 1km 학원 1곳 증가 | 1 | academy_growth-05481780813f |
| 799 | 마곡현대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-f4f79203e0f7 |
| 800 | 마곡힐스테이트 · 1km 학원 1곳 증가 | 1 | academy_growth-a44ee853873b |
| 801 | 마장SH-vill임대 · 1km 학원 1곳 증가 | 1 | academy_growth-021a58567b8f |
| 802 | 마천금호어울림2차 · 1km 학원 1곳 증가 | 1 | academy_growth-cf8b3b3af05c |
| 803 | 마포 아이파크 포레 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-0c01010d06dc |
| 804 | 마포도화우성아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-34ec13a80884 |
| 805 | 마포자이 · 1km 학원 1곳 증가 | 1 | academy_growth-306c3c63c37a |
| 806 | 마포태영아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-7becf9cb983c |
| 807 | 마포태영제2 · 1km 학원 1곳 증가 | 1 | academy_growth-7bf60fe367de |
| 808 | 매봉삼성아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-415f7daf882a |
| 809 | 메이플자이 · 1km 학원 1곳 증가 | 1 | academy_growth-085cf86006d0 |
| 810 | 면목경남아너스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-e70eeb8702d8 |
| 811 | 면목삼익 · 1km 학원 1곳 증가 | 1 | academy_growth-461d067b97cc |
| 812 | 면목신성은하수 · 1km 학원 1곳 증가 | 1 | academy_growth-1e443363e575 |
| 813 | 면목한신 · 1km 학원 1곳 증가 | 1 | academy_growth-1824bcbdc000 |
| 814 | 목동13단지 · 1km 학원 1곳 증가 | 1 | academy_growth-d25e76352cbf |
| 815 | 목동14단지 · 1km 학원 1곳 증가 | 1 | academy_growth-4580dd0a935b |
| 816 | 목동2차우성임대 · 1km 학원 1곳 증가 | 1 | academy_growth-f76fff540dba |
| 817 | 목동센트럴푸르지오아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-374620f06741 |
| 818 | 목동현대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-5fbcd9b12a37 |
| 819 | 무악현대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-d965add3be87 |
| 820 | 무악현대임대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-3166c3d27e16 |
| 821 | 묵동극동늘푸른아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-8a68f4e9cf4f |
| 822 | 묵동자이 · 1km 학원 1곳 증가 | 1 | academy_growth-b27cc4a644ea |
| 823 | 묵동자이2단지아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-794c9beb5a5b |
| 824 | 문래남성 · 1km 학원 1곳 증가 | 1 | academy_growth-89a3a9a10248 |
| 825 | 문래두산위브 · 1km 학원 1곳 증가 | 1 | academy_growth-6fc0819dd337 |
| 826 | 문래삼환 · 1km 학원 1곳 증가 | 1 | academy_growth-58cd1a618851 |
| 827 | 문래한신 · 1km 학원 1곳 증가 | 1 | academy_growth-02dd5a080f3f |
| 828 | 문래현대1차 · 1km 학원 1곳 증가 | 1 | academy_growth-5257ce2a6568 |
| 829 | 문래현대2차 · 1km 학원 1곳 증가 | 1 | academy_growth-ed3f9fc32558 |
| 830 | 문래현대6차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-e4b1830c8069 |
| 831 | 문정시영 · 1km 학원 1곳 증가 | 1 | academy_growth-f2c7069f33b4 |
| 832 | 미아뉴타운두산위브트레지움 · 1km 학원 1곳 증가 | 1 | academy_growth-2a58d173d803 |
| 833 | 미아벽산임대 · 1km 학원 1곳 증가 | 1 | academy_growth-7c3e00931edf |
| 834 | 미아현대 · 1km 학원 1곳 증가 | 1 | academy_growth-25aa409a1823 |
| 835 | 반포르엘2차 · 1km 학원 1곳 증가 | 1 | academy_growth-ca3318cbfaba |
| 836 | 반포센트럴자이아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-00221031bdbd |
| 837 | 반포써밋 · 1km 학원 1곳 증가 | 1 | academy_growth-864615a91b87 |
| 838 | 밤섬현대 · 1km 학원 1곳 증가 | 1 | academy_growth-70f25fdc5398 |
| 839 | 방배대우효령 · 1km 학원 1곳 증가 | 1 | academy_growth-18b82abf6c5f |
| 840 | 방배래미안타워 · 1km 학원 1곳 증가 | 1 | academy_growth-1e3ef04f09c6 |
| 841 | 방배브라운가 · 1km 학원 1곳 증가 | 1 | academy_growth-43bfa0de4d7a |
| 842 | 방학극동아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-3d4b6d4e0414 |
| 843 | 방학동양크레오 · 1km 학원 1곳 증가 | 1 | academy_growth-f3c87e8b0ce9 |
| 844 | 방학벽산2차 · 1km 학원 1곳 증가 | 1 | academy_growth-407185f29e5d |
| 845 | 방학신동아5단지 · 1km 학원 1곳 증가 | 1 | academy_growth-5bf0dcab9e4c |
| 846 | 방화1단지(장미) · 1km 학원 1곳 증가 | 1 | academy_growth-cfbf47712dac |
| 847 | 방화2-2 그린 · 1km 학원 1곳 증가 | 1 | academy_growth-b32c5b10fd4c |
| 848 | 방화2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-9ed393e5ae6b |
| 849 | 방화3차우림필유 · 1km 학원 1곳 증가 | 1 | academy_growth-6ae90d63768c |
| 850 | 방화동부센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-b70b31e69ef9 |
| 851 | 방화삼성꽃마을 · 1km 학원 1곳 증가 | 1 | academy_growth-8b60c9f7ad3e |
| 852 | 백련산파크자이아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-2d3d039fdb30 |
| 853 | 백련산힐스테이트1차 · 1km 학원 1곳 증가 | 1 | academy_growth-8476b35f4992 |
| 854 | 백련산힐스테이트2차 · 1km 학원 1곳 증가 | 1 | academy_growth-c7d6a487e23b |
| 855 | 백련산힐스테이트3차 · 1km 학원 1곳 증가 | 1 | academy_growth-c243726b6db1 |
| 856 | 백련산힐스테이트임대 · 1km 학원 1곳 증가 | 1 | academy_growth-d969b1d5cf76 |
| 857 | 벽산1 · 1km 학원 1곳 증가 | 1 | academy_growth-d9435710b2b6 |
| 858 | 보문아남 · 1km 학원 1곳 증가 | 1 | academy_growth-c7a605b4f92d |
| 859 | 보문파크뷰자이아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-f9d1700152b4 |
| 860 | 봉천건영6차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-72e8af0dddb3 |
| 861 | 봉천벽산블루밍3차 · 1km 학원 1곳 증가 | 1 | academy_growth-8b78e7976f53 |
| 862 | 봉천우성제2 · 1km 학원 1곳 증가 | 1 | academy_growth-5f18b47a11e7 |
| 863 | 북한산래미안아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-438e032cf54d |
| 864 | 브라운스톤공덕 · 1km 학원 1곳 증가 | 1 | academy_growth-43f3972c0037 |
| 865 | 브라운스톤상도 · 1km 학원 1곳 증가 | 1 | academy_growth-af8faf588074 |
| 866 | 사당제일 · 1km 학원 1곳 증가 | 1 | academy_growth-16ceb9ae6053 |
| 867 | 삼각산아이원 · 1km 학원 1곳 증가 | 1 | academy_growth-0a6885850ad1 |
| 868 | 삼각산아이원임대 · 1km 학원 1곳 증가 | 1 | academy_growth-dd4a20ba86c7 |
| 869 | 삼성타운아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-458f9446b2d1 |
| 870 | 삼성홍실 · 1km 학원 1곳 증가 | 1 | academy_growth-7322c3f6f302 |
| 871 | 상계극동늘푸른 · 1km 학원 1곳 증가 | 1 | academy_growth-eb3f201d43a4 |
| 872 | 상계미도 · 1km 학원 1곳 증가 | 1 | academy_growth-d79a7532a451 |
| 873 | 상계수락한신 · 1km 학원 1곳 증가 | 1 | academy_growth-46f62d898fed |
| 874 | 상계수락현대 · 1km 학원 1곳 증가 | 1 | academy_growth-9a4fba6e8ac7 |
| 875 | 상계우방 · 1km 학원 1곳 증가 | 1 | academy_growth-fdd2cf760e24 |
| 876 | 상계은빛1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-2e3fd9937bcd |
| 877 | 상계은빛2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-61435f11ddad |
| 878 | 상계주공10단지 · 1km 학원 1곳 증가 | 1 | academy_growth-4eddd2704274 |
| 879 | 상계주공15단지 · 1km 학원 1곳 증가 | 1 | academy_growth-79ab02c39fde |
| 880 | 상계한신 · 1km 학원 1곳 증가 | 1 | academy_growth-40d9e9af96c4 |
| 881 | 상도2차 두산위브트레지움 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-25c70c1c6b84 |
| 882 | 상도sh-ville · 1km 학원 1곳 증가 | 1 | academy_growth-9a56fc81687e |
| 883 | 상도건영 · 1km 학원 1곳 증가 | 1 | academy_growth-be7c4c471e46 |
| 884 | 상도건영임대 · 1km 학원 1곳 증가 | 1 | academy_growth-7d0b7e06b129 |
| 885 | 상도더샵 · 1km 학원 1곳 증가 | 1 | academy_growth-fd6abfeaf728 |
| 886 | 상도두산위브 · 1km 학원 1곳 증가 | 1 | academy_growth-619d48acd7f7 |
| 887 | 상봉건영캐스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-c3ae124225e3 |
| 888 | 상봉태영데시앙 · 1km 학원 1곳 증가 | 1 | academy_growth-e1b178c2aa2b |
| 889 | 상봉프레미어스엠코 · 1km 학원 1곳 증가 | 1 | academy_growth-b8012ae8d353 |
| 890 | 서강GS · 1km 학원 1곳 증가 | 1 | academy_growth-589b40f3b527 |
| 891 | 서대문천연뜨란채아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-92e510951b4c |
| 892 | 서울대입구아이원 (1560-61) · 1km 학원 1곳 증가 | 1 | academy_growth-002b23764593 |
| 893 | 서울숲 아이파크 리버포레2차 · 1km 학원 1곳 증가 | 1 | academy_growth-50893aa73b5f |
| 894 | 서울숲삼부아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-634eae0a9b6c |
| 895 | 서울숲힐스테이트 · 1km 학원 1곳 증가 | 1 | academy_growth-0eb51693f457 |
| 896 | 서울우면 · 1km 학원 1곳 증가 | 1 | academy_growth-78252e8664db |
| 897 | 서울주택도시공사 목동현대B 임대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-740b031dd864 |
| 898 | 서초네이처힐1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-5756e40f29f6 |
| 899 | 서초네이처힐3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-d55c93df099a |
| 900 | 서초네이처힐4단지 · 1km 학원 1곳 증가 | 1 | academy_growth-7a9d64bdfc3e |
| 901 | 서초네이처힐5단지 · 1km 학원 1곳 증가 | 1 | academy_growth-b73237cfb306 |
| 902 | 서초네이처힐7단지 · 1km 학원 1곳 증가 | 1 | academy_growth-e136999cf519 |
| 903 | 서초대우아이빌 · 1km 학원 1곳 증가 | 1 | academy_growth-8d2834af9cb7 |
| 904 | 서초삼성쉐르빌2 · 1km 학원 1곳 증가 | 1 | academy_growth-dcd8147d7f6a |
| 905 | 서초우성5차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-191e6ebc4981 |
| 906 | 서초푸르지오써밋 · 1km 학원 1곳 증가 | 1 | academy_growth-3656838b89d1 |
| 907 | 서초현대4차 · 1km 학원 1곳 증가 | 1 | academy_growth-3ebd1a6ccc9e |
| 908 | 석관두산 · 1km 학원 1곳 증가 | 1 | academy_growth-aed0df11e832 |
| 909 | 석관중앙하이츠 · 1km 학원 1곳 증가 | 1 | academy_growth-84fcc9dcfdd9 |
| 910 | 석관코오롱 · 1km 학원 1곳 증가 | 1 | academy_growth-4975da09f9c1 |
| 911 | 선경301(대치동) · 1km 학원 1곳 증가 | 1 | academy_growth-5b59f4de7234 |
| 912 | 성북힐스테이트 · 1km 학원 1곳 증가 | 1 | academy_growth-e8cd3acdcc76 |
| 913 | 성수1차대우아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-e76a830fccd1 |
| 914 | 성수갤러리아포레 · 1km 학원 1곳 증가 | 1 | academy_growth-790474002851 |
| 915 | 성수금호3차 · 1km 학원 1곳 증가 | 1 | academy_growth-a626b1758fa7 |
| 916 | 성수금호타운2차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-0e6c9a039080 |
| 917 | 성수동아그린 · 1km 학원 1곳 증가 | 1 | academy_growth-34b98d1171d6 |
| 918 | 성수두산위브 · 1km 학원 1곳 증가 | 1 | academy_growth-f4d3bcda428d |
| 919 | 성수롯데캐슬 · 1km 학원 1곳 증가 | 1 | academy_growth-b9f6e5235bed |
| 920 | 성수쌍용 · 1km 학원 1곳 증가 | 1 | academy_growth-acb81446aabd |
| 921 | 성수아이파크 · 1km 학원 1곳 증가 | 1 | academy_growth-ba186d8203ef |
| 922 | 성수청구강변 · 1km 학원 1곳 증가 | 1 | academy_growth-4577874edc2f |
| 923 | 성수한강한신 · 1km 학원 1곳 증가 | 1 | academy_growth-93d163a45bf6 |
| 924 | 성수한진타운 · 1km 학원 1곳 증가 | 1 | academy_growth-3cd177d84da8 |
| 925 | 성수현대 · 1km 학원 1곳 증가 | 1 | academy_growth-b8bbb82b7484 |
| 926 | 성수현대그린 · 1km 학원 1곳 증가 | 1 | academy_growth-aa9295e8b745 |
| 927 | 성원(사슴4) · 1km 학원 1곳 증가 | 1 | academy_growth-85a7f7d245c1 |
| 928 | 세양청마루 · 1km 학원 1곳 증가 | 1 | academy_growth-7813b81fd960 |
| 929 | 센트레빌아스테리움영등포 · 1km 학원 1곳 증가 | 1 | academy_growth-63057ed108b5 |
| 930 | 송파레미니스2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-92fcfda96e75 |
| 931 | 송파삼성래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-12bbe1977c42 |
| 932 | 송파파인타운6단지 · 1km 학원 1곳 증가 | 1 | academy_growth-49d65f48ad8f |
| 933 | 송파한양2차 · 1km 학원 1곳 증가 | 1 | academy_growth-d69393f83b78 |
| 934 | 송파호반베르디움더퍼스트 · 1km 학원 1곳 증가 | 1 | academy_growth-c6937febe1f2 |
| 935 | 수락산벨리체아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-b794ad84a867 |
| 936 | 수유역푸르지오시티 · 1km 학원 1곳 증가 | 1 | academy_growth-c90f2c5c2ccc |
| 937 | 시흥현대빌라 · 1km 학원 1곳 증가 | 1 | academy_growth-1788e90edca7 |
| 938 | 신공덕1차삼성래미안아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-d148a48b2c39 |
| 939 | 신공덕3차삼성래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-a0c7611fbdcf |
| 940 | 신공덕e-편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-c6634fefd1d2 |
| 941 | 신공덕삼성임대 · 1km 학원 1곳 증가 | 1 | academy_growth-90b977d3c04a |
| 942 | 신길삼두 · 1km 학원 1곳 증가 | 1 | academy_growth-8d8721038f7d |
| 943 | 신길센트럴자이 · 1km 학원 1곳 증가 | 1 | academy_growth-ccaa6dd9ab86 |
| 944 | 신내10단지 · 1km 학원 1곳 증가 | 1 | academy_growth-0e10bdf58d4d |
| 945 | 신내12단지 · 1km 학원 1곳 증가 | 1 | academy_growth-d75781cbc519 |
| 946 | 신내건영1차 · 1km 학원 1곳 증가 | 1 | academy_growth-ae8e773283d0 |
| 947 | 신내건영2차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-7deebbcb51ab |
| 948 | 신내경남아너스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-2ecb7c0152df |
| 949 | 신내다우훼밀리 · 1km 학원 1곳 증가 | 1 | academy_growth-b3078e166009 |
| 950 | 신내대명11단지 · 1km 학원 1곳 증가 | 1 | academy_growth-d1ebb1a7a059 |
| 951 | 신내대성유니드아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-def0236bb417 |
| 952 | 신내동성1,2차 · 1km 학원 1곳 증가 | 1 | academy_growth-6852359ed334 |
| 953 | 신내동성3차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-ba5360806ee9 |
| 954 | 신내동성4차 · 1km 학원 1곳 증가 | 1 | academy_growth-7d3a1815e2fc |
| 955 | 신내동성7차 · 1km 학원 1곳 증가 | 1 | academy_growth-0ed20645e8cd |
| 956 | 신내벽산 · 1km 학원 1곳 증가 | 1 | academy_growth-053099bf8f02 |
| 957 | 신내새한아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-839cace08a0c |
| 958 | 신내석탑 · 1km 학원 1곳 증가 | 1 | academy_growth-6e748a9ccee5 |
| 959 | 신내성원 · 1km 학원 1곳 증가 | 1 | academy_growth-00f9b8c606a3 |
| 960 | 신내엘지쌍용 · 1km 학원 1곳 증가 | 1 | academy_growth-e092fe720027 |
| 961 | 신내영풍마드레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-90f775c64767 |
| 962 | 신내우남푸르미아 · 1km 학원 1곳 증가 | 1 | academy_growth-e855dd8f73a9 |
| 963 | 신대방경남아너스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-41c5c281f3bd |
| 964 | 신도림대림1,2차 · 1km 학원 1곳 증가 | 1 | academy_growth-8739873e240e |
| 965 | 신도림대림3차 · 1km 학원 1곳 증가 | 1 | academy_growth-2da26cf2055a |
| 966 | 신도림대림5차e-편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-9026b6f4a3f3 |
| 967 | 신도림롯데 · 1km 학원 1곳 증가 | 1 | academy_growth-fde741786cb4 |
| 968 | 신도림미성 · 1km 학원 1곳 증가 | 1 | academy_growth-995e40c6f952 |
| 969 | 신도림우성5차 · 1km 학원 1곳 증가 | 1 | academy_growth-75514891ac2b |
| 970 | 신동아리버파크임대 · 1km 학원 1곳 증가 | 1 | academy_growth-819b76456036 |
| 971 | 신림건영1차 · 1km 학원 1곳 증가 | 1 | academy_growth-ae022d13165c |
| 972 | 신림미성 · 1km 학원 1곳 증가 | 1 | academy_growth-2fa3e0d6df6c |
| 973 | 신림푸르지오 · 1km 학원 1곳 증가 | 1 | academy_growth-b7905fd4c9d5 |
| 974 | 신마곡 벽산 블루밍 · 1km 학원 1곳 증가 | 1 | academy_growth-fadaf0cdc4d9 |
| 975 | 신반포한신14차 · 1km 학원 1곳 증가 | 1 | academy_growth-f874b2c9b82d |
| 976 | 신반포한신16차 · 1km 학원 1곳 증가 | 1 | academy_growth-d6796eb76a81 |
| 977 | 신사동 한신 휴 플러스 · 1km 학원 1곳 증가 | 1 | academy_growth-fd2b39bd3212 |
| 978 | 신사씨티 · 1km 학원 1곳 증가 | 1 | academy_growth-e838cdb02bb5 |
| 979 | 신이문금호어울림 · 1km 학원 1곳 증가 | 1 | academy_growth-c148f5ec0f78 |
| 980 | 신창세방리버하이빌 · 1km 학원 1곳 증가 | 1 | academy_growth-4f0f1e9b9a6f |
| 981 | 쌍문경남 · 1km 학원 1곳 증가 | 1 | academy_growth-3a5103526778 |
| 982 | 쌍문금호1차아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-bbb03d9c0ed6 |
| 983 | 쌍문금호2차 · 1km 학원 1곳 증가 | 1 | academy_growth-54195a852c95 |
| 984 | 쌍문삼익 · 1km 학원 1곳 증가 | 1 | academy_growth-9c9148a61560 |
| 985 | 쌍문성원 · 1km 학원 1곳 증가 | 1 | academy_growth-edc6dc708606 |
| 986 | 쌍문청구 · 1km 학원 1곳 증가 | 1 | academy_growth-d048410d57a7 |
| 987 | 쌍문한양2,3,4차 · 1km 학원 1곳 증가 | 1 | academy_growth-b0e16ac2e027 |
| 988 | 쌍문한양5차 · 1km 학원 1곳 증가 | 1 | academy_growth-f2c8b3e60c55 |
| 989 | 쌍문한양6차 · 1km 학원 1곳 증가 | 1 | academy_growth-d264804ffc82 |
| 990 | 쌍문한양7차 · 1km 학원 1곳 증가 | 1 | academy_growth-70cb42de2812 |
| 991 | 쌍문현대1차 · 1km 학원 1곳 증가 | 1 | academy_growth-71e88903d86d |
| 992 | 쌍문현대2차 · 1km 학원 1곳 증가 | 1 | academy_growth-ceb6cb756691 |
| 993 | 쌍용스위트닷홈임대 · 1km 학원 1곳 증가 | 1 | academy_growth-ab53466f338e |
| 994 | 아크로 서울포레스트 · 1km 학원 1곳 증가 | 1 | academy_growth-f12105531c6b |
| 995 | 아크로삼성 · 1km 학원 1곳 증가 | 1 | academy_growth-13128f247bc7 |
| 996 | 암사한강현대 · 1km 학원 1곳 증가 | 1 | academy_growth-16e2e971f4ed |
| 997 | 압구정미성1차 · 1km 학원 1곳 증가 | 1 | academy_growth-87ecd7df9bd5 |
| 998 | 양재우성 · 1km 학원 1곳 증가 | 1 | academy_growth-766abcfeec39 |
| 999 | 양재우성KBS(113동) · 1km 학원 1곳 증가 | 1 | academy_growth-76cc152bceb2 |
| 1000 | 양평경남1차 · 1km 학원 1곳 증가 | 1 | academy_growth-6087e5e409d6 |
| 1001 | 양평경남2차아너스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-2b35bbb2df1b |
| 1002 | 양평동6차현대아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-78df460858c2 |
| 1003 | 양평벽산 · 1km 학원 1곳 증가 | 1 | academy_growth-dc9be2a8f1be |
| 1004 | 양평서통한신 · 1km 학원 1곳 증가 | 1 | academy_growth-85102f60b797 |
| 1005 | 양평우림루미아트 · 1km 학원 1곳 증가 | 1 | academy_growth-acad4ee916ba |
| 1006 | 양평현대2차 · 1km 학원 1곳 증가 | 1 | academy_growth-cf2653d43856 |
| 1007 | 에드가 수유 청년주택 · 1km 학원 1곳 증가 | 1 | academy_growth-77b00c8bb574 |
| 1008 | 엠브이아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-95dfca315c96 |
| 1009 | 여의도대우트럼프월드 · 1km 학원 1곳 증가 | 1 | academy_growth-5532c9881eb8 |
| 1010 | 여의도더리브스타일 · 1km 학원 1곳 증가 | 1 | academy_growth-4966d9ed7bcb |
| 1011 | 역삼금호어울림 · 1km 학원 1곳 증가 | 1 | academy_growth-74b61673479f |
| 1012 | 영등포자이르네 · 1km 학원 1곳 증가 | 1 | academy_growth-ad29b4c4c69f |
| 1013 | 영화 아이닉스 · 1km 학원 1곳 증가 | 1 | academy_growth-a273b0020a04 |
| 1014 | 오목교벽산블루밍아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-88c24ebaa279 |
| 1015 | 왕십리금호어울림아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-e26bf630de87 |
| 1016 | 왕십리중앙하이츠 · 1km 학원 1곳 증가 | 1 | academy_growth-35746d38f921 |
| 1017 | 왕십리풍림아이원 · 1km 학원 1곳 증가 | 1 | academy_growth-a0b93419287e |
| 1018 | 용산 KCC 웰츠타워 · 1km 학원 1곳 증가 | 1 | academy_growth-a8c97106af1c |
| 1019 | 용산 남영역 롯데캐슬 헤리티지 · 1km 학원 1곳 증가 | 1 | academy_growth-a1ec564e76ac |
| 1020 | 용산CJ나인파크 · 1km 학원 1곳 증가 | 1 | academy_growth-66676e3d23f2 |
| 1021 | 용산e편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-1130fa17e2a8 |
| 1022 | 용산더프라임 · 1km 학원 1곳 증가 | 1 | academy_growth-c341f6c33944 |
| 1023 | 용산아크로타워 · 1km 학원 1곳 증가 | 1 | academy_growth-ed9eddc7e7cb |
| 1024 | 용산원효루미니 · 1km 학원 1곳 증가 | 1 | academy_growth-2e89f03c1167 |
| 1025 | 용산파크자이 · 1km 학원 1곳 증가 | 1 | academy_growth-ae33cd6ea7a1 |
| 1026 | 우림루미아트1.2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-5a7d01f19000 |
| 1027 | 우면대림 · 1km 학원 1곳 증가 | 1 | academy_growth-1d43b0010f7a |
| 1028 | 우면동동고 · 1km 학원 1곳 증가 | 1 | academy_growth-78acc5570f04 |
| 1029 | 우면코오롱 · 1km 학원 1곳 증가 | 1 | academy_growth-7a059485725b |
| 1030 | 우성캐릭터199 아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-848f6777afad |
| 1031 | 월계사슴1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-2466c4ccd5b6 |
| 1032 | 월계사슴2단지 · 1km 학원 1곳 증가 | 1 | academy_growth-e335eb227bc1 |
| 1033 | 월계사슴3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-3e019a2012c8 |
| 1034 | 월계삼호4차 · 1km 학원 1곳 증가 | 1 | academy_growth-5827f746156b |
| 1035 | 월계역신도브래뉴 · 1km 학원 1곳 증가 | 1 | academy_growth-df56afed6ae4 |
| 1036 | 위례포레샤인아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-f9814af50417 |
| 1037 | 유원도봉아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-3c7ec2478fd2 |
| 1038 | 은평신사두산위브아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-473aef1e348f |
| 1039 | 응봉신동아 · 1km 학원 1곳 증가 | 1 | academy_growth-ab491136eeae |
| 1040 | 이문e-편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-9c3b14cefabb |
| 1041 | 이문삼익아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-a3a69823427f |
| 1042 | 이안용산프리미어 · 1km 학원 1곳 증가 | 1 | academy_growth-e6fa95bb6324 |
| 1043 | 이편한세상 강동 프레스티지원 · 1km 학원 1곳 증가 | 1 | academy_growth-9f6cae3a2e1f |
| 1044 | 이편한세상 상도노빌리티 · 1km 학원 1곳 증가 | 1 | academy_growth-0307a5a53c59 |
| 1045 | 인왕산2차아이파크아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-b0bee5a175fa |
| 1046 | 인왕산아이파크 · 1km 학원 1곳 증가 | 1 | academy_growth-ef68a032869e |
| 1047 | 일성트루웰 · 1km 학원 1곳 증가 | 1 | academy_growth-eaa56dc888ce |
| 1048 | 일원동 수서아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-8f9f6aebf343 |
| 1049 | 잠실더샵스타파크 · 1km 학원 1곳 증가 | 1 | academy_growth-2445118aea7b |
| 1050 | 잠실래미안아이파크 · 1km 학원 1곳 증가 | 1 | academy_growth-b261abd0bf29 |
| 1051 | 잠실르엘 · 1km 학원 1곳 증가 | 1 | academy_growth-c25b56af356a |
| 1052 | 잠실올림픽공원아이파크 · 1km 학원 1곳 증가 | 1 | academy_growth-bd229ba1d6d1 |
| 1053 | 잠실우성1,2,3차 · 1km 학원 1곳 증가 | 1 | academy_growth-01588459d047 |
| 1054 | 잠실파크리오 · 1km 학원 1곳 증가 | 1 | academy_growth-4dffd731a3eb |
| 1055 | 잠실푸르지오월드마크 · 1km 학원 1곳 증가 | 1 | academy_growth-abbfd4631075 |
| 1056 | 잠실한솔 · 1km 학원 1곳 증가 | 1 | academy_growth-9993484d7a75 |
| 1057 | 장미3차 · 1km 학원 1곳 증가 | 1 | academy_growth-8f9d75779fa1 |
| 1058 | 장안삼성쉐르빌 · 1km 학원 1곳 증가 | 1 | academy_growth-3e90b1928818 |
| 1059 | 장안한신 · 1km 학원 1곳 증가 | 1 | academy_growth-f9349cf62df2 |
| 1060 | 장안현대 · 1km 학원 1곳 증가 | 1 | academy_growth-edf6fba84ec0 |
| 1061 | 장안현대힐스테이트 · 1km 학원 1곳 증가 | 1 | academy_growth-eeb9e2204965 |
| 1062 | 전농삼성 · 1km 학원 1곳 증가 | 1 | academy_growth-6506f9cebea9 |
| 1063 | 전농삼성임대 · 1km 학원 1곳 증가 | 1 | academy_growth-84ab431c58aa |
| 1064 | 정릉2차 e편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-c0e30cc090b4 |
| 1065 | 정릉2차대주피오레 · 1km 학원 1곳 증가 | 1 | academy_growth-740fc82bf102 |
| 1066 | 정릉성원 · 1km 학원 1곳 증가 | 1 | academy_growth-3626cb4ba085 |
| 1067 | 정릉쌍용 · 1km 학원 1곳 증가 | 1 | academy_growth-9c6de5a796a3 |
| 1068 | 정릉중앙하이츠빌1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-abd3d9911d3d |
| 1069 | 정릉푸르지오 · 1km 학원 1곳 증가 | 1 | academy_growth-d9ed4c00b701 |
| 1070 | 종로센트레빌 · 1km 학원 1곳 증가 | 1 | academy_growth-1aacc9fd54d9 |
| 1071 | 종암아이파크1차 · 1km 학원 1곳 증가 | 1 | academy_growth-46d89f49cf92 |
| 1072 | 중계라이프신동아청구아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-cb8b9dbc1573 |
| 1073 | 중계주공5단지 · 1km 학원 1곳 증가 | 1 | academy_growth-9304be51b3bd |
| 1074 | 중계주공6단지 · 1km 학원 1곳 증가 | 1 | academy_growth-1fa8df0d2563 |
| 1075 | 중계중앙하이츠 · 1km 학원 1곳 증가 | 1 | academy_growth-697d24e88dc0 |
| 1076 | 중계진로유통조합아파트(중계진로대림아파트) · 1km 학원 1곳 증가 | 1 | academy_growth-54e74b07f42c |
| 1077 | 중계청구3차 · 1km 학원 1곳 증가 | 1 | academy_growth-f37c78ad35d9 |
| 1078 | 중계현대3차 · 1km 학원 1곳 증가 | 1 | academy_growth-03ac466133c7 |
| 1079 | 중랑숲Liga아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-a082121c64ba |
| 1080 | 중앙구로하이츠 · 1km 학원 1곳 증가 | 1 | academy_growth-2efef5d91b71 |
| 1081 | 중앙하이츠 · 1km 학원 1곳 증가 | 1 | academy_growth-7873ba4f0688 |
| 1082 | 지웰홈스 왕십리 · 1km 학원 1곳 증가 | 1 | academy_growth-4d9637fe1dc3 |
| 1083 | 창동서울가든아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-9d87e92e6a82 |
| 1084 | 창동주공3단지 · 1km 학원 1곳 증가 | 1 | academy_growth-5f0350ff7d1c |
| 1085 | 창신두산 · 1km 학원 1곳 증가 | 1 | academy_growth-b17f0b27d7fa |
| 1086 | 창신쌍용1단지 · 1km 학원 1곳 증가 | 1 | academy_growth-e32caa58e2e5 |
| 1087 | 천호e-편한세상 · 1km 학원 1곳 증가 | 1 | academy_growth-0172da2c194d |
| 1088 | 천호동아코아 · 1km 학원 1곳 증가 | 1 | academy_growth-266c0c8d3237 |
| 1089 | 천호삼성임대 · 1km 학원 1곳 증가 | 1 | academy_growth-803b7360fff7 |
| 1090 | 청년주택 와이엔타워 · 1km 학원 1곳 증가 | 1 | academy_growth-69650b683d1b |
| 1091 | 청담2차e편한세상아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-d35952bc5ac2 |
| 1092 | 청담르엘 · 1km 학원 1곳 증가 | 1 | academy_growth-789008cd822c |
| 1093 | 청담삼성1차 · 1km 학원 1곳 증가 | 1 | academy_growth-09bf50dcf7d7 |
| 1094 | 청담삼익 · 1km 학원 1곳 증가 | 1 | academy_growth-53ac41b60971 |
| 1095 | 청담휴먼스타빌 · 1km 학원 1곳 증가 | 1 | academy_growth-11b5840bcab0 |
| 1096 | 칼튼테라스 · 1km 학원 1곳 증가 | 1 | academy_growth-aa98d50420b2 |
| 1097 | 타워팰리스G동 · 1km 학원 1곳 증가 | 1 | academy_growth-36ec8cf84787 |
| 1098 | 토정한강삼성 · 1km 학원 1곳 증가 | 1 | academy_growth-b1d2331066ce |
| 1099 | 포스코더샵스타리버 · 1km 학원 1곳 증가 | 1 | academy_growth-91d06e60eb44 |
| 1100 | 풍납 현대리버빌1차 · 1km 학원 1곳 증가 | 1 | academy_growth-2d8a0052f6c5 |
| 1101 | 풍납극동 · 1km 학원 1곳 증가 | 1 | academy_growth-1cbf1bd5573e |
| 1102 | 풍납미성 · 1km 학원 1곳 증가 | 1 | academy_growth-9d4a35bc09db |
| 1103 | 풍납시티극동 · 1km 학원 1곳 증가 | 1 | academy_growth-d764f96b2ed2 |
| 1104 | 풍납신성노바빌 · 1km 학원 1곳 증가 | 1 | academy_growth-b4d2d0b6b538 |
| 1105 | 풍납한강극동 · 1km 학원 1곳 증가 | 1 | academy_growth-1efff896d2b2 |
| 1106 | 프라비다2 · 1km 학원 1곳 증가 | 1 | academy_growth-6ee5060f6ba8 |
| 1107 | 프라이어팰리스 · 1km 학원 1곳 증가 | 1 | academy_growth-91d15bb1f6d2 |
| 1108 | 하계학여울청구A · 1km 학원 1곳 증가 | 1 | academy_growth-c292b96563b9 |
| 1109 | 하계학여울청구B · 1km 학원 1곳 증가 | 1 | academy_growth-36697a7af6be |
| 1110 | 하왕십리극동미라주2 · 1km 학원 1곳 증가 | 1 | academy_growth-2e85e688b73b |
| 1111 | 한신코아 · 1km 학원 1곳 증가 | 1 | academy_growth-e2a9b91ff454 |
| 1112 | 한양아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-04f83321a172 |
| 1113 | 한일휴니스빌 · 1km 학원 1곳 증가 | 1 | academy_growth-0d9bdb973784 |
| 1114 | 행당두산 · 1km 학원 1곳 증가 | 1 | academy_growth-474fa5904158 |
| 1115 | 행당한진타운제2 · 1km 학원 1곳 증가 | 1 | academy_growth-3434a929ef65 |
| 1116 | 현대성우 · 1km 학원 1곳 증가 | 1 | academy_growth-107df8e6465f |
| 1117 | 현대썬앤빌601 · 1km 학원 1곳 증가 | 1 | academy_growth-a6ecddeb84c3 |
| 1118 | 홍은극동 · 1km 학원 1곳 증가 | 1 | academy_growth-f3cd0790f065 |
| 1119 | 홍제삼성래미안 · 1km 학원 1곳 증가 | 1 | academy_growth-a33cf9f5dfa0 |
| 1120 | 화양현대 · 1km 학원 1곳 증가 | 1 | academy_growth-cc83d4419760 |
| 1121 | 효창파크푸르지오 · 1km 학원 1곳 증가 | 1 | academy_growth-36ca7bbdfc2b |
| 1122 | 흑석자이 · 1km 학원 1곳 증가 | 1 | academy_growth-3d51d7fb2564 |
| 1123 | 흑석한강센트레빌2차 · 1km 학원 1곳 증가 | 1 | academy_growth-8f402d387b32 |
| 1124 | 힐데스하임천호아파트 · 1km 학원 1곳 증가 | 1 | academy_growth-f020614c801e |
| 1125 | 힐스테이트뉴포레 · 1km 학원 1곳 증가 | 1 | academy_growth-46c1a24b9d97 |
| 1126 | 힐스테이트백련산4차 · 1km 학원 1곳 증가 | 1 | academy_growth-b3616d16ba0d |
| 1127 | 강변역센트럴아이파크 · 신규 등록 215세대 | 1 | new_complex-004c12ee2bbb |
| 1128 | 궁전아파트 · 신규 등록 108세대 | 1 | new_complex-dbe10bf7e9f6 |
| 1129 | 더샵송파루미스타 · 신규 등록 179세대 | 1 | new_complex-e2de566dd610 |
| 1130 | 디마크당산 · 신규 등록 152세대 | 1 | new_complex-2271c7a5aeb2 |
| 1131 | 보문센트럴아이파크아파트 · 신규 등록 199세대 | 1 | new_complex-fc41aa1f73a7 |
| 1132 | 서초벽산블루밍아파트 · 신규 등록 60세대 | 1 | new_complex-1bed74b711d4 |
| 1133 | 이문아이파크자이3단지 · 신규 등록 152세대 | 1 | new_complex-9df71b9c3658 |
| 1134 | 스타벅스 강남구청정문점 · 스타벅스 추가 후보 | 1 | starbucks-472ff899796e |
| 1135 | 스타벅스 공덕점 · 스타벅스 소실 후보 | 1 | starbucks-b595b436e119 |
| 1136 | 스타벅스 구의역점 · 스타벅스 추가 후보 | 1 | starbucks-f3d05add7135 |
| 1137 | 스타벅스 남부터미널역5번출구점 · 스타벅스 추가 후보 | 1 | starbucks-ebd129b0348f |
| 1138 | 스타벅스 노원KT점 · 스타벅스 추가 후보 | 1 | starbucks-b98ebf3d3c18 |
| 1139 | 스타벅스 대치사거리점 · 스타벅스 추가 후보 | 1 | starbucks-cfc326c1fed7 |
| 1140 | 스타벅스 등촌역점 · 스타벅스 추가 후보 | 1 | starbucks-ed92c9e5fa8a |
| 1141 | 스타벅스 마포이마트점 · 스타벅스 소실 후보 | 1 | starbucks-0aac3e1a3bfb |
| 1142 | 스타벅스 묵동점 · 스타벅스 추가 후보 | 1 | starbucks-4252be04a36c |
| 1143 | 스타벅스 문래동점 · 스타벅스 추가 후보 | 1 | starbucks-16d1a48c3149 |
| 1144 | 스타벅스 문화일보점 · 스타벅스 추가 후보 | 1 | starbucks-a21fa513dea4 |
| 1145 | 스타벅스 미아이마트 · 스타벅스 소실 후보 | 1 | starbucks-f58e70a39d14 |
| 1146 | 스타벅스 서울세관사거리점 · 스타벅스 추가 후보 | 1 | starbucks-04f02bca31e1 |
| 1147 | 스타벅스 신촌오거리점 · 스타벅스 추가 후보 | 1 | starbucks-f6776722752e |
| 1148 | 스타벅스 오목교역점 · 스타벅스 소실 후보 | 1 | starbucks-0f9b332d6ba2 |
| 1149 | 스타벅스 왕십리역 · 스타벅스 추가 후보 | 1 | starbucks-6d1de4726da5 |
| 1150 | 스타벅스 자양역점 · 스타벅스 소실 후보 | 1 | starbucks-a88dbe61b6f5 |
| 1151 | 스타벅스 잠실시그마타워점 · 스타벅스 추가 후보 | 1 | starbucks-9b5119963a85 |
| 1152 | 스타벅스 잠실트리지움점 · 스타벅스 추가 후보 | 1 | starbucks-7eb79b0d3039 |
| 1153 | 스타벅스 천호사거리 · 스타벅스 소실 후보 | 1 | starbucks-afd6b18daa97 |
| 1154 | 스타벅스 천호이마트점 · 스타벅스 소실 후보 | 1 | starbucks-e0ed5280ca36 |
| 1155 | 스타벅스 하이테크시티점 · 스타벅스 소실 후보 | 1 | starbucks-81575a4a9175 |
| 1156 | 은마 84㎡ · 매매 -7.9% | 1 | price_down-e0fee9d781a4 |
| 1157 | 문정시영 25㎡ · 매매 +45.8% | 1 | price_up-53d03f138550 |
| 1158 | 역삼래미안 59㎡ · 매매 -7.6% | 1 | price_down-fd401b924d81 |
| 1159 | 논현신동아 35㎡ · 매매 +37.8% | 1 | price_up-da3c9ec2c704 |
| 1160 | 도곡렉슬 84㎡ · 매매 -7.5% | 1 | price_down-c9a33baa9db8 |
| 1161 | 답십리두산 59㎡ · 매매 +37.8% | 1 | price_up-8885daf4636d |
| 1162 | 당산삼성래미안 115㎡ · 매매 -6.6% | 1 | price_down-73e1b001d425 |
| 1163 | 답십리동아 84㎡ · 매매 +37.7% | 1 | price_up-3649b9bc98f1 |
| 1164 | 쌍문한양2,3,4차 35㎡ · 매매 -5.9% | 1 | price_down-044c90409343 |
| 1165 | 성현동아 59㎡ · 매매 +36.9% | 1 | price_up-810105c650ae |
| 1166 | 잠실동트리지움 59㎡ · 매매 -5.8% | 1 | price_down-392b60625020 |
| 1167 | 신길한성 59㎡ · 매매 +31.7% | 1 | price_up-94e38b1dce04 |
| 1168 | 푸른마을아파트 59㎡ · 매매 -5.7% | 1 | price_down-498b4783a618 |
| 1169 | 길음뉴타운푸르지오아파트2,3단지 59㎡ · 매매 +31.3% | 1 | price_up-a93455141eef |
| 1170 | 신천장미1차2차 71㎡ · 매매 -5.6% | 1 | price_down-3eca8dd21b4a |
| 1171 | 풍납 현대리버빌1차 43㎡ · 매매 +30.8% | 1 | price_up-e22218ba979f |
| 1172 | 잠실파크리오 121㎡ · 매매 -5.4% | 1 | price_down-b271530eedc4 |
| 1173 | 사당자이 59㎡ · 매매 +29.9% | 1 | price_up-caefa519b6b2 |
| 1174 | 역삼럭키 124㎡ · 매매 -5.1% | 1 | price_down-b265ae15e161 |
| 1175 | 답십리대우 59㎡ · 매매 +29.8% | 1 | price_up-22ad1a7e0ed4 |
| 1176 | 삼성힐스테이트1단지 84㎡ · 매매 -5.0% | 1 | price_down-352395878272 |
| 1177 | 가양2단지 39㎡ · 매매 +29.6% | 1 | price_up-055d95393ad9 |
| 1178 | 서초삼성쉐르빌2 35㎡ · 매매 -5.0% | 1 | price_down-1e23f91c8370 |
| 1179 | 청계현대아파트 84㎡ · 매매 +29.5% | 1 | price_up-d8e8c3bc341f |
| 1180 | 남서울 무지개 53㎡ · 매매 -4.6% | 1 | price_down-9e544c067d1e |
| 1181 | 거여5단지 59㎡ · 매매 +29.0% | 1 | price_up-b7c912456c8c |
| 1182 | 여의도진주 48㎡ · 매매 -4.5% | 1 | price_down-22266bf8e599 |
| 1183 | 마포중동현대 59㎡ · 매매 +29.0% | 1 | price_up-8f56814ec4db |
| 1184 | 목동7단지 59㎡ · 매매 -4.4% | 1 | price_down-94321534e996 |
| 1185 | 고덕아남 50㎡ · 매매 +29.0% | 1 | price_up-53a95e0b90c2 |
| 1186 | 대우디오빌역삼 59㎡ · 매매 -4.4% | 1 | price_down-2c40e5b11fe4 |
| 1187 | 가양3단지(강변) 49㎡ · 매매 +28.8% | 1 | price_up-82ec1b5b8e2f |
| 1188 | 래미안옥수리버젠 59㎡ · 매매 -4.3% | 1 | price_down-7cc2e4e9766f |
| 1189 | 전농SK 59㎡ · 매매 +28.6% | 1 | price_up-aeac3e94ffcd |
| 1190 | 대청 39㎡ · 매매 -4.1% | 1 | price_down-624e9be1ce58 |
| 1191 | 신월시영아파트 43㎡ · 매매 +28.6% | 1 | price_up-60251aba6e59 |
| 1192 | 쌍문삼익 79㎡ · 매매 -3.8% | 1 | price_down-7734f0bd16ea |
| 1193 | 월계삼호4차 59㎡ · 매매 +28.1% | 1 | price_up-dc0d5bc293ba |
| 1194 | 올림픽훼밀리타운 158㎡ · 매매 -3.8% | 1 | price_down-f3602a9489e9 |
| 1195 | 하왕금호베스트빌 114㎡ · 매매 +28.0% | 1 | price_up-356a5d991bc5 |

</details>

from services.baseline_service import get_subway_percentiles
from services.baseline_service import get_cctv_percentiles
from services.baseline_service import get_convenience_percentiles
from services.baseline_service import get_mart_percentiles
from services.baseline_service import get_cafe_percentiles


CATEGORY_META = {
    "subway": {
        "label": "🚇 지하철역",
        "description": "지하철역 접근성과 역까지의 거리를 기준으로 계산합니다.",
        "empty": "반경 내 확인된 지하철역이 아직 없습니다.",
        "radius": 1500,
        "percentile": 42,
    },
    "bus": {
        "label": "🚌 버스정류장",
        "description": "버스정류장 접근성과 노선 수를 기준으로 계산합니다.",
        "empty": "반경 내 확인된 버스 데이터가 아직 없습니다.",
        "radius": 400,
        "percentile": 35,
    },
    "bike": {
        "label": "🚲 따릉이",
        "description": "서울시 공공자전거 따릉이 대여소 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 따릉이 대여소 데이터가 아직 없습니다.",
        "radius": 500,
        "percentile": None,
    },
    "mart": {
        "label": "🛒 대형마트",
        "description": "일상 장보기 가능한 대형마트 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 대형마트가 아직 없습니다.",
        "radius": 1500,
        "percentile": 28,
        "frequency_weight": 0.45,
    },
    "cafe": {
        "label": "☕ 카페",
        "description": "카페 밀도와 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 카페 데이터가 아직 없습니다.",
        "radius": 500,
        "percentile": 6,
        "frequency_weight": 1.0,
    },
    "hospital": {
        "label": "🏥 병원",
        "description": "병원과 약국 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 병원 데이터가 아직 없습니다.",
        "radius": 700,
        "percentile": 8,
        "frequency_weight": 0.6,
    },
    "park": {
        "label": "🌳 공원",
        "description": "서울시 주요 공원 및 대형 녹지 접근성을 반영합니다",
        "empty": "반경 내 확인된 공원 데이터가 아직 없습니다.",
        "radius": 1500,
        "percentile": 31,
        "frequency_weight": 0.7,
    },
    "hangang": {
        "label": "🌊 한강",
        "description": "한강공원과 수변 접근성을 별도 요소로 계산합니다.",
        "empty": "반경 내 확인된 한강/수변 데이터가 아직 없습니다.",
        "radius": 3000,
        "percentile": 18,
    },
    "academy": {
        "label": "✏️ 학원",
        "description": "학원 밀도와 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 학원 데이터가 아직 없습니다.",
        "radius": 1000,
        "percentile": 22,
    },
    "fire-station": {
        "label": "🚒 119안전센터/구조대",
        "description": "119안전센터와 구조대 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 119안전센터/구조대 정보가 없습니다.",
        "radius": 1500,
        "percentile": None,
    },
    "cctv": {
        "label": "🛡 CCTV",
        "description": "CCTV와 주변 안전 인프라를 기준으로 계산합니다.",
        "empty": "반경 내 확인된 CCTV 데이터가 아직 없습니다.",
        "radius": 500,
        "percentile": 19,
        "frequency_weight": 0.8,
    },
    "nightlife": {
        "label": "🍺 유흥주점",
        "description": "유흥주점은 사용자 취향에 따라 플러스 또는 마이너스로 반영됩니다.",
        "empty": "반경 내 확인된 유흥주점 데이터가 아직 없습니다.",
        "radius": 500,
        "percentile": 55,
    },
    "commercial": {
        "label": "🌃 상권 활기",
        "description": "서울시 상권분석서비스 영역 데이터를 기준으로 주변 상권 접근성을 계산합니다.",
        "empty": "반경 내 확인된 상권 데이터가 없습니다.",
        "radius": 1000,
        "percentile": None,
    },
    "culture": {
        "label": "🎭 문화생활",
        "description": "공연, 전시, 체육, 체험 등 생활권 문화활동 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 문화생활 데이터가 없습니다.",
        "radius": 1500,
        "percentile": None,
    },
    "shopping": {
        "label": "🛍 쇼핑",
        "description": "대형마트를 제외한 백화점, 쇼핑몰, 시장 등 쇼핑시설 접근성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 쇼핑시설 데이터가 없습니다.",
        "radius": 3000,
        "percentile": None,
    },
    "pharmacy": {
        "label": "💊 약국",
        "description": "약국 접근성과 주변 의료 편의성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 약국 데이터가 아직 없습니다.",
        "radius": 700,
        "percentile": 15,
    },
    "convenience": {
        "label": "🏪 편의점",
        "description": "편의점 접근성과 생활 편의성을 기준으로 계산합니다.",
        "empty": "반경 내 확인된 편의점 데이터가 아직 없습니다.",
        "radius": 500,
        "percentile": 12,
        "frequency_weight": 1.3,
    },
    "ev-charger": {
        "label": "⚡ 전기차 충전",
        "description": "아파트 주변 전기차 충전소 접근성을 기준으로 계산합니다.",
        "empty": "반경 1km 안에서 확인된 전기차 충전소 정보가 없습니다.",
        "radius": 1000,
        "percentile": None,
    },
}

DOMAIN_META = {
    "transport": {
        "label": "🚇 교통",
        "description": "지하철, 버스 등 이동 편의성",
        "initial_load": True,
    },
    "medical": {
        "label": "🏥 의료",
        "description": "병원, 약국 등 의료 접근성",
        "initial_load": True,
    },
    "convenience": {
        "label": "🛒 생활편의",
        "description": "마트, 편의점 등 일상 편의시설",
        "initial_load": True,
    },
    "rest": {
        "label": "☕ 휴식/여가",
        "description": "카페, 공원, 한강 등 휴식 요소",
        "initial_load": True,
    },
    "culture": {
        "label": "🎭 문화생활",
        "description": "공연, 전시, 체육, 체험 등 활동형 여가",
        "initial_load": False,
    },
    "education": {
        "label": "🏫 교육",
        "description": "학원, 교육 인프라",
        "initial_load": False,
    },
    "safety": {
        "label": "🛡 안전",
        "description": "CCTV, 파출소, 소방서 등 안전 요소",
        "initial_load": False,
    },
    "activity": {
        "label": "🌃 상권/활기",
        "description": "유흥시설, 상권 밀집도",
        "initial_load": False,
    },
}


CATEGORY_TO_DOMAIN = {
    "subway": "transport",
    "bus": "transport",
    "bike": "transport",

    "hospital": "medical",
    "pharmacy": "medical",

    "mart": "convenience",
    "convenience": "convenience",
    "ev-charger": "convenience",

    "cafe": "rest",
    "park": "rest",
    "hangang": "rest",

    "culture": "culture",

    "academy": "education",

    "cctv": "safety",
    "fire-station": "safety",

    "nightlife": "activity",
    "commercial": "activity",
    "shopping": "activity",
}

SUBTYPE_RULES = {
    "hospital": [
        {"name": "치과", "keywords": ["치과"]},
        {"name": "내과", "keywords": ["내과"]},
        {"name": "소아과", "keywords": ["소아", "소아청소년"]},
        {"name": "산부인과", "keywords": ["산부인과"]},
        {"name": "정형외과", "keywords": ["정형외과"]},
        {"name": "안과", "keywords": ["안과"]},
        {"name": "이비인후과", "keywords": ["이비인후과", "이비인후"]},
        {"name": "피부과", "keywords": ["피부과"]},
        {"name": "정신건강의학과", "keywords": ["정신건강", "정신과"]},
        {"name": "대학병원", "keywords": ["대학병원", "대학교병원"]},
        {"name": "비뇨기과", "keywords": ["비뇨기과", "비뇨"]},
        {"name": "한의원", "keywords": ["한의원", "한방"]},
        {"name": "성형외과", "keywords": ["성형외과", "성형"]},
        {"name": "신경/통증의학과", "keywords": ["신경", "통증"]},
        {"name": "동물병원", "keywords": ["동물", "동물병원", "가축"]},
    ],
    "cafe": [
        {
            "name": "스타벅스",
            "display": "스타벅스",
            "keywords": ["스타벅스"],
            "priority": 1,
            "style": "brand-starbucks",
        },
        {
            "name": "투썸플레이스",
            "display": "투썸",
            "keywords": ["투썸", "투썸플레이스"],
            "priority": 2,
            "style": "brand-twosome",
        },
        {
            "name": "메가MGC",
            "display": "메가MGC",
            "keywords": ["메가MGC", "메가엠지씨", "MEGA MGC", "MEGAMGC"],
            "priority": 3,
            "style": "brand-mega",
        },
        {
            "name": "컴포즈커피",
            "display": "컴포즈",
            "keywords": ["컴포즈", "컴포즈커피"],
            "priority": 4,
            "style": "brand-compose",
        },
        {
            "name": "이디야",
            "display": "이디야",
            "keywords": ["이디야"],
            "priority": 5,
            "style": "brand-ediya",
        },
        {
            "name": "빽다방",
            "display": "빽다방",
            "keywords": ["빽다방"],
            "priority": 6,
            "style": "brand-paik",
        },
    ],
    "subway": [
        {"name": "지하철역", "keywords": ["역"]},
    ],
    "mart": [
        {
            "name": "이마트",
            "display": "이마트",
            "keywords": ["이마트", "emart", "E-MART"],
            "priority": 2,
            "style": "brand-emart",
        },
        {
            "name": "홈플러스",
            "display": "홈플러스",
            "keywords": ["홈플러스", "Homeplus"],
            "priority": 5,
            "style": "brand-homeplus",
        },
        {
            "name": "롯데마트",
            "display": "롯데마트",
            "keywords": ["롯데마트", "롯데슈퍼", "롯데프레시", "롯데슈퍼프레시", "롯데쇼핑"],
            "priority": 4,
            "style": "brand-lottemart",
        },
        {
            "name": "트레이더스",
            "display": "트레이더스",
            "keywords": ["트레이더스", "이마트트레이더스"],
            "priority": 3,
            "style": "brand-traders",
        },
        {
            "name": "코스트코",
            "display": "코스트코",
            "keywords": ["코스트코", "Costco"],
            "priority": 1,
            "style": "brand-costco",
        },
        {
            "name": "GS더프레시",
            "display": "GS더프레시",
            "keywords": ["GS더프레시", "GS THE FRESH", "지에스더프레시"],
            "priority": 6,
            "style": "brand-gsfresh",
        },
        {
            "name": "하나로마트",
            "display": "하나로마트",
            "keywords": ["하나로마트"],
            "priority": 7,
            "style": "brand-hanaro",
        },

    ],
    "pharmacy": [
        {
            "name": "W스토어",
            "display": "W스토어",
            "keywords": ["W스토어", "더블유스토어", "W STORE", "W-STORE"],
            "priority": 1,
            "style": "brand-wstore",
        },
        {
            "name": "약국",
            "display": "약국",
            "keywords": ["약국"],
            "priority": 2,
            "style": "brand-pharmacy",
        },
    ],
    "convenience": [
        {
            "name": "CU",
            "display": "CU",
            "keywords": ["CU ", "CU", "씨유"],
            "priority": 1,
            "style": "brand-cu",
        },
        {
            "name": "GS25",
            "display": "GS25",
            "keywords": ["GS25", "지에스25"],
            "priority": 2,
            "style": "brand-gs25",
        },
        {
            "name": "세븐일레븐",
            "display": "세븐일레븐",
            "keywords": ["세븐일레븐", "7ELEVEN", "Seven Eleven"],
            "priority": 3,
            "style": "brand-seven",
        },
        {
            "name": "이마트24",
            "display": "이마트24",
            "keywords": ["이마트24", "emart24"],
            "priority": 4,
            "style": "brand-emart24",
        },
        ],
        "cctv": [
            {
                "name": "생활방범",
                "display": "생활방범",
                "keywords": ["생활방범", "방범"],
                "priority": 1,
                "style": "brand-cctv-safety",
            },
            {
                "name": "어린이보호",
                "display": "어린이보호",
                "keywords": ["어린이보호", "어린이", "보호"],
                "priority": 2,
                "style": "brand-cctv-child",
            },
            {
                "name": "교통/단속",
                "display": "교통/단속",
                "keywords": ["교통/단속", "교통", "단속"],
                "priority": 3,
                "style": "brand-cctv-traffic",
            },
            {
                "name": "시설안전",
                "display": "시설안전",
                "keywords": ["시설안전", "시설"],
                "priority": 4,
                "style": "brand-cctv-facility",
            },
        ],
        "park": [
        {
            "name": "대형공원",
            "display": "대형공원",
            "keywords": ["대형공원"],
            "priority": 1,
            "style": "brand-park-large",
        },
        {
            "name": "중형공원",
            "display": "중형공원",
            "keywords": ["중형공원"],
            "priority": 2,
            "style": "brand-park-medium",
        },
        {
            "name": "소형공원",
            "display": "소형공원",
            "keywords": ["소형공원"],
            "priority": 3,
            "style": "brand-park-small",
        },
        ],
}

def get_subtype_chips(category, pois):
    rules = SUBTYPE_RULES.get(category, [])

    if not rules:
        counts = {}

        for poi in pois:
            subtype = poi.get("subtype") or "기타"
            counts[subtype] = counts.get(subtype, 0) + 1
            poi["subtype"] = subtype

        chips = [
            {
                "name": name,
                "display": name,
                "count": count,
                "style": "brand-etc",
                "priority": 9999,
                "nearest_distance": None,
            }
            for name, count in counts.items()
        ]

        chips.sort(key=lambda x: x["name"])

        return chips

    counts = {}
    styles = {}
    displays = {}
    priorities = {}
    min_distances = {}

    for poi in pois:
        poi_name = " ".join([
            str(poi.get("name", "")),
            str(poi.get("label", "")),
            str(poi.get("subtype", "")),
        ])
        distance = poi.get("distance", 99999)

        matched = False

        for rule in rules:
            for keyword in rule["keywords"]:
                if keyword.lower() in poi_name.lower():

                    name = rule["name"]

                    counts[name] = counts.get(name, 0) + 1
                    styles[name] = rule.get("style", "")
                    displays[name] = rule.get("display", name)
                    priorities[name] = rule.get("priority", 999)

                    if name not in min_distances:
                        min_distances[name] = distance
                    else:
                        min_distances[name] = min(
                            min_distances[name],
                            distance
                        )

                    poi["subtype"] = name

                    matched = True
                    break

            if matched:
                break

        if not matched:
            counts["기타"] = counts.get("기타", 0) + 1
            styles["기타"] = "brand-etc"
            displays["기타"] = "기타"
            priorities["기타"] = 9999

            if "기타" not in min_distances:
                min_distances["기타"] = distance
            else:
                min_distances["기타"] = min(
                    min_distances["기타"],
                    distance
                )

            poi["subtype"] = "기타"

    chips = []

    for name, count in counts.items():
        chips.append({
            "name": name,
            "display": displays[name],
            "count": count,
            "style": styles[name],
            "priority": priorities[name],
            "nearest_distance": min_distances.get(name),
        })

    chips.sort(key=lambda x: (x["priority"], -x["count"]))

    return chips

def distance_weight(distance):
    if distance <= 200:
        return 1.0
    elif distance <= 500:
        return 0.7
    elif distance <= 1000:
        return 0.4
    return 0.15


def calculate_dynamic_score(pois, frequency_weight=1.0):
    if not pois:
        return 0

    weighted_sum = 0

    for poi in pois:
        distance = poi.get("distance", 99999)

        weighted_sum += (
            distance_weight(distance)
            * frequency_weight
        )

    score = min(weighted_sum * 12, 100)

    return round(score)

def get_score_class(score):
    if score >= 80:
        return "score-good"

    if score >= 60:
        return "score-normal"

    return "score-low"


def get_category_summaries(apartment, preference_keys):
    pois = apartment.get("pois", [])

   
    scores = apartment.get("scores", {})
    summaries = []

    for key in preference_keys:
        related_pois = [
            poi for poi in pois
            if poi.get("category") == key
        ]

        meta = CATEGORY_META[key]

        frequency_weight = meta.get("frequency_weight", 1.0)

        score = calculate_dynamic_score(
            related_pois,
            frequency_weight
        )

        subtype_chips = get_subtype_chips(key, related_pois)

        nearest_poi = None

        percentile = meta.get("percentile")

        seoul_percentile = None
        gu_percentile = None

        if related_pois:
            nearest_poi = min(
                related_pois,
                key=lambda x: x.get("distance", 99999)
            )

            seoul_percentile = None
            gu_percentile = None

            if key == "subway":
                percentile_result = get_subway_percentiles(
                    nearest_poi.get("distance"),
                    apartment.get("district")
                )

                seoul_percentile = percentile_result.get("seoul")
                gu_percentile = percentile_result.get("gu")
            
            if key == "cctv":
                percentile_result = get_cctv_percentiles(
                    len(related_pois),
                    apartment.get("district")
                )

                seoul_percentile = percentile_result.get("seoul")
                gu_percentile = percentile_result.get("gu")

            if key == "convenience":

                percentile_result = (
                    get_convenience_percentiles(
                        len(related_pois),
                        apartment.get("district")
                    )
                )

                seoul_percentile = percentile_result.get("seoul")
                gu_percentile = percentile_result.get("gu")

            if key == "mart":
                percentile_result = get_mart_percentiles(
                    len(related_pois),
                    apartment.get("district")
                )

                seoul_percentile = percentile_result.get("seoul")
                gu_percentile = percentile_result.get("gu")
                
            if key == "cafe":
                percentile_result = get_cafe_percentiles(
                    len(related_pois),
                    apartment.get("district")
                )

                seoul_percentile = (
                    percentile_result.get("seoul")
                )

                gu_percentile = (
                    percentile_result.get("gu")
                )

                seoul_percentile = percentile_result.get("seoul")
                gu_percentile = percentile_result.get("gu")

        summaries.append({
            "key": key,
            "label": meta["label"],
            "domain": CATEGORY_TO_DOMAIN.get(key, "etc"),
            "domain_label": DOMAIN_META.get(CATEGORY_TO_DOMAIN.get(key, ""), {}).get("label", "기타"),
            "description": meta["description"],
            "empty": meta["empty"],
            "score": score,
            "score_class": get_score_class(score),
            "count": len(related_pois),
            "pois": related_pois,
            "radius": meta["radius"],
            "percentile": seoul_percentile if seoul_percentile is not None else percentile,
            "subtype_chips": subtype_chips,
            "nearest_poi": nearest_poi,
            "source": (
                "공공데이터포털"
                if key == "cctv"
                else "서울시 공공데이터"
                if key == "park"
                else "Kakao Local API"
            ),
            "seoul_percentile": seoul_percentile,
            "gu_percentile": gu_percentile,
        })


    return summaries


def get_preference_labels():
    return {
        key: value["label"]
        for key, value in CATEGORY_META.items()
    }


def get_sample_pois(apartment):
    return apartment.get("pois", [])

def get_domain_summaries(category_summaries):
    domain_map = {}

    for summary in category_summaries:
        domain_key = summary.get("domain", "etc")

        if domain_key not in domain_map:
            meta = DOMAIN_META.get(domain_key, {
                "label": "기타",
                "description": "",
                "initial_load": False,
            })

            domain_map[domain_key] = {
                "key": domain_key,
                "label": meta["label"],
                "description": meta["description"],
                "initial_load": meta["initial_load"],
                "category_count": 0,
                "poi_count": 0,
                "categories": [],
                "max_score": 0,
            }

        domain_map[domain_key]["category_count"] += 1
        domain_map[domain_key]["poi_count"] += summary.get("count", 0)
        domain_map[domain_key]["categories"].append(summary)
        domain_map[domain_key]["max_score"] = max(
            domain_map[domain_key]["max_score"],
            summary.get("score", 0),
        )

    domains = list(domain_map.values())

    # Domain 안의 카테고리는 점수 높은 순
    for domain in domains:
        domain["categories"].sort(
            key=lambda x: x.get("score", 0),
            reverse=True
        )

    # Domain 자체도 가장 높은 카테고리 점수 기준 정렬
    domains.sort(
        key=lambda x: x.get("max_score", 0),
        reverse=True
    )

    return domains

def calculate_percentile(value, values):

    if not values:
        return 0

    sorted_values = sorted(values)

    rank = 0

    for v in sorted_values:
        if value <= v:
            break
        rank += 1

    percentile = 100 - (
        rank / len(sorted_values)
    ) * 100

    return round(percentile)

def get_subway_distance_baseline(apartment_data):

    distances = []

    for apt in apartment_data:

        lat = apt.get("lat")
        lng = apt.get("lng")

        if not lat or not lng:
            continue

        pois = fetch_kakao_category_places(
            lat,
            lng,
            "subway"
        )

        if not pois:
            continue

        nearest = min(
            poi["distance"]
            for poi in pois
        )

        distances.append(nearest)

    return distances

import re


def to_number(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def to_int(value, default=0):
    number = to_number(value)
    if number is None:
        return default
    return int(number)


def format_meters(value):
    number = to_number(value)
    if number is None:
        return ""
    return f"{int(round(number)):,}m"


def find_summary(category_summaries, key):
    return next(
        (summary for summary in category_summaries if summary.get("key") == key),
        None,
    )


def find_chip(summary, keyword):
    if not summary:
        return None
    for chip in summary.get("subtype_chips", []):
        text = f"{chip.get('name', '')} {chip.get('display', '')}"
        if keyword in text:
            return chip
    return None


def nearest_distance(summary):
    if not summary:
        return None
    nearest = summary.get("nearest_poi") or {}
    return to_number(nearest.get("distance"))


def clean_label(value):
    text = str(value or "").strip()
    text = re.sub(r"^[^\w가-힣]+", "", text).strip()
    return text


def nearest_name(summary):
    if not summary:
        return ""
    nearest = summary.get("nearest_poi") or {}
    return clean_label(nearest.get("label") or nearest.get("name"))


def evidence(summary, count_label=None, radius_label=None, fallback_name="최근접"):
    count = to_int((summary or {}).get("count"))
    distance = nearest_distance(summary)
    name = nearest_name(summary) or fallback_name
    parts = []
    if distance is not None:
        parts.append(f"{name} {format_meters(distance)}")
    elif name and name != fallback_name:
        parts.append(name)
    if count_label and count:
        parts.append(f"{radius_label or '반경 내'} {count:,}곳")
    return " · ".join(parts)


def add_feature(features, icon, label, tone="good", reason="", priority=50):
    if any(item.get("label") == label for item in features):
        return
    features.append({
        "icon": icon,
        "label": label,
        "tone": tone,
        "reason": reason,
        "priority": priority,
    })


def add_message(messages, icon, title, body="", tone="good"):
    if any(item.get("title") == title for item in messages):
        return
    messages.append({
        "icon": icon,
        "title": title,
        "body": body,
        "tone": tone,
    })


def chip_count(chip):
    if not chip:
        return 0
    for key in ("count", "value"):
        number = to_int(chip.get(key), None)
        if number is not None:
            return number
    text = str(chip.get("display") or chip.get("name") or "")
    match = re.search(r"(\d+)", text.replace(",", ""))
    return int(match.group(1)) if match else 0


def build_apartment_insight(apartment, category_summaries, preference_tags=None, complex_info=None):
    preference_tags = preference_tags or []
    complex_info = complex_info or {}

    subway = find_summary(category_summaries, "subway")
    bus = find_summary(category_summaries, "bus-baseline")
    bike = find_summary(category_summaries, "bike")
    mart = find_summary(category_summaries, "mart")
    cafe = find_summary(category_summaries, "cafe")
    culture = find_summary(category_summaries, "culture")
    hangang = find_summary(category_summaries, "hangang")
    academy = find_summary(category_summaries, "academy")
    nightlife = find_summary(category_summaries, "nightlife")
    emergency = find_summary(category_summaries, "emergency-room")
    general_hospital = find_summary(category_summaries, "general-hospital")
    pharmacy = find_summary(category_summaries, "pharmacy")
    ev = find_summary(category_summaries, "ev-charger")

    features = []
    strengths = []
    cautions = []
    lifestyle_types = []

    subway_distance = nearest_distance(subway)
    subway_text = " ".join([
        str((subway or {}).get("nearest_poi", {}).get("label", "")),
        " ".join(str(chip.get("name", "")) for chip in (subway or {}).get("subtype_chips", [])),
    ])
    transfer_chip = find_chip(subway, "환승")
    if "9호선" in subway_text:
        add_feature(
            features,
            "🚇",
            "9호선 접근",
            "good",
            evidence(subway, True, "1km 내", "지하철"),
            5,
        )
    if transfer_chip:
        count = chip_count(transfer_chip)
        add_feature(features, "🚇", "환승역 접근", "good", f"{nearest_name(subway) or '환승역'} · 1km 내 {count}곳" if count else evidence(subway, True, "1km 내", "환승역"), 8)
        add_message(strengths, "🚇", "환승역 접근성이 좋습니다", "여러 노선으로 갈아타기 쉬운 입지입니다.")
    if subway_distance is not None and subway_distance <= 500:
        add_feature(features, "🚶", "도보 역세권", "good", evidence(subway, True, "1km 내", "지하철"), 10)

    bus_count = to_int((bus or {}).get("count"))
    if bus_count >= 5 and subway_distance is not None and subway_distance <= 800:
        add_feature(features, "🚶", "차 없이 살기 좋은 곳", "good", f"{nearest_name(subway) or '지하철'} {format_meters(subway_distance)} · 버스 {bus_count:,}곳", 18)
        lifestyle_types.append("도보생활형")
    if to_int((bike or {}).get("count")) >= 3:
        add_feature(features, "🚲", "따릉이 접근", "good", evidence(bike, True, "500m 내", "따릉이"), 35)

    emergency_distance = nearest_distance(emergency)
    if emergency_distance is not None and emergency_distance <= 3000:
        add_feature(features, "🚑", "응급 의료 접근", "good", evidence(emergency, True, "3km 내", "응급실"), 12)
        lifestyle_types.append("의료안심형")
    general_count = to_int((general_hospital or {}).get("count"))
    if general_count > 0:
        add_feature(features, "🏨", "종합병원 생활권", "good", evidence(general_hospital, True, "5km 내", "종합병원"), 16)
    night_pharmacy = find_chip(pharmacy, "야간")
    if night_pharmacy:
        add_feature(features, "💊", "야간약국 접근", "good", f"{nearest_name(pharmacy) or '약국'} · 야간 {chip_count(night_pharmacy):,}곳", 24)

    costco_chip = find_chip(mart, "코스트코")
    if costco_chip:
        add_feature(features, "🛒", "코스트코 접근", "good", f"{nearest_name(mart) or '대형마트'} · 코스트코 {chip_count(costco_chip):,}곳", 20)
    elif to_int((mart or {}).get("count")) >= 2:
        add_feature(features, "🛒", "대형마트 생활권", "good", evidence(mart, True, "반경 내", "대형마트"), 28)

    starbucks_chip = find_chip(cafe, "스타벅스")
    if starbucks_chip:
        add_feature(features, "☕", "스타벅스 접근", "good", f"{nearest_name(cafe) or '카페'} · 스타벅스 {chip_count(starbucks_chip):,}곳", 34)
    elif to_int((cafe or {}).get("count")) >= 5:
        add_feature(features, "☕", "카페 밀집", "good", evidence(cafe, True, "500m 내", "카페"), 36)
    if to_int((cafe or {}).get("count")) >= 5:
        lifestyle_types.append("생활편의형")

    culture_text = " ".join(str(chip.get("name", "")) for chip in (culture or {}).get("subtype_chips", []))
    if "공연" in culture_text or "전시" in culture_text:
        add_feature(features, "🎭", "공연·전시 생활권", "good", evidence(culture, True, "1.5km 내", "문화시설"), 30)
        lifestyle_types.append("문화생활형")
    if "체험" in culture_text or "키즈" in culture_text:
        add_feature(features, "🧒", "키즈 체험 접근", "good", evidence(culture, True, "1.5km 내", "체험시설"), 32)
        lifestyle_types.append("육아형")

    hangang_distance = nearest_distance(hangang)
    if hangang_distance is not None and hangang_distance <= 1500:
        add_feature(features, "🌳", "한강 접근", "good", evidence(hangang, True, "반경 내", "한강공원"), 22)
        lifestyle_types.append("휴식형")

    nightlife_count = to_int((nightlife or {}).get("count"))
    if nightlife_count == 0:
        add_feature(features, "🌿", "조용한 주거형", "calm", "500m 내 유흥시설 없음", 26)
    elif nightlife_count >= 10:
        add_feature(features, "⚠", "유흥시설 밀집", "caution", f"500m 내 {nightlife_count}곳", 14)
        add_message(cautions, "⚠", "야간 상권 밀도가 높은 편입니다", "주거 조용함을 중시한다면 상세 위치를 함께 확인하세요.", "caution")

    academy_count = to_int((academy or {}).get("count"))
    if academy_count >= 50:
        add_feature(features, "🎓", "학원 밀집형", "good", evidence(academy, True, "1km 내", "학원"), 38)
        lifestyle_types.append("육아형")

    ev_count = to_int((ev or {}).get("count"))
    if ev_count > 0:
        add_feature(features, "⚡", "전기차 충전 접근", "good", evidence(ev, True, "1km 내", "충전소"), 40)

    for summary in category_summaries:
        percentile = to_number(summary.get("seoul_percentile"))
        if percentile is not None and percentile <= 20:
            add_message(
                strengths,
                "✓",
                f"{summary.get('label', '생활 요소')} 서울 상위권",
                f"서울 기준 상위 {max(1, int(percentile))}% 수준입니다.",
            )
        elif percentile is not None and percentile >= 85 and summary.get("key") not in {"nightlife", "school-environment"}:
            add_message(
                cautions,
                "ⓘ",
                f"{summary.get('label', '생활 요소')} 접근성은 보통 이하",
                "다른 장점과 함께 균형 있게 보는 편이 좋습니다.",
                "info",
            )

    if not lifestyle_types:
        lifestyle_types.append("균형형")

    features.sort(key=lambda item: item.get("priority", 50))
    primary_features = features[:6]
    feature_labels = [item["label"] for item in primary_features[:3]]
    if feature_labels:
        summary = f"{apartment.get('name', '이 단지')}는 " + ", ".join(feature_labels) + "이 눈에 띕니다."
    else:
        summary = f"{apartment.get('name', '이 단지')}는 주요 생활 요소를 균형 있게 확인해볼 필요가 있습니다."

    return {
        "summary": summary,
        "feature_tags": primary_features,
        "strengths": strengths[:4],
        "cautions": cautions[:4],
        "lifestyle_types": list(dict.fromkeys(lifestyle_types))[:4],
    }


def has_feature_from_rows(feature_key, rows):
    subway = rows.get("subway") or {}
    medical = rows.get("medical") or {}
    mart = rows.get("mart") or {}
    nightlife = rows.get("nightlife") or {}
    hangang = rows.get("hangang") or {}
    culture = rows.get("culture") or {}

    if feature_key == "transfer":
        return to_int(subway.get("transfer_station_count_1km")) > 0
    if feature_key == "emergency":
        return to_number(medical.get("nearest_emergency_distance")) is not None and to_number(medical.get("nearest_emergency_distance")) <= 3000
    if feature_key == "general_hospital":
        return to_int(medical.get("superior_hospital_count_5km")) > 0
    if feature_key == "costco":
        return to_number(mart.get("nearest_코스트코_distance")) is not None
    if feature_key == "nightlife_low":
        return to_int(nightlife.get("nightlife_count_500m")) == 0
    if feature_key == "hangang":
        return to_number(hangang.get("nearest_hangang_distance")) is not None and to_number(hangang.get("nearest_hangang_distance")) <= 1500
    if feature_key == "culture":
        return to_int(culture.get("culture_count_1500m")) > 0
    return False

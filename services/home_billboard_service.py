"""Serve a small offline ranking artifact; never read baseline CSVs here."""
import json
import logging
import math
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path


DEFAULT_DATA_PATH = "data/derived/home_rankings.json"
TOPICS = (
    ("academy", "academy-apartments", "Education", "입시·수학·영어 학원이 가장 많은 아파트", "반경 1,000m · 입시/보습+수학+영어"),
    ("dong_academy", "academy-neighborhoods", "Neighborhood", "입시·수학·영어 학원이 가장 많은 동네", "학원 주소의 법정동 · 입시/보습+수학+영어"),
    ("value_combo", "value-transit-academy", "Price × Life", "국민평형 10억 미만 + 역세권 + 학원가", "300세대 이상 · 가장 가까운 역 500m 이내 · 전체 학원 1,000m"),
    ("subway", "subway-lines", "Transit", "반경 500m 안에 지하철 노선이 가장 많은 아파트", "반경 500m · 서로 다른 지하철 노선"),
    ("starbucks", "starbucks", "Daily life", "스세권: 반경 500m 스타벅스가 가장 많은 아파트", "반경 500m · 스타벅스 매장"),
    ("convenience", "convenience-stores", "Daily life", "편세권: 편의점 4사 매장이 가장 많은 아파트", "반경 500m · GS25·CU·세븐일레븐·이마트24"),
    ("quiet", "quiet-large-complexes", "Safety", "반경 500m 유흥주점이 없는 1,000세대 이상 대단지", "최근접 유흥주점까지 직선거리가 먼 순"),
    ("emergency", "emergency-facilities", "Health", "반경 1km 안에 응급실이 가장 많은 아파트", "반경 1,000m · 응급실 운영 의료기관"),
    ("gu_best_dong", "district-academy-winners", "By district", "우리 구에서 학원이 가장 많은 동", "구별 법정동 1위 · 구 이름 가나다순"),
    ("price_up", "price-rising", "Price trend", "최근 6개월 매매가가 가장 많이 오른 아파트", "같은 단지·같은 전용면적 · 매매 중앙값 6개월 비교"),
    ("price_down", "price-falling", "Price trend", "최근 6개월 매매가가 가장 많이 내린 아파트", "같은 단지·같은 전용면적 · 매매 중앙값 6개월 비교"),
)
NUMERIC_FIELDS = {
    "academy": ("total", "exam", "math", "english", "households"),
    "dong_academy": ("total", "exam", "math", "english"),
    "value_combo": ("price84", "price84_n", "station_m", "academy_1km", "households"),
    "subway": ("lines", "stations", "nearest_m", "households"),
    "starbucks": ("count", "nearest_m", "households"),
    "convenience": ("total", "GS25", "CU", "세븐일레븐", "이마트24", "households"),
    "quiet": ("nearest_nightlife_m", "households"),
    "emergency": ("er_1km", "hospital_m", "households"),
    "gu_best_dong": ("total",),
    "price_up": ("change_pct", "area", "prev_median", "recent_median", "prev_n", "recent_n", "households"),
    "price_down": ("change_pct", "area", "prev_median", "recent_median", "prev_n", "recent_n", "households"),
}
# 하락률은 음수로 저장한다. 나머지 숫자는 모두 0 이상이어야 한다.
SIGNED_FIELDS = {"change_pct"}
GROUPS = (
    ("education", "학원가와 동네", "같은 학원도 단지 주변과 동네 전체로 보면 다른 답이 됩니다.", ("academy", "dong_academy", "gu_best_dong")),
    ("value-transit", "매매가 및 교통", "예산, 역까지의 거리, 생활 인프라를 함께 살펴보세요.", ("value_combo", "subway")),
    ("price-trend", "최근 6개월 매매가 추이", "같은 단지·같은 면적끼리, 최근 6개월과 그 전 6개월의 실거래 중앙값을 비교했습니다.", ("price_up", "price_down")),
    ("daily", "생활의 편리함", "자주 찾는 가게부터 응급의료와 주변 환경까지, 집 가까이의 숫자입니다.", ("starbucks", "convenience", "quiet", "emergency")),
)
QUESTIONS = {
    "academy": "입시·수학·영어 학원이 가장 많이 모인 아파트는?",
    "dong_academy": "입시·수학·영어 학원이 가장 많은 동네는?",
    "value_combo": "10억 미만 국민평형, 역도 학원가도 가까운 곳은?",
    "subway": "500m 안에서 가장 많은 지하철 노선을 이용할 수 있는 곳은?",
    "starbucks": "500m 안에 스타벅스가 가장 많은 아파트는?",
    "convenience": "500m 안에 편의점 4사 매장이 가장 많은 곳은?",
    "quiet": "500m 안에 유흥주점이 없는 대단지, 가장 멀리 떨어진 곳은?",
    "emergency": "1km 안에 응급실 운영 의료기관이 가장 많은 곳은?",
    "gu_best_dong": "우리 구에서는 어느 동에 학원이 가장 많을까?",
    "price_up": "최근 6개월, 매매가가 가장 많이 오른 아파트는?",
    "price_down": "최근 6개월, 매매가가 가장 많이 내린 아파트는?",
}
TOPIC_SOURCES = {
    "academy": ("academy",), "dong_academy": ("academy",), "gu_best_dong": ("academy",),
    "value_combo": ("transactions", "master", "subway", "academy"), "subway": ("subway",),
    "starbucks": ("cafe",), "convenience": ("convenience",), "quiet": ("nightlife", "master"),
    "emergency": ("medical",),
    "price_up": ("transactions", "master"), "price_down": ("transactions", "master"),
}


def validate_rankings(data):
    """Reject corrupt/incompatible artifacts before exposing any partial rankings."""
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported home ranking schema")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(data.get("data_month", ""))):
        raise ValueError("Invalid data_month")
    datetime.fromisoformat(data["generated_at"])
    if "complex_count" in data and (type(data["complex_count"]) is not int or data["complex_count"] < 0):
        raise ValueError("Invalid complex_count")
    definitions = data.get("definitions")
    if not isinstance(definitions, dict) or not isinstance(data.get("sources"), dict):
        raise ValueError("Missing definitions/sources")
    for source_key in ("academy", "subway", "cafe", "convenience", "nightlife", "medical", "transactions", "master"):
        source = data["sources"].get(source_key)
        if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not source["name"]:
            raise ValueError(f"Invalid source: {source_key}")
        collected = source["collected_at"]
        if collected is not None:
            if not isinstance(collected, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collected):
                raise ValueError(f"Invalid collected_at: {source_key}")
            date.fromisoformat(collected)
    for key in (*NUMERIC_FIELDS, "changes"):
        rules = definitions.get(key)
        if not isinstance(rules, list) or not rules:
            raise ValueError(f"Missing rules: {key}")
        for rule in rules:
            if not isinstance(rule, list) or len(rule) != 2 or not all(isinstance(v, str) and v for v in rule):
                raise ValueError(f"Invalid rule: {key}")
    for key, *_ in TOPICS:
        rows = data.get(key)
        if not isinstance(rows, list) or len(rows) > 50:
            raise ValueError(f"Invalid rows: {key}")
        identities = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Invalid row: {key}")
            strings = ["gu", "dong"]
            if key not in ("dong_academy", "gu_best_dong"):
                strings.append("name")
            for field in strings:
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError(f"Missing {key}.{field}")
            identity = tuple(row[f] for f in strings)
            if identity in identities:
                raise ValueError(f"Duplicate identity: {key}")
            identities.add(identity)
            for field in {"value_combo": ("station",), "subway": ("nearest",), "emergency": ("hospital",)}.get(key, ()):
                if not isinstance(row.get(field), str):
                    raise ValueError(f"Invalid {key}.{field}")
            if key == "subway" and not (isinstance(row.get("line_names"), list)
                                        and all(isinstance(v, str) and v for v in row["line_names"])):
                raise ValueError("Invalid subway.line_names")
            for field in NUMERIC_FIELDS[key]:
                value = row.get(field)
                if type(value) not in (int, float) or not math.isfinite(value) or (value < 0 and field not in SIGNED_FIELDS):
                    raise ValueError(f"Invalid {key}.{field}")
            if key in ("price_up", "price_down") and (row["change_pct"] > 0) != (key == "price_up"):
                raise ValueError(f"Invalid {key}.change_pct direction")
    for key in ("new_complexes", "er_changes"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"Missing changes: {key}")
        for row in data[key]:
            if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("name", "gu")):
                raise ValueError(f"Invalid change: {key}")
            if key == "new_complexes":
                value = row.get("households")
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid new_complexes.households")
                fields = ("dong", "built")
            else:
                value = row.get("distance")
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid er_changes.distance")
                fields = ("dong", "hospital")
            if not all(isinstance(row.get(field), str) for field in fields):
                raise ValueError(f"Invalid change display: {key}")
    hospitals = data.get("er_hospitals", [])
    if not isinstance(hospitals, list) or not all(
            isinstance(h, dict) and all(isinstance(h.get(k), str) for k in ("name", "gu", "dong")) for h in hospitals):
        raise ValueError("Invalid er_hospitals")
    if not isinstance(data.get("changes_meta"), dict):
        raise ValueError("Missing changes_meta")
    for key in ("master_compared", "er_compared"):
        if type(data["changes_meta"].get(key)) is not bool:
            raise ValueError(f"Invalid changes_meta.{key}")
    return data


@lru_cache(maxsize=2)
def load_rankings(path):
    """Read once per process/path. Monthly updates require worker restart."""
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return validate_rankings(json.load(handle))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logging.getLogger(__name__).warning("Home rankings unavailable: %s", exc)
        return None


def configure(app, env):
    for key, default in (
        ("BILLBOARD_ENABLED", "1"), ("GRAPH_ENABLED", "1"),
        ("MOBILE_ENABLED", "1"), ("KAKAO_RANKINGS_ENABLED", "1"),
        ("RANKING_PAGES_ENABLED", "1"),
    ):
        app.config["HOME_" + key] = env("HOME_" + key, default) == "1"
    try:
        limit = int(env("HOME_RANKING_LIMIT", "20"))
    except ValueError:
        limit = 20
    app.config["HOME_RANKING_LIMIT"] = max(20, min(50, limit))
    app.config["HOME_RANKINGS_PATH"] = env("HOME_RANKINGS_PATH", str(Path(app.root_path) / DEFAULT_DATA_PATH))


def settings(config):
    return {
        "billboard_enabled": config["HOME_BILLBOARD_ENABLED"],
        "graph_enabled": config["HOME_GRAPH_ENABLED"],
        "mobile_enabled": config["HOME_MOBILE_ENABLED"],
        "kakao_enabled": config["HOME_KAKAO_RANKINGS_ENABLED"],
        "pages_enabled": config["HOME_RANKING_PAGES_ENABLED"],
        "ranking_limit": max(20, min(50, int(config["HOME_RANKING_LIMIT"]))),
    }


def _number(value):
    return f"{value:,}"


def _eok(manwon):
    """만원 → '7억', '13억 4,000만', '9,500만'."""
    eok, rest = divmod(int(manwon), 10000)
    if not eok:
        return f"{rest:,}만"
    return f"{eok}억" + (f" {rest:,}만" if rest else "")


def _values(key, row):
    n = lambda field: _number(row[field])
    if key in ("price_up", "price_down"):
        return f"{row['change_pct']:+.1f}%", f"전용 {row['area']}㎡ · {_eok(row['prev_median'])} → {_eok(row['recent_median'])}"
    if key in ("academy", "dong_academy"):
        return f"{n('total')}곳", f"입시 {n('exam')} · 수학 {n('math')} · 영어 {n('english')}"
    if key == "gu_best_dong":
        return f"{n('total')}곳", "입시/보습·수학·영어"
    if key == "value_combo":
        # Show the stored mean in 만원: rounding 9.99억 up to 10억 obscures the strict filter.
        return f"학원 {n('academy_1km')}곳", f"최근 6개월 전용 80~90㎡ 평균 {n('price84')}만원({n('price84_n')}건) · {row['station']} {n('station_m')}m"
    if key == "subway":
        return f"{n('lines')}개 노선", " · ".join(row["line_names"])
    if key == "starbucks":
        return f"{n('count')}곳", f"가장 가까운 매장 {n('nearest_m')}m"
    if key == "convenience":
        return f"{n('total')}곳", f"GS25 {n('GS25')} · CU {n('CU')} · 세븐 {n('세븐일레븐')} · 이마트24 {n('이마트24')}"
    if key == "quiet":
        return f"{n('nearest_nightlife_m')}m", f"가장 가까운 유흥주점까지 · {n('households')}세대"
    return f"응급실 {n('er_1km')}곳", f"종합병원급 {row['hospital']} {n('hospital_m')}m"


def _answer(key, rows, month):
    """A citable sentence drawn only from the stored first row and fixed definition."""
    if key == "gu_best_dong":
        return f"{month} 데이터 기준, 각 구에서 개원 상태의 입시/보습·수학·영어 학원·교습소가 가장 많은 법정동을 선정했습니다. 구 이름순으로 표시하며, 구 사이의 순위는 아닙니다."
    if not rows:
        return f"{month} 데이터에서 이 조건에 맞는 집계 결과가 없습니다."
    row = rows[0]
    n = lambda field: _number(row[field])
    place = f"{row['gu']} {row['dong']}" + (f" {row['name']}" if key != "dong_academy" else "")
    if key == "academy":
        fact = f"단지 대표 좌표 반경 1,000m 안의 입시/보습·수학·영어 학원·교습소 합계가 {n('total')}곳으로 집계 대상 중 1위입니다."
    elif key == "dong_academy":
        fact = f"학원 주소의 법정동 기준으로 개원 중인 입시/보습·수학·영어 학원·교습소가 {n('total')}곳으로 집계 대상 중 1위입니다."
    elif key == "value_combo":
        fact = f"300세대 이상·최근 6개월 전용 80~90㎡ 매매 평균 10억 원 미만·최근접 역 500m 이내 조건을 충족한 단지 중 반경 1,000m 전체 학원 수가 {n('academy_1km')}곳으로 1위입니다. 최근 6개월 매매 평균은 {n('price84')}만원({n('price84_n')}건), 최근접 역은 {row['station']} {n('station_m')}m입니다."
    elif key == "subway":
        fact = f"단지 대표 좌표 반경 500m 안의 역 {n('stations')}곳에 서로 다른 노선 {n('lines')}개({', '.join(row['line_names'])})가 지나 집계 대상 중 1위입니다."
    elif key == "starbucks":
        fact = f"단지 대표 좌표 반경 500m 안의 kakao map에 등록된 스타벅스가 {n('count')}곳으로 집계 대상 중 1위입니다."
    elif key == "convenience":
        fact = f"단지 대표 좌표 반경 500m 안의 GS25·CU·세븐일레븐·이마트24 합계가 {n('total')}곳으로 집계 대상 중 1위입니다."
    elif key in ("price_up", "price_down"):
        word = "올라" if key == "price_up" else "내려"
        fact = (f"전용 {row['area']}㎡ 매매 실거래 중앙값이 직전 6개월 {_eok(row['prev_median'])}원({n('prev_n')}건)에서 "
                f"최근 6개월 {_eok(row['recent_median'])}원({n('recent_n')}건)으로 {abs(row['change_pct']):.1f}% {word} 비교 대상 중 변화가 가장 큽니다.")
    elif key == "quiet":
        fact = f"1,000세대 이상·반경 500m 유흥주점 0곳 조건을 충족한 단지 중 가장 가까운 유흥주점까지 {n('nearest_nightlife_m')}m로 가장 멉니다."
    else:
        fact = f"단지 대표 좌표 반경 1,000m 안의 응급실 운영 의료기관이 {n('er_1km')}곳으로 집계 대상 중 1위입니다. 동률은 가장 가까운 종합병원급까지의 거리로 정합니다."
    return f"{month} 데이터 기준, {place}의 경우 {fact}"


def _source_summary(key, sources):
    return " / ".join(
        sources[k]["name"] for k in TOPIC_SOURCES[key]
    )


def build_view(data, options, apartment_path, area_path):
    """Presentation only; offline order, filter and values remain untouched."""
    if data is None:
        return {"data_month": "준비 중", "generated_at": "", "topics": [], "groups": [],
                "complex_count": None, "district_count": 0, "changes": {
            "new_complexes": [], "er_changes": [], "er_groups": [], "master_compared": False,
            "er_compared": False, "rules": [], "url": "",
        }}
    topics = []
    for key, slug, tag, title, basis in TOPICS:
        if key in ("starbucks", "convenience") and not options["kakao_enabled"]:
            continue
        is_dong = key in ("dong_academy", "gu_best_dong")
        rows = []
        for row in data[key]:
            value, detail = _values(key, row)
            rows.append({
                "name": row["dong"] if is_dong else row["name"],
                "location": row["gu"] if is_dong else f"{row['gu']} {row['dong']}",
                "url": area_path(row["gu"], row["dong"]) if is_dong else apartment_path(row["name"], row["gu"], row["dong"]),
                "location_url": area_path(row["gu"]) if is_dong else "",
                "value": value, "detail": detail,
            })
        topics.append({"key": key, "slug": slug, "tag": tag, "title": title, "basis": basis,
                       "rules": data["definitions"][key], "rows": rows, "is_dong": is_dong,
                       "question": QUESTIONS[key], "answer": _answer(key, data[key], data["data_month"]),
                       "source_summary": _source_summary(key, data["sources"]),
                       "group": next((g for g, _, _, keys in GROUPS if key in keys), "education"),
                       "url": f"/rankings/{slug}" if options["pages_enabled"] else ""})
    changes = {"master_compared": False, "er_compared": False, **data["changes_meta"],
               "new_complexes": [], "er_changes": [],
               "rules": data["definitions"].get("changes", data["definitions"].get("this_month", [])),
               "url": "/rankings/monthly-changes" if options["pages_enabled"] else ""}
    for key in ("new_complexes", "er_changes"):
        for row in data[key]:
            dong = row.get("dong", "")
            url = apartment_path(row["name"], row["gu"], dong) if dong else area_path(row["gu"])
            changes[key].append({
                "name": row["name"], "location": f"{row['gu']} {dong}".strip(), "url": url,
                "value": f"{_number(row['households'])}세대" if key == "new_complexes" else f"{_number(row['distance'])}m",
                "detail": f"준공 {row.get('built') or '기록 없음'}" if key == "new_complexes" else "직선거리",
                "hospital": row.get("hospital", ""),
            })
    # 새 응급실별로 묶고, 각 병원 안에서는 가까운 단지 순(er_changes 가 이미 거리순).
    places = {h["name"]: h for h in data.get("er_hospitals", [])}
    order = [h["name"] for h in data.get("er_hospitals", [])]
    order += [r["hospital"] for r in changes["er_changes"] if r["hospital"] not in order]
    changes["er_groups"] = []
    for name in dict.fromkeys(order):
        members = [r for r in changes["er_changes"] if r["hospital"] == name]
        if not members:
            continue
        place = places.get(name, {})
        changes["er_groups"].append({
            "hospital": name, "rows": members,
            "location": f"{place.get('gu', '')} {place.get('dong', '')}".strip(),
            "url": area_path(place["gu"], place["dong"]) if place.get("gu") and place.get("dong")
                   else area_path(place["gu"]) if place.get("gu") else "",
        })
    # 순위 페이지 행과 JSON-LD 가 화면과 같은 순서가 되게 병원별 순서로 다시 편다.
    changes["er_changes"] = [r for g in changes["er_groups"] for r in g["rows"]]
    groups = [{"key": key, "title": title, "description": description,
               "topics": [t for t in topics if t["key"] in keys]}
              for key, title, description, keys in GROUPS]
    return {"data_month": data["data_month"], "generated_at": data["generated_at"], "topics": topics,
            "groups": [group for group in groups if group["topics"]], "complex_count": data.get("complex_count"),
            "district_count": len(data["gu_best_dong"]), "changes": changes}


def ranking_topics(view):
    topics = list(view["topics"])
    changes = view["changes"]
    if changes["url"]:
        topics.append({"key": "changes", "slug": "monthly-changes", "tag": "This month",
                       "title": "이번 달 바뀐 것", "basis": "직전 달 대비 신규 등록 단지·새롭게 추가된 응급실과 가까운 단지",
                       "rules": changes["rules"], "rows": changes["new_complexes"] + changes["er_changes"],
                       "url": changes["url"], "is_dong": False,
                       "answer": f"{view['data_month']} 데이터를 직전 달과 비교한 기록입니다. 비교 자료가 없는 항목은 미비교로 표시합니다.",
                       "source_summary": next((text for label, text in changes["rules"] if label == "출처"), "")})
    return topics

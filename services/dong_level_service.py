"""동별 정보(배정초·지하철 거리·학교군) — 오프라인 산출물 data/derived/vworld/dong_level.json.

단지 등급은 대표 좌표 기준을 유지하고(비교 공정성), 대단지에서 동마다 갈리는
배정초·역 거리를 보조 정보로 보여 준다. 파일이 없으면 조용히 빈 값(옛 안내 문구 유지).
"""

import json
import os
import re
from functools import lru_cache

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "derived", "vworld", "dong_level.json")


@lru_cache(maxsize=1)
def _data():
    try:
        with open(PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _key(*parts):
    return "|".join(re.sub(r"\s+", " ", str(p or "")).strip() for p in parts)


def _dong_ranges(labels):
    """['101','102','103','105','A'] -> '101~103·105·A동'"""
    nums = sorted({int(x) for x in labels if x.isdigit()})
    other = sorted(x for x in labels if not x.isdigit())
    parts, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            parts.append(f"{start}~{prev}" if prev > start else f"{start}")
            start = prev = n
    if start is not None:
        parts.append(f"{start}~{prev}" if prev > start else f"{start}")
    return "·".join(parts + other) + "동" if parts or other else ""


def card_notes(dl):
    """상세 카드(지하철·교육환경·한강)에 붙일 '동별로 보면' 줄. {summary key: [(본문, 작은 글씨)]}"""
    if not dl:
        return {}
    notes = {}
    stations = " · ".join(f"{s['name']}역 {s['count']}개 동" for s in dl["stations"][:3])
    notes["subway"] = [
        (f"500m 안에 역이 있는 동 {dl['within_500']}개 / {dl['n']}개", ""),
        (f"가장 가까운 역까지 동마다 {dl['station_min']:,}m ~ {dl['station_max']:,}m", stations),
    ]
    school = []
    if dl["schools"]:
        if dl["split_school"]:
            school += [(f"{s['name']} {s['count']}개 동", s["dongs"]) for s in dl["schools"]]
        else:
            school.append((f"전 동 {dl['schools'][0]['name']}", ""))
    for d in dl["straddle"]:
        school.append((f"{d['dong']}동은 통학구역 경계에 걸쳐 있습니다", " · ".join(d["schools"])))
    groups = []
    if dl["middle"]:
        groups.append("중학교 " + "·".join(dl["middle"]))
    if dl["high"]:
        groups.append("고등학교 " + "·".join(dl["high"]))
    if groups:
        school.append((" / ".join(groups), ""))
    if school:
        notes["school-environment"] = school
    if dl.get("hangang_min") is not None and dl["hangang_min"] <= 3000:
        gates = " · ".join(f"{g['name']} {g['count']}개 동" for g in dl["hangang_gates"][:2])
        notes["hangang"] = [(f"한강 나들목까지 동마다 {dl['hangang_min']:,}m ~ {dl['hangang_max']:,}m", gates)]
    return notes


def get(name, gu, dong):
    entry = _data().get(_key(name, gu, dong))
    if not entry:
        return None
    summary, dongs = entry["summary"], entry["dongs"]
    # 작은 단지는 동마다 값이 거의 같아 카드가 길이만 늘린다. 동이 4개 이상이거나
    # 실제로 갈리는(배정초 2곳 이상·역 거리 100m 이상 차이) 단지만 보인다.
    if summary["n"] < 4 and len(summary["schools"]) < 2 and summary["station_max"] - summary["station_min"] < 100:
        return None
    schools = []
    for school, count in summary["schools"].items():
        labels = [d["dong"] for d in dongs if d["school"] == school]
        schools.append({"name": school, "count": count, "dongs": _dong_ranges(labels)})
    stations = [{"name": s, "count": c} for s, c in summary["nearest_stations"].items()]
    straddle = [d for d in dongs if d.get("straddle")]
    return {
        "n": summary["n"],
        "schools": schools,
        "split_school": len(schools) > 1,
        "straddle": [{"dong": d["dong"], "schools": [d["school"]] + d["straddle"]} for d in straddle],
        "station_min": summary["station_min"],
        "station_max": summary["station_max"],
        "within_500": summary["within_500"],
        "stations": stations,
        "hangang_min": summary.get("hangang_min"),
        "hangang_max": summary.get("hangang_max"),
        "hangang_gates": [{"name": g, "count": c} for g, c in (summary.get("hangang_gates") or {}).items()],
        "middle": summary.get("middle", []),
        "high": summary.get("high", []),
    }

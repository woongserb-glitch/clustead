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


def get(name, gu, dong):
    entry = _data().get(_key(name, gu, dong))
    if not entry:
        return None
    summary, dongs = entry["summary"], entry["dongs"]
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

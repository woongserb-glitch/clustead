"""Reproduce the home 'billboard' rankings (Claude prototype, 2026-10-01).

Read-only over the service repo's data/. Writes one JSON next to this file (or --output).
Every ranking is computed from the same baseline CSVs the site serves, so numbers match
the apartment pages. Definitions are printed into the JSON under "definitions" so the page
and this script cannot drift apart.

  python compute_home_preview.py \
      --prev-master <seoul_apartments.csv before this month's refresh> \
      --prev-school <school_zone_baseline.csv before this month's refresh>

Without --prev-* the "this month" section is left empty.
"""
import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("C:/Users/hyr19/OneDrive/Desktop/apartment-life-score")
csv.field_size_limit(2**31 - 1)


def f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def baseline(name):
    path = REPO / "data" / "baseline" / f"{name}.csv"
    return {(r["name"], r["gu"], r["dong"]): r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def master_rows(path):
    return list(csv.DictReader(open(path, encoding="cp949")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path(__file__).with_name("home_preview.json"))
    ap.add_argument("--prev-master", type=Path)
    ap.add_argument("--prev-school", type=Path)
    a = ap.parse_args()

    ac, sub, cafe, conv = baseline("academy_baseline"), baseline("subway_baseline"), baseline("cafe_baseline"), baseline("convenience_baseline")
    nl, med, tx = baseline("nightlife_baseline"), baseline("medical_baseline"), baseline("transaction_summary")
    master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r for r in master_rows(REPO / "data/apartment/seoul_apartments.csv")}
    hh = lambda k: int(f(master.get(k, {}).get("k-전체세대수"), 0) or 0)
    keys = [k for k in ac if k in sub]
    lab = lambda k: {"name": k[0], "gu": k[1], "dong": k[2], "households": hh(k)}
    trio = lambda k: f(ac[k]["exam_count"], 0) + f(ac[k]["math_count"], 0) + f(ac[k]["english_count"], 0)
    out = {}

    # 1. apartments with most exam/math/english academies within 1 km (subtype counts are 1 km in the builder)
    t = sorted(keys, key=lambda k: (-trio(k), -f(ac[k]["academy_count_500m"], 0)))
    out["academy"] = [{**lab(k), "total": int(trio(k)), "exam": int(f(ac[k]["exam_count"])), "math": int(f(ac[k]["math_count"])),
                       "english": int(f(ac[k]["english_count"]))} for k in t[:5]]

    # 2. neighbourhoods (legal dong of the academy's own address), same subtypes, open only
    spec = importlib.util.spec_from_file_location("ab", REPO / "scripts/build_academy_baseline.py")
    ab = importlib.util.module_from_spec(spec)
    sys.argv = [sys.argv[0]]
    spec.loader.exec_module(ab)  # module-level code only defines constants/functions
    cnt, no_dong = defaultdict(Counter), 0
    for r in csv.DictReader(open(REPO / "data/academy/academy_geocoded.csv", encoding="utf-8-sig")):
        if (r.get("등록상태명") or "").strip() != "개원":
            continue
        subtype = ab.classify_academy(r)
        if subtype not in ("입시/보습", "수학", "영어"):
            continue
        m = re.search(r"\(([^,()]*?[0-9]*(?:동|가))[,)]", r.get("도로명상세주소") or "")
        gu = (r.get("행정구역명") or "").strip()
        if not m or not gu:
            no_dong += 1
            continue
        cnt[(gu, m.group(1).strip())][subtype] += 1
    rows = sorted(((g, d, sum(c.values()), c) for (g, d), c in cnt.items()), key=lambda x: -x[2])
    out["dong_academy"] = [{"gu": g, "dong": d, "total": n, "exam": c["입시/보습"], "math": c["수학"], "english": c["영어"]} for g, d, n, c in rows[:5]]
    best = {}
    for g, d, n, _ in rows:
        best.setdefault(g, {"gu": g, "dong": d, "total": n})
    out["gu_best_dong"] = [best[g] for g in sorted(best)]
    out["dong_academy_meta"] = {"counted": sum(sum(c.values()) for c in cnt.values()), "no_dong": no_dong}

    # 3. 84m2 average < 1.0bn KRW + >=300 households + nearest station <= 500 m, by academies within 1 km
    pool = [k for k in keys if k in tx and f(tx[k]["avg_trade_amount_84"]) and f(tx[k]["avg_trade_amount_84"]) < 100000
            and hh(k) >= 300 and f(sub[k]["nearest_subway_distance"], 9e9) <= 500]
    t = sorted(pool, key=lambda k: (-f(ac[k]["academy_count_1000m"], 0), f(sub[k]["nearest_subway_distance"])))
    out["value_combo"] = [{**lab(k), "price84": int(f(tx[k]["avg_trade_amount_84"])), "station": sub[k]["nearest_subway_name"],
                           "station_m": int(f(sub[k]["nearest_subway_distance"])), "academy_1km": int(f(ac[k]["academy_count_1000m"]))} for k in t[:5]]
    out["value_combo_pool"] = len(pool)

    # 4. distinct subway lines within 500 m
    t = sorted(keys, key=lambda k: (-f(sub[k]["subway_line_count_500m"], 0), -f(sub[k]["subway_station_count_500m"], 0), f(sub[k]["nearest_subway_distance"], 9e9)))
    out["subway"] = [{**lab(k), "lines": int(f(sub[k]["subway_line_count_500m"])), "stations": int(f(sub[k]["subway_station_count_500m"])),
                      "nearest": sub[k]["nearest_subway_name"], "nearest_m": int(f(sub[k]["nearest_subway_distance"]))} for k in t[:5]]

    # 5. Starbucks within 500 m / 6. four convenience brands within 500 m (Kakao)
    t = sorted([k for k in keys if k in cafe], key=lambda k: (-f(cafe[k]["스타벅스_count_500m"], 0), f(cafe[k]["nearest_스타벅스_distance"], 9e9)))
    out["starbucks"] = [{**lab(k), "count": int(f(cafe[k]["스타벅스_count_500m"])), "nearest_m": int(f(cafe[k]["nearest_스타벅스_distance"], 0))} for k in t[:5]]
    brands = ["GS25", "CU", "세븐일레븐", "이마트24"]
    total = lambda k: sum(f(conv[k][b + "_count_500m"], 0) for b in brands)
    t = sorted([k for k in keys if k in conv], key=lambda k: -total(k))
    out["convenience"] = [{**lab(k), "total": int(total(k)), **{b: int(f(conv[k][b + "_count_500m"], 0)) for b in brands}} for k in t[:5]]

    # 7. >=1,000 households, no nightlife venue within 500 m, by distance to nearest venue (any radius)
    pool = [k for k in keys if hh(k) >= 1000 and f(nl[k]["nightlife_count_500m"], 1) == 0 and f(nl[k]["nightlife_nearest_any_distance"])]
    t = sorted(pool, key=lambda k: -f(nl[k]["nightlife_nearest_any_distance"]))
    out["quiet"] = [{**lab(k), "nearest_nightlife_m": int(f(nl[k]["nightlife_nearest_any_distance"]))} for k in t[:5]]
    out["quiet_pool"] = len(pool)

    # 8. ER-operating facilities within 1 km; tie -> nearest general/tertiary hospital
    t = sorted(keys, key=lambda k: (-f(med[k]["emergency_count_1km"], 0), f(med[k]["nearest_superior_hospital_distance"], 9e9)))
    out["emergency"] = [{**lab(k), "er_1km": int(f(med[k]["emergency_count_1km"], 0)), "hospital": med[k]["nearest_superior_hospital_name"],
                         "hospital_m": int(f(med[k]["nearest_superior_hospital_distance"], 0))} for k in t[:5]]

    # 9. this month
    out["new_complexes"], out["school_changes"] = [], []
    if a.prev_master:
        prev = {r["k-아파트코드"] for r in master_rows(a.prev_master)}
        out["new_complexes"] = [{"name": r["k-아파트명"], "gu": r["주소(시군구)"], "dong": r["주소(읍면동)"],
                                 "households": int(f(r["k-전체세대수"], 0) or 0), "built": (r.get("k-사용검사일-사용승인일") or "")[:7].replace("-", ".")}
                                for r in master_rows(REPO / "data/apartment/seoul_apartments.csv") if r["k-아파트코드"] not in prev]
    if a.prev_school:
        old = {(r["name"], r["gu"], r["dong"]): r for r in csv.DictReader(open(a.prev_school, encoding="utf-8-sig"))}
        new = baseline("school_zone_baseline")
        clean = lambda s: re.sub(r"\(적용시기.*$", "", s or "").strip()
        out["school_changes"] = [{"name": k[0], "gu": k[1], "from": clean(old[k]["assigned_elementary_school"]),
                                  "to": clean(new[k]["assigned_elementary_school"])}
                                 for k in old.keys() & new.keys() if old[k]["assigned_elementary_school"] != new[k]["assigned_elementary_school"]]
    a.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()

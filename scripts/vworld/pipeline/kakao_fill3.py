"""v5 보완(2026-10-13): 위치는 있는데 동 번호가 빈 건물에 카카오 '아파트 동' 장소로 번호를 붙인다.

kakao_fill.py 는 카카오 표기("은마아파트 N동")를 101동·1동·201동으로만 찾아서, 그 번호가 카카오에 없는
단지(은마는 1동 장소가 없다)는 통째로 건너뛰었다 → 191개 단지 537개 동이 번호 없이 남았다.
여기서는 이미 붙은 번호로 표기를 먼저 찾고, 빠진 번호만 조회해 '번호 없는 건물'에만 붙인다
(윤곽 안이거나 20m 안, 한 건물엔 한 번호, 이미 붙은 번호·건물은 건드리지 않음).

입력·출력: data/derived/vworld/complex_buildings_v5.jsonl (덮어쓰기 전 .bak_kakao3 백업),
보고서 kakao_fill3_report.json. 그다음 build_dong_level.py 를 다시 돌린다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R  # noqa: E402
import csv, json, re, shutil, time  # noqa: E401,E402
import requests  # noqa: E402
from shapely.geometry import Point, shape  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
V = f"{R}/data/derived/vworld"
PATH = f"{V}/complex_buildings_v5.jsonl"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
U = "https://dapi.kakao.com/v2/local/search/keyword.json"
master = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r
          for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
DONG_RE = re.compile(r"^(.*?)\s*(\d{1,4})동$")
CALLS = {"n": 0}


def kget(q):
    for _ in range(4):
        try:
            r = requests.get(U, headers=H, params={"query": q, "size": 15}, timeout=10)
            CALLS["n"] += 1
            if r.status_code == 200:
                time.sleep(0.03)
                return r.json()["documents"]
            if r.status_code == 429:
                time.sleep(5); continue
            raise RuntimeError(f"HTTP {r.status_code}")
        except requests.RequestException:
            time.sleep(2)
    return []


def road_of(m):
    a = (m.get("kapt도로명주소") or "").strip()
    return a.replace("서울특별시 ", "서울 ") if a else ""


def gu_of(m):
    return (m.get("주소(시군구)") or "").strip()


def same_place(x, road, gu):
    # 동마다 도로명이 다른 단지도 있다 → 도로명이 같거나, 같은 구의 '아파트 동' 이면서 단지 근처(호출부에서 거리 확인)
    return "아파트 동" in x["category_name"] and (x["road_address_name"] == road or f" {gu} " in f" {x['address_name']} ")


def find_prefix(name, road, gu, known, center):
    tries = [f"{name} {n}동" for n in sorted(known)[:3]] + [f"{name}아파트 {n}동" for n in sorted(known)[:3]]
    tries += [f"{name} {n}동" for n in (101, 1, 201, 2, 102, 301)] + [f"{name}아파트 {n}동" for n in (101, 1, 201)]
    for q in tries:
        for x in kget(q):
            m = DONG_RE.match(x["place_name"])
            if m and same_place(x, road, gu) and center.distance(Point(float(x["x"]), float(x["y"]))) * 100000 < 800:
                return m.group(1).strip()
    return None


def candidate_blocks(known):
    """조회할 번호 구간들. 번호가 하나도 없으면 1·101·201… 구간마다 앞에서부터 찾다가 연속 4번 못 찾으면 그 구간을 멈춘다."""
    if not known:
        return [(list(range(s, s + 40)), True) for s in (1, 101, 201, 301, 401, 501, 601, 701, 801, 901, 1001)]
    blocks = []
    if any(n < 100 for n in known):
        blocks.append(([n for n in range(1, max(n for n in known if n < 100) + 8) if n not in known], False))
    for h in sorted({n // 100 for n in known if n >= 100}):
        top = max(n for n in known if n // 100 == h)
        blocks.append(([n for n in range(h * 100 + 1, top + 8) if n not in known], False))
    return blocks


rows = [json.loads(l) for l in open(PATH, encoding="utf-8")]
targets = [i for i, r in enumerate(rows) if len(r.get("buildings", [])) >= 2 and any(not b.get("label") for b in r["buildings"])]
print(f"대상 단지 {len(targets)} · 번호 없는 동 {sum(sum(1 for b in rows[i]['buildings'] if not b.get('label')) for i in targets)}", flush=True)
report = []
for n, i in enumerate(targets, 1):
    r = rows[i]; k = tuple(r["key"]); m = master.get(k, {})
    road, gu = road_of(m), gu_of(m)
    shapes = [shape(b["geom"]) for b in r["buildings"]]
    center = shapes[0].centroid
    known = {int(b["label"]) for b in r["buildings"] if str(b.get("label", "")).isdigit()}
    prefix = find_prefix(k[0], road, gu, known, center) if road else None
    added = []
    if prefix:
        free = [j for j, b in enumerate(r["buildings"]) if not b.get("label")]
        for nums, stop_early in candidate_blocks(known):
            misses, seen = 0, False
            for no in nums:
                if not free:
                    break
                hit = None
                for x in kget(f"{prefix} {no}동"):
                    if x["place_name"] == f"{prefix} {no}동" and same_place(x, road, gu):
                        hit = Point(float(x["x"]), float(x["y"])); break
                if not hit:
                    misses += 1
                    if stop_early and misses >= 4:
                        break
                    continue
                seen, misses = True, 0
                cand = sorted((shapes[j].distance(hit) * 100000, j) for j in free)
                if cand and cand[0][0] <= 20:
                    d, j = cand[0]
                    r["buildings"][j]["label"] = str(no); r["buildings"][j]["src"] = "spbd+kakao3"
                    free.remove(j); added.append((no, round(d, 1)))
        if added:
            r["labeled"] = sum(1 for b in r["buildings"] if b.get("label"))
    report.append({"key": k, "prefix": prefix, "added": added,
                   "left": sum(1 for b in r["buildings"] if not b.get("label"))})
    if n % 20 == 0:
        print(n, k[0], prefix, len(added), "calls", CALLS["n"], flush=True)

shutil.copyfile(PATH, PATH + ".bak_kakao3")
with open(PATH, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
json.dump(report, open(f"{V}/kakao_fill3_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE 붙인 동", sum(len(x["added"]) for x in report), "남은 동", sum(x["left"] for x in report),
      "표기 못 찾은 단지", sum(1 for x in report if not x["prefix"]), "calls", CALLS["n"], flush=True)

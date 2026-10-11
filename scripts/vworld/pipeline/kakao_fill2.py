"""카카오 2차: 주소 일치 대신 '단지 중심 600m 안 + 이름 유사' 로 카카오 아파트 동을 찾는다.
1차에서 카카오 0건이던 채우기·검증 단지만 다시 한다. 결과는 v3 에 반영(v4 로 저장) + 리포트 갱신."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import collections, csv, json, math, os, re, sys, time
from difflib import SequenceMatcher
import requests
from dotenv import dotenv_values
from shapely.geometry import shape, Point
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from building_match_report import residential, NON_RES


def area(b):
    return shape(b["geom"]).area * 111000 * 88400


def attach(buildings, points):
    """카카오 동 좌표를 건물 윤곽에 붙인다. 윤곽 안이면 그 건물, 아니면 20m 안 가장 가까운 건물."""
    shapes = [(b, shape(b["geom"])) for b in buildings]
    used, matched = set(), {}
    for no, (lat, lng) in points.items():
        p = Point(lng, lat)
        cand = [(g.distance(p) * 100000, i) for i, (b, g) in enumerate(shapes) if i not in used]
        if not cand:
            continue
        d, i = min(cand)
        if d <= 20:
            used.add(i); matched[no] = (i, round(d, 1))
    return matched

sys.stdout.reconfigure(encoding="utf-8")
ROOT = R; V = f"{ROOT}/data/derived/vworld"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
U = "https://dapi.kakao.com/v2/local/search/keyword.json"
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{ROOT}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
DONG_RE = re.compile(r"^(.*?)\s*(\d{1,4}|[A-Z]|[가-하])동$")
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s|제\d+|\d+단지", "", s or "")
norm_keep = lambda s: re.sub(r"\(.*?\)|아파트|\s", "", s or "")
LETTERS = [chr(c) for c in range(ord("A"), ord("L"))] + list("가나다라마바사아자차카타파하")


def kget(q, lat, lng, page=1, radius=700):
    for _ in range(4):
        try:
            r = requests.get(U, headers=H, params={"query": q, "x": lng, "y": lat, "radius": radius, "sort": "distance", "size": 15, "page": page}, timeout=10)
            if r.status_code == 200:
                return r.json()
            time.sleep(3)
        except requests.RequestException:
            time.sleep(2)
    return {"documents": [], "meta": {"is_end": True}}


def near(x, lat, lng, m=600):
    return math.hypot((float(x["y"]) - lat) * 111000, (float(x["x"]) - lng) * 88400) <= m


def on_site(x, geoms):
    p = Point(float(x["x"]), float(x["y"]))
    return any(g.distance(p) * 100000 <= 20 for g in geoms)


def prefixes(name, lat, lng, geoms):
    """주변 '아파트 동' 장소 중 이 단지 건물 윤곽 위(20m 안)에 찍힌 것의 이름 앞부분을 모은다.
    이름이 마스터와 달라도(더샵서초 vs 서초더샵, 산장 vs 정릉산장) 위치로 잡는다."""
    found = collections.Counter()
    queries = [(f"{name} 동", 700), (f"{norm_keep(name)}아파트", 700), ("아파트 동", 300), ("101동", 300), ("1동", 300)]
    for q, rad in queries:
        for page in (1, 2, 3):
            d = kget(q, lat, lng, page, rad)
            for x in d["documents"]:
                m = DONG_RE.match(x["place_name"])
                if m and "아파트 동" in x["category_name"] and on_site(x, geoms):
                    found[m.group(1).strip()] += 1
            if d["meta"].get("is_end", True):
                break
            time.sleep(0.03)
    return [p for p, _ in found.most_common(3)]


def enumerate_near(prefix, lat, lng, geoms):
    pts = {}
    blocks = [list(range(1, 41))] + [list(range(s, s + 60)) for s in range(101, 1601, 100)] + [LETTERS]
    for block in blocks:
        misses = 0
        for no in block:
            hit = None
            for x in kget(f"{prefix} {no}동", lat, lng)["documents"]:
                if x["place_name"] == f"{prefix} {no}동" and on_site(x, geoms):
                    hit = (float(x["y"]), float(x["x"])); break
            time.sleep(0.03)
            if hit:
                pts[str(no)] = hit; misses = 0
            else:
                misses += 1
                if misses >= 4:
                    break
    return pts


rows = [json.loads(l) for l in open(f"{V}/complex_buildings_v3.jsonl", encoding="utf-8")]
rep = json.load(open(f"{V}/kakao_fill_report.json", encoding="utf-8"))
redo_fill = {x["name"] for x in rep["fill"] if x["kakao"] == 0}
redo_ver = {x["name"] for x in rep["verify"] if x["kakao"] == 0}
labeled = lambda b: residential(b) and re.search(r"\d+\s*동", (b["dong"] or "") + (b["name"] or ""))
new_fill, new_ver = [], []
for r in rows:
    name = r["key"][0]
    if name not in redo_fill and name not in redo_ver:
        continue
    lat, lng = coords[tuple(r["key"])]
    geoms = [shape(b["geom"]) for b in r["buildings"] if not NON_RES.search((b["dong"] or "") + (b["name"] or "")) and area(b) >= 150]
    pts, pre = {}, prefixes(name, lat, lng, geoms) if geoms else []
    for p in pre:
        for no, v in enumerate_near(p, lat, lng, geoms).items():
            pts.setdefault(no, v)
    if name in redo_fill:
        pool = [b for b in r["buildings"] if not NON_RES.search((b["dong"] or "") + (b["name"] or "")) and area(b) >= 150]
        matched = attach(pool, pts)
        for no, (i, d) in matched.items():
            b = pool[i]
            if not re.search(r"\d+\s*동", (b["dong"] or "") + (b["name"] or "")):
                b["dong"] = f"{no}동"; b["dong_source"] = "kakao"; b["residential"] = True
        r["method"] += f"+kakao2_{len(matched)}/{len(pts)}"
        new_fill.append({"name": name, "prefix": pre, "kakao": len(pts), "attached": len(matched)})
    else:
        lab = {re.search(r"(\d+)\s*동", (b["dong"] or "") + (b["name"] or "")).group(1).lstrip("0"): shape(b["geom"]) for b in r["buildings"] if labeled(b)}
        agree = sum(1 for no, (y, x) in pts.items() if no in lab and lab[no].distance(Point(x, y)) * 100000 <= 20)
        new_ver.append({"name": name, "vworld": len(lab), "kakao": len(pts), "both": len(set(lab) & set(pts)), "agree": agree})
    print(name, pre, len(pts), flush=True)

with open(f"{V}/complex_buildings_v4.jsonl", "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
rep["fill2"] = new_fill; rep["verify2"] = new_ver
json.dump(rep, open(f"{V}/kakao_fill_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE", flush=True)

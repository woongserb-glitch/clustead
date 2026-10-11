"""3차: 브이월드 건물에 동 번호가 없는 단지는 카카오 '아파트 동' 위치로 번호를 채우고,
동 번호가 있는 대단지 30곳은 카카오와 대조해 검증한다.

입력 complex_buildings_v2.jsonl → 출력 complex_buildings_v3.jsonl + kakao_fill_report.json
"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, math, os, random, re, sys, time
import requests
from dotenv import dotenv_values
from shapely.geometry import shape, Point
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from building_match_report import residential, NON_RES

sys.stdout.reconfigure(encoding="utf-8")
ROOT = R
V = f"{ROOT}/data/derived/vworld"
env = ENV
H = {"Authorization": "KakaoAK " + env["KAKAO_REST_API_KEY"]}
U = "https://dapi.kakao.com/v2/local/search/keyword.json"
master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r for r in csv.DictReader(open(f"{ROOT}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
DONG_RE = re.compile(r"^(.*?)\s*(\d{1,4})동$")


def kget(q):
    for attempt in range(4):
        try:
            r = requests.get(U, headers=H, params={"query": q, "size": 15}, timeout=10)
            if r.status_code == 200:
                return r.json()["documents"]
            if r.status_code == 429:
                time.sleep(5); continue
            raise RuntimeError(r.status_code)
        except requests.RequestException:
            time.sleep(2)
    return []


def road_of(m):
    a = (m.get("kapt도로명주소") or "").strip()
    return a.replace("서울특별시 ", "서울 ") if a else ""


def find_prefix(name, road):
    for q in (f"{name} 101동", f"{name}아파트 101동", f"{name} 1동", f"{name}아파트 1동", f"{name} 201동"):
        for x in kget(q):
            if "아파트 동" in x["category_name"] and x["road_address_name"] == road:
                m = DONG_RE.match(x["place_name"])
                if m:
                    return m.group(1).strip()
        time.sleep(0.03)
    return None


def enumerate_dongs(prefix, road):
    found = {}
    for start in (1, 101, 201, 301, 401, 501, 601, 701, 801, 901, 1001, 1101, 1201):
        misses, seen = 0, False
        for no in range(start, start + 60 if start > 1 else 41):
            hit = None
            for x in kget(f"{prefix} {no}동"):
                if x["place_name"] == f"{prefix} {no}동" and x["road_address_name"] == road:
                    hit = (float(x["y"]), float(x["x"])); break
            time.sleep(0.03)
            if hit:
                found[no] = hit; seen = True; misses = 0
            else:
                misses += 1
                if (not seen and misses >= 4) or (seen and misses >= 4):
                    break
    return found


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


rows = [json.loads(l) for l in open(f"{V}/complex_buildings_v2.jsonl", encoding="utf-8")]
want = lambda k: int(float(master.get(k, {}).get("k-전체동수") or 0) or 0)
area = lambda b: shape(b["geom"]).area * 111000 * 88400
labeled = lambda b: residential(b) and re.search(r"\d+\s*동", (b["dong"] or "") + (b["name"] or ""))
fill_targets, verify_pool = [], []
for idx, r in enumerate(rows):
    k = tuple(r["key"]); w = want(k)
    if r["method"] == "unmatched" or w < 2:
        continue
    lab = [b for b in r["buildings"] if labeled(b)]
    unl = [b for b in r["buildings"] if not (b["dong"] or "").strip() and not re.search(r"\d+\s*동", b["name"] or "")
           and not NON_RES.search(b["name"] or "") and area(b) >= 250]
    if len(lab) < 0.9 * w and unl:
        fill_targets.append(idx)
    elif abs(len(lab) - w) <= max(1, round(w * 0.1)) and int(float(master[k].get("k-전체세대수") or 0) or 0) >= 1000:
        verify_pool.append(idx)
random.seed(42)
verify = random.sample(verify_pool, min(30, len(verify_pool)))
report = {"fill": [], "verify": []}
print(f"채울 단지 {len(fill_targets)} · 검증 단지 {len(verify)}", flush=True)

for n, idx in enumerate(fill_targets + verify, 1):
    r = rows[idx]; k = tuple(r["key"]); m = master.get(k, {}); road = road_of(m)
    prefix = find_prefix(k[0], road) if road else None
    pts = enumerate_dongs(prefix, road) if prefix else {}
    is_fill = idx in fill_targets
    if is_fill:
        pool = [b for b in r["buildings"] if not NON_RES.search((b["dong"] or "") + (b["name"] or "")) and area(b) >= 150]
        matched = attach(pool, pts)
        for no, (i, d) in matched.items():
            b = pool[i]
            if not re.search(r"\d+\s*동", (b["dong"] or "") + (b["name"] or "")):
                b["dong"] = f"{no}동"; b["dong_source"] = "kakao"; b["residential"] = True
        r["method"] += f"+kakao{len(matched)}/{len(pts)}"
        report["fill"].append({"name": k[0], "want": want(k), "kakao": len(pts), "attached": len(matched), "prefix": prefix})
    else:
        lab = {int(re.search(r"(\d+)\s*동", (b["dong"] or "") + (b["name"] or "")).group(1)): shape(b["geom"])
               for b in r["buildings"] if labeled(b)}
        agree = sum(1 for no, (lat, lng) in pts.items() if no in lab and lab[no].distance(Point(lng, lat)) * 100000 <= 20)
        report["verify"].append({"name": k[0], "vworld": len(lab), "kakao": len(pts), "both": len(set(lab) & set(pts)), "agree": agree})
    if n % 10 == 0:
        print(n, k[0], "fill" if is_fill else "verify", len(pts), flush=True)

with open(f"{V}/complex_buildings_v3.jsonl", "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
json.dump(report, open(f"{V}/kakao_fill_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE", flush=True)

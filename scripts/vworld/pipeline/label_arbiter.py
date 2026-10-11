"""동번호 충돌(도로명주소 건물 vs 건축물대장) 건물을 카카오 '아파트 동' 위치로 판정해 v5 를 고친다.
카카오가 한쪽 번호를 그 건물 위(20m)에 찍으면 그 번호, 둘 다 없으면 도로명주소 번호 유지."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, sys, time, collections
import requests
from shapely.geometry import shape, Point
from dotenv import dotenv_values
sys.stdout.reconfigure(encoding="utf-8")
R = R; V = f"{R}/data/derived/vworld"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
co = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{R}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
CN = json.load(open(f"{V}/complex_common_names.json", encoding="utf-8")) if __import__("os").path.exists(f"{V}/complex_common_names.json") else {}
rows = [json.loads(l) for l in open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8")]
cache = {}


def where(name, lab, lat, lng):
    q = f"{name} {lab}동"
    if q in cache:
        return cache[q]
    p = None
    for _ in range(3):
        try:
            d = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json", headers=H, params={"query": q, "x": lng, "y": lat, "radius": 800, "sort": "distance", "size": 5}, timeout=10).json()
            break
        except requests.RequestException:
            time.sleep(2); d = {}
    for x in d.get("documents", []):
        if "아파트 동" in x["category_name"] and x["place_name"].replace(" ", "").endswith(f"{lab}동"):
            p = Point(float(x["x"]), float(x["y"])); break
    cache[q] = p; time.sleep(0.03)
    return p


res = collections.Counter()
for r in rows:
    k = tuple(r["key"]); lat, lng = co[k]
    names = [k[0]] + ([CN["|".join(k)]["kakao"]] if CN.get("|".join(k), {}).get("kakao") else [])
    for b in r["buildings"]:
        if "!bldg=" not in b["src"]:
            continue
        g = shape(b["geom"]).buffer(0); s_lab = b["label"]; b_lab = b["src"].split("!bldg=")[1]
        best = None
        for nm in names:
            ps, pb = where(nm, s_lab, lat, lng), where(nm, b_lab, lat, lng)
            ds = g.distance(ps) * 1e5 if ps else 1e9; db = g.distance(pb) * 1e5 if pb else 1e9
            if ds <= 20 and ds < db:
                best = "spbd"; break
            if db <= 20 and db < ds:
                best = "bldg"; break
        if best == "bldg":
            b["label"] = b_lab
        b["src"] = b["src"].split("!bldg=")[0] + f"+arb_{best or 'none'}"
        res[best or "none"] += 1
# 같은 동번호 + 붙어 있는(5m) 조각은 한 동(날개·저층부 분할 등록)으로 합친다.
from shapely.ops import unary_union
merged_n = 0
for r in rows:
    by = collections.defaultdict(list)
    for b in r["buildings"]:
        if b["label"]:
            by[b["label"]].append(b)
    for lab, bs in by.items():
        if len(bs) < 2:
            continue
        gs = [shape(b["geom"]).buffer(0) for b in bs]
        groups = []
        for b, g in zip(bs, gs):
            for grp in groups:
                if any(g.distance(h) * 1e5 <= 5 for _, h in grp):
                    grp.append((b, g)); break
            else:
                groups.append([(b, g)])
        if len(groups) < len(bs):
            keep = []
            for grp in groups:
                b0 = dict(grp[0][0]); b0["geom"] = unary_union([g for _, g in grp]).__geo_interface__
                if len(grp) > 1:
                    b0["src"] += f"+joined{len(grp)}"; merged_n += len(grp) - 1
                keep.append(b0)
            r["buildings"] = [b for b in r["buildings"] if b["label"] != lab] + keep
    w, n = r["want"], len(r["buildings"])
    r["n"] = n; r["labeled"] = sum(1 for x in r["buildings"] if x["label"])
    if n:
        r["status"] = "exact" if w and n == w else "near" if w and abs(n - w) <= max(1, round(w * 0.1)) else "diff"
print("붙은 조각 합침:", merged_n, "· 상태:", dict(collections.Counter(r["status"] for r in rows)))
with open(f"{V}/complex_buildings_v5.jsonl", "w", encoding="utf-8") as fh:
    for r in rows:
        r["conflicts"] = 0
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("동번호 충돌 판정:", dict(res))
# 같은 단지 안 동번호 중복 점검
dup = sum(1 for r in rows if len([b["label"] for b in r["buildings"] if b["label"]]) != len({b["label"] for b in r["buildings"] if b["label"]}))
print("동번호 중복 단지:", dup)

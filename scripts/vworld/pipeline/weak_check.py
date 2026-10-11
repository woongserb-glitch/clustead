"""근거 1개 이하 단지: 매칭된 건물 위치의 건축물대장(BLDGINFO) 이름·사용승인일을 마스터와 대조."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, re, sys, collections
from difflib import SequenceMatcher
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
sys.stdout.reconfigure(encoding="utf-8")
R = R; V = f"{R}/data/derived/vworld"
M = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
B = {"|".join(r["key"]): r for r in map(json.loads, open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8"))}
A = json.load(open(f"{V}/coord_audit.json", encoding="utf-8"))
C = json.load(open(f"{V}/complex_common_names.json", encoding="utf-8"))
L = json.load(open(f"{V}/complex_status_ledger.json", encoding="utf-8"))
F = json.load(open(f"{V}/bldginfo_apt.geojson", encoding="utf-8"))["features"]
G = [shape(f["geometry"]).buffer(0) for f in F]; P = [f["properties"] for f in F]; T = STRtree(G)
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s|제|단지|차|\d+동$", "", s or "")
weak = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
out = []
for k in weak:
    key = tuple(k.split("|")); m = M[key]; r = B[k]
    mdate = (m.get("k-사용검사일-사용승인일") or "")[:10].replace("-", "")
    if r["buildings"]:
        area = unary_union([shape(b["geom"]).buffer(0) for b in r["buildings"]]).buffer(0.0001)
    else:
        geo = A[k].get("geo") or A[k]["site"]; area = Point(geo[1], geo[0]).buffer(0.0008)
    hits = [P[int(i)] for i in T.query(area) if G[int(i)].intersects(area)]
    names = collections.Counter(re.sub(r"\s*\d+\s*동$", "", p.get("bld_nm") or "").strip() for p in hits)
    dates = collections.Counter(p.get("useapr_day") for p in hits)
    date_ok = mdate in dates
    best = max(names, key=lambda n: SequenceMatcher(None, norm(n), norm(key[0])).ratio(), default="")
    sim = round(SequenceMatcher(None, norm(best), norm(key[0])).ratio(), 2) if best else 0
    verdict = "확인됨(대장 이름+승인일)" if date_ok and sim >= 0.5 else "확인됨(대장 승인일)" if date_ok else "확인됨(대장 이름)" if sim >= 0.6 else "대장에 없음"
    out.append((verdict, key[0], key[1], mdate, best, sim, dict(dates.most_common(2)), L[k]["status"], len(r["buildings"])))
for x in sorted(out): print(x)
print(collections.Counter(x[0] for x in out))
json.dump([list(map(str, x)) for x in out], open(f"{V}/weak_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

"""단지별 현장 통용명: 단지 건물 윤곽 위에 찍힌 카카오 '아파트 동'/'아파트' 장소 이름 + 브이월드 건물명.
마스터명과 다르면 통용명 후보로 기록. 읽기 전용(결과 파일만 씀)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import collections, csv, json, re, sys, time
from difflib import SequenceMatcher
import requests
from dotenv import dotenv_values
from shapely.geometry import shape, Point
sys.stdout.reconfigure(encoding="utf-8")
ROOT = R; V = f"{ROOT}/data/derived/vworld"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
U = "https://dapi.kakao.com/v2/local/search/keyword.json"
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{ROOT}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
DONG_RE = re.compile(r"^(.*?)\s*(\d{1,4}|[A-Z]|[가-하])동$")
VW_RE = re.compile(r"^(.*?)\s*\d{1,4}\s*동$")
clean = lambda s: re.sub(r"\s+", "", re.sub(r"아파트$", "", (s or "").strip()))
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s|제|단지|차", "", s or "")


def kget(q, lat, lng, page):
    for _ in range(4):
        try:
            r = requests.get(U, headers=H, params={"query": q, "x": lng, "y": lat, "radius": 300, "sort": "distance", "size": 15, "page": page}, timeout=10)
            if r.status_code == 200:
                return r.json()
            time.sleep(3)
        except requests.RequestException:
            time.sleep(2)
    return {"documents": [], "meta": {"is_end": True}}


src = f"{V}/complex_buildings_v4.jsonl" if len(sys.argv) < 2 else sys.argv[1]
out = {}
rows = [json.loads(l) for l in open(src, encoding="utf-8")]
for n, r in enumerate(rows, 1):
    k = tuple(r["key"]); lat, lng = coords[k]
    geoms = [shape(b["geom"]) for b in r["buildings"]]
    on = lambda x: any(g.distance(Point(float(x["x"]), float(x["y"]))) * 100000 <= 20 for g in geoms)
    kc = collections.Counter()
    if geoms:
        for q in ("아파트 동", "아파트"):
            for page in (1, 2, 3):
                d = kget(q, lat, lng, page)
                for x in d["documents"]:
                    if not on(x):
                        continue
                    m = DONG_RE.match(x["place_name"])
                    if "아파트 동" in x["category_name"] and m:
                        kc[clean(m.group(1))] += 1
                    elif x["category_name"].endswith("아파트"):
                        kc[clean(x["place_name"])] += 2
                if d["meta"].get("is_end", True):
                    break
                time.sleep(0.02)
    vc = collections.Counter()
    for b in r["buildings"]:
        nm = (b.get("name") or "").strip()
        m = VW_RE.match(nm)
        nm = clean(m.group(1) if m else nm)
        if nm:
            vc[nm] += 1
    kname = kc.most_common(1)[0][0] if kc else ""
    vname = vc.most_common(1)[0][0] if vc else ""
    common = kname or vname
    sim = SequenceMatcher(None, norm(common), norm(k[0])).ratio() if common else 1.0
    out["|".join(k)] = {"kakao": kname, "kakao_all": dict(kc.most_common(3)), "vworld": vname, "common": common, "sim": round(sim, 2)}
    if n % 200 == 0:
        print(n, flush=True)
json.dump(out, open(f"{V}/complex_common_names.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE", sum(1 for v in out.values() if v["common"] and v["sim"] < 0.6), flush=True)

"""건축물정보(대장)로만 고른 단지의 건물이 지금도 현장에 있는지: 도로명주소 건물(LT_C_SPBD, 현행)과 겹치는 비율.
철거됐지만 대장이 말소 안 된 '유령 건물'을 거른다. → exist_cache.json {key: {frac, n}}"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import json, sys, os, time
from shapely.geometry import shape
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vworld_api as C
sys.stdout.reconfigure(encoding="utf-8")
V = V
cache_p = f"{V}/exist_cache.json"
cache = json.load(open(cache_p, encoding="utf-8")) if os.path.exists(cache_p) else {}
rows = [json.loads(l) for l in open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8")]
todo = [r for r in rows if r["bldg_how"].startswith("bldg_") and "|".join(r["key"]) not in cache]
print("대상", len(todo), flush=True)
for n, r in enumerate(todo, 1):
    gs = [shape(b["geom"]).buffer(0) for b in r["buildings"]]
    minx = min(g.bounds[0] for g in gs); miny = min(g.bounds[1] for g in gs); maxx = max(g.bounds[2] for g in gs); maxy = max(g.bounds[3] for g in gs)
    sp, page = [], 1
    while True:
        resp = C.api({"data": "LT_C_SPBD", "geomFilter": f"BOX({minx-0.0002},{miny-0.0002},{maxx+0.0002},{maxy+0.0002})", "page": page})
        if resp["status"] == "NOT_FOUND":
            break
        sp += [shape(f["geometry"]).buffer(0) for f in resp["result"]["featureCollection"]["features"]]
        if page >= int(resp["page"]["total"]):
            break
        page += 1
    hit = sum(1 for g in gs if any(g.intersection(s).area > 0.3 * g.area for s in sp if s.intersects(g)))
    cache["|".join(r["key"])] = {"frac": round(hit / len(gs), 2), "n": len(gs)}
    if n % 25 == 0:
        json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False); print(n, flush=True)
    time.sleep(0.03)
json.dump(cache, open(cache_p, "w", encoding="utf-8"), ensure_ascii=False)
print("DONE", sum(1 for v in cache.values() if v["frac"] < 0.5), "유령/철거 추정", flush=True)

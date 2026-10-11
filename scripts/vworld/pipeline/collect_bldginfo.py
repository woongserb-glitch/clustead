"""서울 전역 건축물정보(LT_C_BLDGINFO) 중 공동주택(usability 02000)만 수집 → bldginfo_apt.geojson."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import sys, os, json, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vworld_api as C
feats, seen = [], set()
lng = C.LNG0; n = 0
while lng < C.LNG1:
    lat = C.LAT0
    while lat < C.LAT1:
        box = f"BOX({lng},{lat},{min(lng+C.DLNG, C.LNG1)},{min(lat+C.DLAT, C.LAT1)})"
        page = 1
        while True:
            resp = C.api({"data": "LT_C_BLDGINFO", "geomFilter": box, "attrFilter": "usability:=:02000", "page": page})
            if resp["status"] == "NOT_FOUND":
                break
            for f in resp["result"]["featureCollection"]["features"]:
                h = hashlib.md5(json.dumps([f["properties"], f["geometry"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if h not in seen:
                    seen.add(h); feats.append(f)
            if page >= int(resp["page"]["total"]):
                break
            page += 1
        lat += C.DLAT; n += 1
        if n % 20 == 0:
            print(n, len(feats), flush=True)
    lng += C.DLNG
json.dump({"type": "FeatureCollection", "features": feats}, open(C.OUT / "bldginfo_apt.geojson", "w", encoding="utf-8"), ensure_ascii=False)
print("DONE", len(feats), flush=True)

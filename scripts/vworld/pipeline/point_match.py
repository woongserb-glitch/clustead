"""좌표 지점 매칭: 미매칭(none) 단지와 2동 이하 단지 중 차이 큰 곳.
카카오 장소(단지명, 아파트 분류) 좌표 + K-apt 원본 좌표(좌표X/Y) + 현재 대표좌표 → 그 점을 품은 도로명주소 건물(15m 이내)
+ 같은 건물명을 가진 150m 안 건물. → point_cache.json"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, os, re, sys, time
from difflib import SequenceMatcher
import requests
from dotenv import dotenv_values
from shapely.geometry import shape, Point
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vworld_api as C
sys.stdout.reconfigure(encoding="utf-8")
R = R; V = f"{R}/data/derived/vworld"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
M = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{R}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s|임대|분양", "", s or "")
rows = [json.loads(l) for l in open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8")]
CA = json.load(open(f"{V}/coord_audit.json", encoding="utf-8")) if os.path.exists(f"{V}/coord_audit.json") else {}
targets = [r for r in rows if r["status"] == "none" or (r["status"] == "diff" and r["want"] <= 2 and r["n"] == 0)]
REDO = len(sys.argv) > 1 and sys.argv[1] == "--redo"
out = json.load(open(f"{V}/point_cache.json", encoding="utf-8")) if os.path.exists(f"{V}/point_cache.json") else {}
targets = [r for r in targets if REDO or "|".join(r["key"]) not in out]
print("대상", len(targets), flush=True)
for r in targets:
    k = tuple(r["key"]); lat, lng = coords[k]; m = M[k]
    pts = [("center", lat, lng)]
    try:
        pts.append(("kapt", float(m["좌표Y"]), float(m["좌표X"])))
    except (ValueError, KeyError):
        pass
    geo = CA.get("|".join(k), {}).get("geo")
    if geo:
        pts.append(("geo", geo[0], geo[1]))
    d = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json", headers=H, params={"query": k[0], "x": lng, "y": lat, "radius": 3000, "sort": "accuracy", "size": 10}, timeout=10).json()
    conf_pts = []
    for x in d.get("documents", []):
        pn = re.sub(r"(관리사무소|경로당|정문|후문|상가|오피스텔|\(.*?\))", "", x["place_name"])
        if SequenceMatcher(None, norm(pn), norm(k[0])).ratio() < 0.7:
            continue
        # 마스터 주소와 같은 곳에 찍힌 단지명 장소 = 이 단지 위치 확인
        same_addr = m.get("kapt도로명주소") and x["road_address_name"] and m["kapt도로명주소"].replace("서울특별시 ", "서울 ").strip() == x["road_address_name"].strip()
        if same_addr or "아파트" in x["category_name"] or "주택" in x["category_name"]:
            conf_pts.append(("kakaoconf:" + x["place_name"], float(x["y"]), float(x["x"])))
    pts += conf_pts[:2]
    found = []
    for src, y, x in pts:
        resp = C.api({"data": "LT_C_SPBD", "geomFilter": f"BOX({x-0.0018},{y-0.0014},{x+0.0018},{y+0.0014})"})
        feats = resp["result"]["featureCollection"]["features"] if resp["status"] == "OK" else []
        p = Point(x, y)
        best = min(((shape(f["geometry"]).buffer(0).distance(p) * 100000, f) for f in feats), default=None, key=lambda t: t[0])
        if not best or best[0] > 15:
            continue
        f0 = best[1]; nm = (f0["properties"].get("buld_nm") or "").strip()
        same = [f0]
        if nm:
            g0 = shape(f0["geometry"]).centroid
            same += [f for f in feats if f is not f0 and (f["properties"].get("buld_nm") or "").strip() == nm and shape(f["geometry"]).centroid.distance(g0) * 100000 <= 150]
        same = [f for f in same if int(f["properties"].get("gro_flo_co") or 0) >= 3 or src.startswith("kakaoconf")]
        if same:
            found.append({"src": src, "conf": src.startswith("kakaoconf"), "name": nm, "sim": round(SequenceMatcher(None, norm(nm), norm(k[0])).ratio(), 2),
                          "buildings": [{"dong": f["properties"].get("buld_nm_dc") or "", "name": f["properties"].get("buld_nm") or "", "floors": f["properties"].get("gro_flo_co"),
                                         "rd": f["properties"].get("rn"), "no": f["properties"].get("buld_mnnm"), "bd_mgt_sn": f["properties"].get("bd_mgt_sn"), "geom": f["geometry"]} for f in same]})
        time.sleep(0.03)
    out["|".join(k)] = found
    print(k[0], [(f["src"][:20], f["name"], f["sim"], len(f["buildings"])) for f in found], flush=True)
json.dump(out, open(f"{V}/point_cache.json", "w", encoding="utf-8"), ensure_ascii=False)
print("DONE", flush=True)

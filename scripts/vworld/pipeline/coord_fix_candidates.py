import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, math, sys, time, requests
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from dotenv import dotenv_values
sys.stdout.reconfigure(encoding="utf-8")
R = R; V = f"{R}/data/derived/vworld"
H = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
M = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
A = json.load(open(f"{V}/coord_audit.json", encoding="utf-8"))
B = {"|".join(r["key"]): r for r in map(json.loads, open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8"))}
L = json.load(open(f"{V}/complex_status_ledger.json", encoding="utf-8"))
approved = {(r["name"], r["gu"], r["dong"]) for r in csv.DictReader(open(f"{R}/scripts/manual_overrides/wrong_apartment_geocodes_approved.csv", encoding="utf-8-sig"))}
ok, hold = [], []
for k, v in A.items():
    key = tuple(k.split("|")); r = B[k]; m = M[key]
    if not r["buildings"]:
        continue
    g = unary_union([shape(b["geom"]).buffer(0) for b in r["buildings"]])
    e = round(g.distance(Point(v["site"][1], v["site"][0])) * 1e5)
    if e <= 100:
        continue
    c = g.centroid
    if g.distance(c) * 1e5 > 30:
        c = g.representative_point()
    reasons = []
    geo = v.get("geo")
    gd = round(g.distance(Point(geo[1], geo[0])) * 1e5) if geo else None
    if gd is None or gd > 150: reasons.append(f"주소좌표 불일치({gd})")
    if r["status"] not in ("exact", "near") and L[k]["status"] not in ("split_rental", "shared_address"): reasons.append(f"동수 {r['status']}")
    if L[k]["status"] in ("rebuilt_old", "rebuilding", "alias"): reasons.append(L[k]["status"])
    if key in approved: reasons.append("이미 승인목록")
    d = requests.get("https://dapi.kakao.com/v2/local/geo/coord2regioncode.json", headers=H, params={"x": c.x, "y": c.y}, timeout=10).json()
    bdong = next((x["region_3depth_name"] for x in d.get("documents", []) if x["region_type"] == "B"), "")
    bgu = next((x["region_2depth_name"] for x in d.get("documents", []) if x["region_type"] == "B"), "")
    if bgu != key[1] or bdong.replace(" ", "") != key[2].replace(" ", ""): reasons.append(f"법정동 {bgu} {bdong}")
    time.sleep(0.03)
    row = {"name": m["k-아파트명"].strip(), "gu": key[1], "dong": key[2], "lat": f"{c.y:.7f}", "lng": f"{c.x:.7f}", "road_address": m["kapt도로명주소"].strip(),
           "old_lat": m["좌표Y"], "old_lng": m["좌표X"],
           "reason": f"K-apt 좌표가 단지 건물에서 {e}m 이탈. 브이월드 단지 건물(동 {r['n']}개) 중심으로 교체, 도로명주소 좌표와 {gd}m",
           "confidence": "HIGH", "source": "vworld_spbd_buildings+kakao_address_api+coord2regioncode_verified"}
    (hold if reasons else ok).append((row, reasons, e))
print("통과", len(ok), "보류", len(hold))
for row, rs, e in sorted(hold, key=lambda x: -x[2]): print("  보류", row["name"], row["gu"], e, "m |", "; ".join(rs))
json.dump({"ok": [x[0] for x in ok], "hold": [[x[0], x[1]] for x in hold]}, open(f"{V}/coord_fix_candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

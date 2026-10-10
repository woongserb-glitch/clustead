"""대표좌표 감사: 마스터 도로명주소를 카카오 주소검색으로 좌표화해 사이트 대표좌표(park_baseline)와 거리 비교.
→ data/derived/vworld/coord_audit.json  (읽기 전용 산출물)"""
import csv, json, math, sys, time
import requests
sys.stdout.reconfigure(encoding="utf-8")
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def kakao_key():
    """KAKAO_REST_API_KEY: 환경변수 → 저장소 .env 순."""
    if os.environ.get("KAKAO_REST_API_KEY"):
        return os.environ["KAKAO_REST_API_KEY"]
    from dotenv import dotenv_values
    return dotenv_values(ROOT / ".env").get("KAKAO_REST_API_KEY", "")

R = str(ROOT).replace("\\", "/")
H = {"Authorization": "KakaoAK " + kakao_key()}
M = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
co = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{R}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
out = {}
for n, (k, (lat, lng)) in enumerate(co.items(), 1):
    m = M.get(k, {}); a = (m.get("kapt도로명주소") or "").strip()
    e = {"addr": a, "site": [lat, lng]}
    try:
        e["kapt"] = [float(m["좌표Y"]), float(m["좌표X"])]
    except (KeyError, ValueError):
        pass
    if a:
        for _ in range(3):
            try:
                d = requests.get("https://dapi.kakao.com/v2/local/search/address.json", headers=H, params={"query": a}, timeout=10).json(); break
            except requests.RequestException:
                time.sleep(2); d = {}
        docs = d.get("documents", [])
        if docs:
            e["geo"] = [float(docs[0]["y"]), float(docs[0]["x"])]
            e["dist_site_geo"] = round(math.hypot((lat - e["geo"][0]) * 111000, (lng - e["geo"][1]) * 88400))
    if "kapt" in e:
        e["dist_site_kapt"] = round(math.hypot((lat - e["kapt"][0]) * 111000, (lng - e["kapt"][1]) * 88400))
    out["|".join(k)] = e
    time.sleep(0.02)
    if n % 500 == 0:
        print(n, flush=True)
json.dump(out, open(f"{R}/data/derived/vworld/coord_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
big = sorted(((v.get("dist_site_geo", 0), k) for k, v in out.items() if v.get("dist_site_geo", 0) >= 300), reverse=True)
print("DONE 300m+ 차이", len(big), flush=True)
for d, k in big[:80]:
    print(f"  {d}m {k} {out[k]['addr']}", flush=True)

"""(파이프라인 전용) 브이월드 GetFeature 호출·타일 상수 — 예전 collect_layers 의 API 부분.
월간 레이어 수집은 scripts/vworld/collect_layers.py 를 쓴다."""
"""서울 전역 브이월드 레이어 수집(바둑판 타일, 10㎢ 제한). 레이어마다 data/derived/vworld/<레이어>.geojson.

이미 받은 레이어 파일이 있으면 건너뛴다. 중복 객체는 속성+도형으로 거른다.
"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import json, sys, time, hashlib
from pathlib import Path
import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")
env = ENV
KEY = env.get("VWORLD_API_KEY") or env.get("V-WORLD_KEY")
OUT = REPO / "data" / "derived" / "vworld"
OUT.mkdir(parents=True, exist_ok=True)
LAYERS = {
    "LT_C_DESCH": "초등학교통학구역", "LT_C_DMSCH": "중학교학교군", "LT_C_DHSCH": "고등학교학교군",
    "LT_C_UPISUQ153": "도시계획(공간시설: 공원·녹지·광장)", "LT_P_TRADSIJANG": "전통시장",
    "LT_P_SMALLLIBRARY": "작은도서관", "LT_C_DOGPARK": "반려견놀이터", "LT_P_DGMUSEUMART": "박물관미술관",
    "LT_C_UQ111": "용도지역(도시지역)", "LT_C_WKMSTRM": "하천망", "LT_C_UPISUQ155": "도시계획(공공문화체육시설)",
}
LNG0, LNG1, LAT0, LAT1 = 126.76, 127.19, 37.41, 37.72
DLNG, DLAT = 0.025, 0.02   # 약 2.2km × 2.2km = 4.9㎢


def api(params, retries=5):
    base = {"service": "data", "request": "GetFeature", "key": KEY, "domain": "https://clustead.com",
            "format": "json", "crs": "EPSG:4326", "geometry": "true", "attribute": "true", "size": 1000}
    base.update(params)
    for attempt in range(retries):
        try:
            resp = requests.get("https://api.vworld.kr/req/data", params=base, timeout=60).json()["response"]
            if resp["status"] in ("OK", "NOT_FOUND"):
                return resp
            raise RuntimeError(resp.get("error"))
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def collect(layer):
    seen, feats = set(), []
    lng = LNG0
    while lng < LNG1:
        lat = LAT0
        while lat < LAT1:
            box = f"BOX({lng},{lat},{min(lng+DLNG, LNG1)},{min(lat+DLAT, LAT1)})"
            page = 1
            while True:
                resp = api({"data": layer, "geomFilter": box, "page": page})
                if resp["status"] == "NOT_FOUND":
                    break
                for f in resp["result"]["featureCollection"]["features"]:
                    h = hashlib.md5(json.dumps([f["properties"], f["geometry"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    if h not in seen:
                        seen.add(h); feats.append(f)
                if page >= int(resp["page"]["total"]):
                    break
                page += 1
            lat += DLAT
            time.sleep(0.03)
        lng += DLNG
    return feats


if __name__ == "__main__":
    for layer, label in LAYERS.items():
        path = OUT / f"{layer}.geojson"
        if path.exists():
            print("skip", layer, flush=True); continue
        t = time.time()
        feats = collect(layer)
        path.write_text(json.dumps({"type": "FeatureCollection", "layer": layer, "label": label, "features": feats}, ensure_ascii=False), encoding="utf-8")
        print(f"{layer} {label}: {len(feats)}개 · {time.time()-t:.0f}s", flush=True)
    print("DONE", flush=True)

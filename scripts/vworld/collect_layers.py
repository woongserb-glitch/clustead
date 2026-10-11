"""(월간 갱신) 서울 전역 브이월드 레이어 수집 → data/derived/vworld/<레이어>.geojson

바둑판 타일(약 2.2km × 2.2km, 브이월드 10㎢ 제한 안)로 받고, 속성+도형이 같은 중복 객체는 거른다.
매달 다시 받는 레이어(MONTHLY)와 한 번 받아 둔 참고 레이어(EXTRA)를 나눈다.

    python scripts/vworld/collect_layers.py                 # MONTHLY 전부 다시 받기(기존 파일 덮어씀)
    python scripts/vworld/collect_layers.py LT_P_TRADSIJANG # 지정 레이어만
    python scripts/vworld/collect_layers.py --missing-only  # 파일 없는 것만(MONTHLY + EXTRA)

키: 환경변수 VWORLD_API_KEY → 저장소 .env (옛 이름 V-WORLD_KEY 도 읽음). 받은 파일은 .new 로 쓴 뒤
피처 수가 0 이 아니면 교체한다(한도·오류로 빈 결과가 덮어쓰지 않게).

쓰는 곳:
  LT_C_UPISUQ153 → scripts/build_park_source_vworld.py → data/park/vworld_parks.geojson → 공원 baseline
  LT_P_TRADSIJANG → scripts/build_shopping_baseline.py (전통시장)
  LT_C_DMSCH / LT_C_DHSCH → scripts/vworld/build_dong_level.py (중·고 학교군)
  (초등 통학구역 LT_C_DESCH 는 scripts/fetch_school_zones_vworld.py 가 따로 받는다)
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "derived" / "vworld"

MONTHLY = {
    "LT_C_UPISUQ153": "도시계획(공간시설: 공원·녹지·광장)",
    "LT_P_TRADSIJANG": "전통시장",
    "LT_C_DMSCH": "중학교학교군",
    "LT_C_DHSCH": "고등학교학교군",
}
EXTRA = {
    "LT_P_SMALLLIBRARY": "작은도서관", "LT_C_DOGPARK": "반려견놀이터", "LT_P_DGMUSEUMART": "박물관미술관",
    "LT_C_UQ111": "용도지역(도시지역)", "LT_C_WKMSTRM": "하천망", "LT_C_UPISUQ155": "도시계획(공공문화체육시설)",
}
LNG0, LNG1, LAT0, LAT1 = 126.76, 127.19, 37.41, 37.72
DLNG, DLAT = 0.025, 0.02   # 약 2.2km × 2.2km = 4.9㎢


def vworld_key():
    key = os.environ.get("VWORLD_API_KEY") or os.environ.get("V-WORLD_KEY")
    if key:
        return key
    from dotenv import dotenv_values
    env = dotenv_values(ROOT / ".env")
    return env.get("VWORLD_API_KEY") or env.get("V-WORLD_KEY") or ""


def api(key, params, retries=5):
    base = {"service": "data", "request": "GetFeature", "key": key, "domain": "https://clustead.com",
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


def collect(key, layer):
    seen, feats = set(), []
    lng = LNG0
    while lng < LNG1:
        lat = LAT0
        while lat < LAT1:
            box = f"BOX({lng},{lat},{min(lng + DLNG, LNG1)},{min(lat + DLAT, LAT1)})"
            page = 1
            while True:
                resp = api(key, {"data": layer, "geomFilter": box, "page": page})
                if resp["status"] == "NOT_FOUND":
                    break
                for f in resp["result"]["featureCollection"]["features"]:
                    h = hashlib.md5(json.dumps([f["properties"], f["geometry"]], sort_keys=True,
                                               ensure_ascii=False).encode()).hexdigest()
                    if h not in seen:
                        seen.add(h)
                        feats.append(f)
                if page >= int(resp["page"]["total"]):
                    break
                page += 1
            lat += DLAT
            time.sleep(0.03)
        lng += DLNG
    return feats


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    key = vworld_key()
    if not key:
        raise SystemExit("VWORLD_API_KEY 가 없다(환경변수 또는 저장소 .env)")
    missing_only = "--missing-only" in argv
    named = [a for a in argv if not a.startswith("--")]
    every = {**MONTHLY, **EXTRA}
    if named:
        targets = {k: every.get(k, k) for k in named}
    elif missing_only:
        targets = {k: v for k, v in every.items() if not (OUT / f"{k}.geojson").exists()}
    else:
        targets = MONTHLY
    OUT.mkdir(parents=True, exist_ok=True)
    for layer, label in targets.items():
        t = time.time()
        feats = collect(key, layer)
        path = OUT / f"{layer}.geojson"
        if not feats:
            print(f"[SKIP] {layer} {label}: 0개 — 기존 파일 유지", flush=True)
            continue
        old = len(json.loads(path.read_text(encoding="utf-8"))["features"]) if path.exists() else None
        tmp = path.with_suffix(".geojson.new")
        tmp.write_text(json.dumps({"type": "FeatureCollection", "layer": layer, "label": label,
                                   "features": feats}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        print(f"[OK] {layer} {label}: {old if old is not None else '-'} → {len(feats)}개 · {time.time() - t:.0f}s",
              flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

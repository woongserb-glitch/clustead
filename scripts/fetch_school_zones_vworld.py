"""초등학교 통학구역 원천을 브이월드 API(LT_C_DESCH)로 받는다 → data/school/zone/vworld_desch.geojson

예전 원천(교육시설안전원 SHP, data.go.kr 15159265)은 매년 3·9월 파일을 손으로 내려받아
교체해야 했다. 브이월드 LT_C_DESCH 는 같은 데이터(2026-03-20판 기준 서울 629구역, 구역 ID
까지 동일함을 2026-10-10 확인)라 월간 갱신에서 자동으로 받는다. build_school_zone_baseline 은
이 파일이 있으면 이것을, 없으면 SHP 를 읽는다.

키: 환경변수 VWORLD_API_KEY(.env). 도메인은 브이월드에 등록된 https://clustead.com.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
OUT = BASE_DIR / "data" / "school" / "zone" / "vworld_desch.geojson"
API = "https://api.vworld.kr/req/data"
# 서울 전역을 2.2km 바둑판으로(브이월드 BOX 한도 10㎢)
LNG0, LNG1, LAT0, LAT1 = 126.76, 127.19, 37.41, 37.72
DLNG, DLAT = 0.025, 0.02


def fetch(key, box, page):
    params = {"service": "data", "request": "GetFeature", "data": "LT_C_DESCH", "key": key,
              "domain": "https://clustead.com", "format": "json", "crs": "EPSG:4326",
              "geometry": "true", "attribute": "true", "size": 1000, "geomFilter": box, "page": page}
    for attempt in range(5):
        try:
            resp = requests.get(API, params=params, timeout=60).json()["response"]
            if resp["status"] in ("OK", "NOT_FOUND"):
                return resp
            raise RuntimeError(resp.get("error"))
        except Exception:
            if attempt == 4:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    key = os.environ.get("VWORLD_API_KEY") or os.environ.get("V-WORLD_KEY")
    if not key:
        sys.exit("VWORLD_API_KEY 가 없습니다(.env 로드 후 실행).")
    seen, feats = set(), []
    lng = LNG0
    while lng < LNG1:
        lat = LAT0
        while lat < LAT1:
            box = f"BOX({lng},{lat},{min(lng + DLNG, LNG1)},{min(lat + DLAT, LAT1)})"
            page = 1
            while True:
                resp = fetch(key, box, page)
                if resp["status"] == "NOT_FOUND":
                    break
                for f in resp["result"]["featureCollection"]["features"]:
                    if f["properties"].get("edu_up_nm") != "서울특별시교육청":
                        continue
                    ident = f["properties"].get("hakgudo_id") or hashlib.md5(
                        json.dumps(f, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    if ident not in seen:
                        seen.add(ident)
                        feats.append(f)
                if page >= int(resp["page"]["total"]):
                    break
                page += 1
            lat += DLAT
        lng += DLNG
    if len(feats) < 500:
        sys.exit(f"서울 통학구역이 {len(feats)}개뿐입니다. 받기 실패로 보고 파일을 바꾸지 않습니다.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    base = max(f["properties"].get("base_dt", "") for f in feats)
    print(f"[OK] {OUT} 서울 통학구역 {len(feats)}개 (기준일 {base})")


if __name__ == "__main__":
    main()

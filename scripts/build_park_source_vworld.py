"""공원 원천: 브이월드 도시계획시설 공원(LT_C_UPISUQ153) 중 조성된 서울 공원 → data/park/vworld_parks.geojson

예전 공원 지표는 서울시 '주요 공원' 133곳의 대표점만 써서 동네 근린·어린이공원이 모두
빠졌다(가장 가까운 공원 중앙값 942m). 도시계획 공원 윤곽을 쓰면 110m 다.

- 대상: 대분류 '공원' 중 집행완료·부분집행(미집행=아직 조성 안 된 부지 제외), 서울(sig 11)
- 이름: 도면 이름의 괄호 안 이름 → 윤곽 안(30m)의 카카오 '공원' 장소명 → 주요 공원 133곳 이름
        → 없으면 종류명(예: '어린이공원')
- 입력: data/derived/vworld/LT_C_UPISUQ153.geojson (scripts 밖 수집기로 받음)
- 카카오 키: 환경변수 KAKAO_REST_API_KEY (.env 를 로드해서 실행)

Usage:
    python scripts/build_park_source_vworld.py            # 카카오 이름 보강 포함
    python scripts/build_park_source_vworld.py --no-kakao # 이름 보강 없이
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import Point, mapping, shape

BASE_DIR = Path(__file__).resolve().parents[1]
SRC = BASE_DIR / "data" / "derived" / "vworld" / "LT_C_UPISUQ153.geojson"
MAJOR = BASE_DIR / "data" / "park" / "park.csv"
OUT = BASE_DIR / "data" / "park" / "vworld_parks.geojson"
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
M2_PER_DEG2 = 111000 * 88400  # 서울 위도 근사


def read_csv(path):
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError:
            continue
    return []


def paren_name(dgm_nm):
    m = re.search(r"\(([^()]*)\)\s*$", dgm_nm or "")
    if not m:
        return ""
    name = m.group(1).strip()
    # '(공원)', '(소공원)', '(아동공원)' 처럼 종류만 적힌 괄호는 이름이 아니다.
    return "" if re.fullmatch(r"(어린이|아동|소|근린|가로|수변)?공원|녹지", name) else name


def trim_facility(name):
    """'향림근린공원 관리사무소' → '향림근린공원' (공원 안 시설 이름을 떼어 낸다)."""
    name = re.sub(r"\s+", " ", name or "").strip()
    m = re.match(r"^(.*?공원)(?:\s|$)", name)
    return m.group(1) if m else name


def kakao_name(geom, key):
    c = geom.representative_point()
    radius = int(min(1000, max(100, (geom.area * M2_PER_DEG2) ** 0.5)))
    for _ in range(3):
        try:
            resp = requests.get(KAKAO_URL, headers={"Authorization": f"KakaoAK {key}"},
                                params={"query": "공원", "x": c.x, "y": c.y, "radius": radius, "sort": "distance", "size": 15},
                                timeout=10)
            if resp.status_code == 200:
                break
            time.sleep(2)
        except requests.RequestException:
            time.sleep(2)
    else:
        return ""
    for doc in resp.json().get("documents", []):
        if "공원" not in doc.get("category_name", ""):
            continue
        p = Point(float(doc["x"]), float(doc["y"]))
        if geom.distance(p) * 100000 <= 30:
            return trim_facility(doc["place_name"])
    return ""


def main():
    use_kakao = "--no-kakao" not in sys.argv[1:]
    key = os.environ.get("KAKAO_REST_API_KEY", "")
    if use_kakao and not key:
        sys.exit("KAKAO_REST_API_KEY 가 없습니다(.env 로드 후 실행하거나 --no-kakao).")

    features = json.loads(SRC.read_text(encoding="utf-8"))["features"]
    majors = []
    for row in read_csv(MAJOR):
        try:
            majors.append((row["공원명"].strip(), Point(float(row["X좌표(WGS84)"]), float(row["Y좌표(WGS84)"]))))
        except (KeyError, ValueError):
            continue

    out, named = [], {"paren": 0, "kakao": 0, "major": 0, "type": 0}
    for f in features:
        p = f["properties"]
        if p.get("lcl_nam") != "공원" or p.get("exc_nam") == "미집행" or str(p.get("signgu_se", "")).strip()[:2] != "11":
            continue
        geom = shape(f["geometry"]).buffer(0)
        if geom.is_empty:
            continue
        kind = p.get("mls_nam") or "공원"
        if kind in ("기타공원시설", "미분류", "공원"):
            kind = re.sub(r"/.*|\(.*\)|\s", "", p.get("dgm_nm") or "") or "공원"
        name, how = paren_name(p.get("dgm_nm")), "paren"
        if not name:
            name, how = next((n for n, pt in majors if geom.distance(pt) * 100000 <= 30), ""), "major"
        if not name and use_kakao:
            name, how = kakao_name(geom, key), "kakao"
            time.sleep(0.02)
        if not name:
            name, how = kind, "type"
        named[how] += 1
        rp = geom.representative_point()
        out.append({
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "name": name, "kind": kind, "area_m2": round(geom.area * M2_PER_DEG2),
                "status": p.get("exc_nam", ""), "name_source": how,
                "lat": round(rp.y, 7), "lng": round(rp.x, 7),
            },
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {OUT} 공원 {len(out)}곳 | 이름 출처 {named}")


if __name__ == "__main__":
    main()

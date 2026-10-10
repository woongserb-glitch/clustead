"""한강 나들목 출입구(카카오 '한강공원 XX나들목 진출입로N') 전 구간 수집 → data/derived/hangang_access_points.json"""
import json, re, sys, time, requests
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

H = {"Authorization": "KakaoAK " + kakao_key()}
# 한강 중심선 근사: 강서(서) → 강동(동) 경유점
PATH = [(37.5866, 126.8175), (37.5667, 126.8760), (37.5556, 126.8990), (37.5437, 126.9013), (37.5284, 126.9336),
        (37.5240, 126.9550), (37.5176, 126.9705), (37.5126, 126.9966), (37.5206, 127.0146), (37.5270, 127.0400),
        (37.5297, 127.0690), (37.5186, 127.0883), (37.5300, 127.1000), (37.5449, 127.1195), (37.5560, 127.1330)]
pts = []
for (a, b), (c, d) in zip(PATH, PATH[1:]):
    for t in (0, 0.5):
        pts.append((a + (c - a) * t, b + (d - b) * t))
pts.append(PATH[-1])
NAME = re.compile(r"(?:한강공원\s*)?(.+?(?:나들목|경사로|계단|보행육교|육교|입구))")
out = {}
for y, x in pts:
    for q in ("한강공원 나들목", "나들목 진출입로", "나들목", "한강공원 진출입로", "한강공원 경사로", "한강공원 계단", "한강공원 보행육교", "한강공원 입구"):
        for page in (1, 2, 3):
            d = requests.get("https://dapi.kakao.com/v2/local/search/keyword.json", headers=H,
                             params={"query": q, "x": x, "y": y, "radius": 2500, "page": page, "size": 15}, timeout=10).json()
            for doc in d.get("documents", []):
                pn = doc["place_name"]
                cat = doc["category_name"]
                is_gate = "나들목" in pn and "IC" not in pn and ("입출구" in cat or "도로시설" in cat or "한강" in pn)
                # 나들목 외 출입구: '한강공원 OO경사로/계단/보행육교 진출입로' 등(입출구 분류)
                is_other = "한강공원" in pn and ("진출입로" in pn or "입구" in pn) and "입출구" in cat                     and not any(w in pn for w in ("주차장", "수영장", "물놀이", "캠핑", "매점"))
                if not (is_gate or is_other):
                    continue
                if not doc["address_name"].startswith("서울"):
                    continue
                out[doc["id"]] = {"name": pn, "group": (NAME.search(pn).group(1) if NAME.search(pn) else re.sub(r"\s*진출입로\d*$", "", pn)).replace("한강공원", "").replace(" ", ""),
                                  "lat": float(doc["y"]), "lng": float(doc["x"]), "category": doc["category_name"].split(">")[-1].strip(),
                                  "address": doc["road_address_name"] or doc["address_name"]}
            if d.get("meta", {}).get("is_end", True):
                break
            time.sleep(0.03)
json.dump(list(out.values()), open(ROOT / "data" / "derived" / "hangang_access_points.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
groups = sorted({v["group"] for v in out.values()})
print("출입구", len(out), "나들목", len(groups)); print(groups)

"""대형/창고형 마트 점포 리스트 생성기 (API 0콜).

대형(이마트·홈플러스·롯데마트)·창고형(코스트코·트레이더스)은 서울 전체에 70여 개뿐인
고정 점포라, 단지마다 키워드 검색을 반복할 필요가 없다. 이미 수집된 MT1 카테고리 캐시
(data/cache/kakao/mart_*.json, 서울 전역 1.5km 커버)에 모든 점포가 들어 있으므로,
그 캐시에서 점포를 추출·중복제거해 단일 리스트로 저장한다.
이후 build_mart_baseline.py가 이 리스트와 단지 좌표로 거리만 계산한다(API 0콜).
"""
import csv
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.poi_service import SUBTYPE_RULES, MART_CATEGORY_GROUPS

# 점포 리스트로 관리할 브랜드(대형 + 창고형). 슈퍼(SSM)는 점포가 많고 MT1 캐시로 무료
# 처리되므로 제외한다.
TARGET_BRANDS = set(
    MART_CATEGORY_GROUPS["large_mart"]["brands"]
    + MART_CATEGORY_GROUPS["warehouse_mart"]["brands"]
)

OUTPUT_PATH = "data/mart/large_warehouse_stores.csv"


def classify_brand(label, name=""):
    """SUBTYPE_RULES['mart'] 첫매칭 규칙으로 브랜드명을 판별(빌드와 동일 로직)."""
    text = f"{label} {name}".lower()
    for rule in SUBTYPE_RULES["mart"]:
        if any(keyword.lower() in text for keyword in rule["keywords"]):
            return rule["name"]
    return None


def main():
    stores = {}  # (round lat, round lng) -> {name, brand, lat, lng}
    cache_files = glob.glob("data/cache/kakao/mart_*.json")
    print(f"[STORE] MT1 캐시 {len(cache_files)}개 스캔")

    for path in cache_files:
        try:
            docs = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for doc in docs:
            label = str(doc.get("label", "")).replace("🛒", "").strip()
            name = str(doc.get("name", ""))
            brand = classify_brand(label, name)
            if brand not in TARGET_BRANDS:
                continue
            try:
                lat = float(doc["lat"])
                lng = float(doc["lng"])
            except Exception:
                continue
            key = (round(lat, 5), round(lng, 5))
            if key in stores:
                continue
            stores[key] = {
                "name": label or name,
                "brand": brand,
                "lat": lat,
                "lng": lng,
            }

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["name", "brand", "lat", "lng"])
        writer.writeheader()
        for store in sorted(stores.values(), key=lambda s: (s["brand"], s["name"])):
            writer.writerow(store)

    # 브랜드별 집계
    counts = {}
    for store in stores.values():
        counts[store["brand"]] = counts.get(store["brand"], 0) + 1
    print(f"[STORE] 점포 {len(stores)}개 → {OUTPUT_PATH}")
    for brand, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {brand}: {count}")


if __name__ == "__main__":
    main()

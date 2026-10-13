"""(분기 갱신) 서울시 정비사업 추진현황 → 단지별 재건축·재개발 단계.

입력: data/redevelopment/raw/seoul_redevelopment_YYMM.xlsx (서울 열린데이터광장 OA-22856
      '서울특별시 도시정비사업 통계' 첨부 엑셀, 분기마다 새 기준월 파일이 올라온다 — docs/MONTHLY_UPDATE.md)
      data/apartment/building_registry.csv (scripts/fetch_building_registry.py — 단지 지번)
출력: data/redevelopment/redevelopment_zones.csv   구역 전체(지번 좌표화 결과 포함)
      data/redevelopment/complex_redevelopment.csv 단지와 연결된 구역(단지당 1행)

연결 규칙(보수적으로):
  1) 구역 대표 지번(법정동·본번·부번)이 단지 지번과 같다 → lot_exact
  2) 구역 부번이 없고(본번만) 같은 법정동·본번 단지가 하나뿐이다 → lot_bun
  3) 위 둘이 아니면 구역명(괄호 안 포함)이 단지명과 같은 법정동에서 이름으로 겹친다 → name
여러 단지를 묶은 구역(압구정 특별계획구역 등)은 대표 지번 단지만 잡히므로 이름 연결로 보완하지 않은 단지는 빠진다.
"""
import csv
import json
import re
import time
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "vworld" / "pipeline"))
from _paths import ENV  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
RAW = ROOT / "data" / "redevelopment" / "raw"
OUT_DIR = ROOT / "data" / "redevelopment"
CACHE = OUT_DIR / "zone_geocode_cache.json"
REGISTRY = ROOT / "data" / "apartment" / "building_registry.csv"
KAKAO = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}

# 엑셀 열(0부터): 시트 1행 머리 4줄 아래부터 자료
COL = {"code": 0, "gu": 2, "zone": 3, "jibun": 4, "road": 5, "public": 6, "district_type": 7, "type": 8,
       "stage": 9, "households_before": 10, "designated": 11, "designated_changed": 12, "committee": 13,
       "union": 14, "architecture_review": 15, "project_approval": 16, "project_approval_changed": 17,
       "management_disposal": 18, "management_disposal_changed": 19, "relocation_start": 20,
       "relocation_end": 21, "construction_start": 22, "units_total": 23, "units_sale": 24, "units_rental": 25}
STAGES = ["구역지정", "추진위", "조합설립", "건축심의", "사업시행", "관리처분", "착공"]
DATE_KEYS = [k for k in COL if k in ("designated", "designated_changed", "committee", "union", "architecture_review",
                                     "project_approval", "project_approval_changed", "management_disposal",
                                     "management_disposal_changed", "relocation_start", "relocation_end",
                                     "construction_start")]


def latest_raw():
    files = sorted(RAW.glob("seoul_redevelopment_*.xlsx"))
    if not files:
        raise SystemExit("data/redevelopment/raw/seoul_redevelopment_YYMM.xlsx 가 없습니다")
    return files[-1]


def fmt(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return "" if v is None else str(v).strip()


def norm(name):
    return re.sub(r"아파트|\s|주택|재건축|통합|\(.*?\)|[0-9]+차$", "", name or "")


SEOUL_GU = ("종로구|중구|용산구|성동구|광진구|동대문구|중랑구|성북구|강북구|도봉구|노원구|은평구|서대문구|마포구|"
            "양천구|강서구|구로구|금천구|영등포구|동작구|관악구|서초구|강남구|송파구|강동구")
# 앞에 붙은 구 이름만 뗀다 — '[가-힣]+구' 로 떼면 '압구정동'의 '압구'까지 잘려 '정동 490'을 찾았다(2026-10-13)
GU_PREFIX = re.compile(rf"^(?:{SEOUL_GU})(?=[가-힣])")


def kakao_lot(query, key, cache):
    """카카오 주소검색 → 법정동코드·본번·부번·좌표. 요청 제한(429)·네트워크 오류는 재시도하고,
    그런 실패는 캐시하지 않는다(2026-10-13: 캐시를 지우고 다시 돌렸더니 429 실패가 '없음'으로 저장됐다)."""
    for attempt in range(4):
        try:
            r = requests.get("https://dapi.kakao.com/v2/local/search/address.json", headers=KAKAO,
                             params={"query": query}, timeout=10)
        except requests.RequestException:
            time.sleep(2); continue
        if r.status_code == 429:
            time.sleep(3); continue
        if r.status_code != 200:
            return None
        time.sleep(0.05)
        out = None
        for d in r.json().get("documents", []):
            a = d.get("address")
            if a and a.get("b_code", "").startswith("11"):
                out = {"b_code": a["b_code"], "bun": a["main_address_no"], "ji": a.get("sub_address_no") or "0",
                       "lat": d.get("y"), "lng": d.get("x")}
                break
        cache[key] = out
        return out
    return None


def geocode(gu, jibun, cache):
    first = re.split(r",|일대|번지", jibun or "")[0].strip()
    first = GU_PREFIX.sub("", first)  # '양천구신정동1200' → '신정동1200'
    key = f"{gu} {first}"
    if key in cache:
        return cache[key]
    # '당산동4가91'·'을지로3가227'·'중곡4동18-24' 처럼 동 이름 안에 숫자가 있다 — 가장 긴 동 이름부터
    m = re.match(r"([가-힣]+동\d+가|[가-힣]+\d+가|[가-힣]+\d+동|[가-힣]+동|[가-힣]+가)\s*(산?\d+)(?:-(\d+))?", first)
    query = f"서울 {gu} {m.group(1)} {m.group(2)}{'-' + m.group(3) if m.group(3) else ''}" if m else f"서울 {gu} {first}"
    return kakao_lot(query, key, cache)


def geocode_road(gu, road, cache):
    """지번으로 못 찾으면(압구정 특별계획구역 등 대표 지번이 실제 필지가 아님) 도로명주소로."""
    first = re.split(r",|일대|\(", road or "")[0].strip()
    first = GU_PREFIX.sub("", first)
    # 끝 번호 앞만 띄운다: '압구정로321'→'압구정로 321', '압구정로29길71'→'압구정로29길 71'
    first = re.sub(r"(로|길)(\d+(?:-\d+)?)$", r"\1 \2", first)
    if not first:
        return None
    key = f"road {gu} {first}"
    if key in cache:
        return cache[key]
    return kakao_lot(f"서울 {gu} {first}", key, cache)


def main():
    src = latest_raw()
    ws = openpyxl.load_workbook(src, read_only=True, data_only=True).worksheets[0]
    rows = [r for r in list(ws.iter_rows(values_only=True))[4:] if r[COL["zone"]]]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    zones = []
    for r in rows:
        z = {k: fmt(r[i]) if i < len(r) else "" for k, i in COL.items()}
        g = geocode(z["gu"], z["jibun"], cache) or geocode_road(z["gu"], z["road"], cache)
        z.update({"b_code": g["b_code"] if g else "", "bun": g["bun"] if g else "", "ji": g["ji"] if g else "",
                  "lat": g["lat"] if g else "", "lng": g["lng"] if g else "",
                  "stage_order": STAGES.index(z["stage"]) + 1 if z["stage"] in STAGES else ""})
        zones.append(z)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    complexes = list(csv.DictReader(open(REGISTRY, encoding="utf-8-sig")))
    by_lot, by_bun = {}, {}
    for c in complexes:
        if not c.get("b_code"):
            continue
        by_lot.setdefault((c["b_code"], c["bun"], c["ji"] or "0"), []).append(c)
        by_bun.setdefault((c["b_code"], c["bun"]), []).append(c)

    built = {(m["k-아파트명"].strip(), m["주소(시군구)"].strip(), m["주소(읍면동)"].strip()):
             (m.get("k-사용검사일-사용승인일") or "")[:10]
             for m in csv.DictReader(open(ROOT / "data" / "apartment" / "seoul_apartments.csv", encoding="cp949"))}

    def road_key(text):
        t = re.sub(r"^서울(특별시)?\s*", "", text or "")
        t = re.sub(r"^[가-힣]+구\s*", "", t)
        return re.sub(r"\s|번지|일대", "", t)

    by_road = {}
    for m in csv.DictReader(open(ROOT / "data" / "apartment" / "seoul_apartments.csv", encoding="cp949")):
        rk = road_key(m.get("kapt도로명주소"))
        if rk:
            by_road.setdefault(rk, []).append({"name": m["k-아파트명"].strip(), "gu": m["주소(시군구)"].strip(),
                                               "dong": m["주소(읍면동)"].strip()})

    linked = {}
    for z in zones:
        # 단지에 붙이는 건 아파트 재건축 구역만. 재개발·단독주택재건축 구역 안 아파트는 드물고, 지번이 겹치면
        # 그 사업으로 새로 지은 단지(영천 재개발 → 경희궁 유보라)에 '착공'이 붙는 오류가 났다(2026-10-13).
        if not z["b_code"] or z["type"] not in ("공동주택재건축", "아파트지구재건축"):
            continue
        hits, method = by_lot.get((z["b_code"], z["bun"], z["ji"] or "0"), []), "lot_exact"
        if not hits and (z["ji"] or "0") == "0" and len(by_bun.get((z["b_code"], z["bun"]), [])) == 1:
            hits, method = by_bun[(z["b_code"], z["bun"])], "lot_bun"
        if not hits:
            # 구역 도로명주소(여럿이면 쉼표)가 단지 도로명주소와 같으면 → road (대치쌍용1차: 구역 지번 66, 단지 지번 다름)
            for part in re.split(r",", z["road"] or ""):
                cands = by_road.get(road_key(part), [])
                cands = [c for c in cands if c["gu"] == z["gu"]]
                if len(cands) == 1:
                    hits, method = cands, "road"
                    break
        if not hits and z["type"] in ("공동주택재건축", "아파트지구재건축"):
            # 이름 연결은 아파트 재건축 구역만, 숫자로 끝나는 구역번호('방화3'·'신길1')는 빼고, 4글자 이상이
            # 같은 법정동 단지 이름과 통째로 같거나 한쪽이 다른 쪽을 품을 때만(2026-10-13: 느슨하게 했더니
            # '방화3'→'방화3차우림필유', '용답동'→청년주택처럼 16건 중 대부분이 틀렸다)
            names = [norm(z["zone"])] + [norm(x) for x in re.findall(r"\((.*?)\)", z["zone"])]
            names = [n for n in names if len(n) >= 4 and not re.search(r"\d$", n)]
            hits = [c for c in complexes if c.get("b_code") == z["b_code"]
                    and any(n == norm(c["name"]) or (len(norm(c["name"])) >= 4 and (n in norm(c["name"]) or norm(c["name"]) in n))
                            for n in names)]
            method = "name" if len(hits) == 1 else ""
            hits = hits if len(hits) == 1 else []
        # 새 단지 판별은 착공(없으면 관리처분·사업시행) 뒤 준공 — 구역지정일은 아파트지구(1976)처럼 옛 단지보다 앞설 수 있다
        since = z["construction_start"] or z["management_disposal"] or z["project_approval"]
        for c in hits:
            key = (c["name"], c["gu"], c["dong"])
            # 구역 지정 뒤에 준공한 단지는 그 사업의 결과물(새 단지) — 옛 단지 단계를 붙이지 않는다
            if since and built.get(key) and built[key] >= since:
                continue
            prev = linked.get(key)
            # 한 단지에 구역이 둘이면 더 진행된 단계를 남긴다
            if prev and (prev["stage_order"] or 0) >= (z["stage_order"] or 0):
                continue
            linked[key] = {**z, "name": c["name"], "complex_gu": c["gu"], "complex_dong": c["dong"], "match": method}

    # 여러 단지를 묶은 구역(압구정 특별계획구역 등)은 대표 지번 단지만 자동으로 잡힌다 → 사람이 확인한 구성으로 보완
    by_code = {z["code"]: z for z in zones}
    overrides = ROOT / "scripts" / "manual_overrides" / "redevelopment_zone_complexes.csv"
    if overrides.exists():
        for o in csv.DictReader(open(overrides, encoding="utf-8-sig")):
            z = by_code.get(o["zone_code"])
            if z:
                linked[(o["name"], o["gu"], o["dong"])] = {**z, "name": o["name"], "complex_gu": o["gu"],
                                                           "complex_dong": o["dong"], "match": "manual"}

    zone_fields = list(COL) + ["stage_order", "b_code", "bun", "ji", "lat", "lng"]
    with open(OUT_DIR / "redevelopment_zones.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=zone_fields); w.writeheader()
        for z in zones:
            w.writerow({k: z.get(k, "") for k in zone_fields})
    yymm = re.search(r"(\d{2})(\d{2})", src.stem)
    basis = f"20{yymm.group(1)}년 {int(yymm.group(2))}월" if yymm else ""
    for v in linked.values():
        v["basis"] = basis
    link_fields = ["name", "complex_gu", "complex_dong", "match", "basis", "code", "zone", "type", "stage", "stage_order",
                   "public", "district_type", "households_before", "units_total", "units_sale", "units_rental"] + DATE_KEYS
    with open(OUT_DIR / "complex_redevelopment.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=link_fields); w.writeheader()
        for v in sorted(linked.values(), key=lambda v: (v["complex_gu"], v["name"])):
            w.writerow({k: v.get(k, "") for k in link_fields})
    recon = [z for z in zones if "재건축" in z["type"]]
    print(f"원본 {src.name} · 구역 {len(zones)}(재건축 {len(recon)}) · 좌표화 실패 {sum(1 for z in zones if not z['b_code'])} · "
          f"단지 연결 {len(linked)} (지번 {sum(1 for v in linked.values() if v['match'].startswith('lot'))} · "
          f"도로명 {sum(1 for v in linked.values() if v['match'] == 'road')} · 이름 {sum(1 for v in linked.values() if v['match'] == 'name')} · "
          f"수동 {sum(1 for v in linked.values() if v['match'] == 'manual')})")


if __name__ == "__main__":
    main()

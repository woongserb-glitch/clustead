"""(분기 갱신) 단지별 건축물대장 요약: 용적률·건폐율·대지면적·최고층수 → data/apartment/building_registry.csv

원천: 국토교통부 건축HUB 건축물대장정보(공공데이터포털, PUBLIC_DATA_SERVICE_KEY) 총괄표제부·표제부.
지번: 카카오 주소검색(KAKAO_REST_API_KEY)으로 단지 도로명주소 → 법정동코드·본번·부번.

오래된 단지는 대장의 대지면적·용적률이 0 인 경우가 많다(은마: 구대장). 그때는
  용적률 = 총괄표제부 '용적률산정연면적' ÷ 지적도 필지 면적(브이월드 LP_PA_CBND_BUBUN)
  건폐율 = 총괄표제부 '건축면적' ÷ 필지 면적
으로 계산하고 ratio_source 를 'parcel' 로 남긴다(은마 204.2%·20.1% — 네이버 표기 204%·20% 와 일치).

이어받기: data/apartment/registry_cache.json 에 단지별 결과를 쌓는다. 공공데이터포털 일일 호출 한도에 걸리면
저장하고 멈춘다 → 다음 날 다시 돌리면 남은 단지만 받는다. --refresh 는 캐시를 무시하고 다시 받는다.
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "vworld" / "pipeline"))
from _paths import ENV  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
MASTER = ROOT / "data" / "apartment" / "seoul_apartments.csv"
CACHE = ROOT / "data" / "apartment" / "registry_cache.json"
OUT = ROOT / "data" / "apartment" / "building_registry.csv"
KAKAO = {"Authorization": "KakaoAK " + ENV["KAKAO_REST_API_KEY"]}
DATA_KEY = ENV["PUBLIC_DATA_SERVICE_KEY"]
VWORLD_KEY = ENV.get("VWORLD_API_KEY") or ENV.get("V-WORLD_KEY")
HUB = "https://apis.data.go.kr/1613000/BldRgstHubService/"
FIELDS = ["name", "gu", "dong", "b_code", "bun", "ji", "registry_name", "plat_area", "arch_area", "vl_area",
          "tot_area", "vl_rat", "bc_rat", "ratio_source", "max_floor", "main_bld_cnt", "hhld_cnt", "status"]


class QuotaExceeded(Exception):
    pass


def to_f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def lot_of(m):
    """도로명주소 → (법정동코드 10자리, 본번, 부번). 실패하면 지번주소로 한 번 더."""
    queries = [(m.get("kapt도로명주소") or "").strip()]
    jibun = f"서울 {m['주소(시군구)']} {m['주소(읍면동)']} {(m.get('나머지주소') or '').strip()}".strip()
    queries.append(jibun)
    for q in queries:
        if not q:
            continue
        r = requests.get("https://dapi.kakao.com/v2/local/search/address.json", headers=KAKAO,
                         params={"query": q}, timeout=10)
        docs = r.json().get("documents", []) if r.status_code == 200 else []
        for d in docs:
            a = d.get("address")
            if a and a.get("b_code", "").startswith("11"):
                return a["b_code"], a["main_address_no"], a.get("sub_address_no") or "0"
    return None


def hub(op, b_code, bun, ji):
    """한 지번의 기록 전부(100건씩 페이지). numOfRows 를 100 넘게 주면 기본 10건만 돌아온다."""
    out, page = [], 1
    while True:
        params = {"serviceKey": DATA_KEY, "sigunguCd": b_code[:5], "bjdongCd": b_code[5:], "bun": str(bun).zfill(4),
                  "ji": str(ji or "0").zfill(4), "_type": "json", "numOfRows": 100, "pageNo": page}
        body = None
        for attempt in range(3):
            try:
                r = requests.get(HUB + op, params=params, timeout=30)
            except requests.RequestException:
                time.sleep(3); continue
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in r.text or r.status_code == 429:
                raise QuotaExceeded(op)
            try:
                body = r.json()["response"]["body"]; break
            except (ValueError, KeyError):
                time.sleep(2)
        if not body:
            return out
        items = body.get("items") or {}
        items = items.get("item", []) if isinstance(items, dict) else []
        out += items if isinstance(items, list) else [items]
        if len(out) >= int(body.get("totalCount") or 0) or page >= 10:
            return out
        page += 1


def parcel_area(b_code, bun, ji):
    """지적도 필지 면적(㎡). 브이월드 연속지적도 — 실패하면 0."""
    if not VWORLD_KEY:
        return 0.0
    from pyproj import Geod
    from shapely.geometry import shape
    pnu = f"{b_code}1{str(bun).zfill(4)}{str(ji or '0').zfill(4)}"
    try:
        resp = requests.get("https://api.vworld.kr/req/data", params={
            "service": "data", "request": "GetFeature", "key": VWORLD_KEY, "domain": "https://clustead.com",
            "format": "json", "crs": "EPSG:4326", "geometry": "true", "attribute": "true",
            "data": "LP_PA_CBND_BUBUN", "attrFilter": f"pnu:=:{pnu}"}, timeout=30).json()["response"]
        if resp["status"] != "OK":
            return 0.0
        g = shape(resp["result"]["featureCollection"]["features"][0]["geometry"])
        return abs(Geod(ellps="WGS84").geometry_area_perimeter(g)[0])
    except Exception:
        return 0.0


def summarize(m, lot):
    b_code, bun, ji = lot
    recap = [x for x in hub("getBrRecapTitleInfo", b_code, bun, ji) if "공동주택" in (x.get("mainPurpsCdNm") or "")] \
        or hub("getBrRecapTitleInfo", b_code, bun, ji)
    titles = hub("getBrTitleInfo", b_code, bun, ji)
    homes = [x for x in titles if "공동주택" in (x.get("mainPurpsCdNm") or "")] or titles
    if recap:
        x = recap[0]
        plat, arch, vl_area, tot = (to_f(x.get(k)) for k in ("platArea", "archArea", "vlRatEstmTotArea", "totArea"))
        vl, bc, name = to_f(x.get("vlRat")), to_f(x.get("bcRat")), (x.get("bldNm") or "").strip()
        main_cnt, hhld = int(to_f(x.get("mainBldCnt"))), int(to_f(x.get("hhldCnt")))
    elif homes:  # 동이 하나인 단지 등 총괄표제부가 없으면 표제부를 합친다(대지는 공유라 최댓값)
        plat = max(to_f(x.get("platArea")) for x in homes)
        arch = sum(to_f(x.get("archArea")) for x in homes)
        vl_area = sum(to_f(x.get("vlRatEstmTotArea")) for x in homes)
        tot = sum(to_f(x.get("totArea")) for x in homes)
        vl = max(to_f(x.get("vlRat")) for x in homes)
        bc = max(to_f(x.get("bcRat")) for x in homes)
        name = (homes[0].get("bldNm") or "").strip()
        main_cnt, hhld = len(homes), int(sum(to_f(x.get("hhldCnt")) for x in homes))
    else:
        return {"status": "no_registry"}
    source = "registry" if vl > 0 else ""
    if vl <= 0 and vl_area > 0:
        # 대장에 용적률이 없으면 계산: 대장 대지면적이 있으면 그것으로, 없으면 지적도 필지 면적으로
        if plat > 0:
            area, source = plat, "registry_area"
        else:
            area, source = parcel_area(b_code, bun, ji), "parcel"
        if area > 0:
            vl = vl_area / area * 100
            bc = arch / area * 100 if arch > 0 else bc
            plat = area
        else:
            source = ""
    max_floor = max((int(to_f(x.get("grndFlrCnt"))) for x in homes), default=0)
    return {"registry_name": name, "plat_area": round(plat), "arch_area": round(arch), "vl_area": round(vl_area),
            "tot_area": round(tot), "vl_rat": round(vl, 1) if vl > 0 else "", "bc_rat": round(bc, 1) if bc > 0 else "",
            "ratio_source": source, "max_floor": max_floor or "", "main_bld_cnt": main_cnt or "",
            "hhld_cnt": hhld or "", "status": "ok" if vl > 0 else "no_ratio"}


def plausible(row):
    """말이 안 되는 값 거르기(2026-10-13 전수 수집에서 확인): 대장 값 자체 오류(249,024%),
    엉뚱한 작은 필지로 계산(18,226%), 여러 단지가 큰 필지 하나를 공유(18%) 등.
    대장 값은 30~1,500%, 필지 계산은 50~600% 이면서 건폐율 5~70% 일 때만 쓴다."""
    try:
        v, b = float(row.get("vl_rat") or 0), float(row.get("bc_rat") or 0)
    except (TypeError, ValueError):
        return False
    if row.get("ratio_source") == "registry":
        return 30 <= v <= 1500
    return 50 <= v <= 600 and 5 <= b <= 70


def main():
    refresh = "--refresh" in sys.argv
    master = list(csv.DictReader(open(MASTER, encoding="cp949")))
    cache = {} if refresh or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
    todo = [m for m in master if "|".join((m["k-아파트명"].strip(), m["주소(시군구)"].strip(), m["주소(읍면동)"].strip())) not in cache]
    print(f"단지 {len(master)} · 남은 단지 {len(todo)}", flush=True)
    stopped = None
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def one(m):
        key = "|".join((m["k-아파트명"].strip(), m["주소(시군구)"].strip(), m["주소(읍면동)"].strip()))
        lot = lot_of(m)
        if not lot:
            return key, {"status": "no_lot"}
        row = summarize(m, lot)
        row.update({"b_code": lot[0], "bun": lot[1], "ji": lot[2]})
        return key, row

    # 6개씩 동시에(단지 하나에 호출 4~5번 — 순서대로면 2,861곳에 4시간). 일일 한도에 걸리면 받은 데까지 저장.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(one, m) for m in todo]
        try:
            for n, fut in enumerate(as_completed(futures), 1):
                key, row = fut.result()
                cache[key] = row
                if n % 100 == 0:
                    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                    print(n, key, row.get("vl_rat"), row.get("status"), flush=True)
        except QuotaExceeded as exc:
            stopped = f"공공데이터포털 일일 한도({exc}) — 내일 다시 실행하면 이어서 받습니다"
            for f_ in futures:
                f_.cancel()
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for m in master:
            key = "|".join((m["k-아파트명"].strip(), m["주소(시군구)"].strip(), m["주소(읍면동)"].strip()))
            row = cache.get(key)
            if row and row.get("status") == "ok" and not plausible(row):
                row = {**row, "vl_rat": "", "bc_rat": "", "status": "suspect"}
            if row:
                w.writerow({"name": key.split("|")[0], "gu": key.split("|")[1], "dong": key.split("|")[2],
                            **{k: row.get(k, "") for k in FIELDS[3:]}})
    done = [v for v in cache.values() if v.get("status") == "ok" and plausible(v)]
    print(f"완료 {len(cache)}/{len(master)} · 용적률 있음 {len(done)} "
          f"(대장 {sum(1 for v in done if v.get('ratio_source') == 'registry')} · 필지계산 {sum(1 for v in done if v.get('ratio_source') == 'parcel')})"
          + (f" · 중단: {stopped}" if stopped else ""), flush=True)


if __name__ == "__main__":
    main()

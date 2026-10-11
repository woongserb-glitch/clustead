"""전 단지 동별 건물(브이월드 LT_C_SPBD = 도로명주소 건물) 수집. 이어받기 가능(이미 받은 단지는 건너뜀).

1순위: 마스터 도로명주소(rd_nm + buld_no)로 정확히 조회.
2순위(주소 없음/0건): 단지 대표 좌표 400m 상자 안 건물을 건물명 유사도로 골라 묶음.
결과: data/derived/vworld/complex_buildings.jsonl (단지 1줄)
"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, os, re, sys, time
from difflib import SequenceMatcher
from pathlib import Path
import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10**9)
ROOT = REPO
env = ENV
KEY = env.get("VWORLD_API_KEY") or env.get("V-WORLD_KEY")
OUT = ROOT / "data/derived/vworld/complex_buildings.jsonl"
OUT.parent.mkdir(parents=True, exist_ok=True)
NON_RES = re.compile(r"상가|관리|경로|어린이집|유치원|주민|커뮤니티|근린|생활지원|노인|보육|복지|체육|독서실|도서관|경비|기계|전기|변전|주차|펌프|문고|교회|판매|부대|공용|창고|쓰레기|분리수거|놀이")
RES = re.compile(r"^(제)?\s*([0-9]{1,4}|[가-하]|[A-Z])\s*동$")


def api(params, retries=4):
    base = {"service": "data", "request": "GetFeature", "data": "LT_C_SPBD", "key": KEY, "domain": "https://clustead.com",
            "format": "json", "crs": "EPSG:4326", "geometry": "true", "attribute": "true", "size": 1000}
    base.update(params)
    for attempt in range(retries):
        try:
            r = requests.get("https://api.vworld.kr/req/data", params=base, timeout=40)
            resp = r.json()["response"]
            if resp["status"] in ("OK", "NOT_FOUND"):
                return resp
            raise RuntimeError(resp.get("error"))
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def features(params):
    out, page = [], 1
    while True:
        resp = api({**params, "page": page})
        if resp["status"] == "NOT_FOUND":
            return out
        out += resp["result"]["featureCollection"]["features"]
        if page >= int(resp["page"]["total"]):
            return out
        page += 1
        time.sleep(0.05)


def norm(s):
    s = re.sub(r"\(.*?\)|아파트|apt|APT|\s", "", s or "")
    return s


def box(lat, lng, m):
    dlat, dlng = m / 111000, m / 88400
    return f"BOX({lng-dlng},{lat-dlat},{lng+dlng},{lat+dlat})"


def slim(f):
    p = f["properties"]
    g = f["geometry"]
    # 좌표는 소수 6자리(약 10cm)로 줄인다.
    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 6), round(c[1], 6)]
    return {"dong": (p.get("buld_nm_dc") or "").strip(), "name": p.get("buld_nm") or "", "floors": p.get("gro_flo_co"),
            "rd": p.get("rd_nm"), "no": p.get("buld_no"), "bd_mgt_sn": p.get("bd_mgt_sn"),
            "geom": {"type": g["type"], "coordinates": rnd(g["coordinates"])}}


def main():
    master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r
              for r in csv.DictReader(open(ROOT / "data/apartment/seoul_apartments.csv", encoding="cp949"))}
    coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"]))
              for r in csv.DictReader(open(ROOT / "data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
    done = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            done.add(tuple(json.loads(line)["key"]))
    todo = [k for k in coords if k not in done]
    print(f"전체 {len(coords)} · 완료 {len(done)} · 남음 {len(todo)}", flush=True)
    with OUT.open("a", encoding="utf-8") as fh:
        for i, key in enumerate(todo, 1):
            lat, lng = coords[key]
            m = master.get(key, {})
            rd, no = (m.get("주소(도로명)") or "").strip(), (m.get("주소(도로상세주소)") or "").strip()
            feats, method = [], ""
            if rd and no:
                feats = features({"geomFilter": box(lat, lng, 1400), "attrFilter": f"rd_nm:=:{rd}|buld_no:=:{no}"})
                method = "address"
            if not feats:
                cand = features({"geomFilter": box(lat, lng, 400)})
                target = norm(key[0])
                groups = {}
                for f in cand:
                    nm = f["properties"].get("buld_nm") or ""
                    if nm:
                        groups.setdefault(nm, []).append(f)
                best = max(groups, key=lambda nm: SequenceMatcher(None, norm(nm), target).ratio(), default=None)
                if best and SequenceMatcher(None, norm(best), target).ratio() >= 0.6:
                    feats, method = groups[best], f"name~{best}"
                else:
                    method = "unmatched"
            rows = [slim(f) for f in feats]
            for r in rows:
                r["residential"] = bool(RES.match(r["dong"])) and not NON_RES.search(r["dong"])
            fh.write(json.dumps({"key": list(key), "method": method, "households": m.get("k-전체세대수"),
                                 "buildings": rows}, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)} {key[0]} {method} {len(rows)}", flush=True)
            time.sleep(0.05)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

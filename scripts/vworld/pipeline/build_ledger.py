"""단지 상태 원장: 마스터 2,886(좌표 있는 단지) 전부의 상태를 증거와 함께 판정한다. 읽기 전용(결과 파일만 씀).

상태:
  normal            현존 · 동 매칭 정상
  split_rental      같은 단지의 분양/임대(제2) 분리 — 건물 공유
  shared_address    같은 주소의 서로 다른 단지 — 건물 분할 필요
  rebuilt_old       재건축 전 옛 단지(새 단지가 마스터에 있음) → successor 로 301
  rebuilding        재건축·철거 진행 추정(현장에 아파트 없음/거래 없음) → 안내 페이지
  alias             현존하지만 이름·주소가 마스터와 다름(동 매칭 실패) → 수동 확인
  partial           동 수가 마스터와 크게 다름 → 확인 필요
  review            판정 불가 → 수동 확인
"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, re, sys, time, collections
from difflib import SequenceMatcher
import requests
from dotenv import dotenv_values
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from building_match_report import residential

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10**9)
ROOT = R
S = V
KEY = ENV["VWORLD_API_KEY"]
OUT_JSON = f"{ROOT}/data/derived/vworld/complex_status_ledger.json"
OUT_CSV = f"{ROOT}/data/derived/vworld/complex_status_ledger.csv"

rows = list(csv.DictReader(open(f"{ROOT}/data/apartment/seoul_apartments.csv", encoding="cp949")))
key = lambda r: (r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip())
M = {key(r): r for r in rows}
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{ROOT}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
B = {tuple(r["key"]): r for r in map(json.loads, open(f"{ROOT}/data/derived/vworld/complex_buildings_v5.jsonl", encoding="utf-8"))}
try:
    CN = json.load(open(f"{ROOT}/data/derived/vworld/complex_common_names.json", encoding="utf-8"))
except FileNotFoundError:
    CN = {}
CNV = json.load(open(f"{ROOT}/data/derived/vworld/common_names_verified.json", encoding="utf-8"))
RT = re.compile(r"\(.*?\)|임대|분양|제\d+|SH|sh|공공|국민|행복|영구|아파트|\s")
T = {tuple(k.split("|")): v for k, v in json.load(open(f"{S}/last_trade.json", encoding="utf-8")).items()}
year = lambda k: int((M[k].get("k-사용검사일-사용승인일") or "0000")[:4] or 0)
want = lambda k: int(float(M[k].get("k-전체동수") or 0) or 0)
hh = lambda k: int(float(M[k].get("k-전체세대수") or 0) or 0)
RENTAL = re.compile(r"임대|제2|제\d|SH|sh|분양|\(.*\)|행복|청년")
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s", "", s or "")


def site_names(lat, lng, m=200):
    dlat, dlng = m / 111000, m / 88400
    r = requests.get("https://api.vworld.kr/req/data", params={"service": "data", "request": "GetFeature", "data": "LT_C_SPBD", "key": KEY,
        "domain": "https://clustead.com", "geomFilter": f"BOX({lng-dlng},{lat-dlat},{lng+dlng},{lat+dlat})", "format": "json", "size": 1000,
        "crs": "EPSG:4326", "geometry": "false"}, timeout=30).json()["response"]
    c = collections.Counter()
    for f in r.get("result", {}).get("featureCollection", {}).get("features", []):
        p = f["properties"]
        if p.get("buld_nm") and (re.search(r"\d+\s*동", p.get("buld_nm_dc") or "") or int(p.get("gro_flo_co") or 0) >= 10):
            c[p["buld_nm"]] += 1
    return [n for n, _ in c.most_common(3)]


def master_successor(names, lat, lng, exclude):
    """현장 아파트 이름과 비슷한(0.7+) 마스터 단지 중 600m 안에서 가장 가까운 것."""
    best = None
    for k, (y, x) in coords.items():
        if k == exclude:
            continue
        d = ((y - lat) * 111000) ** 2 + ((x - lng) * 88400) ** 2
        if d > 600 ** 2:
            continue
        s = max((SequenceMatcher(None, norm(n), norm(k[0])).ratio() for n in names), default=0)
        if s >= 0.7 and (best is None or (s, -d) > best[0]):
            best = ((s, -d), k)
    return best[1] if best else None


from shapely.geometry import shape as _shape, Point as _Point
from shapely.ops import unary_union as _union
from shapely.strtree import STRtree as _Tree
PC = json.load(open(f"{ROOT}/data/derived/vworld/point_cache.json", encoding="utf-8"))
_g, _o = [], []
for kk, rr in B.items():
    for bb in rr["buildings"]:
        _g.append(_shape(bb["geom"]).buffer(0)); _o.append(kk)
_tree = _Tree(_g)


def spatial_successor(k):
    """옛 단지 자리(건축물대장 옛 윤곽, 없으면 좌표 지점 건물·대표좌표 30m)에 지금 서 있는 단지 = 후속 단지."""
    b = B.get(k, {})
    polys = [_shape(g).buffer(0) for g in b.get("old_site", [])]
    if not polys:
        for f in PC.get("|".join(k), []):
            polys += [_shape(x["geom"]).buffer(0) for x in f["buildings"]]
    lat, lng = coords[k]
    near_p = [p for p in polys if ((p.centroid.y - lat) * 111000) ** 2 + ((p.centroid.x - lng) * 88400) ** 2 <= 250 ** 2]
    polys = near_p or polys
    area = _union(polys).buffer(0.0001) if polys else _Point(lng, lat).buffer(0.0003)
    c = collections.Counter()
    for i in _tree.query(area):
        i = int(i)
        if _o[i] != k and _g[i].intersects(area):
            c[_o[i]] += 1
    if not c:
        return None
    best = c.most_common(1)[0][0]
    if polys:
        sg = _union([_g[i] for i in range(len(_g)) if _o[i] == best]).buffer(0.00005)
        cover = sum(1 for p in polys if p.intersects(sg)) / len(polys)
        if cover < 0.3:
            return None
    return best


ledger = {}
# 1) 같은 주소 묶음
groups = collections.defaultdict(list)
for k in coords:
    a = (M.get(k, {}).get("kapt도로명주소") or "").strip()
    if a:
        groups[a].append(k)
for a, ks in groups.items():
    if len(ks) < 2:
        continue
    ys = sorted(year(k) for k in ks)
    if ys[-1] - ys[0] >= 10 and ys[-1] >= 2015:
        new = max(ks, key=year)
        for k in ks:
            if k != new and year(k) <= ys[0] + 5:
                ledger[k] = {"status": "rebuilt_old", "successor": list(new), "evidence": f"같은 주소 {a} · {year(k)}년 단지와 {year(new)}년 단지"}
    elif len({year(k) for k in ks}) == 1 and any(RENTAL.search(k[0]) for k in ks):
        main = max(ks, key=hh)
        for k in ks:
            ledger.setdefault(k, {"status": "split_rental", "group_main": list(main), "evidence": f"같은 주소 {a} · 같은 해 사용승인 · 분양/임대 분리"})
    else:
        for k in ks:
            ledger.setdefault(k, {"status": "shared_address", "group": [list(x) for x in ks if x != k], "evidence": f"같은 주소 {a}"})

# 2) 나머지 판정
n_api = 0
for k in coords:
    if k in ledger:
        continue
    b = B.get(k, {"status": "none", "n": 0, "bldg_how": "missing"})
    w = want(k); trades = T.get(k, {}).get("n_2025plus", 0)
    if b["status"] not in ("none", "ghost"):
        st = "partial" if b["status"] == "diff" else "normal"
        ledger[k] = {"status": st, "evidence": f"매칭 {b['n']}동 / 마스터 {w}동 · 동번호 {b['labeled']} · {b['spbd_method'][:24]} · {b['bldg_how']}"}
        continue
    fam = [x for x in coords if x != k and x[1] == k[1] and RT.sub("", x[0]) and RT.sub("", x[0]) == RT.sub("", k[0])]
    if fam and RENTAL.search(k[0]):
        ledger[k] = {"status": "split_rental", "group_main": list(max(fam, key=hh)), "evidence": f"건물 단독 매칭 없음 · 같은 이름 단지 {fam[0][0]}의 임대/분리분"}
        continue
    lat, lng = coords[k]
    names = site_names(lat, lng); n_api += 1; time.sleep(0.05)
    succ = spatial_successor(k); succ_by = "위치"
    name_guess = master_successor(names, lat, lng, k)
    ev = ("건축물대장에만 남은 건물(현행 도로명주소 건물 없음·철거 추정) · " if b["status"] == "ghost" else "") + f"동 매칭 실패 · 현장 아파트 {names or '없음'} · 2025년 이후 거래 {trades}건 · {year(k)}년 사용승인"
    if b["status"] == "ghost" or (trades == 0 and not RENTAL.search(k[0])):
        if succ and year(succ) >= year(k) + 20:
            chk = "" if succ[2] == k[2] else f" · 확인필요: 후속 단지 법정동({succ[2]})이 옛 단지({k[2]})와 다름"
            ledger[k] = {"status": "rebuilt_old", "successor": list(succ), "successor_by": succ_by, "check": bool(chk), "evidence": ev + f" · 후속 판정 {succ_by}" + chk}
        elif b["status"] == "ghost" or not names or (succ is None and year(k) < 2000):
            ledger[k] = {"status": "rebuilding", "evidence": ev}
        else:
            ledger[k] = {"status": "review", "candidates": names, "evidence": ev}
    else:
        ledger[k] = {"status": "alias", "candidates": names, "successor_guess": list(succ or name_guess) if (succ or name_guess) else None, "evidence": ev}

# 카카오 장소명에 '(YYYY년MM월예정)' 이 붙은 새 단지 = 그 자리 재건축 진행 중
try:
    SIG = {kk: nm for kk, nm in json.load(open(f"{ROOT}/data/derived/vworld/rebuild_signals_from_names.json", encoding="utf-8"))}
except FileNotFoundError:
    SIG = {}
for k, v in list(ledger.items()):
    nm = SIG.get("|".join(k))
    if nm and v["status"] not in ("rebuilt_old", "rebuilding"):
        ledger[k] = {"status": "rebuilding", "planned": nm, "evidence": f"카카오에 마스터 주소와 같은 곳 '{nm}' 등록(재건축·조합 신호) · 이전 판정 {v['status']}"}
for k, v in ledger.items():
    planned = [n for n in CN.get("|".join(k), {}).get("kakao_all", {}) if re.search(r"\d{4}년\s*\d{1,2}월\s*예정", n)]
    if planned and v["status"] not in ("rebuilt_old",):
        ledger[k] = {"status": "rebuilding", "planned": planned[0], "evidence": f"카카오에 그 자리 새 단지 '{planned[0]}' 등록 · 이전 판정 {v['status']}"}
for k, v in ledger.items():
    cn = CN.get("|".join(k), {})
    if "|".join(k) in CNV:
        v["common_name"] = CNV["|".join(k)]
json.dump({"|".join(k): v for k, v in ledger.items()}, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh); w.writerow(["단지명", "구", "동", "상태", "통용명 후보", "연결 대상", "증거"])
    for k, v in sorted(ledger.items(), key=lambda x: (x[1]["status"], x[0])):
        tgt = v.get("successor") or v.get("group_main") or v.get("successor_guess") or ""
        w.writerow([k[0], k[1], k[2], v["status"], v.get("common_name", ""), " ".join(tgt) if tgt else "", v["evidence"]])
c = collections.Counter(v["status"] for v in ledger.values())
print(dict(c), "합계", sum(c.values()), "· 현장 조회", n_api)
for st in ("rebuilt_old", "rebuilding", "alias", "review"):
    print(f"\n## {st}")
    for k, v in ledger.items():
        if v["status"] == st:
            print("  ", k[0], k[1], "→", v.get("successor") or v.get("candidates") or "", "|", v["evidence"][:110])

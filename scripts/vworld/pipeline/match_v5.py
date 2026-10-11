"""마스터 ↔ 브이월드 단지 매칭 v5: 세 근거를 합친다.

  S  도로명주소 건물(LT_C_SPBD) — complex_buildings_v4.jsonl (주소·이름·근접 + 카카오 동번호)
  B  건축물정보(LT_C_BLDGINFO, 공동주택) — 사용승인일이 마스터와 같은 건물 = 이 단지 건물
  K  카카오 현장 이름(complex_common_names.json, 있으면)

B 매칭:
  1) 중심 800m 안 공동주택 중 사용승인일 == 마스터 사용승인일
  2) 그 건물들의 이름 앞부분(동 제외)과 같은 이름이면 날짜가 달라도(차수·추가 승인) 500m 안이면 포함
  3) 1)이 없으면 같은 해·월 + 이름 유사(0.6+) 500m 안
B 와 S 의 건물 윤곽이 겹치면 같은 건물로 보고, 동번호는 S → B 순으로 채운다.

출력: complex_buildings_v5.jsonl, match_v5_report.json (읽기 전용 산출물)
"""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import collections, csv, json, re, sys
from difflib import SequenceMatcher
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
ROOT = R; V = f"{ROOT}/data/derived/vworld"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from building_match_report import residential, NON_RES

M = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip()): r for r in csv.DictReader(open(f"{ROOT}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{ROOT}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
SRC = sys.argv[1] if len(sys.argv) > 1 else f"{V}/complex_buildings_v4.jsonl"
S = {tuple(json.loads(l)["key"]): json.loads(l) for l in open(SRC, encoding="utf-8")}
try:
    CN = json.load(open(f"{V}/complex_common_names.json", encoding="utf-8"))
except FileNotFoundError:
    CN = {}

try:
    EX = json.load(open(f"{V}/exist_cache.json", encoding="utf-8"))
except FileNotFoundError:
    EX = {}
try:
    PC = json.load(open(f"{V}/point_cache.json", encoding="utf-8"))
except FileNotFoundError:
    PC = {}
feats = json.load(open(f"{V}/bldginfo_apt.geojson", encoding="utf-8"))["features"]
BG = [shape(f["geometry"]) for f in feats]
BP = [f["properties"] for f in feats]
BC = [g.centroid for g in BG]
tree = STRtree(BC)

DONG_TAIL = re.compile(r"\s*(제?\s*\d{1,4}|[A-Za-z]|[가-하]|에이|비|씨|디)\s*동\s*$")
base = lambda s: re.sub(r"\s+", "", DONG_TAIL.sub("", (s or "").strip()))
norm = lambda s: re.sub(r"\(.*?\)|아파트|\s|제|단지|차", "", s or "")
mdate = lambda k: (M[k].get("k-사용검사일-사용승인일") or "")[:10].replace("-", "")
want = lambda k: int(float(M[k].get("k-전체동수") or 0) or 0)
NONRES_B = re.compile(r"관리|경비|상가|근린|노인|경로|유치원|어린이집|보육|주민|커뮤니티|기계|전기|변전|펌프|쓰레기|분리수거|주차|창고|부속|초소|복리|판매|교회|사무")


HANGUL_DONG = "가나다라마바사아자차카타파하"
LAB_RE = re.compile(r"(?:^|[^가-힣])(?:제\s*)?(\d{1,4}|[A-Z]|[" + HANGUL_DONG + r"])\s*동\s*$")
LAB_RE2 = re.compile(r"(\d{1,4})\s*동\s*$")


def label_of(text):
    t = (text or "").strip()
    m = LAB_RE2.search(t) or LAB_RE.search(t)
    return (m.group(1).lstrip("0") or m.group(1)) if m else ""


def is_nonres_b(p):
    return bool(NONRES_B.search((p.get("bld_nm") or "") + " " + (p.get("dong_nm") or "")))


def dong_label(p):
    d = (p.get("dong_nm") or "").strip()
    if d:
        d2 = label_of(d if d.endswith("동") else d + "동")
        return d2
    m = re.search(r"(\d{1,4})\s*동\s*$", p.get("bld_nm") or "")
    return m.group(1) if m else ""


def near_idx(lat, lng, m):
    dl, dg = m / 111000, m / 88400
    from shapely.geometry import box
    return [int(i) for i in tree.query(box(lng - dg, lat - dl, lng + dg, lat + dl))]


def dist_m(p, lat, lng):
    return ((p.y - lat) * 111000) ** 2 + ((p.x - lng) * 88400) ** 2


def bldginfo_match(k, lat, lng):
    d = mdate(k)
    cand = [i for i in near_idx(lat, lng, 800) if not is_nonres_b(BP[i]) and BG[i].area * 111000 * 88400 >= 150]
    exact = [i for i in cand if d and BP[i].get("useapr_day") == d]
    how = "date"
    if exact:
        # 같은 날짜라도 다른 단지가 섞일 수 있다: 이름 앞부분별로 묶고 중심에 가까운 묶음(들)만 쓴다.
        groups = collections.defaultdict(list)
        for i in exact:
            groups[base(BP[i].get("bld_nm"))].append(i)
        def gscore(item):
            nm, ids = item
            dmin = min(dist_m(BC[i], lat, lng) for i in ids) ** 0.5
            sim = SequenceMatcher(None, norm(nm), norm(k[0])).ratio() if nm else 0
            return (dmin <= 150 or sim >= 0.6, -dmin)
        ranked = sorted(groups.items(), key=gscore, reverse=True)
        keep = [ranked[0]] + [g for g in ranked[1:] if gscore(g)[0] and (gscore(g)[1] > -250)]
        chosen = [i for _, ids in keep for i in ids]
        names = {nm for nm, _ in keep if nm}
        # 같은 이름의 다른 날짜(추가 사용승인) 건물 보강
        cx = sum(BC[i].x for i in chosen) / len(chosen); cy = sum(BC[i].y for i in chosen) / len(chosen)
        extra = [i for i in cand if i not in chosen and names and base(BP[i].get("bld_nm")) in names and dist_m(BC[i], cy, cx) <= 500 ** 2]
        return chosen, how
    ym = d[:6]
    if ym:
        loose = [i for i in near_idx(lat, lng, 500) if (BP[i].get("useapr_day") or "")[:6] == ym
                 and SequenceMatcher(None, norm(base(BP[i].get("bld_nm"))), norm(k[0])).ratio() >= 0.6 and not NONRES_B.search(BP[i].get("bld_nm") or "")]
        if loose:
            return loose, "month+name"
    return [], "none"


def merge(srow, bids):
    """S 건물과 B 건물을 윤곽으로 합친다. 반환: [{label, geom, src}]"""
    out = []
    s_res = [b for b in (srow or {}).get("buildings", []) if (b.get("residential") or residential(b)) and not NON_RES.search((b["dong"] or "") + (b["name"] or ""))]
    s_geoms = [shape(b["geom"]) for b in s_res]
    used_b = set()
    for b, g in zip(s_res, s_geoms):
        lab = ""
        lab = label_of(b["dong"]) or label_of(b["name"])
        src = "spbd" + ("/kakao" if b.get("dong_source") == "kakao" else "")
        for i in bids:
            if i in used_b:
                continue
            if g.buffer(0).intersects(BG[i]) and (g.contains(BC[i]) or BG[i].contains(g.centroid) or g.intersection(BG[i]).area > 0.3 * min(g.area, BG[i].area)):
                used_b.add(i)
                bl = dong_label(BP[i])
                if not lab and bl:
                    lab, src = bl, src + "+bldg"
                elif lab and bl and bl != lab:
                    src += f"!bldg={bl}"
                else:
                    src += "+bldg"
                break
        out.append({"label": lab, "src": src, "geom": g})
    for i in bids:
        if i in used_b:
            continue
        # S 에 없는 B 건물(브이월드 도로명주소 건물에서 빠진 동)
        if any(o["geom"].intersects(BG[i]) for o in out):
            continue
        out.append({"label": dong_label(BP[i]), "src": "bldg", "geom": BG[i]})
    return out


report = collections.Counter(); rows = []; detail = []
KEYS = [k for k in coords if k in M]
maddr = lambda k: re.sub(r"\s+", " ", (M[k].get("kapt도로명주소") or "").replace("서울특별시 ", "").strip())
RENT_TOK = re.compile(r"\(.*?\)|임대|분양|제\d+|SH|sh|공공|국민|행복|영구|아파트|\s")
same_family = lambda a, b: maddr(a) == maddr(b) or RENT_TOK.sub("", a[0]) == RENT_TOK.sub("", b[0])

# A) 도로명주소 건물 소유권 정리: 서로 다른 단지가 같은 건물을 잡으면 주소 일치 → 가까운 중심 순으로 한 곳에.
s_bld = {}
for k in KEYS:
    srow = S.get(k)
    s_bld[k] = [b for b in (srow or {}).get("buildings", []) if (b.get("residential") or residential(b)) and not NON_RES.search((b["dong"] or "") + (b["name"] or ""))]
claims = collections.defaultdict(list)
for k in KEYS:
    for b in s_bld[k]:
        claims[b["bd_mgt_sn"]].append(k)
dropped = collections.Counter()
for sn, ks in claims.items():
    if len(ks) < 2:
        continue
    fam = [x for x in ks]
    # 같은 가족(같은 주소·분양/임대)끼리만이면 공유 유지
    if all(same_family(ks[0], x) for x in ks[1:]):
        continue
    b0 = next(b for b in s_bld[ks[0]] if b["bd_mgt_sn"] == sn)
    g = shape(b0["geom"]).centroid
    def score(k):
        a = maddr(k); hit = bool(b0.get("rd")) and a.endswith(f"{b0['rd']} {b0['no']}")
        lat, lng = coords[k]
        return (hit, -dist_m(g, lat, lng))
    owner = max(ks, key=score)
    for k in ks:
        if k != owner and not same_family(k, owner):
            s_bld[k] = [b for b in s_bld[k] if b["bd_mgt_sn"] != sn]; dropped[k] += 1

# 다른 단지 소유 S 건물 색인(건축물정보 보충 시 제외용)
own_geo, own_key = [], []
for k in KEYS:
    for b in s_bld[k]:
        own_geo.append(shape(b["geom"]).buffer(0)); own_key.append(k)
own_tree = STRtree(own_geo)


def owned_by_other(i, k):
    for j in own_tree.query(BC[i]):
        j = int(j)
        if own_key[j] != k and not same_family(own_key[j], k) and own_geo[j].contains(BC[i]):
            return True
    return False


for k in KEYS:
    lat, lng = coords[k]
    srow = {"buildings": s_bld[k], "method": (S.get(k) or {}).get("method", "missing")}
    bids_date, how_date = bldginfo_match(k, lat, lng)
    bids_date = [i for i in bids_date if not owned_by_other(i, k)]
    s_res = [shape(b["geom"]) for b in s_bld[k]]
    w = want(k)
    options = []
    if s_res:
        from shapely.ops import unary_union
        hull = unary_union([g.buffer(0) for g in s_res]).convex_hull.buffer(0.0003)
        inside = [i for i in near_idx(lat, lng, 800) if hull.contains(BC[i]) and not is_nonres_b(BP[i]) and BG[i].area * 111000 * 88400 >= 150 and not owned_by_other(i, k)]
        bh = [i for i in inside if i in set(bids_date) or BP[i].get("useapr_day") == mdate(k)]
        sb = merge(srow, bh)
        options.append(("spbd+bldg_label", [x for x in sb if x["src"] != "bldg"], bh))
        if any(x["src"] == "bldg" for x in sb):
            options.append(("spbd+bldg_add", sb, bh))
    ghost = EX.get("|".join(k), {}).get("frac", 1) < 0.5
    if bids_date and not ghost:
        options.append(("bldg_" + how_date, merge(None, bids_date), bids_date))
    if not options:
        # 좌표 지점 매칭(1~2동 주상복합 등): 이름이 비슷한(0.6+) 건물만, 마스터 동수까지 가까운 순
        cands = sorted([f for f in PC.get("|".join(k), []) if f["sim"] >= 0.6 or f.get("conf")], key=lambda f: (not f.get("conf"), -f["sim"], f["src"] != "kapt"))
        if cands:
            f = cands[0]
            pt = shape(f["buildings"][0]["geom"]).centroid
            bl = sorted(f["buildings"], key=lambda b: shape(b["geom"]).distance(pt))[:max(w, 1)]
            options.append(("point_" + f["src"].split(":")[0], [{"label": label_of(b["dong"]) or label_of(b["name"]), "src": "point", "geom": shape(b["geom"]).buffer(0)} for b in bl], []))
    if options:
        how, merged, bids = min(options, key=lambda o: (abs(len(o[1]) - w) if w else 0, options.index(o)))
    else:
        how, merged, bids = "none", [], []
    n = len(merged)
    labeled = sum(1 for x in merged if x["label"])
    if not merged:
        st = "ghost" if ghost else "none"
    elif w and n == w:
        st = "exact"
    elif w and abs(n - w) <= max(1, round(w * 0.1)):
        st = "near"
    else:
        st = "diff"
    report[st] += 1
    report["b_" + how] += 1
    conflicts = sum(1 for x in merged if "!bldg" in x["src"])
    report["label_conflicts"] += conflicts
    rows.append({"key": list(k), "status": st, "want": w, "n": n, "labeled": labeled, "spbd_method": srow["method"],
                 "bldg_how": how, "bldg_n": len(bids), "conflicts": conflicts, "dropped_shared": dropped[k], "ghost": ghost,
                 "old_site": [BG[i].__geo_interface__ for i in bids_date] if ghost else [],
                 "common_name": CN.get("|".join(k), {}).get("common", ""),
                 "buildings": [{"label": x["label"], "src": x["src"], "geom": x["geom"].__geo_interface__} for x in merged]})
    detail.append((st, k, w, n, labeled, srow["method"][:25], how, len(bids)))
print("공유건물 정리로 뺀 건물", sum(dropped.values()), "단지", len(dropped))

# D) 최종 정리: 가족이 아닌 두 단지가 같은 건물을 가지면, 그 자리 건축물대장 사용승인일이 일치하는 단지에 준다.
def bdate_at(geom):
    c = geom.centroid
    ds = [BP[i].get("useapr_day") for i in tree.query(geom) if geom.contains(BC[int(i)])]
    return set(d for d in ds if d)


def restatus(r):
    w, n = r["want"], len(r["buildings"])
    r["n"] = n; r["labeled"] = sum(1 for x in r["buildings"] if x["label"])
    if not n:
        r["status"] = "ghost" if r.get("ghost") else "none"
    elif w and n == w:
        r["status"] = "exact"
    elif w and abs(n - w) <= max(1, round(w * 0.1)):
        r["status"] = "near"
    else:
        r["status"] = "diff"


allg, allo = [], []
for ri, r in enumerate(rows):
    for bi, b in enumerate(r["buildings"]):
        allg.append(shape(b["geom"]).buffer(0)); allo.append((ri, bi))
atree = STRtree(allg)
remove = set(); moved = 0
for a, g in enumerate(allg):
    for bidx in atree.query(g):
        bidx = int(bidx)
        if bidx <= a:
            continue
        (ra, ba), (rb, bb) = allo[a], allo[bidx]
        if ra == rb or (ra, ba) in remove or (rb, bb) in remove:
            continue
        ka, kb = tuple(rows[ra]["key"]), tuple(rows[rb]["key"])
        if same_family(ka, kb) or g.intersection(allg[bidx]).area <= 0.5 * min(g.area, allg[bidx].area):
            continue
        ds = bdate_at(g)
        ma, mb = mdate(ka) in ds, mdate(kb) in ds
        if ma and not mb:
            remove.add((rb, bb))
        elif mb and not ma:
            remove.add((ra, ba))
        else:
            la, lb = coords[ka], coords[kb]
            remove.add((rb, bb) if dist_m(g.centroid, *la) <= dist_m(g.centroid, *lb) else (ra, ba))
        moved += 1
for ri, r in enumerate(rows):
    if any((ri, bi) in remove for bi in range(len(r["buildings"]))):
        r["buildings"] = [b for bi, b in enumerate(r["buildings"]) if (ri, bi) not in remove]
        restatus(r)
report = collections.Counter(r["status"] for r in rows)
detail = [(r["status"], tuple(r["key"]), r["want"], r["n"], r["labeled"], r["spbd_method"][:25], r["bldg_how"], r["bldg_n"]) for r in rows]
print("최종 정리로 옮긴 겹침 건물", moved)

with open(f"{V}/complex_buildings_v5.jsonl", "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
json.dump({"counts": dict(report), "rows": [list(map(str, d)) for d in detail if d[0] != "exact"]}, open(f"{V}/match_v5_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(dict(report))
# 이전(v4) 대비
prev = collections.Counter()
for k in coords:
    if k not in M:
        continue
    srow = S.get(k); w = want(k)
    if not srow or srow["method"] == "unmatched":
        prev["none"] += 1; continue
    n = sum(1 for b in srow["buildings"] if (b.get("residential") or residential(b)))
    prev["exact" if n == w else "near" if abs(n - w) <= max(1, round(w * 0.1)) else "diff"] += 1
print("v4(S만):", dict(prev))

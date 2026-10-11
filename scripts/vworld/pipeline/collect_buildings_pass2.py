"""2차 보완: (1) 주거동이 마스터 동수의 70% 미만인 단지는 반경 500m에서 같은/비슷한 건물명 동을 더한다.
(2) 이름으로 찾은 단지는 엄격한 기준(유사도 0.8+, 역·상가 이름 제외, 주거동 1개 이상)으로 다시 판정한다.
결과: complex_buildings_v2.jsonl (method 에 보완 내역 기록)."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, re, sys, time
from difflib import SequenceMatcher
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_buildings as C
from building_match_report import residential

sys.stdout.reconfigure(encoding="utf-8")
ROOT = R
SRC = f"{ROOT}/data/derived/vworld/complex_buildings.jsonl"
DST = f"{ROOT}/data/derived/vworld/complex_buildings_v2.jsonl"
BAD_NAME = re.compile(r"역$|상가|빌딩|오피스텔|학교|센터$|교회|병원")
master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r for r in csv.DictReader(open(f"{ROOT}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
coords = {(r["name"], r["gu"], r["dong"]): (float(r["lat"]), float(r["lng"])) for r in csv.DictReader(open(f"{ROOT}/data/baseline/park_baseline.csv", encoding="utf-8-sig"))}
sim = lambda a, b: SequenceMatcher(None, C.norm(a), C.norm(b)).ratio()

out = open(DST, "w", encoding="utf-8")
changed = {"보완": 0, "이름재판정_유지": 0, "이름재판정_실패": 0}
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line); key = tuple(r["key"]); lat, lng = coords[key]
    want = int(float(master.get(key, {}).get("k-전체동수") or 0) or 0)
    res = [b for b in r["buildings"] if residential(b)]
    if r["method"].startswith("name") or r["method"] == "unmatched":
        cand = [C.slim(f) for f in C.features({"geomFilter": C.box(lat, lng, 500)})]
        groups = {}
        for b in cand:
            if b["name"] and not BAD_NAME.search(b["name"]):
                groups.setdefault(b["name"], []).append(b)
        scored = sorted(((sim(nm, key[0]), nm) for nm in groups), reverse=True)
        pick = [nm for s, nm in scored if s >= 0.8 and any(residential(b) for b in groups[nm])][:1]
        if pick:
            r["buildings"] = [b for nm in pick for b in groups[nm]]
            r["method"] = "name2~" + "/".join(pick)[:60]; changed["이름재판정_유지"] += 1
        else:
            r["buildings"] = []; r["method"] = "unmatched"; changed["이름재판정_실패"] += 1
        time.sleep(0.05)
    elif want and len(res) < 0.7 * want:
        names = {b["name"] for b in r["buildings"] if b["name"]}
        cand = [C.slim(f) for f in C.features({"geomFilter": C.box(lat, lng, 500)})]
        have = {b["bd_mgt_sn"] for b in r["buildings"]}
        import math
        def cdist(b):
            ring = b["geom"]["coordinates"][0] if b["geom"]["type"] == "Polygon" else b["geom"]["coordinates"][0][0]
            x = sum(p[0] for p in ring) / len(ring); y = sum(p[1] for p in ring) / len(ring)
            return math.hypot((y - lat) * 111000, (x - lng) * 88400)
        road = (master.get(key, {}).get("주소(도로명)") or "").strip()
        pool = sorted((b for b in cand if b["bd_mgt_sn"] not in have and not BAD_NAME.search(b["name"] or "")
                       and residential(b) and cdist(b) <= 350
                       and ((b["name"] and (b["name"] in names or sim(b["name"], key[0]) >= 0.85))
                            or (not b["name"] and road and b["rd"] == road))), key=cdist)
        add = pool[:max(0, want - len(res))]
        if add:
            r["buildings"] += add; r["method"] += f"+near{len(add)}"; changed["보완"] += 1
        time.sleep(0.05)
    for b in r["buildings"]:
        b["residential"] = residential(b)
    out.write(json.dumps(r, ensure_ascii=False) + "\n")
out.close()
print(changed)

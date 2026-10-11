"""동별 건물 수집 결과 점검: 주거동 분류 → 마스터 '전체동수'와 비교."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
ROOT = R
NON_RES = re.compile(r"상가|관리|경로|노인|어린이집|유치원|주민|커뮤니티|근린|생활지원|보육|복지|체육|독서|도서|경비|기계|전기|변전|주차|펌프|문고|교회|판매|부대|공용|창고|쓰레기|분리|놀이|정자|부속|화장실|변소|휴게|초소|수위|게이트|사무")


def residential(b):
    d = (b["dong"] or "").strip()
    if NON_RES.search(d):
        return False
    if re.search(r"\d+\s*동", d) or re.fullmatch(r"제?\s*\d+", d) or re.fullmatch(r"[A-Za-z가-하]\s*동|에이동|비동|씨동|디동", d):
        return True
    if d == "":
        nm = b.get("name") or ""
        if re.search(r"\d+\s*동$", nm) and not NON_RES.search(nm):
            return True
        try:
            return int(b.get("floors") or 0) >= 4
        except ValueError:
            return False
    return False


def classify(rows):
    for r in rows:
        r["res"] = [b for b in r["buildings"] if residential(b)]
    return rows


if __name__ == "__main__":
    master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r for r in csv.DictReader(open(f"{ROOT}/data/apartment/seoul_apartments.csv", encoding="cp949"))}
    rows = classify([json.loads(l) for l in open(f"{ROOT}/data/derived/vworld/complex_buildings.jsonl", encoding="utf-8")])
    buckets = collections.Counter(); diffs = []
    for r in rows:
        k = tuple(r["key"]); want = int(float(master.get(k, {}).get("k-전체동수") or 0) or 0); got = len(r["res"])
        if r["method"] == "unmatched":
            buckets["매칭 실패"] += 1; continue
        if want == 0:
            buckets["마스터 동수 없음"] += 1
        elif got == want:
            buckets["동수 일치"] += 1
        elif abs(got - want) <= max(1, round(want * 0.1)):
            buckets["거의 일치(±10%)"] += 1
        else:
            buckets["차이 큼"] += 1; diffs.append((k[0], k[1], want, got, r["method"][:18], len(r["buildings"])))
    print(dict(buckets))
    hh = {k: int(float(m.get("k-전체세대수") or 0) or 0) for k, m in master.items()}
    big = [r for r in rows if hh.get(tuple(r["key"]), 0) >= 1000]
    print("1,000세대 이상", len(big), "중 동수 일치/거의", sum(1 for r in big if abs(len(r["res"]) - int(float(master[tuple(r['key'])].get('k-전체동수') or 0) or 0)) <= max(1, round(int(float(master[tuple(r['key'])].get('k-전체동수') or 0) or 0) * 0.1))))
    print("\n매칭 실패:", [r["key"][0] + "(" + r["key"][1] + ")" for r in rows if r["method"] == "unmatched"])
    print("\n차이 큰 예(이름, 구, 마스터 동수, 주거동 수, 방법, 전체건물):")
    for d in sorted(diffs, key=lambda x: -abs(x[2] - x[3]))[:25]:
        print("  ", d)
    print("\n이름으로 찾은 단지:", [(r["key"][0], r["method"]) for r in rows if r["method"].startswith("name")][:44])

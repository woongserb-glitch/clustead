"""단지별 마지막 실거래(매매·전월세) 계약일 — 철거·재건축 판정 증거. 매핑 파일로 거래 → 마스터 단지 연결."""
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import ENV, R, REPO, V  # noqa: E402,F401
import csv, json, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10**9)
ROOT = R
sys.path.insert(0, ROOT)
from services.transaction_service import normalize_address, normalize_dong, normalize_name

mp = defaultdict(set)
for r in csv.DictReader(open(f"{ROOT}/data/transactions/apartment_transaction_mapping.csv", encoding="utf-8-sig")):
    ident = (r["livefit_name"], r["gu"], r["dong"])
    mp[(r["gu"], normalize_dong(r["dong"]), normalize_name(r["transaction_apt_name"]), normalize_address(r["transaction_road_address"]))].add(ident)
last = defaultdict(lambda: {"last": "", "n_2025plus": 0, "first": "9999"})
for r in csv.DictReader(open(f"{ROOT}/data/transactions/transaction_master.csv", encoding="utf-8-sig")):
    k = (r.get("gu"), normalize_dong(r.get("dong")), normalize_name(r.get("apartment_name")), normalize_address(r.get("road_address")))
    d = (r.get("contract_date") or "")[:10]
    for ident in mp.get(k, ()):
        e = last[ident]
        if d > e["last"]:
            e["last"] = d
        if d and d < e["first"]:
            e["first"] = d
        if d >= "2025-01-01":
            e["n_2025plus"] += 1
out = {"|".join(k): v for k, v in last.items()}
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else f"{V}/last_trade.json", "w", encoding="utf-8"), ensure_ascii=False)
print(len(out))

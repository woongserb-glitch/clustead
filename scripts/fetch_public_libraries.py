"""(월간 갱신) 서울시 공공도서관 → data/culture/public_libraries.csv

원천: 서울 열린데이터광장 '서울시 공공도서관 현황정보'(SeoulPublicLibraryInfo, 216곳 · 2026-10).
작은도서관(브이월드 LT_P_SMALLLIBRARY)은 scripts/vworld/collect_layers.py 가 받는다.
키: 환경변수 SEOUL_OPEN_DATA_KEY → 저장소 .env. 0곳이면 기존 파일을 지킨다.
주의: 원천 칸 이름이 XCNTS=위도, YDNTS=경도로 뒤바뀌어 있다(값으로 판정해 맞춘다).
"""
import csv
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "culture" / "public_libraries.csv"
FIELDS = ["name", "gu", "address", "lat", "lng", "op_time", "closed", "homepage", "tel"]


def seoul_key():
    if os.environ.get("SEOUL_OPEN_DATA_KEY"):
        return os.environ["SEOUL_OPEN_DATA_KEY"]
    from dotenv import dotenv_values
    return dotenv_values(ROOT / ".env").get("SEOUL_OPEN_DATA_KEY", "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    key = seoul_key()
    if not key:
        raise SystemExit("SEOUL_OPEN_DATA_KEY 가 없다(환경변수 또는 저장소 .env)")
    rows, start = [], 1
    while True:
        url = f"http://openapi.seoul.go.kr:8088/{key}/json/SeoulPublicLibraryInfo/{start}/{start + 999}/"
        body = requests.get(url, timeout=30).json().get("SeoulPublicLibraryInfo") or {}
        if (body.get("RESULT") or {}).get("CODE") != "INFO-000":
            raise SystemExit(f"API 응답 이상: {(body.get('RESULT') or body)}")
        batch = body.get("row") or []
        rows += batch
        if len(rows) >= int(body.get("list_total_count", 0)) or not batch:
            break
        start += 1000

    out = []
    for r in rows:
        try:
            a, b = float(r.get("XCNTS")), float(r.get("YDNTS"))
        except (TypeError, ValueError):
            continue
        lat, lng = (a, b) if a < b else (b, a)   # 서울은 위도 37·경도 127 → 작은 쪽이 위도
        if not (37.3 < lat < 37.8 and 126.7 < lng < 127.3):
            continue
        out.append({
            "name": (r.get("LBRRY_NAME") or "").strip(),
            "gu": (r.get("CODE_VALUE") or "").strip(),
            "address": (r.get("ADRES") or "").strip(),
            "lat": round(lat, 7), "lng": round(lng, 7),
            "op_time": (r.get("OP_TIME") or "").strip(),
            "closed": (r.get("FDRM_CLOSE_DATE") or "").strip(),
            "homepage": (r.get("HMPG_URL") or "").strip(),
            "tel": (r.get("TEL_NO") or "").strip(),
        })
    if not out:
        print("[SKIP] 0곳 — 기존 파일 유지")
        return
    old = sum(1 for _ in csv.DictReader(OUT.open(encoding="utf-8-sig"))) if OUT.exists() else None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".csv.new")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(out, key=lambda x: (x["gu"], x["name"])))
    tmp.replace(OUT)
    print(f"[OK] 공공도서관 {old if old is not None else '-'} → {len(out)}곳 ({len(rows) - len(out)}곳 좌표 없음·서울 밖 제외)")


if __name__ == "__main__":
    main()

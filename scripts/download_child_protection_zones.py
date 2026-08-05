"""전국어린이보호구역표준데이터 수집 (공공데이터포털 표준데이터 15012891).

CCTV 원본(national_cctv.csv)의 `설치목적구분`은 자치구별 등록 관행 차이가 커서
'어린이보호' 분류를 구간 비교에 쓸 수 없다(어린이보호 0건인 구가 6곳).
이 표준데이터는 지정 구역을 좌표로 직접 제공하고 `cctvYn`/`cctvNumber`까지
담고 있어, 분류에 의존하지 않고 위치로 판정할 수 있다.

선행 조건 (1회, 사람이 해야 함):
    공공데이터포털 로그인 → https://www.data.go.kr/data/15012891/standard.do
    → '활용신청'(자동승인) → 승인 후 기존 PUBLIC_DATA_SERVICE_KEY 그대로 사용

    신청 전에는 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 돌아온다.

사용:
    python scripts/download_child_protection_zones.py           # 서울만
    python scripts/download_child_protection_zones.py --all     # 전국
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from services.transaction_service import get_public_data_service_key


API_URL = "https://api.data.go.kr/openapi/tn_pubr_public_child_prtc_zn_api"
OUTPUT_DIR = "data/child_zone"
OUTPUT_PATH = f"{OUTPUT_DIR}/child_protection_zone.csv"
PAGE_SIZE = 1000
MAX_RETRY = 3


def fetch_page(key, page_no):
    url = API_URL + "?" + urllib.parse.urlencode({
        "serviceKey": key,
        "pageNo": page_no,
        "numOfRows": PAGE_SIZE,
        "type": "json",
    })

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "clustead/1.0"},
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_page_with_retry(key, page_no):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return fetch_page(key, page_no)

        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")

            if "SERVICE_KEY_IS_NOT_REGISTERED" in body:
                print(
                    "[ERROR] 이 서비스에 키가 등록되어 있지 않습니다.\n"
                    "        https://www.data.go.kr/data/15012891/standard.do 에서\n"
                    "        '활용신청'(자동승인)을 먼저 진행하세요."
                )
                raise SystemExit(1)

            if attempt == MAX_RETRY:
                raise

            print(f"[RETRY] page={page_no} HTTP {error.code} ({attempt}/{MAX_RETRY})")
            time.sleep(2 * attempt)

        except Exception as error:
            if attempt == MAX_RETRY:
                raise

            print(f"[RETRY] page={page_no} {type(error).__name__} ({attempt}/{MAX_RETRY})")
            time.sleep(2 * attempt)


def extract_body(payload):
    """이 API는 실거래가 API와 달리 response 래퍼가 없고
    items 가 {"item": [...]} 형태다."""
    return payload.get("body") or payload.get("response", {}).get("body", {})


def extract_items(body):
    items = body.get("items")

    if isinstance(items, dict):
        items = items.get("item")

    if items is None:
        return []

    if isinstance(items, dict):
        return [items]

    return items


def is_seoul(row):
    address = (row.get("rdnmadr") or "") + (row.get("lnmadr") or "")
    return "서울특별시" in address


def main():
    seoul_only = "--all" not in sys.argv

    key = get_public_data_service_key()

    if not key:
        print("[ERROR] PUBLIC_DATA_SERVICE_KEY 가 없습니다 (.env 확인)")
        raise SystemExit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    collected = []
    page_no = 1
    total_count = None

    while True:
        payload = fetch_page_with_retry(key, page_no)
        body = extract_body(payload)

        if total_count is None:
            total_count = int(body.get("totalCount") or 0)
            print(f"[INFO] 전국 총 {total_count:,}건")

        items = extract_items(body)

        if not items:
            break

        kept = [row for row in items if not seoul_only or is_seoul(row)]
        collected.extend(kept)

        print(
            f"[{page_no}] {len(items)}건 수신 "
            f"(누적 {len(collected):,}건{'/서울' if seoul_only else ''})"
        )

        if page_no * PAGE_SIZE >= total_count:
            break

        page_no += 1
        time.sleep(0.2)

    if not collected:
        print("[WARN] 수집된 행이 없습니다.")
        raise SystemExit(1)

    fieldnames = list(collected[0].keys())

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for row in collected:
            writer.writerow(row)

    print(f"[DONE] {OUTPUT_PATH} — {len(collected):,}행, 컬럼 {len(fieldnames)}개")
    print("[NEXT] 좌표·CCTV 컬럼 검증 후 baseline 빌더 작성")


if __name__ == "__main__":
    main()

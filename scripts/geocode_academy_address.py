import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_PATH = BASE_DIR / "data" / "academy" / "academy_seoul.csv"
OUTPUT_PATH = BASE_DIR / "data" / "academy" / "academy_geocoded.csv"
FAILED_PATH = BASE_DIR / "data" / "academy" / "academy_geocode_failed.csv"

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
REQUEST_DELAY_SEC = 0.12
SAVE_EVERY = 20


def read_csv_with_fallback(path):
    for enc in ["utf-8-sig", "cp949", "euc-kr", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    raise RuntimeError(f"CSV 인코딩을 읽을 수 없습니다: {path}")


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ["nan", "none", "null"]:
        return ""
    return text


def get_kakao_rest_key():
    load_dotenv(BASE_DIR / ".env")
    key = os.getenv("KAKAO_REST_API_KEY") or os.getenv("KAKAO_REST_KEY") or os.getenv("KAKAO_API_KEY")
    if not key:
        raise RuntimeError(
            ".env에 KAKAO_REST_API_KEY=발급받은_REST_API_KEY 를 추가해 주세요. "
            "JavaScript 키가 아니라 REST API 키가 필요합니다."
        )
    return key


def geocode_address(address, api_key):
    if not address:
        return None

    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": address}

    response = requests.get(KAKAO_ADDRESS_URL, headers=headers, params=params, timeout=8)
    response.raise_for_status()

    payload = response.json()
    documents = payload.get("documents", [])
    if not documents:
        return None

    doc = documents[0]
    return {
        "lat": float(doc.get("y")),
        "lng": float(doc.get("x")),
        "matched_address": doc.get("address_name", ""),
    }


def main():
    api_key = get_kakao_rest_key()
    source_df = read_csv_with_fallback(INPUT_PATH)

    if "도로명주소" not in source_df.columns:
        raise KeyError("academy_seoul.csv에 '도로명주소' 컬럼이 없습니다.")

    done_map = {}
    if OUTPUT_PATH.exists():
        previous_df = read_csv_with_fallback(OUTPUT_PATH)
        if "학원지정번호" in previous_df.columns:
            for _, row in previous_df.iterrows():
                academy_id = clean_text(row.get("학원지정번호"))
                lat = clean_text(row.get("lat"))
                lng = clean_text(row.get("lng"))
                if academy_id and lat and lng:
                    done_map[academy_id] = row.to_dict()

    output_rows = []
    failed_rows = []

    total = len(source_df)

    for idx, row in source_df.iterrows():
        print(f"[GEOCODING] {idx + 1}/{total}", flush=True)
        row_dict = row.to_dict()
        academy_id = clean_text(row.get("학원지정번호"))

        if academy_id in done_map:
            output_rows.append(done_map[academy_id])
            continue

        road_address = clean_text(row.get("도로명주소"))
        detail_address = clean_text(row.get("도로명상세주소"))

        result = None
        query_used = road_address

        try:
            result = geocode_address(road_address, api_key)
            time.sleep(REQUEST_DELAY_SEC)

            if result is None and detail_address:
                detail_head = detail_address.split(",")[0].replace("?", " ").strip()
                if detail_head:
                    query_used = f"{road_address} {detail_head}".strip()
                    result = geocode_address(query_used, api_key)
                    time.sleep(REQUEST_DELAY_SEC)

        except Exception as exc:
            failed = dict(row_dict)
            failed["geocode_query"] = query_used
            failed["geocode_error"] = str(exc)
            failed_rows.append(failed)
            continue

        if result is None:
            failed = dict(row_dict)
            failed["geocode_query"] = query_used
            failed["geocode_error"] = "NO_RESULT"
            failed_rows.append(failed)
            continue

        enriched = dict(row_dict)
        enriched["lat"] = result["lat"]
        enriched["lng"] = result["lng"]
        enriched["geocode_query"] = query_used
        enriched["matched_address"] = result["matched_address"]
        output_rows.append(enriched)

        if len(output_rows) % SAVE_EVERY == 0:
            pd.DataFrame(output_rows).to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
            if failed_rows:
                pd.DataFrame(failed_rows).to_csv(FAILED_PATH, index=False, encoding="utf-8-sig")
            print(f"[ACADEMY GEOCODE] {idx + 1}/{total} 처리, 성공 {len(output_rows)}, 실패 {len(failed_rows)}")

    pd.DataFrame(output_rows).to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    if failed_rows:
        pd.DataFrame(failed_rows).to_csv(FAILED_PATH, index=False, encoding="utf-8-sig")

    print(f"[ACADEMY GEOCODE] 저장 완료: {OUTPUT_PATH}")
    print(f"[ACADEMY GEOCODE] 성공 {len(output_rows)}개 / 실패 {len(failed_rows)}개")
    if failed_rows:
        print(f"[ACADEMY GEOCODE] 실패 목록: {FAILED_PATH}")


if __name__ == "__main__":
    main()

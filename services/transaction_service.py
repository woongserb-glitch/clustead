import csv
import functools
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import requests


SALE_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
RENT_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
CACHE_DIR = Path("data/cache/transactions")
TRANSACTION_MASTER_PATH = Path("data/transactions/transaction_master.csv")
TRANSACTION_MAPPING_PATH = Path("data/transactions/apartment_transaction_mapping.csv")
TRANSACTION_SUMMARY_PATH = Path("data/baseline/transaction_summary.csv")
TRANSACTION_DETAIL_INDEX_PATH = Path("data/transactions/transaction_detail_index.json")
TRANSACTION_DETAIL_DIR = Path("data/transactions/detail_index")
TRANSACTION_DETAIL_MANIFEST_PATH = TRANSACTION_DETAIL_DIR / "manifest.json"

_BATCH_MAPPING_CACHE = None
_BATCH_SUMMARY_CACHE = None
_BATCH_DETAIL_CACHE = None
_BATCH_DETAIL_MANIFEST_CACHE = None

SEOUL_LAWD_CODES = {
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740",
}


def get_public_data_service_key():
    for key in (
        "PUBLIC_DATA_SERVICE_KEY",
        "PUBLIC_DATA_API_KEY",
        "DATA_GO_KR_SERVICE_KEY",
    ):
        value = os.getenv(key)
        if value:
            return unquote(value.strip())

    return ""


def get_recent_deal_months(today=None, count=3):
    current = today or date.today()
    year = current.year
    month = current.month
    months = []

    for _ in range(count):
        months.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year -= 1
            month = 12

    return months


def normalize_name(value):
    text = str(value or "").lower()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    text = re.sub(r"(아파트|apt)$", "", text)
    return text


def normalize_dong(value):
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", str(value or "")).strip()


def normalize_address(value):
    text = str(value or "").lower()
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def read_batch_csv(path):
    if not path.exists():
        return []

    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    except Exception as exc:
        print(f"[TRANSACTION] batch csv read failed: {path} {exc}")
        return []


def _master_row_to_dict(header, row):
    """csv.DictReader 와 같은 모양의 dict — 짧은 행은 None 으로 채운다."""
    item = dict(zip(header, row))
    if len(row) < len(header):
        for name in header[len(row):]:
            item[name] = None
    return item


@functools.lru_cache(maxsize=32)
def find_batch_master_rows(gu, dong, tx_name, tx_road):
    """마스터 CSV 를 흘려 읽어 **해당 단지 거래 행만** 모은다.

    예전에는 마스터 495,366행을 통째로 dict 리스트로 올린 뒤((gu,dong,이름,도로명)
    → 행목록) 전역 인덱스를 만들었다. 그 인덱스의 힙 사용량이 **1.23GB**인데
    앱 컨테이너 상한은 768MB 다. 즉 이 경로를 밟은 워커는 cgroup OOM 으로
    SIGKILL 됐다 — gunicorn 로그의 "Worker was sent SIGKILL! Perhaps out of
    memory?" 가 그것이다. 컨테이너 자체는 살아 있어 `.State.OOMKilled` 는 false
    라 원인이 오래 가려져 있었다.

    실제로 이 경로가 필요한 단지는 **2,861개 중 6개**(마곡 5개 + 광화문스페이스본)
    뿐이다. 전역 인덱스를 만들 이유가 없어, 요청된 키에 맞는 행만 모은다.
    메모리는 매칭 행 수에 비례하고(수십~수백 행), 스캔은 lru_cache 로 단지당
    한 번만 돈다.

    속도: 구(gu)가 다르면 정규화(정규식 4회)를 아예 건너뛴다. 49만 행 중 대부분이
    문자열 비교 한 번으로 걸러져, DictReader 로 전수 파싱하던 것보다 빠르다.

    반환 순서는 옛 인덱스 조회와 같다 — 도로명까지 맞는 그룹이 있으면 그것,
    없으면 (구·동·이름)이 같은 그룹들을 첫 등장 순서로 이어붙인다.
    """
    path = TRANSACTION_MASTER_PATH
    if not path.exists():
        return []

    groups = {}

    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)

            try:
                header = next(reader)
            except StopIteration:
                return []

            col = {name: i for i, name in enumerate(header)}
            i_gu = col.get("gu")
            i_dong = col.get("dong")
            i_name = col.get("apt_name_raw")
            i_road = col.get("road_address")

            if i_gu is None or i_name is None:
                return []

            for row in reader:
                try:
                    if str(row[i_gu] or "").strip() != gu:
                        continue
                    if normalize_dong(row[i_dong] if i_dong is not None else "") != dong:
                        continue
                    if normalize_name(row[i_name]) != tx_name:
                        continue
                    road = normalize_address(row[i_road] if i_road is not None else "")
                except IndexError:
                    continue

                groups.setdefault(road, []).append(_master_row_to_dict(header, row))

    except Exception as exc:
        print(f"[TRANSACTION] master scan failed: {path} {exc}")
        return []

    exact = groups.get(tx_road)
    if exact:
        return exact

    rows = []
    for items in groups.values():
        rows.extend(items)
    return rows


def apartment_identity(name, gu, dong):
    """실거래를 붙일 때 쓰는 단지 식별키.

    이름만으로는 유일하지 않다 — 같은 이름이 2곳 이상에 쓰이는 단지가 7개
    이름·15곳 있다(신동아아파트 3곳, 우리유앤미 2곳 …). 이름만 키로 쓰면
    나중 행이 앞 행을 덮어, 동작구 흑석동 우리유앤미 화면에 구로구 단지의
    거래금액이 떴다. 빌더(build_transaction_summary.py)와 같은 형식이어야 한다.
    """
    return "{}|{}|{}".format(
        str(name or "").strip(), str(gu or "").strip(), str(dong or "").strip()
    )


def _index_by_identity(rows, name_keys, gu_key="gu", dong_key="dong"):
    """식별키로 색인하고, 이름만으로 찾는 옛 경로를 위해 이름 키도 남긴다.

    이름 키는 setdefault 라 첫 행이 이긴다 — 덮어쓰기로 값이 뒤바뀌는 일은
    없앤다. 동명 단지는 반드시 식별키로 조회해야 한다.
    """
    index = {}
    for row in rows:
        name = ""
        for key in name_keys:
            name = str(row.get(key) or "").strip()
            if name:
                break
        if not name:
            continue
        index[apartment_identity(name, row.get(gu_key), row.get(dong_key))] = row
        index.setdefault(name, row)
    return index


def load_batch_mapping():
    global _BATCH_MAPPING_CACHE
    if _BATCH_MAPPING_CACHE is None:
        _BATCH_MAPPING_CACHE = _index_by_identity(
            read_batch_csv(TRANSACTION_MAPPING_PATH), ("clustead_name", "livefit_name")
        )
    return _BATCH_MAPPING_CACHE


def load_batch_summary():
    global _BATCH_SUMMARY_CACHE
    if _BATCH_SUMMARY_CACHE is None:
        _BATCH_SUMMARY_CACHE = _index_by_identity(
            read_batch_csv(TRANSACTION_SUMMARY_PATH), ("name",)
        )
    return _BATCH_SUMMARY_CACHE


def load_batch_detail_index():
    global _BATCH_DETAIL_CACHE
    if _BATCH_DETAIL_CACHE is not None:
        return _BATCH_DETAIL_CACHE
    if not TRANSACTION_DETAIL_INDEX_PATH.exists():
        _BATCH_DETAIL_CACHE = {}
        return _BATCH_DETAIL_CACHE
    try:
        _BATCH_DETAIL_CACHE = json.loads(TRANSACTION_DETAIL_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[TRANSACTION] detail index read failed: {TRANSACTION_DETAIL_INDEX_PATH} {exc}")
        _BATCH_DETAIL_CACHE = {}
    return _BATCH_DETAIL_CACHE


def load_batch_detail_manifest():
    global _BATCH_DETAIL_MANIFEST_CACHE
    if _BATCH_DETAIL_MANIFEST_CACHE is not None:
        return _BATCH_DETAIL_MANIFEST_CACHE
    if not TRANSACTION_DETAIL_MANIFEST_PATH.exists():
        _BATCH_DETAIL_MANIFEST_CACHE = {}
        return _BATCH_DETAIL_MANIFEST_CACHE
    try:
        _BATCH_DETAIL_MANIFEST_CACHE = json.loads(TRANSACTION_DETAIL_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[TRANSACTION] detail manifest read failed: {TRANSACTION_DETAIL_MANIFEST_PATH} {exc}")
        _BATCH_DETAIL_MANIFEST_CACHE = {}
    return _BATCH_DETAIL_MANIFEST_CACHE


def load_batch_detail_for_apartment(apartment_name, gu=None, dong=None):
    manifest = load_batch_detail_manifest()
    detail_filename = manifest.get(apartment_identity(apartment_name, gu, dong))
    if detail_filename is None:
        # 아직 옛 형식(이름 키)으로 만들어진 매니페스트도 읽을 수 있게 둔다.
        detail_filename = manifest.get(apartment_name)
    if detail_filename:
        path = TRANSACTION_DETAIL_DIR / detail_filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[TRANSACTION] detail file read failed: {path} {exc}")

    return load_batch_detail_index().get(apartment_name)


def is_trusted_batch_mapping(row):
    if not row:
        return False
    if str(row.get("manual_override") or "").strip().upper() == "Y":
        return True
    if str(row.get("verified") or "").strip().upper() == "Y":
        return True
    try:
        return float(row.get("match_confidence") or 0) >= 0.9
    except Exception:
        return False


def split_deal_date(value):
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return "", "", ""
    return match.group(1), match.group(2), match.group(3)


def batch_item_from_master(row, trade_type):
    year, month, day = split_deal_date(row.get("deal_date"))
    amount_field = "deal_amount" if trade_type == "sale" else "deposit_amount"
    amount = parse_amount_to_manwon(row.get(amount_field))

    return {
        "apt_name": row.get("apt_name_raw"),
        "dong": row.get("dong"),
        "area": row.get("area_m2"),
        "amount": amount,
        "floor": row.get("floor"),
        "deal_year": year,
        "deal_month": month,
        "deal_day": day,
        "monthly_rent": row.get("monthly_rent"),
        "deal_type": row.get("deal_type"),
    }


def get_batch_transaction_summary(apartment):
    # 이름만으로 찾으면 동명 단지끼리 서로의 거래를 가져간다. 단지 화면이 쓰는
    # 뷰는 구를 district 로 들고 있고, 원본 dict 는 gu 로 들고 있다.
    apartment_name = str(apartment.get("name") or "").strip()
    apartment_gu = str(apartment.get("district") or apartment.get("gu") or "").strip()
    apartment_dong = str(apartment.get("dong") or "").strip()
    identity = apartment_identity(apartment_name, apartment_gu, apartment_dong)

    mapping_index = load_batch_mapping()
    mapping = mapping_index.get(identity) or mapping_index.get(apartment_name)
    if not is_trusted_batch_mapping(mapping):
        return None

    summary_index = load_batch_summary()
    batch_metrics = summary_index.get(identity) or summary_index.get(apartment_name) or {}
    detail_payload = load_batch_detail_for_apartment(apartment_name, apartment_gu, apartment_dong)
    if detail_payload and detail_payload.get("area_tabs"):
        # 샤드에는 기간별 건수가 없다(경계가 "오늘" 기준이라 미리 넣으면 낡는다).
        # 저장된 행과 탭의 실제 합계로 요청 시점에 만든다.
        transactions_by_area = detail_payload.get("transactions_by_area", {})
        for tab in detail_payload.get("area_tabs", []):
            tab["period_counts"] = build_period_counts(
                transactions_by_area.get(tab.get("area_label"), []),
                {
                    "sale": tab.get("sale_count") or 0,
                    "jeonse": tab.get("jeonse_count") or 0,
                    "monthly": tab.get("monthly_count") or 0,
                },
            )
        batch_metrics_display = build_batch_metric_display(batch_metrics)
        insight_badges = build_transaction_insight_badges(batch_metrics, detail_payload.get("area_tabs", []))
        return {
            "enabled": True,
            "source_label": "국토교통부 실거래가 공개시스템 자료 기준",
            "months": [],
            "areas": [],
            "area_tabs": detail_payload.get("area_tabs", []),
            "transactions_by_area": detail_payload.get("transactions_by_area", {}),
            "sale_count": sum(tab.get("sale_count", 0) or 0 for tab in detail_payload.get("area_tabs", [])),
            "jeonse_count": sum(tab.get("jeonse_count", 0) or 0 for tab in detail_payload.get("area_tabs", [])),
            "has_data": True,
            "data_layer": "molit_rt_xls",
            "batch_metrics": batch_metrics,
            "batch_metrics_display": batch_metrics_display,
            "insight_badges": insight_badges,
        }

    gu = str(apartment.get("district") or "").strip()
    dong = normalize_dong(apartment.get("dong"))
    tx_name = normalize_name(mapping.get("transaction_apt_name"))
    tx_road = normalize_address(mapping.get("transaction_road_address"))
    if not tx_name:
        return None

    rows = list(find_batch_master_rows(gu, dong, tx_name, tx_road))

    sale_items = []
    jeonse_items = []
    for row in rows:
        if row.get("transaction_type") == "trade":
            item = batch_item_from_master(row, "sale")
            if item.get("amount") is not None:
                sale_items.append(item)
        elif row.get("transaction_type") == "rent" and row.get("deal_type") in ("전세", "월세"):
            item = batch_item_from_master(row, "rent")
            if item.get("amount") is not None:
                jeonse_items.append(item)

    if not sale_items and not jeonse_items:
        return None

    area_summaries = build_area_summaries(sale_items, jeonse_items)
    area_tabs, transactions_by_area = build_transaction_lists(sale_items, jeonse_items)
    batch_metrics_display = build_batch_metric_display(batch_metrics)
    insight_badges = build_transaction_insight_badges(batch_metrics, area_tabs)
    months = sorted(
        {
            f"{item.get('deal_year')}{str(item.get('deal_month') or '').zfill(2)}"
            for item in sale_items + jeonse_items
            if item.get("deal_year") and item.get("deal_month")
        },
        reverse=True,
    )[:12]

    return {
        "enabled": True,
        "source_label": "국토교통부 실거래가 공개시스템 자료 기준",
        "months": months,
        "areas": area_summaries,
        "area_tabs": area_tabs,
        "transactions_by_area": transactions_by_area,
        "sale_count": len(sale_items),
        "jeonse_count": len(jeonse_items),
        "has_data": bool(area_tabs),
        "data_layer": "molit_rt_xls",
        "batch_metrics": batch_metrics,
        "batch_metrics_display": batch_metrics_display,
        "insight_badges": insight_badges,
    }


def get_text(item, *names):
    for name in names:
        node = item.find(name)
        if node is not None and node.text is not None:
            return node.text.strip()

    return ""


def parse_amount_to_manwon(value):
    text = str(value or "").replace(",", "").replace(" ", "")
    text = text.replace("만원", "")
    if not text:
        return None

    try:
        return int(float(text))
    except Exception:
        return None


def parse_float(value):
    try:
        return float(str(value or "").replace(",", "").strip())
    except Exception:
        return None


def parse_int(value):
    number = parse_float(value)
    if number is None:
        return None
    return int(round(number))


def format_price_manwon(value):
    if value is None:
        return ""

    value = int(round(value))
    if value >= 10000:
        return f"{value / 10000:.1f}억"

    return f"{value:,}만원"


def format_count(value):
    try:
        return f"{int(float(value or 0)):,}"
    except Exception:
        return "0"


def format_percent(value):
    number = parse_float(value)
    if number is None:
        return ""
    return f"{number:.1f}%"


def format_display_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("-", ".")


def format_rent_price(deposit, monthly_rent):
    monthly = parse_amount_to_manwon(monthly_rent)
    if monthly and monthly > 0:
        return f"보증금 {format_price_manwon(deposit)} / {monthly:,}만원"
    return format_price_manwon(deposit)


def format_area_label(value):
    area = parse_float(value)
    if area is None:
        return "면적 미상"

    return f"{round(area):.0f}㎡"


MIN_AREA_TAB_TRANSACTION_COUNT = 5
MIN_AREA_TAB_DOMINANCE_RATIO = 0.03
MAX_PRIMARY_AREA_TABS = 5


def split_area_labels(grouped):
    if not grouped:
        return [], []

    dominant_count = max(len(items) for items in grouped.values())
    sorted_labels = sorted(
        grouped,
        key=lambda label: (-len(grouped[label]), int(re.sub(r"\D", "", label) or "9999")),
    )
    primary = [
        label
        for label in sorted_labels
        if len(grouped[label]) >= MIN_AREA_TAB_TRANSACTION_COUNT
        and (not dominant_count or len(grouped[label]) / dominant_count >= MIN_AREA_TAB_DOMINANCE_RATIO)
    ][:MAX_PRIMARY_AREA_TABS]

    if not primary and sorted_labels:
        primary = [sorted_labels[0]]

    secondary = [label for label in sorted_labels if label not in primary]
    return primary, secondary


def make_cache_path(trade_type, lawd_cd, deal_ym):
    return CACHE_DIR / f"{trade_type}_{lawd_cd}_{deal_ym}.json"


def read_cache(path):
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list) and payload and "floor" not in payload[0]:
            return None

        return payload
    except Exception:
        return None


def write_cache(path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def sanitize_error_text(value):
    return re.sub(
        r"([?&](?:serviceKey|ServiceKey)=)[^&\s]+",
        r"\1***",
        str(value or ""),
    )


def parse_xml_items(text, trade_type):
    root = ElementTree.fromstring(text)
    items = []

    for item in root.findall(".//item"):
        if trade_type == "sale":
            amount = parse_amount_to_manwon(
                get_text(item, "거래금액", "dealAmount")
            )
        else:
            amount = parse_amount_to_manwon(
                get_text(item, "보증금액", "deposit")
            )

        parsed = {
            "apt_name": get_text(item, "아파트", "aptNm"),
            "dong": get_text(item, "법정동", "umdNm"),
            "area": get_text(item, "전용면적", "excluUseAr"),
            "amount": amount,
            "floor": get_text(item, "층", "floor"),
            "deal_year": get_text(item, "년", "dealYear"),
            "deal_month": get_text(item, "월", "dealMonth"),
            "deal_day": get_text(item, "일", "dealDay"),
            "monthly_rent": get_text(item, "월세금액", "monthlyRent"),
        }

        if parsed["apt_name"] and amount is not None:
            items.append(parsed)

    return items


def fetch_transactions(trade_type, lawd_cd, deal_ym, service_key):
    cache_path = make_cache_path(trade_type, lawd_cd, deal_ym)
    cached = read_cache(cache_path)
    if cached is not None:
        return cached

    url = SALE_API_URL if trade_type == "sale" else RENT_API_URL
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ym,
        "pageNo": "1",
        "numOfRows": "5000",
    }

    try:
        response = requests.get(url, params=params, timeout=8)
        if not response.ok:
            snippet = sanitize_error_text(response.text[:300])
            print(
                f"[TRANSACTION] {trade_type} {lawd_cd} {deal_ym} "
                f"failed: status={response.status_code} body={snippet}"
            )
            return []

        items = parse_xml_items(response.text, trade_type)
        write_cache(cache_path, items)
        return items
    except Exception as exc:
        print(
            f"[TRANSACTION] {trade_type} {lawd_cd} {deal_ym} "
            f"failed: {sanitize_error_text(exc)}"
        )
        return []


def is_jeonse(item):
    monthly_rent = str(item.get("monthly_rent") or "").strip()
    monthly_rent = monthly_rent.replace(",", "").replace(" ", "").replace("만원", "")
    return monthly_rent in ("", "0", "0.0")


def is_apartment_match(item, apartment):
    target_name = normalize_name(apartment.get("name"))
    item_name = normalize_name(item.get("apt_name"))

    if not target_name or not item_name:
        return False

    if target_name == item_name:
        return True

    target_dong = normalize_dong(apartment.get("dong"))
    item_dong = normalize_dong(item.get("dong"))
    same_dong = target_dong and item_dong and target_dong == item_dong

    if same_dong and len(target_name) >= 4 and len(item_name) >= 4:
        return target_name in item_name or item_name in target_name

    return False


def summarize_trade_items(items):
    grouped = {}

    for item in items:
        area_label = format_area_label(item.get("area"))
        grouped.setdefault(area_label, []).append(item)

    summary = {}
    for area_label, rows in grouped.items():
        prices = [row["amount"] for row in rows if row.get("amount") is not None]
        if not prices:
            continue

        latest = sorted(
            rows,
            key=lambda row: (
                str(row.get("deal_year") or ""),
                str(row.get("deal_month") or "").zfill(2),
                str(row.get("deal_day") or "").zfill(2),
            ),
            reverse=True,
        )[0]

        avg_price = sum(prices) / len(prices)
        summary[area_label] = {
            "count": len(prices),
            "latest_price": format_price_manwon(latest.get("amount")),
            "avg_price": format_price_manwon(avg_price),
            "range": f"{format_price_manwon(min(prices))} ~ {format_price_manwon(max(prices))}",
        }

    return summary


def build_area_summaries(sale_items, jeonse_items):
    sale_summary = summarize_trade_items(sale_items)
    jeonse_summary = summarize_trade_items(jeonse_items)
    area_labels = sorted(
        set(sale_summary.keys()) | set(jeonse_summary.keys()),
        key=lambda label: int(re.sub(r"\D", "", label) or "9999"),
    )

    return [
        {
            "area_label": area_label,
            "sale": sale_summary.get(area_label),
            "jeonse": jeonse_summary.get(area_label),
        }
        for area_label in area_labels
    ]


def format_deal_date(item):
    year = str(item.get("deal_year") or "").strip()
    month = str(item.get("deal_month") or "").strip().zfill(2)
    day = str(item.get("deal_day") or "").strip().zfill(2)

    if year and month and day:
        return f"{year}.{month}.{day}"

    return ""


def format_floor(value):
    text = str(value or "").strip()
    if not text:
        return ""

    return f"{text}층"


TRANSACTION_PANEL_ROW_CAP = 80
TRANSACTION_PERIOD_MONTHS = {"3m": 3, "6m": 6, "1y": 12, "2y": 24}


def transaction_period_threshold(months, today=None):
    """화면 JS 의 new Date(y, m - months, d) 와 같은 경계를 만든다.

    JS 는 존재하지 않는 날짜(2월 31일)를 다음 달로 굴린다. 파이썬은 예외를
    내므로, 그 달 1일에 (일 - 1) 을 더해 같은 결과를 얻는다. 서버가 센 건수와
    화면이 거른 행이 하루 차이로 어긋나면 "필터가 안 먹는다" 로 읽힌다.
    """
    today = today or date.today()
    year, month = today.year, today.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1) + timedelta(days=today.day - 1)


def parse_transaction_date(value):
    """화면에 쓰는 "YYYY.MM.DD" 를 date 로. 못 읽으면 None."""
    matched = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})$", str(value or ""))
    if not matched:
        return None
    return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))


def build_period_counts(rows, totals):
    """면적 탭 하나의 (거래유형 x 기간) 표시 건수를 문자열로 만든다.

    패널은 유형당 최근 80 건만 그린다(고덕 그라시움 60㎡ 전세는 355 건이다).
    그런데 헤더 건수를 그려진 행에서 세면 355 건짜리가 "전체 80건" 이 되어 바로
    위 요약줄과 어긋난다. "전체" 는 자르기 전 실제 건수를 그대로 쓴다.

    기간 필터는 남아 있는 행이 그 기간을 다 덮는지에 따라 갈린다. 가장 오래된
    보유 행이 경계보다 더 과거면 그 기간의 행은 전부 손에 있으므로 정확하다.
    아니면 잘려 나간 행이 그 기간에 더 있을 수 있어 "80+" 로 적는다 — 모르는
    수를 아는 척하지 않는다. 전체 칸의 2.4% 만 여기에 해당한다.

    미리 계산해 두지 않고 요청마다 세는 이유는 경계가 "오늘" 기준이라서다.
    샤드에 넣어 두면 날이 갈수록 틀린 값이 된다.
    """
    counts = {}
    for filter_type in ("sale", "jeonse", "monthly"):
        typed = [row for row in rows if row.get("filter_type") == filter_type]
        true_total = totals.get(filter_type) or 0
        truncated = len(typed) < true_total
        oldest = min((parse_transaction_date(row.get("date")) for row in typed), default=None)

        bucket = {"all": format_count(true_total)}
        for period, months in TRANSACTION_PERIOD_MONTHS.items():
            threshold = transaction_period_threshold(months)
            found = sum(
                1 for row in typed
                if (parse_transaction_date(row.get("date")) or threshold) >= threshold
            )
            exact = not truncated or (oldest is not None and oldest < threshold)
            bucket[period] = format_count(found) if exact else f"{format_count(found)}+"
        counts[filter_type] = bucket
    return counts


def build_transaction_entry(item, trade_label):
    filter_type = "sale" if trade_label == "매매" else ("monthly" if trade_label == "월세" else "jeonse")
    price = format_price_manwon(item.get("amount"))
    if trade_label == "월세":
        price = format_rent_price(item.get("amount"), item.get("monthly_rent"))

    return {
        "type": trade_label,
        "filter_type": filter_type,
        "date": format_deal_date(item),
        "price": price,
        "area_label": format_area_label(item.get("area")),
        "floor": format_floor(item.get("floor")),
        "dong": str(item.get("dong") or "").strip(),
        "apt_name": str(item.get("apt_name") or "").strip(),
    }


def build_transaction_lists(sale_items, jeonse_items):
    transactions_by_area = {}

    for item in sale_items:
        entry = build_transaction_entry(item, "매매")
        transactions_by_area.setdefault(entry["area_label"], []).append(entry)

    for item in jeonse_items:
        entry = build_transaction_entry(item, item.get("deal_type") if item.get("deal_type") in ("전세", "월세") else "전세")
        transactions_by_area.setdefault(entry["area_label"], []).append(entry)

    for rows in transactions_by_area.values():
        rows.sort(
            key=lambda row: (
                row.get("date") or "",
                0 if row.get("type") == "매매" else (1 if row.get("type") == "전세" else 2),
            ),
            reverse=True,
        )

    area_tabs = []
    primary_labels, secondary_labels = split_area_labels(transactions_by_area)
    primary_set = set(primary_labels)
    for area_label in primary_labels + secondary_labels:
        rows = transactions_by_area[area_label]
        sale_count = sum(1 for row in rows if row.get("type") == "매매")
        jeonse_count = sum(1 for row in rows if row.get("type") == "전세")
        monthly_count = sum(1 for row in rows if row.get("type") == "월세")
        area_tabs.append({
            "area_label": area_label,
            "count": len(rows),
            "count_label": format_count(len(rows)),
            "sale_count": sale_count,
            "sale_count_label": format_count(sale_count),
            "jeonse_count": jeonse_count,
            "jeonse_count_label": format_count(jeonse_count),
            "monthly_count": monthly_count,
            "monthly_count_label": format_count(monthly_count),
            "is_primary": area_label in primary_set,
            "period_counts": build_period_counts(
                rows,
                {"sale": sale_count, "jeonse": jeonse_count, "monthly": monthly_count},
            ),
        })
        capped_rows = []
        for filter_type in ("sale", "jeonse", "monthly"):
            capped_rows.extend(
                [row for row in rows if row.get("filter_type") == filter_type][:TRANSACTION_PANEL_ROW_CAP]
            )
        capped_rows.sort(
            key=lambda row: (
                row.get("date") or "",
                0 if row.get("type") == "매매" else (1 if row.get("type") == "전세" else 2),
            ),
            reverse=True,
        )
        transactions_by_area[area_label] = capped_rows

    return area_tabs, transactions_by_area


def build_batch_metric_display(batch_metrics):
    trade_count = parse_int(batch_metrics.get("trade_count_1y")) or 0
    rent_count = parse_int(batch_metrics.get("rent_count_1y")) or 0
    jeonse_count = parse_int(batch_metrics.get("jeonse_count_1y"))
    monthly_count = parse_int(batch_metrics.get("monthly_count_1y"))
    if jeonse_count is None and monthly_count is None:
        jeonse_count = rent_count
        monthly_count = 0
    else:
        jeonse_count = jeonse_count or 0
        monthly_count = monthly_count or 0
    total_count = trade_count + jeonse_count + monthly_count
    return {
        "latest_trade_amount": format_price_manwon(parse_amount_to_manwon(batch_metrics.get("latest_trade_amount"))),
        "latest_trade_date": format_display_date(batch_metrics.get("latest_trade_date")),
        "latest_rent_deposit": format_price_manwon(parse_amount_to_manwon(batch_metrics.get("latest_rent_deposit"))),
        "latest_rent_date": format_display_date(batch_metrics.get("latest_rent_date")),
        "trade_count_1y": format_count(trade_count),
        "rent_count_1y": format_count(rent_count),
        "jeonse_count_1y": format_count(jeonse_count),
        "monthly_count_1y": format_count(monthly_count),
        "total_count_1y": format_count(total_count),
        "jeonse_ratio": format_percent(batch_metrics.get("jeonse_ratio")),
    }


def build_transaction_insight_badges(batch_metrics, area_tabs):
    trade_count = parse_int(batch_metrics.get("trade_count_1y")) or 0
    rent_count = parse_int(batch_metrics.get("rent_count_1y")) or 0
    total_count = trade_count + rent_count
    monthly_count = sum(tab.get("monthly_count", 0) or 0 for tab in area_tabs)
    badges = []

    if total_count == 0:
        return ["데이터 부족"]
    if total_count >= 100:
        badges.append("거래 활발")
    elif total_count >= 10:
        badges.append("최근 거래 있음")

    if rent_count >= 10 and rent_count > max(trade_count * 3, 0):
        badges.append("전월세 수요 높음")
    if monthly_count > 0:
        badges.append("월세 거래 있음")

    if area_tabs:
        primary_area = max(area_tabs, key=lambda tab: tab.get("count", 0) or 0)
        area_number = parse_int(re.sub(r"\D", "", primary_area.get("area_label", "")))
        if area_number is not None and area_number <= 60:
            badges.append("소형 거래 중심")
        elif area_number is not None and area_number >= 84:
            badges.append("중대형 거래 있음")

    return badges[:4] or ["최근 거래 있음"]

def empty_transaction_summary(reason=""):
    return {
        "enabled": False,
        "source_label": "국토교통부 공개 실거래 기준",
        "months": [],
        "areas": [],
        "area_tabs": [],
        "transactions_by_area": {},
        "reason": reason,
    }


def get_transaction_summary(apartment):
    batch_summary = get_batch_transaction_summary(apartment)
    if batch_summary and batch_summary.get("has_data"):
        return batch_summary

    fallback_enabled = os.getenv(
        "CLUSTEAD_ENABLE_TRANSACTION_API_FALLBACK",
        os.getenv("LIVEFIT_ENABLE_TRANSACTION_API_FALLBACK", "0"),
    )
    if fallback_enabled.strip() != "1":
        return empty_transaction_summary("molit_batch_data_missing")

    service_key = get_public_data_service_key()
    if not service_key:
        print("[TRANSACTION] PUBLIC DATA service key missing")
        return empty_transaction_summary("service_key_missing")

    lawd_cd = SEOUL_LAWD_CODES.get(str(apartment.get("district") or "").strip())
    if not lawd_cd:
        return empty_transaction_summary("lawd_code_missing")

    months = get_recent_deal_months()
    sale_items = []
    jeonse_items = []

    try:
        for deal_ym in months:
            sale_rows = fetch_transactions("sale", lawd_cd, deal_ym, service_key)
            rent_rows = fetch_transactions("rent", lawd_cd, deal_ym, service_key)

            sale_items.extend([
                row for row in sale_rows
                if is_apartment_match(row, apartment)
            ])
            jeonse_items.extend([
                row for row in rent_rows
                if is_jeonse(row) and is_apartment_match(row, apartment)
            ])

        area_summaries = build_area_summaries(sale_items, jeonse_items)
        area_tabs, transactions_by_area = build_transaction_lists(
            sale_items,
            jeonse_items,
        )

        return {
            "enabled": True,
            "source_label": "국토교통부 공개 실거래 기준",
            "months": months,
            "areas": area_summaries,
            "area_tabs": area_tabs,
            "transactions_by_area": transactions_by_area,
            "sale_count": len(sale_items),
            "jeonse_count": len(jeonse_items),
            "has_data": bool(area_tabs),
        }
    except Exception as exc:
        print(f"[TRANSACTION] summary failed: {exc}")
        return empty_transaction_summary("summary_failed")

import json
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta

from transaction_layer_utils import (
    TRANSACTION_DETAIL_INDEX_PATH,
    TRANSACTION_DETAIL_DIR,
    TRANSACTION_DETAIL_MANIFEST_PATH,
    TRANSACTION_MAPPING_PATH,
    TRANSACTION_MASTER_PATH,
    TRANSACTION_SUMMARY_PATH,
    clean_text,
    ensure_transaction_dirs,
    normalize_address,
    normalize_dong,
    normalize_name,
    parse_float,
    read_apartment_master,
    read_csv_rows,
    write_csv,
)


SUMMARY_FIELDS = [
    "name",
    "kapt_code",
    "gu",
    "dong",
    "road_address",
    "latest_trade_amount",
    "latest_trade_date",
    "latest_rent_deposit",
    "latest_rent_date",
    "trade_count_3m",
    "trade_count_1y",
    "rent_count_3m",
    "rent_count_1y",
    "jeonse_count_3m",
    "jeonse_count_1y",
    "monthly_count_3m",
    "monthly_count_1y",
    "avg_trade_amount_1y",
    "avg_rent_deposit_1y",
    "avg_trade_amount_84",
    "avg_rent_amount_84",
    "max_trade_amount_1y",
    "min_trade_amount_1y",
    "jeonse_ratio",
    "recent_trade_trend",
    "price_per_m2",
    "data_confidence",
    "transaction_area_summary_json",
]

MIN_AREA_TAB_TRANSACTION_COUNT = 5
MIN_AREA_TAB_DOMINANCE_RATIO = 0.03
MAX_PRIMARY_AREA_TABS = 5


def parse_date(value):
    try:
        return datetime.strptime(clean_text(value), "%Y-%m-%d").date()
    except Exception:
        return None


def number(value):
    return parse_float(value)


def trusted_mapping(row):
    if clean_text(row.get("manual_override")).upper() == "Y":
        return True
    if clean_text(row.get("verified")).upper() == "Y":
        return True
    try:
        return float(row.get("match_confidence") or 0) >= 0.9
    except Exception:
        return False


def load_mapping_index():
    if not TRANSACTION_MAPPING_PATH.exists():
        return {}
    rows, _ = read_csv_rows(TRANSACTION_MAPPING_PATH)
    return {clean_text(row.get("livefit_name")): row for row in rows}


def load_transaction_index():
    if not TRANSACTION_MASTER_PATH.exists():
        return defaultdict(list)

    rows, _ = read_csv_rows(TRANSACTION_MASTER_PATH)
    index = defaultdict(list)
    for row in rows:
        apt_name = row.get("apartment_name") or row.get("apt_name_raw")
        road_address = row.get("normalized_road_address") or row.get("road_address")
        key = (
            clean_text(row.get("gu")),
            normalize_dong(row.get("dong")),
            normalize_name(apt_name),
            normalize_address(road_address),
        )
        index[key].append(row)
    return index


def find_rows(apartment, mapping, tx_index):
    if not mapping or not trusted_mapping(mapping):
        return []

    gu = clean_text(apartment["gu"])
    dong = normalize_dong(apartment["dong"])
    tx_name = normalize_name(mapping.get("transaction_apt_name"))
    tx_road = normalize_address(mapping.get("transaction_road_address"))

    rows = []
    if tx_name:
        rows.extend(tx_index.get((gu, dong, tx_name, tx_road), []))
        if not rows:
            for key, items in tx_index.items():
                if key[0] == gu and key[1] == dong and key[2] == tx_name:
                    rows.extend(items)
    return rows


def latest(rows, amount_field):
    usable = [
        row for row in rows
        if parse_date(row.get("deal_date")) and number(row.get(amount_field)) is not None
    ]
    if not usable:
        return None
    return sorted(usable, key=lambda row: row.get("deal_date"), reverse=True)[0]


def average(values):
    values = [value for value in values if value is not None]
    if not values:
        return ""
    return round(sum(values) / len(values), 1)


def format_count(value):
    try:
        return f"{int(float(value or 0)):,}"
    except Exception:
        return "0"


def format_price_manwon(value):
    amount = number(value)
    if amount is None:
        return ""
    amount = int(round(amount))
    if amount >= 10000:
        return f"{amount / 10000:.1f}억"
    return f"{amount:,}만원"


def format_display_date(value):
    return clean_text(value).replace("-", ".")


def format_floor(value):
    text = clean_text(value)
    if not text:
        return ""
    try:
        text = str(int(float(text)))
    except Exception:
        pass
    return f"{text}층"


def area_label(value):
    area = number(value)
    if area is None:
        return "면적 미상"
    return f"{round(area):.0f}㎡"


def normalized_area_sort_key(label):
    return int("".join(ch for ch in clean_text(label) if ch.isdigit()) or 9999)


def split_area_labels(grouped):
    if not grouped:
        return [], []

    dominant_count = max(len(items) for items in grouped.values())
    sorted_labels = sorted(
        grouped,
        key=lambda label: (-len(grouped[label]), normalized_area_sort_key(label)),
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


def deal_filter_type(row):
    if row.get("transaction_type") == "trade":
        return "sale"
    return "monthly" if (number(row.get("monthly_rent")) or 0) > 0 else "jeonse"


def transaction_price(row):
    if row.get("transaction_type") == "trade":
        return format_price_manwon(row.get("deal_amount"))
    monthly = number(row.get("monthly_rent")) or 0
    if monthly > 0:
        return f"보증금 {format_price_manwon(row.get('deposit_amount'))} / {int(round(monthly)):,}만원"
    return format_price_manwon(row.get("deposit_amount"))


def build_transaction_detail_payload(rows):
    grouped = defaultdict(list)
    for row in rows:
        filter_type = deal_filter_type(row)
        label = area_label(row.get("area_m2"))
        grouped[label].append({
            "type": {"sale": "매매", "jeonse": "전세", "monthly": "월세"}[filter_type],
            "filter_type": filter_type,
            "date": format_display_date(row.get("deal_date")),
            "price": transaction_price(row),
            "area_label": label,
            "floor": format_floor(row.get("floor")),
            "dong": clean_text(row.get("dong")),
            "apt_name": clean_text(row.get("apartment_name") or row.get("apt_name_raw")),
        })

    area_tabs = []
    transactions_by_area = {}
    primary_labels, secondary_labels = split_area_labels(grouped)
    primary_set = set(primary_labels)
    for label in primary_labels + secondary_labels:
        items = grouped[label]
        items.sort(
            key=lambda item: (
                item.get("date") or "",
                0 if item.get("filter_type") == "sale" else (1 if item.get("filter_type") == "jeonse" else 2),
            ),
            reverse=True,
        )
        sale_count = sum(1 for item in items if item.get("filter_type") == "sale")
        jeonse_count = sum(1 for item in items if item.get("filter_type") == "jeonse")
        monthly_count = sum(1 for item in items if item.get("filter_type") == "monthly")
        area_tabs.append({
            "area_label": label,
            "count": len(items),
            "count_label": format_count(len(items)),
            "sale_count": sale_count,
            "sale_count_label": format_count(sale_count),
            "jeonse_count": jeonse_count,
            "jeonse_count_label": format_count(jeonse_count),
            "monthly_count": monthly_count,
            "monthly_count_label": format_count(monthly_count),
            "is_primary": label in primary_set,
        })

        capped = []
        for item_type in ("sale", "jeonse", "monthly"):
            capped.extend([item for item in items if item.get("filter_type") == item_type][:80])
        capped.sort(
            key=lambda item: (
                item.get("date") or "",
                0 if item.get("filter_type") == "sale" else (1 if item.get("filter_type") == "jeonse" else 2),
            ),
            reverse=True,
        )
        transactions_by_area[label] = capped

    return {
        "area_tabs": area_tabs,
        "transactions_by_area": transactions_by_area,
    }


def build_area_summary(trade_rows, rent_rows):
    grouped = defaultdict(lambda: {"sale": [], "rent": []})
    for row in trade_rows:
        grouped[area_label(row.get("area_m2"))]["sale"].append(row)
    for row in rent_rows:
        grouped[area_label(row.get("area_m2"))]["rent"].append(row)

    result = []
    area_groups = {
        label: groups["sale"] + groups["rent"]
        for label, groups in grouped.items()
    }
    primary_labels, secondary_labels = split_area_labels(area_groups)
    for label in primary_labels + secondary_labels:
        groups = grouped[label]
        latest_sale = latest(groups["sale"], "deal_amount")
        latest_rent = latest(groups["rent"], "deposit_amount")
        result.append({
            "area_label": label,
            "sale_count": len(groups["sale"]),
            "rent_count": len(groups["rent"]),
            "latest_sale": latest_sale.get("deal_amount") if latest_sale else "",
            "latest_rent": latest_rent.get("deposit_amount") if latest_rent else "",
        })
    return result


def trend_label(trade_rows, today):
    six_months_ago = today - timedelta(days=183)
    one_year_ago = today - timedelta(days=365)
    recent = []
    prior = []
    for row in trade_rows:
        row_date = parse_date(row.get("deal_date"))
        amount = number(row.get("deal_amount"))
        if not row_date or amount is None:
            continue
        if row_date >= six_months_ago:
            recent.append(amount)
        elif row_date >= one_year_ago:
            prior.append(amount)
    if len(recent) < 2 or len(prior) < 2:
        return "insufficient"
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior)
    if recent_avg >= prior_avg * 1.03:
        return "up"
    if recent_avg <= prior_avg * 0.97:
        return "down"
    return "flat"


def summarize_apartment(apartment, rows, mapping, today):
    one_year_ago = today - timedelta(days=365)
    three_months_ago = today - timedelta(days=93)
    trade_rows = [row for row in rows if row.get("transaction_type") == "trade"]
    rent_rows = [row for row in rows if row.get("transaction_type") == "rent"]
    jeonse_rows = [row for row in rent_rows if not number(row.get("monthly_rent"))]
    monthly_rows = [row for row in rent_rows if (number(row.get("monthly_rent")) or 0) > 0]

    trade_3m = [row for row in trade_rows if (parse_date(row.get("deal_date")) or date.min) >= three_months_ago]
    rent_3m = [row for row in rent_rows if (parse_date(row.get("deal_date")) or date.min) >= three_months_ago]
    jeonse_3m = [row for row in jeonse_rows if (parse_date(row.get("deal_date")) or date.min) >= three_months_ago]
    monthly_3m = [row for row in monthly_rows if (parse_date(row.get("deal_date")) or date.min) >= three_months_ago]
    trade_1y = [row for row in trade_rows if (parse_date(row.get("deal_date")) or date.min) >= one_year_ago]
    rent_1y = [row for row in rent_rows if (parse_date(row.get("deal_date")) or date.min) >= one_year_ago]
    jeonse_1y = [row for row in jeonse_rows if (parse_date(row.get("deal_date")) or date.min) >= one_year_ago]
    monthly_1y = [row for row in monthly_rows if (parse_date(row.get("deal_date")) or date.min) >= one_year_ago]

    latest_trade = latest(trade_rows, "deal_amount")
    latest_rent = latest(jeonse_rows, "deposit_amount")

    trade_84 = [
        number(row.get("deal_amount")) for row in trade_rows
        if (number(row.get("area_m2")) or 0) >= 80 and (number(row.get("area_m2")) or 0) <= 90
    ]
    rent_84 = [
        number(row.get("deposit_amount")) for row in jeonse_rows
        if (number(row.get("area_m2")) or 0) >= 80 and (number(row.get("area_m2")) or 0) <= 90
    ]
    trade_1y_amounts = [number(row.get("deal_amount")) for row in trade_1y if number(row.get("deal_amount")) is not None]
    rent_1y_deposits = [number(row.get("deposit_amount")) for row in jeonse_1y if number(row.get("deposit_amount")) is not None]

    latest_trade_amount = number(latest_trade.get("deal_amount")) if latest_trade else None
    latest_rent_amount = number(latest_rent.get("deposit_amount")) if latest_rent else None
    latest_trade_area = number(latest_trade.get("area_m2")) if latest_trade else None

    jeonse_ratio = ""
    if latest_trade_amount and latest_rent_amount:
        jeonse_ratio = round((latest_rent_amount / latest_trade_amount) * 100, 1)

    price_per_m2 = ""
    if latest_trade_amount and latest_trade_area:
        price_per_m2 = round(latest_trade_amount / latest_trade_area, 1)

    confidence = mapping.get("match_confidence") if mapping else "0.00"
    return {
        "name": apartment["livefit_name"],
        "kapt_code": apartment["kapt_code"],
        "gu": apartment["gu"],
        "dong": apartment["dong"],
        "road_address": apartment["road_address"],
        "latest_trade_amount": int(latest_trade_amount) if latest_trade_amount is not None else "",
        "latest_trade_date": latest_trade.get("deal_date") if latest_trade else "",
        "latest_rent_deposit": int(latest_rent_amount) if latest_rent_amount is not None else "",
        "latest_rent_date": latest_rent.get("deal_date") if latest_rent else "",
        "trade_count_3m": len(trade_3m),
        "trade_count_1y": len(trade_1y),
        "rent_count_3m": len(rent_3m),
        "rent_count_1y": len(rent_1y),
        "jeonse_count_3m": len(jeonse_3m),
        "jeonse_count_1y": len(jeonse_1y),
        "monthly_count_3m": len(monthly_3m),
        "monthly_count_1y": len(monthly_1y),
        "avg_trade_amount_1y": average(trade_1y_amounts),
        "avg_rent_deposit_1y": average(rent_1y_deposits),
        "avg_trade_amount_84": average(trade_84),
        "avg_rent_amount_84": average(rent_84),
        "max_trade_amount_1y": int(max(trade_1y_amounts)) if trade_1y_amounts else "",
        "min_trade_amount_1y": int(min(trade_1y_amounts)) if trade_1y_amounts else "",
        "jeonse_ratio": jeonse_ratio,
        "recent_trade_trend": trend_label(trade_rows, today),
        "price_per_m2": price_per_m2,
        "data_confidence": confidence if rows else "0.00",
        "transaction_area_summary_json": json.dumps(build_area_summary(trade_rows, rent_rows), ensure_ascii=False),
    }


def build_summary():
    ensure_transaction_dirs()
    apartments = read_apartment_master()
    mapping_index = load_mapping_index()
    tx_index = load_transaction_index()
    today = date.today()

    rows = []
    detail_index = {}
    detail_manifest = {}
    connected = 0
    for apartment in apartments:
        mapping = mapping_index.get(apartment["livefit_name"], {})
        tx_rows = find_rows(apartment, mapping, tx_index)
        if tx_rows:
            connected += 1
            detail_payload = build_transaction_detail_payload(tx_rows)
            if detail_payload.get("area_tabs"):
                detail_index[apartment["livefit_name"]] = detail_payload
                digest = hashlib.sha1(apartment["livefit_name"].encode("utf-8")).hexdigest()[:16]
                detail_filename = f"{digest}.json"
                (TRANSACTION_DETAIL_DIR / detail_filename).write_text(
                    json.dumps(detail_payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                detail_manifest[apartment["livefit_name"]] = detail_filename
        rows.append(summarize_apartment(apartment, tx_rows, mapping, today))

    write_csv(TRANSACTION_SUMMARY_PATH, rows, SUMMARY_FIELDS)
    TRANSACTION_DETAIL_MANIFEST_PATH.write_text(
        json.dumps(detail_manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    TRANSACTION_DETAIL_INDEX_PATH.write_text(
        json.dumps(detail_index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"[OK] transaction_summary.csv rows={len(rows)} path={TRANSACTION_SUMMARY_PATH}")
    print(f"[OK] transaction_detail_index.json apartments={len(detail_index)} path={TRANSACTION_DETAIL_INDEX_PATH}")
    print(f"[OK] apartments_with_transactions={connected} apartments_without_transactions={len(rows) - connected}")
    if not tx_index:
        print("[WARNING] transaction_master.csv is empty or missing; summary was generated with empty transaction metrics.")


if __name__ == "__main__":
    build_summary()

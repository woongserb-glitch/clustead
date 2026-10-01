"""매매 가격 추이 순위: 최근 6개월과 직전 6개월의 같은 단지·같은 전용면적 중앙값 비교.

2026-10-01 사용자 결정. 정의와 근거는 outputs/home-scout/analysis_rental_policy.md
(Codex 사전 조사)와 price-trend-check.md 에 있다.

- 기간: 기준월은 신고 기한(30일) 때문에 덜 들어오므로 뺀다. 기준월 2026-09 이면
  최근 = 2026-03~08, 직전 = 2025-09~2026-02.
- 대상: 분양형태가 '분양'이고 운영 구분이 '임대'가 아닌 300세대 이상 단지.
  '기타'에는 공공임대와 일반 단지가 섞여 있어 판별할 수 없으므로 뺀다.
  전세는 공공임대 보증금 혼입을 거래 단위로 가를 수 없어 아직 공개하지 않는다.
- 단지 귀속: 신뢰 매핑의 (구, 동, 거래 단지명, 거래 도로명주소)가 정확히 같은 거래만.
  한 거래 키가 여러 단지에 걸리면 버린다(오류동 금강 / 금강(343) 같은 동명 단지).
- 직거래 제외: 거래 마스터에는 표시가 없어 국토부 원본 엑셀의 거래유형을 대조한다.
- 표본: 기간마다 5건 이상. 값은 중앙값. 한 단지는 변화가 가장 큰 면적 하나만 싣는다.
"""
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
from services.transaction_service import (is_trusted_batch_mapping, normalize_address,
                                          normalize_dong, normalize_name)

WINDOW_MONTHS = 6
MIN_TRADES = 5
MIN_HOUSEHOLDS = 300
SALE_TYPE_COLUMN = "k-세대타입(분양형태)"
OPERATION_COLUMN = "기타/의무/임대/임의=1/2/3/4"
RENTAL_NAME = re.compile(r"임대|장기전세|행복주택")


def month_shift(month, delta):
    y, m = map(int, month.split("-"))
    index = y * 12 + (m - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def windows(data_month):
    """(직전 시작, 직전 끝, 최근 시작, 최근 끝) — 모두 포함 구간, 기준월 제외."""
    date.fromisoformat(data_month + "-01")
    recent_end = month_shift(data_month, -1)
    recent_start = month_shift(recent_end, -(WINDOW_MONTHS - 1))
    prev_end = month_shift(recent_start, -1)
    prev_start = month_shift(prev_end, -(WINDOW_MONTHS - 1))
    return prev_start, prev_end, recent_start, recent_end


def eligible(master_row):
    households = int(float(master_row.get("k-전체세대수") or 0) or 0)
    return (households >= MIN_HOUSEHOLDS
            and (master_row.get(SALE_TYPE_COLUMN) or "").strip() == "분양"
            and (master_row.get(OPERATION_COLUMN) or "").strip() != "임대"
            and not RENTAL_NAME.search(master_row.get("k-아파트명") or ""))


# --- 직거래 대조 (outputs/home-scout/analysis_direct.py 를 옮김) ---------------------

def _number_key(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return ""
    try:
        return format(Decimal(text).normalize(), "f")
    except InvalidOperation:
        return text


def trade_identity(row):
    """원본 엑셀(정규화 후)과 거래 마스터 행이 같은 거래인지 맞추는 정확 키(근사 매칭 없음)."""
    from transaction_layer_utils import clean_text, normalize_address as addr, normalize_dong as dong, normalize_lot_part
    main = normalize_lot_part(row.get("bonbun"))
    sub = normalize_lot_part(row.get("bubun"))
    if not main:
        parts = clean_text(row.get("jibun")).split("-", 1)
        main = normalize_lot_part(parts[0])
        sub = normalize_lot_part(parts[1] if len(parts) > 1 else "")
    return (clean_text(row.get("gu")), dong(row.get("dong")),
            clean_text(row.get("apartment_name") or row.get("apt_name_raw")),
            addr(row.get("normalized_road_address") or row.get("road_address")),
            main, "" if sub == "0" else sub,
            clean_text(row.get("contract_date") or row.get("deal_date")),
            _number_key(row.get("area_m2")), _number_key(row.get("floor")),
            _number_key(row.get("trade_price_manwon") or row.get("deal_amount")))


def _raw_rows(path):
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book[book.sheetnames[0]]
        if sheet.max_row == 1:
            sheet.reset_dimensions()
        headers = None
        for raw in sheet.iter_rows(values_only=True):
            values = [str(v).strip() if v is not None else "" for v in raw]
            if headers is None:
                compact = ["".join(v.split()) for v in values]
                if all(field in compact for field in ("시군구", "단지명", "계약년월")):
                    headers = compact
                continue
            row = dict(zip(headers, values))
            if row.get("단지명"):
                yield row
    finally:
        book.close()


def load_direct_trade_keys(raw_dir, years):
    """국토부 매매 원본에서 거래유형=직거래인 거래의 정확 키. 원본은 읽기만 한다."""
    from build_molit_transaction_master import normalize_row
    from transaction_layer_utils import clean_text
    keys = set()
    for year in sorted(years):
        path = Path(raw_dir) / f"trade_{year}.xlsx"
        if not path.exists():
            raise FileNotFoundError(f"직거래 판별에 필요한 원본이 없습니다: {path}")
        for row in _raw_rows(path):
            if clean_text(row.get("거래유형")) != "직거래":
                continue
            normalized = normalize_row(row, path.name, "trade")
            if normalized is not None:
                keys.add(trade_identity(normalized))
    return keys


# --- 계산 ---------------------------------------------------------------------------

def mapping_lookup(mapping_rows, masters):
    lookup = defaultdict(set)
    for r in mapping_rows:
        ident = (r.get("clustead_name") or r.get("livefit_name"), r.get("gu"), r.get("dong"))
        road = normalize_address(r.get("transaction_road_address"))
        if ident in masters and road and is_trusted_batch_mapping(r):
            lookup[(r["gu"], normalize_dong(r["dong"]), normalize_name(r["transaction_apt_name"]), road)].add(ident)
    return lookup


def collect_trades(transaction_rows, mapping_rows, masters, served, start, end, direct_keys):
    """[(단지 키, 계약월, 전용면적, 매매가 만원)] — 기간 안의 매매 중 단지에 정확히 귀속되고
    직거래가 아닌 것만. 가격 추이와 국민평형 가격 조건이 같은 거래 집합을 쓴다."""
    lookup = mapping_lookup(mapping_rows, masters)
    trades, stats = [], defaultdict(int)
    for r in transaction_rows:
        if r.get("transaction_type") != "trade":
            continue
        month = (r.get("contract_date") or "")[:7]
        if not start <= month <= end:
            continue
        stats["window_trades"] += 1
        targets = lookup.get((r.get("gu"), normalize_dong(r.get("dong")),
                              normalize_name(r.get("apartment_name")), normalize_address(r.get("road_address"))), set())
        if len(targets) != 1:
            stats["ambiguous" if targets else "unmapped"] += 1
            continue
        ident = next(iter(targets))
        if ident not in served:
            stats["not_served"] += 1
            continue
        if trade_identity(r) in direct_keys:
            stats["direct_excluded"] += 1
            continue
        try:
            area, price = float(r["area_m2"]), float(r["trade_price_manwon"])
        except (KeyError, TypeError, ValueError):
            stats["invalid"] += 1
            continue
        if price <= 0 or area <= 0:
            stats["invalid"] += 1
            continue
        trades.append((ident, month, area, price))
    return trades, stats


def recent_84_average(trades, data_month, min_trades=3):
    """{단지 키: (평균 만원, 건수)} — 최근 6개월(기준월 제외) 전용 80~90㎡ 매매 평균."""
    _, _, recent_start, recent_end = windows(data_month)
    prices = defaultdict(list)
    for ident, month, area, price in trades:
        if recent_start <= month <= recent_end and 80 <= area <= 90:
            prices[ident].append(price)
    return {ident: (sum(v) / len(v), len(v)) for ident, v in prices.items() if len(v) >= min_trades}


def build_price_trend(trades, stats, masters, served, data_month, limit):
    """masters: {(name, gu, dong): master row}, served: 사이트가 보여주는 단지 키 집합."""
    prev_start, prev_end, recent_start, recent_end = windows(data_month)
    prices = defaultdict(lambda: ([], []))
    stats = defaultdict(int, stats)
    for ident, month, area, price in trades:
        if not prev_start <= month <= recent_end:
            continue
        if not eligible(masters[ident]):
            stats["not_eligible"] += 1
            continue
        stats["used"] += 1
        prices[(ident, int(area))][0 if month <= prev_end else 1].append(price)

    best = {}
    compared = 0
    for (ident, area), (before, after) in prices.items():
        if len(before) < MIN_TRADES or len(after) < MIN_TRADES:
            continue
        compared += 1
        a, b = median(before), median(after)
        row = {"name": ident[0], "gu": ident[1], "dong": ident[2],
               "households": int(float(masters[ident].get("k-전체세대수") or 0)),
               "area": area, "prev_median": int(round(a)), "recent_median": int(round(b)),
               "prev_n": len(before), "recent_n": len(after),
               "change_pct": round((b / a - 1) * 100, 1)}
        for direction in ("up", "down"):
            sign = 1 if direction == "up" else -1
            if sign * row["change_pct"] <= 0:
                continue
            current = best.get((direction, ident))
            # 한 단지는 변화가 가장 큰 면적 하나만. 같으면 거래가 많은 면적, 그다음 작은 면적.
            rank = (-sign * row["change_pct"], -(row["prev_n"] + row["recent_n"]), area)
            if current is None or rank < current[0]:
                best[(direction, ident)] = (rank, row)

    def ranked(direction):
        sign = 1 if direction == "up" else -1
        rows = [row for (d, _), (_, row) in best.items() if d == direction]
        rows.sort(key=lambda r: (-sign * r["change_pct"], -(r["prev_n"] + r["recent_n"]), r["gu"], r["dong"], r["name"]))
        return rows[:limit]

    meta = {"prev_start": prev_start, "prev_end": prev_end, "recent_start": recent_start, "recent_end": recent_end,
            "min_trades": MIN_TRADES, "min_households": MIN_HOUSEHOLDS, "compared": compared,
            "eligible_complexes": sum(1 for k in served if k in masters and eligible(masters[k])),
            **{k: stats[k] for k in ("window_trades", "used", "direct_excluded", "unmapped", "ambiguous", "not_eligible")}}
    return ranked("up"), ranked("down"), meta


def dotted(month):
    return month.replace("-", ".")

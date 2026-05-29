import csv
import io
import re
import unicodedata
import zipfile
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
APARTMENT_MASTER_PATH = BASE_DIR / "data" / "apartment" / "seoul_apartments.csv"
TRANSACTION_DIR = BASE_DIR / "data" / "transactions"
TRANSACTION_RAW_DIR = TRANSACTION_DIR / "raw"
MOLIT_TRANSACTION_RAW_DIR = TRANSACTION_RAW_DIR / "molit"
TRANSACTION_MASTER_PATH = TRANSACTION_DIR / "transaction_master.csv"
TRANSACTION_MAPPING_PATH = TRANSACTION_DIR / "apartment_transaction_mapping.csv"
TRANSACTION_MANUAL_MAPPING_PATH = TRANSACTION_DIR / "apartment_transaction_mapping_manual.csv"
TRANSACTION_REJECT_MAPPING_PATH = TRANSACTION_DIR / "apartment_transaction_mapping_reject.csv"
TRANSACTION_DETAIL_INDEX_PATH = TRANSACTION_DIR / "transaction_detail_index.json"
TRANSACTION_DETAIL_DIR = TRANSACTION_DIR / "detail_index"
TRANSACTION_DETAIL_MANIFEST_PATH = TRANSACTION_DETAIL_DIR / "manifest.json"
TRANSACTION_MAPPING_AUDIT_PATH = BASE_DIR / "data" / "reports" / "transaction_mapping_audit.csv"
TRANSACTION_SUMMARY_PATH = BASE_DIR / "data" / "baseline" / "transaction_summary.csv"

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")


def ensure_transaction_dirs():
    TRANSACTION_RAW_DIR.mkdir(parents=True, exist_ok=True)
    MOLIT_TRANSACTION_RAW_DIR.mkdir(parents=True, exist_ok=True)
    TRANSACTION_DIR.mkdir(parents=True, exist_ok=True)
    TRANSACTION_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    TRANSACTION_MAPPING_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSACTION_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def normalize_space(value):
    return re.sub(r"\s+", " ", clean_text(value))


def normalize_korean_text(value):
    return unicodedata.normalize("NFKC", clean_text(value)).lower()


def normalize_name(value):
    text = normalize_korean_text(value)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"(아파트|apt)$", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def normalize_address(value):
    text = normalize_korean_text(value)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"^(서울특별시|서울시)", "", text)
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def normalize_dong(value):
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", clean_text(value))


def normalize_lot_part(value):
    text = clean_text(value)
    if not text or text == "-":
        return ""
    digits = re.sub(r"\D", "", text)
    if digits:
        return str(int(digits))
    return text


def split_lot_number(value):
    text = clean_text(value)
    if not text:
        return "", ""
    match = re.match(r"^(\d+)(?:-(\d+))?$", text)
    if not match:
        return "", ""
    bonbun = normalize_lot_part(match.group(1))
    bubun = normalize_lot_part(match.group(2) or "")
    if bubun == "0":
        bubun = ""
    return bonbun, bubun


def compose_lot_number(bonbun, bubun):
    main = normalize_lot_part(bonbun)
    sub = normalize_lot_part(bubun)
    if sub == "0":
        sub = ""
    if not main:
        return ""
    return f"{main}-{sub}" if sub else main


def normalize_money(value):
    text = clean_text(value)
    text = text.replace(",", "").replace(" ", "")
    text = text.replace("만원", "")
    if not text or text in {"-", "0.0.0"}:
        return None
    try:
        return int(round(float(text)))
    except Exception:
        return None


def parse_float(value):
    text = clean_text(value).replace(",", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except Exception:
        return None


def parse_int(value):
    number = parse_float(value)
    if number is None:
        return None
    return int(round(number))


def format_date(year, month, day):
    year_text = clean_text(year)
    month_text = clean_text(month)
    day_text = clean_text(day)
    if not year_text or not month_text:
        return ""
    if not day_text:
        day_text = "1"
    try:
        return f"{int(float(year_text)):04d}-{int(float(month_text)):02d}-{int(float(day_text)):02d}"
    except Exception:
        return ""


def normalize_deal_date(row, year_names, month_names, day_names, full_date_names):
    full_date = first_value(row, full_date_names)
    digits = re.sub(r"\D", "", clean_text(full_date))
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[:4]}-{digits[4:6]}-01"

    year = first_value(row, year_names)
    month = first_value(row, month_names)
    day = first_value(row, day_names)
    return format_date(year, month, day)


def year_month_from_date(value):
    text = clean_text(value)
    match = re.match(r"^(\d{4})-(\d{2})", text)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def safe_read_text_bytes(data):
    for encoding in CSV_ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except Exception:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def read_csv_rows(path):
    path = Path(path)
    data = path.read_bytes()
    text, encoding = safe_read_text_bytes(data)
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return rows, encoding


def iter_raw_csv_sources(raw_dir, patterns):
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        return

    for path in sorted(raw_dir.iterdir()):
        lower_name = path.name.lower()
        if not any(pattern in lower_name for pattern in patterns):
            continue

        if path.suffix.lower() in (".csv", ".txt"):
            rows, encoding = read_csv_rows(path)
            yield path.name, rows, encoding
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.filename.lower().endswith((".csv", ".txt")):
                        continue
                    text, encoding = safe_read_text_bytes(archive.read(info))
                    reader = csv.DictReader(io.StringIO(text))
                    yield f"{path.name}!{info.filename}", list(reader), encoding


def first_value(row, names):
    if isinstance(names, str):
        names = [names]
    normalized = {clean_text(key).lower().replace(" ", ""): key for key in row.keys()}
    for name in names:
        key = normalized.get(clean_text(name).lower().replace(" ", ""))
        if key is not None and clean_text(row.get(key)):
            return row.get(key)
    for name in names:
        token = clean_text(name).lower().replace(" ", "")
        for norm_key, real_key in normalized.items():
            if token and token in norm_key and clean_text(row.get(real_key)):
                return row.get(real_key)
    return ""


def write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_apartment_master():
    rows, _ = read_csv_rows(APARTMENT_MASTER_PATH)
    normalized = []
    for row in rows:
        jibun = clean_text(row.get("나머지주소"))
        normalized.append({
            "livefit_name": clean_text(row.get("k-아파트명")),
            "kapt_code": clean_text(row.get("k-아파트코드")),
            "kapt_name": clean_text(row.get("k-아파트명")),
            "gu": clean_text(row.get("주소(시군구)")),
            "dong": clean_text(row.get("주소(읍면동)")),
            "road_address": clean_text(row.get("kapt도로명주소")),
            "road_name": clean_text(row.get("주소(도로명)")),
            "road_detail": clean_text(row.get("주소(도로상세주소)")),
            "jibun": jibun,
            "bonbun": split_lot_number(jibun)[0],
            "bubun": split_lot_number(jibun)[1],
            "lat": clean_text(row.get("좌표Y")),
            "lng": clean_text(row.get("좌표X")),
        })
    return normalized


def today_iso():
    return date.today().isoformat()

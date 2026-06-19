import csv
import math
import re
import os

# 일부 baseline CSV는 한 셀에 POI 목록 등 매우 큰 문자열을 담는다.
# csv 모듈 기본 필드 한도(131072B)를 넘으면 읽기가 실패하므로 한도를 올린다.
# (구 pandas read_csv에는 이 제한이 없었음 → 동작 동등성 유지)
csv.field_size_limit(2**31 - 1)


def clustead_env(key, default=""):
    return os.getenv(f"CLUSTEAD_{key}", os.getenv(f"LIVEFIT_{key}", default))


PRELOAD_VERBOSE = clustead_env("PRELOAD_VERBOSE", "0") == "1"


def preload_log(*args):
    if PRELOAD_VERBOSE:
        print(*args)

cctv_data = []
park_data = []
apartment_data = []
bus_stop_data = []
bus_route_data = []

# 스캔(전수 순회)되는 thin baseline은 메모리 유지. 인덱스 조회 전용 baseline
# (academy/medical 등)은 아래 SQLite 호환 블록에서 정의한다(메모리 절감).
subway_baseline_data = []
cctv_baseline_data = []
convenience_baseline_data = []
mart_baseline_data = []
cafe_baseline_data = []
school_data = []
school_zone_baseline_data = []
subway_baseline_index = {}

# Baseline row indexes for fast result-page lookup.
# Key: normalized apartment name / Value: baseline row dict
cctv_baseline_index = {}
cafe_baseline_index = {}
convenience_baseline_index = {}
mart_baseline_index = {}


BASELINE_VERSION = "v3.0"


def normalize_baseline_key(value):
    return str(value or "").strip()


def composite_baseline_key(name, gu, dong):
    """Composite identity key for an apartment.

    (name, gu, dong) is the only unique key in the dataset: apartment names
    alone collide (e.g. 신동아아파트 appears 3x across Seoul). Always prefer
    this key; the name-only fallback below is for legacy/ambiguous lookups.
    """
    return (
        normalize_baseline_key(name),
        normalize_baseline_key(gu),
        normalize_baseline_key(dong),
    )


def rebuild_baseline_index(target_index, rows, key_fields=("name", "apartment_name")):
    target_index.clear()

    for row in rows:
        name = ""
        for field in key_fields:
            name = normalize_baseline_key(row.get(field))
            if name:
                break

        if not name:
            continue

        gu = normalize_baseline_key(row.get("gu"))
        dong = normalize_baseline_key(row.get("dong"))

        # Primary key: composite (name, gu, dong) — always exact, never collides.
        target_index[composite_baseline_key(name, gu, dong)] = row

        # Name-only fallback (string key): kept for callers that don't pass
        # gu/dong. First row wins so behaviour matches the legacy lookup; when
        # the name is unique this is still exact. Composite lookups bypass it.
        target_index.setdefault(name, row)


def get_indexed_baseline_row(target_index, apartment_name, gu=None, dong=None):
    if gu is not None or dong is not None:
        row = target_index.get(
            composite_baseline_key(apartment_name, gu, dong)
        )
        if row is not None:
            return row

    return target_index.get(normalize_baseline_key(apartment_name))


def parse_csv_row(row):
    parsed_row = {}

    for key, value in row.items():
        if value is None:
            parsed_row[key] = ""
            continue

        value = str(value).strip()

        if value == "":
            parsed_row[key] = ""
            continue

        try:
            parsed_row[key] = int(value)
            continue
        except Exception:
            pass

        try:
            parsed_row[key] = float(value)
            continue
        except Exception:
            pass

        parsed_row[key] = value

    return parsed_row


def read_csv_records(path, encodings=("utf-8-sig", "cp949")):
    """CSV를 인코딩 폴백으로 읽어 parse_csv_row를 적용한 dict 리스트를 반환.

    구 `pd.read_csv(path).to_dict("records")` 대체 — 런타임 pandas 의존 제거용.
    pandas는 빈 칸을 NaN(float)으로, 숫자열을 int64/float64로 만들었지만,
    이 프로젝트의 표준 CSV 파서(parse_csv_row)는 빈 칸→"", 숫자형 문자열→int/float로
    변환한다(이미 subway/cctv/convenience/mart/cafe 로더가 쓰는 규칙과 동일).
    """
    last_err = None
    for enc in encodings:
        try:
            with open(path, encoding=enc, newline="") as file:
                reader = csv.DictReader(file)
                return [parse_csv_row(row) for row in reader]
        except UnicodeDecodeError as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return []


def read_csv_rows_raw(path, encodings=("utf-8-sig", "cp949")):
    """parse_csv_row 없이 원본 문자열 그대로 dict 리스트를 반환.

    버스 노선번호처럼 선행 0이 의미 있는 코드(예: "0411")를 보존해야 하는
    필드용. parse_csv_row는 "0411"→int 411로 바꿔 선행 0이 사라지지만,
    구 pandas는 이런 열을 object(문자열) dtype로 두어 "0411"을 보존했다.
    """
    last_err = None
    for enc in encodings:
        try:
            with open(path, encoding=enc, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeDecodeError as e:
            last_err = e
            continue
    if last_err is not None:
        raise last_err
    return []


# ───────────────────────────────────────────────────────────────────
# SQLite 백엔드 baseline (메모리 절감)
# 인덱스 조회 전용 baseline(academy/medical 등 ~388MB)은 메모리에 상주시키지 않고
# data/baseline.db 에서 조회한다. DB가 없으면 기존 CSV 인메모리 로딩으로 자동 폴백
# (배포 안전성). 빌드: python scripts/build_baseline_sqlite.py
# ───────────────────────────────────────────────────────────────────
import sqlite3

_BASELINE_KEY_SEP = "\x1f"
_BASELINE_DB_PATH = "data/baseline.db"
SQLITE_BASELINES = (
    "academy", "medical", "ev_charger", "shopping", "culture",
    "bus", "commercial", "bike", "fire_station", "nightlife", "hangang",
)
_USE_SQLITE_BASELINE = os.path.exists(_BASELINE_DB_PATH)

_baseline_conn_obj = None
_baseline_conn_pid = None


def _baseline_conn():
    """읽기전용 SQLite 연결(프로세스별). gunicorn preload fork 후에도 안전하게 재오픈."""
    global _baseline_conn_obj, _baseline_conn_pid
    pid = os.getpid()
    if _baseline_conn_obj is None or _baseline_conn_pid != pid:
        _baseline_conn_obj = sqlite3.connect(
            f"file:{_BASELINE_DB_PATH}?mode=ro", uri=True, check_same_thread=False
        )
        _baseline_conn_obj.row_factory = sqlite3.Row
        _baseline_conn_pid = pid
    return _baseline_conn_obj


class _SqliteBaseline:
    """기존 list(순회) + index(.get) API를 SQLite 테이블 1개로 대체.

    반환 행은 parse_csv_row로 변환 → 기존 인메모리 dict와 값·타입 동일(바이트 동일성).
    보조 키 컬럼 _ck(composite)/_nk(name-only)는 rebuild_baseline_index 의미를 재현:
    .get(tuple)=composite(rowid DESC, last-wins) / .get(str)=name-only(rowid ASC, first-wins).
    """

    __slots__ = ("table",)

    def __init__(self, table):
        self.table = table

    @staticmethod
    def _row_to_dict(row):
        d = {k: row[k] for k in row.keys()}
        d.pop("_ck", None)
        d.pop("_nk", None)
        return parse_csv_row(d)

    def __iter__(self):
        cur = _baseline_conn().execute(f'SELECT * FROM "{self.table}" ORDER BY rowid')
        for row in cur:
            yield self._row_to_dict(row)

    def get(self, key, default=None):
        conn = _baseline_conn()
        if isinstance(key, tuple):
            ck = _BASELINE_KEY_SEP.join(normalize_baseline_key(k) for k in key)
            row = conn.execute(
                f'SELECT * FROM "{self.table}" WHERE "_ck"=? ORDER BY rowid DESC LIMIT 1',
                (ck,),
            ).fetchone()
        else:
            nk = normalize_baseline_key(key)
            row = conn.execute(
                f'SELECT * FROM "{self.table}" WHERE "_nk"=? ORDER BY rowid ASC LIMIT 1',
                (nk,),
            ).fetchone()
        if row is None:
            return default
        return self._row_to_dict(row)


def iter_baseline_columns(baseline_data, columns):
    """Yield baseline rows with only the requested columns when SQLite is active."""
    table = getattr(baseline_data, "table", None)
    if _USE_SQLITE_BASELINE and table:
        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        cur = _baseline_conn().execute(f'SELECT {quoted_columns} FROM "{table}" ORDER BY rowid')
        for row in cur:
            yield parse_csv_row({column: row[column] for column in columns})
        return

    for row in baseline_data:
        yield row


def _make_baseline(table):
    """DB 있으면 SQLite 백엔드(data·index 동일 객체), 없으면 빈 list/dict 폴백
    (load_* 가 CSV로 채움)."""
    if _USE_SQLITE_BASELINE:
        obj = _SqliteBaseline(table)
        return obj, obj
    return [], {}


bus_baseline_data, bus_baseline_index = _make_baseline("bus")
commercial_baseline_data, commercial_baseline_index = _make_baseline("commercial")
nightlife_baseline_data, nightlife_baseline_index = _make_baseline("nightlife")
bike_baseline_data, bike_baseline_index = _make_baseline("bike")
academy_baseline_data, academy_baseline_index = _make_baseline("academy")
culture_baseline_data, culture_baseline_index = _make_baseline("culture")
hangang_baseline_data, hangang_baseline_index = _make_baseline("hangang")
fire_station_baseline_data, fire_station_baseline_index = _make_baseline("fire_station")
shopping_baseline_data, shopping_baseline_index = _make_baseline("shopping")
ev_charger_baseline_data, ev_charger_baseline_index = _make_baseline("ev_charger")
medical_baseline_data, medical_baseline_index = _make_baseline("medical")


def get_cctv_icon_and_subtype(purpose):
    purpose = purpose or ""

    if "생활방범" in purpose or "방범" in purpose:
        return "🛡", "생활방범"

    if "어린이" in purpose or "보호" in purpose:
        return "🧒", "어린이보호"

    if "교통" in purpose or "단속" in purpose:
        return "🚦", "교통/단속"

    if "시설" in purpose:
        return "🏢", "시설안전"

    return "📹", "기타"


def load_cctv_data():
    global cctv_data

    path = "data/cctv/national_cctv.csv"
    loaded = []

    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[PRELOAD] CCTV CSV 인코딩: {encoding}")
                preload_log(f"[PRELOAD] CCTV 컬럼명: {reader.fieldnames}")

                for row in reader:
                    try:
                        lat = float(row["WGS84위도"])
                        lng = float(row["WGS84경도"])

                        purpose = row.get("설치목적구분", "기타")
                        icon, subtype = get_cctv_icon_and_subtype(purpose)

                        address = (
                            row.get("소재지도로명주소")
                            or row.get("소재지지번주소")
                            or "CCTV"
                        )

                        camera_count = int(float(row.get("카메라대수", 1) or 1))

                        loaded.append({
                            "lat": lat,
                            "lng": lng,
                            "category": "cctv",
                            "label": address,
                            "name": address,
                            "icon": icon,
                            "subtype": subtype,
                            "purpose": purpose,
                            "camera_count": camera_count,
                            "agency": row.get("관리기관명", ""),
                            "source": "공공데이터포털",
                        })

                    except Exception:
                        continue

            cctv_data.clear()
            cctv_data.extend(loaded)

            print(f"[PRELOAD] CCTV {len(cctv_data)}개 로드 완료")
            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(f"[PRELOAD ERROR] CCTV 파일 없음: {path}")
            return

        except Exception as e:
            print("[PRELOAD ERROR]", e)
            return

    preload_log("[PRELOAD ERROR] CCTV CSV 인코딩을 읽지 못했습니다.")


def inspect_park_csv():
    path = "data/park/park.csv"

    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[PARK] encoding: {encoding}")
                preload_log(f"[PARK] columns: {reader.fieldnames}")

                first_row = next(reader)
                preload_log(f"[PARK] sample: {first_row}")

                return

        except Exception:
            continue


def parse_area(area_text):
    if not area_text:
        return 0

    numbers = re.findall(r"\d+", area_text.replace(",", ""))

    if not numbers:
        return 0

    return int(numbers[0])


def get_park_subtype(area):
    if area >= 100000:
        return "대형공원"
    if area >= 10000:
        return "중형공원"
    return "소형공원"


def load_park_data():
    global park_data

    path = "data/park/park.csv"
    loaded = []
    encodings = ["utf-8-sig", "cp949", "euc-kr"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[PRELOAD] PARK CSV 인코딩: {encoding}")
                preload_log(f"[PRELOAD] PARK 컬럼명: {reader.fieldnames}")

                for row in reader:
                    try:
                        lat = float(row["Y좌표(WGS84)"])
                        lng = float(row["X좌표(WGS84)"])

                        area_text = row.get("면적", "")
                        area = parse_area(area_text)
                        subtype = get_park_subtype(area)

                        name = row.get("공원명", "공원")

                        loaded.append({
                            "lat": lat,
                            "lng": lng,
                            "category": "park",
                            "label": f"🌳 {name}",
                            "name": name,
                            "subtype": subtype,
                            "area": area,
                            "area_text": area_text,
                            "address": row.get("공원주소", ""),
                            "district": row.get("지역", ""),
                            "source": "서울시 공공데이터",
                        })

                    except Exception:
                        continue

            park_data.clear()
            park_data.extend(loaded)

            print(f"[PRELOAD] PARK {len(park_data)}개 로드 완료")
            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(f"[PRELOAD ERROR] PARK 파일 없음: {path}")
            return

        except Exception as e:
            print("[PRELOAD PARK ERROR]", e)
            return

    preload_log("[PRELOAD ERROR] PARK CSV 인코딩을 읽지 못했습니다.")


def load_apartment_data():

    global apartment_data

    path = "data/apartment/seoul_apartments.csv"

    try:
        rows = read_csv_records(path)
    except Exception as e:
        print("[APT ERROR] CSV 로드 실패", e)
        return

    apartment_list = []

    for row in rows:

        try:
            lat = float(row["좌표Y"])
            lng = float(row["좌표X"])

        except Exception:
            continue

        if not math.isfinite(lat) or not math.isfinite(lng):
            continue

        apartment = {
            "name": str(row.get("k-아파트명", "")).strip(),
            "gu": str(row.get("주소(시군구)", "")).strip(),
            "dong": str(row.get("주소(읍면동)", "")).strip(),
            "road_address": row.get("kapt도로명주소", ""),
            "lat": lat,
            "lng": lng,
            "household_count": row.get("k-전체세대수", ""),
            "parking_count": row.get("주차대수", ""),
            "approval_date": row.get("k-사용검사일-사용승인일", ""),
            "builder": row.get("k-건설사(시공사)", ""),
            "area_under_60": row.get("k-전용면적별세대현황(60㎡이하)", ""),
            "area_60_85": row.get("k-전용면적별세대현황(60㎡~85㎡이하)", ""),
            "area_85_135": row.get("k-85㎡~135㎡이하", ""),
            "area_over_135": row.get("k-135㎡초과", ""),
        }

        apartment_list.append(apartment)

    apartment_data.clear()
    apartment_data.extend(apartment_list)

    print(f"[APT] {len(apartment_data)}개 로드 완료")


    print(f"[BASELINE VERSION] {BASELINE_VERSION}")

def load_subway_baseline_data():
    global subway_baseline_data, subway_baseline_index

    path = "data/baseline/subway_baseline.csv"
    loaded = []

    encodings = ["utf-8-sig", "cp949", "utf-8"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[BASELINE] SUBWAY CSV 인코딩: {encoding}")
                preload_log(f"[BASELINE] SUBWAY 컬럼명: {reader.fieldnames}")

                for row in reader:
                    try:
                        parsed = parse_csv_row(row)

                        parsed["lat"] = float(row.get("lat"))
                        parsed["lng"] = float(row.get("lng"))
                        parsed["name"] = row.get("name", "").strip()
                        parsed["gu"] = row.get("gu", "").strip()
                        parsed["dong"] = row.get("dong", "").strip()

                        loaded.append(parsed)

                    except Exception:
                        continue

            subway_baseline_data.clear()
            subway_baseline_data.extend(loaded)
            rebuild_baseline_index(subway_baseline_index, subway_baseline_data)

            print(f"[BASELINE] SUBWAY {len(subway_baseline_data)}개 로드 완료")
            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(f"[BASELINE ERROR] SUBWAY 파일 없음: {path}")
            return

        except Exception as e:
            print("[BASELINE SUBWAY ERROR]", e)
            return

    preload_log("[BASELINE ERROR] SUBWAY CSV 인코딩을 읽지 못했습니다.")


def load_cctv_baseline_data():
    global cctv_baseline_data, cctv_baseline_index

    path = "data/baseline/cctv_baseline.csv"
    loaded = []

    encodings = ["utf-8-sig", "cp949", "utf-8"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[BASELINE] CCTV CSV 인코딩: {encoding}")
                preload_log(f"[BASELINE] CCTV 컬럼명: {reader.fieldnames}")

                for row in reader:
                    try:
                        parsed = parse_csv_row(row)

                        parsed["lat"] = float(row.get("lat"))
                        parsed["lng"] = float(row.get("lng"))
                        parsed["name"] = row.get("name", "").strip()
                        parsed["gu"] = row.get("gu", "").strip()
                        parsed["dong"] = row.get("dong", "").strip()

                        loaded.append(parsed)
                    except Exception:
                        continue

            cctv_baseline_data.clear()
            cctv_baseline_data.extend(loaded)
            rebuild_baseline_index(cctv_baseline_index, cctv_baseline_data)

            print(f"[BASELINE] CCTV {len(cctv_baseline_data)}개 로드 완료")
            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(f"[BASELINE ERROR] CCTV 파일 없음: {path}")
            return

        except Exception as e:
            print("[BASELINE CCTV ERROR]", e)
            return

    preload_log("[BASELINE ERROR] CCTV CSV 인코딩을 읽지 못했습니다.")


def load_convenience_baseline_data():
    global convenience_baseline_data, convenience_baseline_index

    path = (
        "data/baseline/"
        "convenience_baseline.csv"
    )

    loaded = []

    encodings = [
        "utf-8-sig",
        "cp949",
        "utf-8"
    ]

    for encoding in encodings:

        try:

            with open(
                path,
                encoding=encoding,
                newline=""
            ) as file:

                reader = csv.DictReader(file)

                preload_log(
                    f"[BASELINE] "
                    f"CONVENIENCE CSV 인코딩: "
                    f"{encoding}"
                )

                preload_log(
                    f"[BASELINE] "
                    f"CONVENIENCE 컬럼명: "
                    f"{reader.fieldnames}"
                )

                for row in reader:

                    try:
                        parsed = parse_csv_row(row)

                        parsed["lat"] = float(row.get("lat"))
                        parsed["lng"] = float(row.get("lng"))
                        parsed["name"] = row.get("name", "").strip()
                        parsed["gu"] = row.get("gu", "").strip()
                        parsed["dong"] = row.get("dong", "").strip()

                        loaded.append(parsed)
                    except Exception:
                        continue

            convenience_baseline_data.clear()

            convenience_baseline_data.extend(
                loaded
            )

            rebuild_baseline_index(
                convenience_baseline_index,
                convenience_baseline_data
            )

            print(
                f"[BASELINE] "
                f"CONVENIENCE "
                f"{len(convenience_baseline_data)}개 "
                f"로드 완료"
            )

            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:

            print(
                f"[BASELINE ERROR] "
                f"CONVENIENCE 파일 없음: "
                f"{path}"
            )

            return

        except Exception as e:

            print(
                "[BASELINE CONVENIENCE ERROR]",
                e
            )

            return

    preload_log("[BASELINE ERROR] CONVENIENCE CSV 인코딩을 읽지 못했습니다.")


def load_mart_baseline_data():
    global mart_baseline_data, mart_baseline_index

    path = (
        "data/baseline/"
        "mart_baseline.csv"
    )

    loaded = []

    encodings = [
        "utf-8-sig",
        "cp949",
        "utf-8"
    ]

    for encoding in encodings:

        try:

            with open(
                path,
                encoding=encoding,
                newline=""
            ) as file:

                reader = csv.DictReader(file)

                preload_log(
                    f"[BASELINE] "
                    f"MART CSV 인코딩: "
                    f"{encoding}"
                )

                preload_log(
                    f"[BASELINE] "
                    f"MART 컬럼명: "
                    f"{reader.fieldnames}"
                )

                for row in reader:

                    try:
                        parsed = parse_csv_row(row)

                        parsed["lat"] = float(row.get("lat"))
                        parsed["lng"] = float(row.get("lng"))
                        parsed["name"] = row.get("name", "").strip()
                        parsed["gu"] = row.get("gu", "").strip()
                        parsed["dong"] = row.get("dong", "").strip()

                        loaded.append(parsed)
                    except Exception:
                        continue

            mart_baseline_data.clear()

            mart_baseline_data.extend(
                loaded
            )

            rebuild_baseline_index(
                mart_baseline_index,
                mart_baseline_data
            )

            print(
                f"[BASELINE] "
                f"MART "
                f"{len(mart_baseline_data)}개 "
                f"로드 완료"
            )

            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:

            print(
                f"[BASELINE ERROR] "
                f"MART 파일 없음: "
                f"{path}"
            )

            return

        except Exception as e:

            print(
                "[BASELINE MART ERROR]",
                e
            )

            return

    preload_log("[BASELINE ERROR] MART CSV 인코딩을 읽지 못했습니다.")


def load_cafe_baseline_data():
    global cafe_baseline_data, cafe_baseline_index

    path = (
        "data/baseline/"
        "cafe_baseline.csv"
    )

    loaded = []

    encodings = [
        "utf-8-sig",
        "cp949",
        "utf-8"
    ]

    for encoding in encodings:

        try:

            with open(
                path,
                encoding=encoding,
                newline=""
            ) as file:

                reader = csv.DictReader(file)

                preload_log(
                    f"[BASELINE] "
                    f"CAFE CSV 인코딩: "
                    f"{encoding}"
                )

                preload_log(
                    f"[BASELINE] "
                    f"CAFE 컬럼명: "
                    f"{reader.fieldnames}"
                )

                for row in reader:

                    try:
                        parsed = parse_csv_row(row)

                        parsed["lat"] = float(row.get("lat"))
                        parsed["lng"] = float(row.get("lng"))
                        parsed["name"] = row.get("name", "").strip()
                        parsed["gu"] = row.get("gu", "").strip()
                        parsed["dong"] = row.get("dong", "").strip()

                        loaded.append(parsed)
                    except Exception:
                        continue

            cafe_baseline_data.clear()

            cafe_baseline_data.extend(
                loaded
            )
            rebuild_baseline_index(cafe_baseline_index, cafe_baseline_data)

            print(
                f"[BASELINE] "
                f"CAFE "
                f"{len(cafe_baseline_data)}개 "
                f"로드 완료"
            )

            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:

            print(
                f"[BASELINE ERROR] "
                f"CAFE 파일 없음: "
                f"{path}"
            )

            return

        except Exception as e:

            print(
                "[BASELINE CAFE ERROR]",
                e
            )

            return

    preload_log("[BASELINE ERROR] CAFE CSV 인코딩을 읽지 못했습니다.")


def get_school_subtype(school_type):
    school_type = school_type or ""

    if "초등" in school_type:
        return "elementary"

    if "중학" in school_type:
        return "middle"

    if "고등" in school_type:
        return "high"

    return "etc"


def load_school_zone_baseline_data():
    global school_zone_baseline_data

    path = "data/baseline/school_zone_baseline.csv"
    loaded = []

    encodings = [
        "utf-8-sig",
        "cp949",
        "euc-kr",
        "utf-8",
    ]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(
                    f"[BASELINE] SCHOOL ZONE CSV 인코딩: {encoding}"
                )

                preload_log(
                    f"[BASELINE] SCHOOL ZONE 컬럼명: {reader.fieldnames}"
                )

                for row in reader:
                    loaded.append(parse_csv_row(row))

            school_zone_baseline_data.clear()
            school_zone_baseline_data.extend(loaded)

            print(
                f"[BASELINE] SCHOOL ZONE "
                f"{len(school_zone_baseline_data)}개 로드 완료"
            )

            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(
                f"[BASELINE ERROR] SCHOOL ZONE 파일 없음: {path}"
            )
            return

        except Exception as e:
            print("[BASELINE SCHOOL ZONE ERROR]", e)
            return

    print(
        "[BASELINE ERROR] SCHOOL ZONE CSV 인코딩 읽기 실패"
    )


def load_school_data():
    global school_data

    path = "data/school/school.csv"
    loaded = []

    encodings = ["utf-8-sig", "cp949", "euc-kr", "utf-8"]

    for encoding in encodings:
        try:
            with open(path, encoding=encoding, newline="") as file:
                reader = csv.DictReader(file)

                preload_log(f"[PRELOAD] SCHOOL CSV 인코딩: {encoding}")
                preload_log(f"[PRELOAD] SCHOOL 컬럼명: {reader.fieldnames}")

                for row in reader:
                    try:
                        if row.get("시도교육청명") != "서울특별시교육청":
                            continue

                        if row.get("운영상태") != "운영":
                            continue

                        school_type = row.get("학교급구분", "")
                        subtype = get_school_subtype(school_type)

                        if subtype not in ["elementary", "middle", "high"]:
                            continue

                        lat = float(row.get("위도"))
                        lng = float(row.get("경도"))

                        name = row.get("학교명", "학교")

                        loaded.append({
                            "lat": lat,
                            "lng": lng,
                            "category": "school",
                            "label": f"🏫 {name}",
                            "name": name,
                            "subtype": subtype,
                            "school_type": school_type,
                            "address": row.get("소재지도로명주소", ""),
                            "agency": row.get("시도교육청명", ""),
                            "source": "공공데이터포털",
                        })

                    except Exception:
                        continue

            school_data.clear()
            school_data.extend(loaded)

            print(f"[PRELOAD] SCHOOL {len(school_data)}개 로드 완료")
            return

        except UnicodeDecodeError:
            continue

        except FileNotFoundError:
            print(f"[PRELOAD ERROR] SCHOOL 파일 없음: {path}")
            return

        except Exception as e:
            print("[PRELOAD SCHOOL ERROR]", e)
            return

    preload_log("[PRELOAD ERROR] SCHOOL CSV 인코딩을 읽지 못했습니다.")


def load_bus_stop_data():
    global bus_stop_data

    csv_path = "data/bus/seoul_bus_stops.csv"

    try:
        rows = read_csv_rows_raw(csv_path)
    except Exception as e:
        print("[PRELOAD BUS STOP ERROR]", e)
        return

    bus_stop_data.clear()

    for row in rows:
        try:
            lat = float(row["Y좌표"])
            lng = float(row["X좌표"])

            bus_stop_data.append({
                # 정류장 CSV는 컬럼명과 실제 내용이 뒤바뀌어 있다: '노드 ID' 컬럼엔
                # ARS 번호(5자리), '정류소번호' 컬럼엔 실제 NODE_ID(9자리)가 들어 있다.
                # 노선 CSV의 NODE_ID와 조인하려면 '정류소번호'를 node_id로 써야 한다
                # (이전엔 '노드 ID'를 node_id로 써서 노선 매칭이 0건 → 노선정보 미표시).
                "node_id": str(row.get("정류소번호", "")).strip(),
                "ars_id": str(row.get("노드 ID", "")).strip(),
                "name": str(row.get("정류소명", "")).strip(),
                "lat": lat,
                "lng": lng,
                "type": str(row.get("정류소 타입", "")).strip(),
            })

        except Exception:
            continue

    print(f"[PRELOAD] BUS STOP {len(bus_stop_data)}개 로드 완료")


def load_bus_route_data():
    global bus_route_data

    csv_path = "data/bus/seoul_bus_routes.csv"

    try:
        rows = read_csv_rows_raw(csv_path)
    except Exception as e:
        print("[PRELOAD BUS ROUTE ERROR]", e)
        return

    bus_route_data.clear()

    for row in rows:
        try:
            bus_route_data.append({
                "route_id": str(row.get("ROUTE_ID", "")).strip(),
                "route_name": str(row.get("노선명", "")).strip(),
                "node_id": str(row.get("NODE_ID", "")).strip(),
                "ars_id": str(row.get("ARS_ID", "")).strip(),
                "stop_name": str(row.get("정류소명", "")).strip(),
            })

        except Exception:
            continue

    print(f"[PRELOAD] BUS ROUTE {len(bus_route_data)}개 로드 완료")


def load_bus_baseline_data():
    global bus_baseline_data, bus_baseline_index

    if _USE_SQLITE_BASELINE:
        return  # 데이터는 data/baseline.db (scripts/build_baseline_sqlite.py)

    csv_path = "data/baseline/bus_baseline.csv"

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE BUS ERROR]", e)
        return

    bus_baseline_data.clear()
    bus_baseline_data.extend(rows)
    rebuild_baseline_index(bus_baseline_index, bus_baseline_data)

    print(f"[BASELINE] BUS {len(bus_baseline_data)}개 로드 완료")


def load_commercial_baseline_data():
    global commercial_baseline_data, commercial_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/commercial_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] COMMERCIAL 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE COMMERCIAL ERROR]", e)
        return

    commercial_baseline_data.clear()
    commercial_baseline_data.extend(rows)
    rebuild_baseline_index(commercial_baseline_index, commercial_baseline_data)

    print(f"[BASELINE] COMMERCIAL {len(commercial_baseline_data)}개 로드 완료")


def load_nightlife_baseline_data():
    global nightlife_baseline_data, nightlife_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/nightlife_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] NIGHTLIFE 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE NIGHTLIFE ERROR]", e)
        return

    nightlife_baseline_data.clear()
    nightlife_baseline_data.extend(rows)
    rebuild_baseline_index(nightlife_baseline_index, nightlife_baseline_data)

    print(f"[BASELINE] NIGHTLIFE {len(nightlife_baseline_data)}개 로드 완료")

def load_bike_baseline_data():
    global bike_baseline_data, bike_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/bike_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] BIKE 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE BIKE ERROR]", e)
        return

    bike_baseline_data.clear()
    bike_baseline_data.extend(rows)
    rebuild_baseline_index(bike_baseline_index, bike_baseline_data)

    print(f"[BASELINE] BIKE {len(bike_baseline_data)}개 로드 완료")



def load_academy_baseline_data():
    global academy_baseline_data, academy_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/academy_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] ACADEMY 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE ACADEMY ERROR]", e)
        return

    academy_baseline_data.clear()
    academy_baseline_data.extend(rows)
    rebuild_baseline_index(academy_baseline_index, academy_baseline_data)

    print(f"[BASELINE] ACADEMY {len(academy_baseline_data)}개 로드 완료")

def load_culture_baseline_data():
    global culture_baseline_data, culture_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/culture_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] CULTURE 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE CULTURE ERROR]", e)
        return

    culture_baseline_data.clear()
    culture_baseline_data.extend(rows)
    rebuild_baseline_index(culture_baseline_index, culture_baseline_data)

    print(f"[BASELINE] CULTURE {len(culture_baseline_data)}개 로드 완료")



def load_hangang_baseline_data():
    global hangang_baseline_data, hangang_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/hangang_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] HANGANG 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE HANGANG ERROR]", e)
        return

    hangang_baseline_data.clear()
    hangang_baseline_data.extend(rows)
    rebuild_baseline_index(hangang_baseline_index, hangang_baseline_data)

    print(f"[BASELINE] HANGANG {len(hangang_baseline_data)}개 로드 완료")


def load_fire_station_baseline_data():
    global fire_station_baseline_data, fire_station_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/fire_station_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] FIRE STATION 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE FIRE STATION ERROR]", e)
        return

    fire_station_baseline_data.clear()
    fire_station_baseline_data.extend(rows)
    rebuild_baseline_index(fire_station_baseline_index, fire_station_baseline_data)

    print(f"[BASELINE] FIRE STATION {len(fire_station_baseline_data)}개 로드 완료")

def load_shopping_baseline_data():
    global shopping_baseline_data, shopping_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/shopping_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] SHOPPING 파일 없음: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE SHOPPING ERROR]", e)
        return

    shopping_baseline_data.clear()
    shopping_baseline_data.extend(rows)
    rebuild_baseline_index(shopping_baseline_index, shopping_baseline_data)

    print(f"[BASELINE] SHOPPING {len(shopping_baseline_data)}개 로드 완료")


def load_ev_charger_baseline_data():
    global ev_charger_baseline_data, ev_charger_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/ev_charger_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] EV CHARGER file not found: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE EV CHARGER ERROR]", e)
        return

    ev_charger_baseline_data.clear()
    ev_charger_baseline_data.extend(rows)
    rebuild_baseline_index(ev_charger_baseline_index, ev_charger_baseline_data)

    print(f"[BASELINE] EV CHARGER {len(ev_charger_baseline_data)} rows loaded")


def load_medical_baseline_data():
    global medical_baseline_data, medical_baseline_index

    if _USE_SQLITE_BASELINE:
        return

    csv_path = "data/baseline/medical_baseline.csv"

    if not os.path.exists(csv_path):
        print(f"[BASELINE] MEDICAL file not found: {csv_path}")
        return

    try:
        rows = read_csv_records(csv_path)
    except Exception as e:
        print("[BASELINE MEDICAL ERROR]", e)
        return

    medical_baseline_data.clear()
    medical_baseline_data.extend(rows)
    rebuild_baseline_index(medical_baseline_index, medical_baseline_data)

    print(f"[BASELINE] MEDICAL {len(medical_baseline_data)} rows loaded")

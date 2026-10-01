"""Build the monthly, read-only home rankings from existing baseline CSVs.

The filters and stable tie order reproduce compute_home_preview.py; only the
ranked lists grow from five to fifty. No baseline is rebuilt. Collection dates
must come from supplied metadata, never file timestamps or source release dates.

python scripts/build_home_rankings.py --data-month 2026-09 \
    --source-dates outputs/clustead-home-billboard/source_dates.json
"""

import argparse
import csv
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_academy_baseline import classify_academy
from services.home_billboard_service import validate_rankings

csv.field_size_limit(2**31 - 1)
LIMIT = 50
BRANDS = ("GS25", "CU", "세븐일레븐", "이마트24")
TOPICS = ("academy", "dong_academy", "value_combo", "subway", "starbucks",
          "convenience", "quiet", "emergency", "gu_best_dong")
SOURCE_NAMES = {
    "academy": "서울시 학원·교습소 정보",
    "subway": "서울시 역사마스터 정보",
    "cafe": "kakao map 기준",
    "convenience": "kakao map 기준",
    "nightlife": "서울시 유흥주점영업 인허가 정보",
    "medical": "서울시 병의원 위치 정보",
    "transactions": "국토교통부 아파트 매매 실거래가",
    "master": "서울시 공동주택 아파트 정보",
}
BASELINE_COLUMNS = {
    "academy_baseline": ("exam_count", "math_count", "english_count", "academy_count_500m", "academy_count_1000m"),
    "subway_baseline": ("nearest_subway_distance", "nearest_subway_name", "subway_line_count_500m", "subway_station_count_500m"),
    "cafe_baseline": ("스타벅스_count_500m", "nearest_스타벅스_distance"),
    "convenience_baseline": tuple(b + "_count_500m" for b in BRANDS),
    "nightlife_baseline": ("nightlife_count_500m", "nightlife_nearest_any_distance"),
    "medical_baseline": ("emergency_count_1km", "nearest_superior_hospital_distance", "nearest_superior_hospital_name",
                         "emergency_items_json"),
    "transaction_summary": ("avg_trade_amount_84",),
}
MASTER_COLUMNS = ("k-아파트코드", "k-아파트명", "주소(시군구)", "주소(읍면동)",
                  "k-전체세대수", "k-사용검사일-사용승인일")


def f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def csv_rows(path, encoding="utf-8-sig", columns=None):
    """Stream rows, discarding large POI JSON columns instead of retaining them."""
    with Path(path).open(encoding=encoding, newline="") as handle:
        for row in csv.DictReader(handle):
            yield {col: row.get(col, "") for col in columns} if columns else row


def baseline(path, columns):
    return {(r["name"], r["gu"], r["dong"]): r
            for r in csv_rows(path, columns=("name", "gu", "dong", *columns))}


def load_sources(value=None):
    """Accept {key: date|null|{collected_at, ...}} or an existing output's sources."""
    if value is None:
        value = {}
    elif isinstance(value, (str, Path)):
        raw = str(value)
        value = json.loads(raw if raw.lstrip().startswith("{") else Path(raw).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("source dates must be a JSON object")
    value = value.get("sources", value)
    if not isinstance(value, dict):
        raise ValueError("sources must be a JSON object")
    result = {}
    for key, name in SOURCE_NAMES.items():
        supplied = value.get(key)
        entry = dict(supplied) if isinstance(supplied, dict) else {"collected_at": supplied}
        collected = entry.get("collected_at")
        if collected is not None:
            if not isinstance(collected, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collected):
                raise ValueError(f"{key}.collected_at must be YYYY-MM-DD or null")
            date.fromisoformat(collected)
        result[key] = {**entry, "name": name, "collected_at": collected}
    for field, expected in (("contract_start", "2025-01"), ("contract_end", "2026-09")):
        if field in result["transactions"] and result["transactions"][field] != expected:
            raise ValueError(f"transactions.{field} conflicts with the fixed calculation definition ({expected})")
    return result


def definitions(out, sources, data_month):
    def source(*keys):
        # 수집일은 화면에 쓰지 않는다(2026-10-01 사용자 결정: 과한 정보). sources 의
        # collected_at 은 출처 추적용으로 데이터에만 남긴다.
        return " / ".join(sources[k]["name"] for k in keys)

    # 산정 기준은 기준점·반경·방식·출처만 보인다(2026-10-01 사용자 결정). 대상 조건은
    # 방식에 합친다. 동률 처리는 코드(정렬 키)에 남고 화면에는 쓰지 않는다.
    point = ["기준점", "단지 대표 좌표"]
    no_dong = out["dong_academy_meta"]["no_dong"]
    dong = [["기준점", "학원 주소에 적힌 법정동"],
            ["방식", f"개수 기준: 동 안의 입시/보습·수학·영어 학원·교습소 수의 합 (주소에서 동을 찾지 못한 {no_dong:,}곳 제외)"],
            ["출처", source("academy")]]
    return {
        "academy": [point, ["반경", "1,000m 이내 (직선거리)"],
                    ["방식", "개수 기준: 입시/보습·수학·영어 학원·교습소 수의 합"], ["출처", source("academy")]],
        "dong_academy": dong,
        "value_combo": [point, ["반경", "학원 1,000m · 지하철역 500m 이내 (직선거리)"],
                        ["방식", "개수 기준: 학원 수가 많은 순. 대상은 전용 80~90㎡ 매매 평균 10억 원 미만(2025.1~2026.9 신고 건) · 300세대 이상 · 역 500m 이내 단지"],
                        ["출처", source("transactions", "master", "subway", "academy")]],
        "subway": [point, ["반경", "500m 이내 (직선거리)"],
                   ["방식", "개수 기준: 반경 안 역들이 지나는 서로 다른 노선 수"], ["출처", source("subway")]],
        "starbucks": [point, ["반경", "500m 이내 (직선거리)"],
                      ["방식", "개수 기준: 스타벅스 매장 수"], ["출처", source("cafe")]],
        "convenience": [point, ["반경", "500m 이내 (직선거리)"],
                        ["방식", "개수 기준: GS25·CU·세븐일레븐·이마트24 매장 수의 합"], ["출처", source("convenience")]],
        "quiet": [point, ["반경", "500m 이내 유흥주점 0곳 (직선거리)"],
                  ["방식", "최근접 기준: 가장 가까운 유흥주점이 먼 순. 대상은 1,000세대 이상 단지"],
                  ["출처", source("nightlife", "master")]],
        "emergency": [point, ["반경", "1,000m 이내 (직선거리)"],
                      ["방식", "개수 기준: 응급실을 운영하는 의료기관 수"], ["출처", source("medical")]],
        "gu_best_dong": [dong[0], ["방식", dong[1][1] + ". 각 구에서 가장 많은 동 1곳"], dong[2]],
        "changes": [["기준점", "신규 단지는 단지 코드, 응급실은 단지 대표 좌표"],
                    ["반경", "응급실 1,000m 이내 (직선거리)"],
                    ["방식", "직전 달과 비교해 새로 등록된 단지와, 반경 안에 응급실이 새로 들어온 단지"],
                    ["출처", source("master", "medical")]],
    }


def er_name_key(name):
    return re.sub(r"\s+", "", name or "")


def er_place(address):
    """'서울특별시 강서구 양천로 600, … (등촌동)' -> ('강서구', '등촌동'). 못 찾으면 빈 문자열."""
    gu = re.search(r"(\S+구)\s", address or "")
    dong = re.findall(r"\(([^,()]*?[0-9]*(?:동|가))[,)]", address or "")
    return (gu.group(1) if gu else ""), (dong[-1].strip() if dong else "")


def er_hospitals(medical):
    """{응급실 이름: {name, gu, dong}} — 현재 의료 베이스라인 항목의 주소에서."""
    found = {}
    for row in medical.values():
        for item in json.loads(row.get("emergency_items_json") or "[]"):
            if item.get("name") and item["name"] not in found:
                gu, dong = er_place(item.get("address"))
                found[item["name"]] = {"name": item["name"], "gu": gu, "dong": dong}
    return found


def er_index(medical):
    """{complex key: {응급실 이름: 거리m}} — 1km 안 응급실. 개수는 emergency_count_1km 를 따른다
    (항목 거리는 m 반올림이라 1,000m 경계에서 개수와 어긋날 수 있다)."""
    index = {}
    for key, row in medical.items():
        n = int(f(row.get("emergency_count_1km"), 0) or 0)
        if n <= 0:
            # 응급실이 없는 단지도 남긴다. 직전 달에 '있었던 단지'인지 알아야 이름이 바뀐
            # 단지(2026-10 목동성원)를 새 응급실로 오인하지 않는다.
            index[key] = {}
            continue
        items = sorted(json.loads(row.get("emergency_items_json") or "[]"), key=lambda i: f(i.get("distance"), 9e9))
        near = {}
        for item in items:
            if len(near) >= n:
                break
            near.setdefault(item["name"], int(f(item.get("distance"), 0) or 0))
        index[key] = near
    return index


def changes(out, master_rows, medical, data_month, previous=None, prev_master=None, prev_medical=None):
    """Retain both current state and the original monthly comparison basis.

    2026-10-01 사용자 결정: 배정초 변경 대신 '응급실이 새로 가까워진 단지'를 보인다.
    """
    out["new_complexes"], out["er_changes"], out["er_hospitals"] = [], [], []
    meta = {"master_compared": False, "er_compared": False}
    old_codes, old_er = None, None
    current_er = er_index(medical)
    current_snapshot = {"master_codes": [r["k-아파트코드"] for r in master_rows],
                        "emergency": [[*k, sorted(v)] for k, v in current_er.items()]}

    def er_from_snapshot(rows):
        return {tuple(r[:3]): dict.fromkeys(r[3], 0) for r in rows}

    def same_er(a, b):
        return a.keys() == b.keys() and all(set(a[k]) == set(b[k]) for k in a)

    if previous:
        previous_month = previous.get("data_month")
        if previous_month == data_month:
            # Recompute against the monthly basis, not the last same-month state.
            for key in ("new_complexes", "er_changes", "er_hospitals"):
                out[key] = previous.get(key, [])
            saved = previous.get("changes_meta", {})
            meta.update({k: v for k, v in saved.items() if k in ("master_compared", "er_compared", "previous_month")})
            basis = previous.get("comparison_snapshot", {})
            old_codes = set(basis["master_codes"]) if "master_codes" in basis else None
            old_er = er_from_snapshot(basis["emergency"]) if "emergency" in basis else None
            # Legacy artifacts have no comparison basis. Preserve their deltas only
            # if the corresponding source snapshot is unchanged; an explicit CSV
            # supersedes that scope. Uncompared scopes remain uncompared.
            snapshot = previous.get("snapshot", {})
            for field, flag, delta, supplied, basis_value in (
                ("master_codes", "master_compared", "new_complexes", prev_master, old_codes),
                ("emergency", "er_compared", "er_changes", prev_medical, old_er),
            ):
                if supplied or basis_value is not None or not (meta.get(flag) or out[delta]):
                    continue
                unchanged = field in snapshot and (
                    set(snapshot[field]) == set(current_snapshot[field]) if field == "master_codes"
                    else same_er(er_from_snapshot(snapshot[field]), current_er)
                )
                if not unchanged:
                    option = "--prev-master" if field == "master_codes" else "--prev-medical"
                    raise ValueError(f"Same-month {field} changed without a comparison_snapshot; provide {option} or the previous month's --previous JSON")
        else:
            current = date.fromisoformat(data_month + "-01")
            prior = date(current.year - (current.month == 1), current.month - 1 or 12, 1).strftime("%Y-%m")
            if previous_month != prior:
                raise ValueError("--previous must be the immediately previous month or a same-month rerun")
            meta["previous_month"] = previous_month
            snapshot = previous.get("snapshot", {})
            old_codes = set(snapshot["master_codes"]) if "master_codes" in snapshot else None
            old_er = er_from_snapshot(snapshot["emergency"]) if "emergency" in snapshot else None
    if prev_master:
        old_codes = {r["k-아파트코드"] for r in csv_rows(prev_master, "cp949", MASTER_COLUMNS)}
    if prev_medical:
        old_er = er_index(baseline(prev_medical, ("emergency_count_1km", "emergency_items_json")))
    if old_codes is not None:
        meta["master_compared"] = True
        out["new_complexes"] = [{"name": r["k-아파트명"], "gu": r["주소(시군구)"], "dong": r["주소(읍면동)"],
                                 "households": int(f(r["k-전체세대수"], 0) or 0),
                                 "built": (r.get("k-사용검사일-사용승인일") or "")[:7].replace("-", ".")}
                                for r in master_rows if r["k-아파트코드"] not in old_codes]
    if old_er is not None:
        meta["er_compared"] = True
        new_keys = {(c["name"], c["gu"], c["dong"]) for c in out["new_complexes"]} if old_codes is not None else set()
        rows = []
        for key, near in current_er.items():
            # 신규 단지는 위 목록에 이미 있다. 직전 달에 없던 단지도 '새로 가까워진' 것이 아니다.
            if key in new_keys or key not in old_er:
                continue
            # 원천이 기관명 띄어쓰기만 바꾸는 달이 있다(2026-10: 중앙보훈병원 등 4곳). 공백을 빼고 비교한다.
            before = {er_name_key(name) for name in old_er.get(key, {})}
            added = {name: m for name, m in near.items() if er_name_key(name) not in before}
            # 병원별로 묶어 보이므로 (단지, 새 응급실) 한 쌍이 한 행이다.
            rows.extend({"name": key[0], "gu": key[1], "dong": key[2], "hospital": name, "distance": meters}
                        for name, meters in added.items())
        out["er_changes"] = sorted(rows, key=lambda r: (r["distance"], r["gu"], r["dong"], r["name"], r["hospital"]))
        places = er_hospitals(medical)
        counts = Counter(r["hospital"] for r in out["er_changes"])
        # 영향 단지가 많은 병원부터. 주소를 못 찾으면 구·동 없이 이름만 보인다.
        out["er_hospitals"] = [places.get(name, {"name": name, "gu": "", "dong": ""})
                               for name, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    out["changes_meta"] = meta
    out["snapshot"] = current_snapshot
    out["comparison_snapshot"] = {}
    if old_codes is not None:
        out["comparison_snapshot"]["master_codes"] = sorted(old_codes)
    if old_er is not None:
        out["comparison_snapshot"]["emergency"] = [[*k, sorted(v)] for k, v in old_er.items()]


def build_rankings(data_dir, *, data_month, source_dates=None, previous=None, prev_master=None, prev_medical=None):
    if not re.fullmatch(r"\d{4}-\d{2}", data_month):
        raise ValueError("data_month must be YYYY-MM")
    date.fromisoformat(data_month + "-01")
    data_dir = Path(data_dir)
    sources = load_sources(source_dates)
    loaded = {name: baseline(data_dir / "baseline" / f"{name}.csv", columns)
              for name, columns in BASELINE_COLUMNS.items()}
    ac, sub, cafe, conv, nl, med, tx = (loaded[name] for name in BASELINE_COLUMNS)
    masters = list(csv_rows(data_dir / "apartment/seoul_apartments.csv", "cp949", MASTER_COLUMNS))
    master = {(r["k-아파트명"], r["주소(시군구)"], r["주소(읍면동)"]): r for r in masters}
    hh = lambda k: int(f(master.get(k, {}).get("k-전체세대수"), 0) or 0)
    keys = [k for k in ac if k in sub]
    lab = lambda k: {"name": k[0], "gu": k[1], "dong": k[2], "households": hh(k)}
    trio = lambda k: f(ac[k]["exam_count"], 0) + f(ac[k]["math_count"], 0) + f(ac[k]["english_count"], 0)
    out = {"schema_version": 1, "data_month": data_month,
           "generated_at": datetime.now(timezone.utc).isoformat(), "sources": sources,
           # Complexes the site actually serves (have baseline rows); the master also lists
           # complexes without coordinates, which never appear on any page.
           "complex_count": len(keys)}

    t = sorted(keys, key=lambda k: (-trio(k), -f(ac[k]["academy_count_500m"], 0)))
    out["academy"] = [{**lab(k), "total": int(trio(k)), "exam": int(f(ac[k]["exam_count"])),
                       "math": int(f(ac[k]["math_count"])), "english": int(f(ac[k]["english_count"]))} for k in t[:LIMIT]]

    cnt, no_dong = defaultdict(Counter), 0
    for r in csv_rows(data_dir / "academy/academy_geocoded.csv"):
        if (r.get("등록상태명") or "").strip() != "개원":
            continue
        subtype = classify_academy(r)
        if subtype not in ("입시/보습", "수학", "영어"):
            continue
        m = re.search(r"\(([^,()]*?[0-9]*(?:동|가))[,)]", r.get("도로명상세주소") or "")
        gu = (r.get("행정구역명") or "").strip()
        if not m or not gu:
            no_dong += 1
            continue
        cnt[(gu, m.group(1).strip())][subtype] += 1
    rows = sorted(((g, d, sum(c.values()), c) for (g, d), c in cnt.items()), key=lambda x: -x[2])
    out["dong_academy"] = [{"gu": g, "dong": d, "total": n, "exam": c["입시/보습"], "math": c["수학"], "english": c["영어"]}
                           for g, d, n, c in rows[:LIMIT]]
    best = {}
    for g, d, n, _ in rows:
        best.setdefault(g, {"gu": g, "dong": d, "total": n})
    out["gu_best_dong"] = [best[g] for g in sorted(best)]
    out["dong_academy_meta"] = {"counted": sum(sum(c.values()) for c in cnt.values()), "no_dong": no_dong}

    pool = [k for k in keys if k in tx and f(tx[k]["avg_trade_amount_84"]) and f(tx[k]["avg_trade_amount_84"]) < 100000
            and hh(k) >= 300 and f(sub[k]["nearest_subway_distance"], 9e9) <= 500]
    t = sorted(pool, key=lambda k: (-f(ac[k]["academy_count_1000m"], 0), f(sub[k]["nearest_subway_distance"])))
    out["value_combo"] = [{**lab(k), "price84": int(f(tx[k]["avg_trade_amount_84"])), "station": sub[k]["nearest_subway_name"],
                           "station_m": int(f(sub[k]["nearest_subway_distance"])), "academy_1km": int(f(ac[k]["academy_count_1000m"]))} for k in t[:LIMIT]]
    out["value_combo_pool"] = len(pool)

    t = sorted(keys, key=lambda k: (-f(sub[k]["subway_line_count_500m"], 0), -f(sub[k]["subway_station_count_500m"], 0), f(sub[k]["nearest_subway_distance"], 9e9)))
    out["subway"] = [{**lab(k), "lines": int(f(sub[k]["subway_line_count_500m"])), "stations": int(f(sub[k]["subway_station_count_500m"])),
                      "nearest": sub[k]["nearest_subway_name"], "nearest_m": int(f(sub[k]["nearest_subway_distance"]))} for k in t[:LIMIT]]
    t = sorted([k for k in keys if k in cafe], key=lambda k: (-f(cafe[k]["스타벅스_count_500m"], 0), f(cafe[k]["nearest_스타벅스_distance"], 9e9)))
    out["starbucks"] = [{**lab(k), "count": int(f(cafe[k]["스타벅스_count_500m"])), "nearest_m": int(f(cafe[k]["nearest_스타벅스_distance"], 0))} for k in t[:LIMIT]]
    total = lambda k: sum(f(conv[k][b + "_count_500m"], 0) for b in BRANDS)
    t = sorted([k for k in keys if k in conv], key=lambda k: -total(k))
    out["convenience"] = [{**lab(k), "total": int(total(k)), **{b: int(f(conv[k][b + "_count_500m"], 0)) for b in BRANDS}} for k in t[:LIMIT]]

    pool = [k for k in keys if hh(k) >= 1000 and f(nl[k]["nightlife_count_500m"], 1) == 0 and f(nl[k]["nightlife_nearest_any_distance"])]
    t = sorted(pool, key=lambda k: -f(nl[k]["nightlife_nearest_any_distance"]))
    out["quiet"] = [{**lab(k), "nearest_nightlife_m": int(f(nl[k]["nightlife_nearest_any_distance"]))} for k in t[:LIMIT]]
    out["quiet_pool"] = len(pool)
    t = sorted(keys, key=lambda k: (-f(med[k]["emergency_count_1km"], 0), f(med[k]["nearest_superior_hospital_distance"], 9e9)))
    out["emergency"] = [{**lab(k), "er_1km": int(f(med[k]["emergency_count_1km"], 0)), "hospital": med[k]["nearest_superior_hospital_name"],
                         "hospital_m": int(f(med[k]["nearest_superior_hospital_distance"], 0))} for k in t[:LIMIT]]
    changes(out, masters, med, data_month, previous, prev_master, prev_medical)
    out["definitions"] = definitions(out, sources, data_month)
    return out


def validate_output_path(output, data_dir, input_paths=()):
    """Resolve junctions/symlinks before allowing a JSON output outside raw data."""
    output = Path(output)
    resolved = output.resolve()
    if output.suffix.lower() != ".json" or resolved.suffix.lower() != ".json":
        raise ValueError("--output must be a .json file")
    for root in {Path(data_dir).resolve(), (ROOT / "data").resolve()}:
        if resolved.is_relative_to(root) and resolved.relative_to(root).parts[0] != "derived":
            raise ValueError("--output cannot overwrite source data; use data/derived or a directory outside data")
    for path in input_paths:
        if path is None:
            continue
        source = Path(path).resolve()
        if resolved == source or (resolved.exists() and source.exists() and resolved.samefile(source)):
            raise ValueError(f"--output conflicts with an input file: {path}")
    return resolved


SNAPSHOT_KEYS = ("snapshot", "comparison_snapshot")


def snapshot_path(path):
    return path.with_name(path.stem + ".snapshot.json")


def write_atomic(path, text):
    temporary = None
    try:
        # A unique file avoids following a stale .tmp symlink or two builds sharing
        # a staging file. Validate and serialize before touching the destination.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/home_rankings.json")
    parser.add_argument("--data-month", required=True, help="Publication's data month, YYYY-MM (does not infer transaction coverage)")
    parser.add_argument("--source-dates", help="JSON object or JSON file of collection dates; absent dates stay unknown")
    parser.add_argument("--previous", type=Path, help="Previous month's JSON snapshot (or same-month JSON to preserve deltas)")
    parser.add_argument("--prev-master", type=Path)
    parser.add_argument("--prev-medical", type=Path, help="Previous month's medical_baseline.csv")
    args = parser.parse_args(argv)
    metadata = args.source_dates
    if metadata is None and (args.data_dir / "derived/home_source_dates.json").exists():
        metadata = args.data_dir / "derived/home_source_dates.json"
    try:
        metadata_path = metadata if metadata is not None and not str(metadata).lstrip().startswith("{") else None
        args.output = validate_output_path(args.output, args.data_dir, (args.prev_master, args.prev_medical, metadata_path))
        # Preserve saved changes on same-month CLI reruns even without --previous.
        previous_path = args.previous or (args.output if args.output.exists() else None)
        previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path else None
        if previous is not None and snapshot_path(previous_path).exists():
            previous.update(json.loads(snapshot_path(previous_path).read_text(encoding="utf-8")))
        output = build_rankings(args.data_dir, data_month=args.data_month, source_dates=metadata,
                                previous=previous, prev_master=args.prev_master, prev_medical=args.prev_medical)
        validate_rankings(output)
        # The web app loads the main file into every worker; the next-month comparison
        # snapshot (all complex codes + 1km emergency rooms, ~480KB) goes to a sidecar it never reads.
        sidecar = {key: output.pop(key) for key in SNAPSHOT_KEYS if key in output}
        encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        encoded_sidecar = json.dumps(sidecar, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(snapshot_path(args.output), encoded_sidecar)
    write_atomic(args.output, encoded)
    print(f"wrote {args.output} ({len(output['academy'])} rankings/topic maximum, {args.data_month})")


if __name__ == "__main__":
    main()

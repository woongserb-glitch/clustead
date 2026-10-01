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
    "cafe": "카카오 로컬 검색 (스타벅스)",
    "convenience": "카카오 로컬 검색 (GS25·CU·세븐일레븐·이마트24)",
    "nightlife": "서울시 유흥주점영업 인허가 정보",
    "medical": "서울시 병의원 위치 정보",
    "transactions": "국토교통부 아파트 매매 실거래가",
    "master": "서울시 공동주택 아파트 정보",
    "school": "한국교육시설안전원 초등학교통학구역",
}
BASELINE_COLUMNS = {
    "academy_baseline": ("exam_count", "math_count", "english_count", "academy_count_500m", "academy_count_1000m"),
    "subway_baseline": ("nearest_subway_distance", "nearest_subway_name", "subway_line_count_500m", "subway_station_count_500m"),
    "cafe_baseline": ("스타벅스_count_500m", "nearest_스타벅스_distance"),
    "convenience_baseline": tuple(b + "_count_500m" for b in BRANDS),
    "nightlife_baseline": ("nightlife_count_500m", "nightlife_nearest_any_distance"),
    "medical_baseline": ("emergency_count_1km", "nearest_superior_hospital_distance", "nearest_superior_hospital_name"),
    "transaction_summary": ("avg_trade_amount_84",),
    "school_zone_baseline": ("assigned_elementary_school",),
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
        return " / ".join(f"{sources[k]['name']} (수집일 {sources[k]['collected_at']})"
                          if sources[k]["collected_at"] else f"{sources[k]['name']} (수집일 기록 없음)"
                          for k in keys)

    point = ["기준점", "단지 대표 좌표"]
    stable = "그 뒤 동률은 원본 학원 베이스라인의 입력 순서 유지"
    dong_tie = "동률은 원본 학원 주소 집계에서 처음 등장한 법정동 순서 유지"
    no_dong = out["dong_academy_meta"]["no_dong"]
    total = out["dong_academy_meta"]["counted"] + no_dong
    excluded = f"주소에서 법정동 또는 구를 확인하지 못한 {no_dong:,}곳({no_dong / total * 100 if total else 0:.1f}%) 제외"
    dong = [["기준점", "해당 없음: 학원 주소의 법정동 기준"], ["반경", "해당 없음: 법정동 전체"],
            ["방식", "개수 기준: 개원 상태 입시/보습·수학·영어 학원·교습소 수의 합"],
            ["제외", excluded], ["동률", dong_tie], ["출처와 수집일", source("academy")]]
    return {
        "academy": [point, ["반경", "1,000m 이내 직선거리 (도보 아님)"],
                    ["방식", "개수 기준: 입시/보습·수학·영어 학원·교습소 수의 합 (종류별 개수는 모두 1km)"],
                    ["동률", f"500m 내 전체 학원 수가 많은 순; {stable}"], ["출처와 수집일", source("academy")]],
        "dong_academy": dong,
        "value_combo": [point, ["반경", "학원 1,000m, 가장 가까운 지하철역 500m 이내 (모두 직선거리, 도보 아님)"],
                        ["조건", "전용 80~90㎡ 매매 실거래 평균 10억 원 미만 · 300세대 이상 · 최근접 역 500m 이내. 가격은 2025.1~2026.9 계약의 신고 건 평균 (호가 아님)"],
                        ["방식", "개수 기준: 반경 1,000m 내 전체 학원 수가 많은 순; 역 조건은 최근접 기준"],
                        ["동률", f"가장 가까운 역까지 거리가 짧은 순; {stable}"],
                        ["후보", f"조건을 모두 만족한 {out['value_combo_pool']:,}개 단지"],
                        ["참고", "최신 월 거래는 신고 기한 30일 때문에 일부만 반영됨"],
                        ["출처와 수집일", source("transactions", "master", "subway", "academy")]],
        "subway": [point, ["반경", "500m 이내 직선거리 (도보 아님)"],
                   ["방식", "개수 기준: 반경 안 역들이 지나는 서로 다른 노선 수 (환승역은 노선별로 셈)"],
                   ["동률", f"500m 안 역 수가 많은 순, 그다음 최근접 역까지 거리가 짧은 순; {stable}"],
                   ["출처와 수집일", source("subway")]],
        "starbucks": [point, ["반경", "500m 이내 직선거리 (도보 아님)"],
                      ["방식", "개수 기준: 카카오맵에 등록된 스타벅스 매장 수"],
                      ["동률", f"가장 가까운 매장까지 거리가 짧은 순; {stable}"], ["출처와 수집일", source("cafe")]],
        "convenience": [point, ["반경", "500m 이내 직선거리 (도보 아님)"],
                        ["방식", "개수 기준: GS25·CU·세븐일레븐·이마트24 매장 수의 합 (한 브랜드가 없어도 포함)"],
                        ["동률", "원본 학원 베이스라인의 입력 순서 유지"], ["출처와 수집일", source("convenience")]],
        "quiet": [point, ["반경", "0곳 조건은 500m 이내; 최근접 거리는 반경 제한 없음 (직선거리, 도보 아님)"],
                  ["조건", "1,000세대 이상 · 반경 500m 이내 영업 중 유흥주점 0곳"],
                  ["방식", "최근접 기준: 가장 가까운 유흥주점까지 직선거리가 먼 순"],
                  ["동률", "원본 학원 베이스라인의 입력 순서 유지"],
                  ["후보", f"조건을 만족한 {out['quiet_pool']:,}개 단지"], ["출처와 수집일", source("nightlife", "master")]],
        "emergency": [point, ["반경", "1,000m 이내 직선거리 (도보 아님); 동률 비교 종합병원급 최근접 거리는 반경 제한 없음"],
                      ["방식", "개수 기준: 응급실을 운영하는 의료기관 수 (병의원 정보의 응급실 운영 여부)"],
                      ["동률", f"가장 가까운 종합병원급(종합병원·상급종합병원)까지 거리가 짧은 순; {stable}"],
                      ["출처와 수집일", source("medical")]],
        "gu_best_dong": [*dong, ["선정", "각 구에서 법정동 학원 수가 가장 많은 동 1곳; 구 이름순 표시"]],
        "changes": [["기준점", "신규 단지는 해당 없음(단지 코드 비교); 배정초는 단지 대표 좌표의 통학구역"],
                    ["반경", "해당 없음: 스냅샷 비교"],
                    ["방식", "신규 등록 단지 및 배정초 원문이 변경된 단지의 개수 기준; 최근접 기준 아님"],
                    ["비교", "직전 스냅샷이 없는 항목은 미비교이며, 변경 0건으로 단정하지 않음"],
                    ["동률", "해당 없음: 순위가 아닌 변경 목록 (신규는 마스터 입력순, 배정초는 이전 스냅샷 입력순)"],
                    ["표시", "배정초 원문으로 변경 여부를 판단한 뒤 '(적용시기: …)' 설명을 표시에서만 제거"],
                    ["출처와 수집일", source("master", "school")]],
    }


def changes(out, master_rows, schools, data_month, previous=None, prev_master=None, prev_school=None):
    """Retain both current state and the original monthly comparison basis."""
    out["new_complexes"], out["school_changes"] = [], []
    meta = {"master_compared": False, "school_compared": False}
    old_codes, old_schools = None, None
    current_snapshot = {"master_codes": [r["k-아파트코드"] for r in master_rows], "schools": list(schools.values())}

    def school_index(rows):
        return {(r["name"], r["gu"], r["dong"]): r for r in rows}

    if previous:
        previous_month = previous.get("data_month")
        if previous_month == data_month:
            # Recompute against the monthly basis, not the last same-month state.
            for key in ("new_complexes", "school_changes"):
                out[key] = previous.get(key, [])
            meta.update(previous.get("changes_meta", {}))
            basis = previous.get("comparison_snapshot", {})
            old_codes = set(basis["master_codes"]) if "master_codes" in basis else None
            old_schools = school_index(basis["schools"]) if "schools" in basis else None
            # Legacy artifacts have no comparison basis. Preserve their deltas only
            # if the corresponding source snapshot is unchanged; an explicit CSV
            # supersedes that scope. Uncompared scopes remain uncompared.
            snapshot = previous.get("snapshot", {})
            for field, flag, delta, supplied, basis_value in (
                ("master_codes", "master_compared", "new_complexes", prev_master, old_codes),
                ("schools", "school_compared", "school_changes", prev_school, old_schools),
            ):
                if supplied or basis_value is not None or not (meta.get(flag) or out[delta]):
                    continue
                unchanged = field in snapshot and (
                    set(snapshot[field]) == set(current_snapshot[field]) if field == "master_codes"
                    else school_index(snapshot[field]) == schools
                )
                if not unchanged:
                    option = "--prev-master" if field == "master_codes" else "--prev-school"
                    raise ValueError(f"Same-month {field} changed without a comparison_snapshot; provide {option} or the previous month's --previous JSON")
        else:
            current = date.fromisoformat(data_month + "-01")
            prior = date(current.year - (current.month == 1), current.month - 1 or 12, 1).strftime("%Y-%m")
            if previous_month != prior:
                raise ValueError("--previous must be the immediately previous month or a same-month rerun")
            meta["previous_month"] = previous_month
            snapshot = previous.get("snapshot", {})
            old_codes = set(snapshot["master_codes"]) if "master_codes" in snapshot else None
            old_schools = school_index(snapshot["schools"]) if "schools" in snapshot else None
    if prev_master:
        old_codes = {r["k-아파트코드"] for r in csv_rows(prev_master, "cp949", MASTER_COLUMNS)}
    if prev_school:
        old_schools = baseline(prev_school, BASELINE_COLUMNS["school_zone_baseline"])
    if old_codes is not None:
        meta["master_compared"] = True
        out["new_complexes"] = [{"name": r["k-아파트명"], "gu": r["주소(시군구)"], "dong": r["주소(읍면동)"],
                                 "households": int(f(r["k-전체세대수"], 0) or 0),
                                 "built": (r.get("k-사용검사일-사용승인일") or "")[:7].replace("-", ".")}
                                for r in master_rows if r["k-아파트코드"] not in old_codes]
    if old_schools is not None:
        meta["school_compared"] = True
        clean = lambda text: re.sub(r"\(적용시기.*$", "", text or "").strip()
        out["school_changes"] = [{"name": k[0], "gu": k[1], "dong": k[2],
                                  "from": clean(old_schools[k]["assigned_elementary_school"]),
                                  "to": clean(schools[k]["assigned_elementary_school"])}
                                 for k in old_schools if k in schools and
                                 old_schools[k]["assigned_elementary_school"] != schools[k]["assigned_elementary_school"]]
    out["changes_meta"] = meta
    out["snapshot"] = current_snapshot
    out["comparison_snapshot"] = {}
    if old_codes is not None:
        out["comparison_snapshot"]["master_codes"] = sorted(old_codes)
    if old_schools is not None:
        out["comparison_snapshot"]["schools"] = list(old_schools.values())


def build_rankings(data_dir, *, data_month, source_dates=None, previous=None, prev_master=None, prev_school=None):
    if not re.fullmatch(r"\d{4}-\d{2}", data_month):
        raise ValueError("data_month must be YYYY-MM")
    date.fromisoformat(data_month + "-01")
    data_dir = Path(data_dir)
    sources = load_sources(source_dates)
    loaded = {name: baseline(data_dir / "baseline" / f"{name}.csv", columns)
              for name, columns in BASELINE_COLUMNS.items()}
    ac, sub, cafe, conv, nl, med, tx, schools = (loaded[name] for name in BASELINE_COLUMNS)
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
    changes(out, masters, schools, data_month, previous, prev_master, prev_school)
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
    parser.add_argument("--prev-school", type=Path)
    args = parser.parse_args(argv)
    metadata = args.source_dates
    if metadata is None and (args.data_dir / "derived/home_source_dates.json").exists():
        metadata = args.data_dir / "derived/home_source_dates.json"
    try:
        metadata_path = metadata if metadata is not None and not str(metadata).lstrip().startswith("{") else None
        args.output = validate_output_path(args.output, args.data_dir, (args.prev_master, args.prev_school, metadata_path))
        # Preserve saved changes on same-month CLI reruns even without --previous.
        previous_path = args.previous or (args.output if args.output.exists() else None)
        previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path else None
        if previous is not None and snapshot_path(previous_path).exists():
            previous.update(json.loads(snapshot_path(previous_path).read_text(encoding="utf-8")))
        output = build_rankings(args.data_dir, data_month=args.data_month, source_dates=metadata,
                                previous=previous, prev_master=args.prev_master, prev_school=args.prev_school)
        validate_rankings(output)
        # The web app loads the main file into every worker; the next-month comparison
        # snapshot (all complex codes + school zones, ~575KB) goes to a sidecar it never reads.
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

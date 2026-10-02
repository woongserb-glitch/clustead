"""Read-only monthly home-item scout. Writes only reports and comparison copies.

No baseline builders, network access, LLM, or live analytics connection are used.
"""
import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_home_rankings as home
from scripts import home_price_trend as price
from services.address_dong import gu_from_address, legal_dong_from_address
from scripts.build_academy_baseline import classify_academy
from scripts.build_subway_baseline import canonical_line, station_key
from services.home_billboard_service import DIRECTORY_EVENTS, QUESTIONS, TOPICS

# label, baseline, authoritative count, items, radius, icon, color, source
FACILITIES = {
    "emergency": ("응급실", "medical", "emergency_count_1km", "emergency_items_json", 1000, "cross", "#e5484d", "서울시 병의원 위치 정보"),
    "hospital": ("종합병원급", "medical", "superior_hospital_count_3km", "superior_hospital_items_json", 3000, "cross", "#e5484d", "서울시 병의원 위치 정보"),
    "mart": ("대형마트", "mart", "large_mart_count_3000m", "large_mart_items_json", 3000, "store", "#d97706", "kakao map 기준"),
    "subway": ("지하철역", "subway", "subway_station_count_500m", "subway_items_500m_json", 500, "station", "#2563eb", "서울시 역사마스터 정보"),
    "starbucks": ("스타벅스", "cafe", "스타벅스_count_500m", "cafe_items_json", 500, "store", "#15803d", "kakao map 기준"),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("유효하지 않은 숫자")
    return result


def label(key):
    return {"name": key[0], "gu": key[1], "dong": key[2]}


def reference(path, key, **extra):
    return {"file": str(Path(path).resolve()), "key": list(key), **extra}


def master_rows(path):
    return list(home.csv_rows(path, "cp949", home.MASTER_COLUMNS))


def master_key(row):
    return (row["k-아파트명"], row["주소(시군구)"], row["주소(읍면동)"])


def baseline(path, columns):
    if not path or not path.is_file():
        return None
    result = {}
    for record, row in enumerate(home.csv_rows(path, columns=("name", "gu", "dong", *columns)), 1):
        key = (row["name"], row["gu"], row["dong"])
        if key in result:
            result[key]["duplicate_key"] = True
        else:
            result[key] = {**row, "record": record}
    return result


def item_name(item):
    return (item.get("name") or re.sub(r"^[^\w]+", "", item.get("label", "")).split(" · ")[0]).strip()


def normalized_item(item, kind):
    name = item_name(item)
    result = {**item, "name": name}
    if kind == "subway":
        # Apply both official functions to BOTH months, before set comparison.
        result["name"] = station_key(name)
        lines = item.get("lines") or item.get("line_label", "").split("/")
        result["lines"] = sorted({canonical_line(line.strip(), name) for line in lines if line.strip()})
    result["key"] = home.er_name_key(result["name"])
    return result


def facility_index(rows, kind):
    """Select the count-column number of nearest items, then normalize/deduplicate.

    For old subway data, select BEFORE merging Seoul/Seoul-station entities:
    the old count describes old entities, not the merged station count.
    """
    spec = FACILITIES[kind]
    count_col, item_col = spec[2:4]
    index, catalogue, invalid = {}, set(), []
    for key, row in sorted(rows.items()):
        try:
            if row.get("duplicate_key"):
                raise ValueError("중복 단지 키: 단지 귀속 불명확")
            n_value = number(row[count_col])
            if n_value < 0 or int(n_value) != n_value:
                raise ValueError("잘못된 시설 수")
            n = int(n_value)
            items = json.loads(row[item_col] or "[]")
            if kind == "starbucks":
                items = [item for item in items if item.get("subtype") == "스타벅스"]
            items = sorted(items, key=lambda i: (number(i.get("distance", 0)), item_name(i)))
            if kind == "subway":
                for item in json.loads(row.get("subway_items_json") or "[]") + items:
                    catalogue.add(normalized_item(item, kind)["key"])
            if kind == "emergency":
                near = home.er_index({key: row})[key]
                selected = [next(i for i in items if i["name"] == name) for name in near]
            else:
                selected = items[:n]
            if len(selected) != n or any(not item_name(i) for i in selected):
                raise ValueError("개수 컬럼과 항목 목록 불일치/잘림")
            normalized = {}
            for item in selected:
                item = normalized_item(item, kind)
                existing = normalized.get(item["key"])
                if existing and kind == "subway":
                    existing["lines"] = sorted(set(existing["lines"]) | set(item["lines"]))
                else:
                    normalized.setdefault(item["key"], item)
            index[key] = normalized
            catalogue.update(normalized)
        except (ValueError, TypeError, KeyError, StopIteration) as exc:
            invalid.append({"key": list(key), "record": row["record"], "reason": str(exc)})
    return index, catalogue, invalid


def checks(**extra):
    return {
        "institution_whitespace": "해당 없음", "complex_identity": "해당 없음",
        "rounded_boundary": "해당 없음", "reporting_delay": "해당 없음",
        "source_confirmation": "검증 대기", **extra,
    }


def candidate(kind, identity, title, affected, metrics, evidence, criteria, risk, check, **extra):
    affected = sorted(affected, key=lambda r: (r.get("gu", ""), r.get("dong", ""), r.get("name", "")))
    count = len({(r["name"], r["gu"], r["dong"]) for r in affected})
    digest = hashlib.sha256(encoded([kind, identity]).encode()).hexdigest()[:12]
    return {"id": f"{kind}-{digest}", "kind": kind, "title": title,
            "impact_complex_count": count, "affected_complexes": affected, "metrics": metrics,
            "evidence": evidence, "criteria": criteria, "risks": risk, "checks": check, **extra}


def facility_candidates(kind, current_path, previous_path, stable):
    title, _, count_col, items_col, radius, icon, color, source = FACILITIES[kind]
    columns = (count_col, items_col, "subway_items_json") if kind == "subway" else (count_col, items_col)
    now, old = baseline(current_path, columns), baseline(previous_path, columns)
    if now is None or old is None:
        return [], {"status": "미비교", "reason": "현재 또는 직전 baseline 없음"}
    current, current_catalogue, invalid_now = facility_index(now, kind)
    previous, previous_catalogue, invalid_old = facility_index(old, kind)
    common = set(current) & set(previous) & stable
    groups, suppressed = defaultdict(list), 0
    for key in sorted(common):
        for direction, changed, catalogue in (
            ("added", current[key].keys() - previous[key].keys(), previous_catalogue),
            ("removed", previous[key].keys() - current[key].keys(), current_catalogue),
        ):
            for facility in sorted(changed):
                if kind == "subway" and facility in catalogue:
                    # Station regrouping changes centroids and can cross 500m.
                    # A station already present in the other month's wider catalogue is not new/closed.
                    suppressed += 1
                    continue
                item = (current if direction == "added" else previous)[key][facility]
                groups[(direction, facility)].append({**label(key), "distance_m": item["distance"],
                    "facility": item, "before_count": int(number(old[key][count_col])),
                    "after_count": int(number(now[key][count_col])),
                    "evidence": [reference(previous_path, key, record=old[key]["record"], column=items_col),
                                 reference(current_path, key, record=now[key]["record"], column=items_col)]})
    results = []
    for (direction, facility), affected in sorted(groups.items()):
        added = direction == "added"
        word = "추가" if added else "소실"
        name = sorted(a["facility"]["name"] for a in affected)[0]
        config = {"heading": f"주변 {title} {word} 후보", "icon": icon, "color": color,
                  "label": f"{title} {word} 후보", "radius": f"반경 {radius:,}m",
                  "empty": f"이번 달 {title} {word} 후보가 없습니다.",
                  "uncompared": f"직전 달 {title} 정보가 없어 비교하지 않았습니다."}
        nearest = min(affected, key=lambda r: (r["distance_m"], r["gu"], r["dong"], r["name"]))
        results.append(candidate(kind, [direction, facility], f"{name} · {title} {word} 후보", affected,
            {"direction": direction, "facility_name": name, "radius_m": radius},
            [e for a in affected for e in a["evidence"]],
            [["기준점", "단지 대표 좌표"], ["반경", f"직선거리 {radius:,}m"],
             ["방식", "동일 단지의 직전·현재 시설 목록을 이름 공백 정규화 후 비교, 개수 컬럼 우선"], ["출처", source]],
            ["데이터 추가·소실이며 실제 신설·폐업은 기관 공지와 원천 이력으로 확인해야 합니다.",
             "동명 기관·좌표 이동·수집 범위 변경 여부를 확인해야 합니다."],
            checks(institution_whitespace="통과", complex_identity="통과: 양쪽 동일 코드·이름 단지만",
                   rounded_boundary="통과: 개수 컬럼 우선", subway_aliases="통과" if kind == "subway" else "해당 없음"),
            question=f"이번 갱신에서 주변 {title} 정보가 {word}된 단지는?",
            first_answer=f"{name}: {len(affected)}개 단지, 가장 가까운 곳은 {nearest['name']}({nearest['distance_m']:,}m)",
            change_kind={"key": f"{kind}_{direction}", **config}))
    return results, {"status": "비교", "compared_complexes": len(common),
                     "excluded_complexes": len(set(now) | set(old)) - len(common),
                     "invalid_current": invalid_now, "invalid_previous": invalid_old,
                     "subway_existing_station_radius_changes_excluded": suppressed}


def academy_candidates(current_path, previous_path, stable):
    column = "academy_count_1000m"
    now, old = baseline(current_path, (column,)), baseline(previous_path, (column,))
    if now is None or old is None:
        return [], {"status": "미비교", "reason": "현재 또는 직전 학원 baseline 없음"}
    result, invalid = [], []
    for key in sorted(set(now) & set(old) & stable):
        try:
            if now[key].get("duplicate_key") or old[key].get("duplicate_key"):
                raise ValueError("중복 단지 키")
            before, after = number(old[key][column]), number(now[key][column])
            if min(before, after) < 0 or int(before) != before or int(after) != after:
                raise ValueError("잘못된 학원 수")
        except (ValueError, TypeError):
            invalid.append(list(key))
            continue
        if after <= before:
            continue
        before, after = int(before), int(after)
        result.append(candidate("academy_growth", key, f"{key[0]} · 1km 학원 {after - before}곳 증가", [label(key)],
            {"before": before, "after": after, "increase": after - before},
            [reference(previous_path, key, record=old[key]["record"], column=column),
             reference(current_path, key, record=now[key]["record"], column=column)],
            [["기준점", "단지 대표 좌표"], ["반경", "직선거리 1,000m"],
             ["방식", "같은 단지 주변 전체 학원 개수의 직전 대비 증가(1곳 이상)"], ["출처", "서울시 학원·교습소 정보"]],
            ["학원 개수 증가이며 교육 성과를 뜻하지 않습니다. 좌표·분류·등록 변경을 확인해야 합니다."],
            checks(complex_identity="통과", rounded_boundary="통과: 개수 컬럼 비교"),
            question="1km 안 학원 수가 가장 많이 늘어난 아파트는?",
            first_answer=f"{key[0]}: {before}곳 → {after}곳(+{after - before}곳)",
            change_kind={"key": "academy_growth", "heading": "주변 학원이 늘어난 단지", "icon": "pin",
                         "color": "#7c3aed", "label": "학원 수 증가", "radius": "반경 1km",
                         "empty": "이번 달 학원이 늘어난 단지가 없습니다.", "uncompared": "직전 학원 정보가 없어 비교하지 않았습니다."}))
    return result, {"status": "비교", "increased_complexes": len(result), "invalid_keys": invalid}


def academy_address_snapshot(path, month):
    """Save auditable source-row/address copies and dong aggregates for next month only."""
    if not path.is_file():
        return {"schema_version": 1, "data_month": month, "status": "미집계", "reason": "학원 원본 없음"}
    rows, groups, skipped, seen, duplicates = [], defaultdict(Counter), 0, set(), 0
    for record, row in enumerate(home.csv_rows(path), 1):
        if (row.get("등록상태명") or "").strip() != "개원":
            continue
        subtype = classify_academy(row)
        if subtype not in ("입시/보습", "수학", "영어"):
            continue
        address = row.get("도로명상세주소") or ""
        # 홈 순위와 같은 판별(services.address_dong): 건물명 제외, 구는 도로명주소 우선.
        dong = legal_dong_from_address(address)
        gu = gu_from_address(row.get("도로명주소")) or (row.get("행정구역명") or "").strip()
        if not dong or not gu:
            skipped += 1
            continue
        source_id = row.get("학원지정번호") or ""
        identity = source_id or (gu, row.get("학원명"), address)
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        groups[(gu, dong)][subtype] += 1
        rows.append({"source_record": record, "source_id": source_id, "name": row.get("학원명"),
                     "gu": gu, "dong": dong, "address": address, "subtype": subtype})
    return {"schema_version": 1, "data_month": month, "status": "저장", "source": str(path.resolve()),
            "definition": "개원 중 입시/보습·수학·영어, 주소 법정동, 학원지정번호 중복 제거",
            "unlocated_rows": skipped, "duplicate_rows_excluded": duplicates,
            "dong_counts": [{"gu": g, "dong": d, "total": sum(c.values()), "subtypes": dict(c)}
                            for (g, d), c in sorted(groups.items())],
            "source_rows": sorted(rows, key=lambda r: (r["gu"], r["dong"], r["source_id"], r["name"] or ""))}


def new_complex_candidates(masters, old_masters, current_path, previous_path, month):
    if old_masters is None:
        return [], {"status": "미비교", "reason": "직전 단지 마스터 없음"}
    old_codes = {r["k-아파트코드"] for r in old_masters}
    old_keys = {master_key(r) for r in old_masters}
    results = []
    for row in masters:
        code, key = row["k-아파트코드"], master_key(row)
        if not code or code in old_codes:
            continue
        hh = int(home.f(row.get("k-전체세대수"), 0) or 0)
        built = (row.get("k-사용검사일-사용승인일") or "")[:10]
        recent_large = hh >= 1000 and built[:7] == month
        results.append(candidate("new_complex", code, f"{key[0]} · 신규 등록 {hh:,}세대", [label(key)],
            {"code": code, "households": hh, "approved_date": built, "large_recent_approval": recent_large},
            [reference(current_path, [code], row=row), reference(previous_path, [code], absent=True)],
            [["기준점", "단지 코드"], ["방식", "직전 마스터에 없던 코드, 1,000세대 이상·기준월 사용승인 별도 표시"],
             ["출처", "서울시 공동주택 아파트 정보"]],
            ["신규 등록이 입주 시작을 뜻하지 않습니다. 실제 입주일을 확인해야 합니다."] +
            (["같은 이름·주소 키가 직전 마스터에 있어 코드 변경 가능성이 있습니다."] if key in old_keys else []),
            checks(complex_identity="확인 필요: 코드 신규"),
            question="이번 갱신에서 새로 등록된 아파트는?", first_answer=f"{key[0]}: {hh:,}세대, 사용승인 {built or '기록 없음'}",
            change_kind={"key": "new_complex", "heading": "새로 등록된 단지", "icon": "pin", "color": "#2563eb",
                         "label": "신규 등록", "radius": "", "empty": "신규 등록 단지가 없습니다.",
                         "uncompared": "직전 단지 정보가 없어 비교하지 않았습니다."}))
    return results, {"status": "비교", "new_complexes": len(results)}


def rank_changes(current, previous, current_path, previous_path):
    if previous is None:
        return [], {"status": "미비교", "reason": "직전 월 home_rankings.json 사본 없음"}
    if previous.get("data_month") != price.month_shift(current["data_month"], -1):
        return [], {"status": "미비교", "reason": "직전 월과 다른 순위 사본"}
    result, skipped = [], []
    for topic, *_ in TOPICS:
        if topic in ("gu_best_dong",):
            continue  # district winners have no city-wide ordinal rank
        if topic not in current or topic not in previous:
            skipped.append(topic)
            continue
        if current.get("definitions", {}).get(topic) != previous.get("definitions", {}).get(topic) and topic == "subway":
            skipped.append(topic)
            continue
        def rows(data):
            return {tuple(r.get(k, "") for k in ("name", "gu", "dong")): (i, r)
                    for i, r in enumerate(data[topic][:5], 1)}
        now, old = rows(current), rows(previous)
        moved = [{**label(k), "before_rank": old[k][0] if k in old else None,
                  "after_rank": now[k][0] if k in now else None}
                 for k in sorted(now.keys() | old.keys()) if now.get(k, (None,))[0] != old.get(k, (None,))[0]]
        if not moved:
            continue
        complexes = [r for r in moved if r["name"]]
        result.append(candidate("top5_change", topic, f"{QUESTIONS[topic]} · TOP 5 변동", complexes,
            {"topic": topic, "moved_rows": moved, "current_top5": current[topic][:5], "previous_top5": previous[topic][:5]},
            [reference(previous_path, [topic]), reference(current_path, [topic])],
            current.get("definitions", {}).get(topic, []),
            ["순위권 밖은 순위 미상입니다. 정의·표본·동률·단지명 변경을 확인해야 합니다."],
            checks(complex_identity="확인 필요: 순위 사본의 이름·구·동 키 비교")))
    return result, {"status": "비교", "changed_topics": len(result), "skipped_topics": skipped}


def price_candidates(data_dir, masters, served, month):
    start, _, _, end = price.windows(month)
    raw_dir = data_dir / "transactions/raw/molit"
    direct = price.load_direct_trade_keys(raw_dir, {int(start[:4]), int(end[:4])})
    transaction_path = data_dir / "transactions/transaction_master.csv"
    mapping_path = data_dir / "transactions/apartment_transaction_mapping.csv"
    mappings = list(home.csv_rows(mapping_path))
    source_keys = defaultdict(list)
    for transaction_key, targets in price.mapping_lookup(mappings, masters).items():
        if len(targets) == 1:
            source_keys[next(iter(targets))].append(list(transaction_key))
    trades, stats = price.collect_trades(home.csv_rows(transaction_path), mappings,
                                        masters, served, start, end, direct)
    up, down, meta = price.build_price_trend(trades, stats, masters, served, month, 20)
    results = []
    for direction, rows in (("price_up", up), ("price_down", down)):
        for rank, row in enumerate(rows, 1):
            key = (row["name"], row["gu"], row["dong"])
            criteria = [["기준점", "같은 단지·같은 전용면적(㎡ 정수)"],
                ["방식", f"{meta['recent_start']}~{meta['recent_end']}와 {meta['prev_start']}~{meta['prev_end']} 매매 중앙값 비교, 분양·300세대 이상·기간별 5건 이상·직거래 제외"],
                ["출처", "국토교통부 아파트 매매 실거래가"]]
            results.append(candidate(direction, [*key, row["area"]],
                f"{row['name']} {row['area']}㎡ · 매매 {row['change_pct']:+.1f}%", [label(key)],
                {**row, "price_rank": rank},
                [reference(transaction_path, key, area=row["area"], period=[start, end],
                           source_key_fields=["gu", "dong", "apartment_name", "road_address"],
                           normalized_source_keys=sorted(source_keys[key])),
                 reference(mapping_path, key), reference(data_dir / "apartment/seoul_apartments.csv", key),
                 {"file": str(raw_dir.resolve()), "key": [f"trade_{y}.xlsx" for y in sorted({int(start[:4]), int(end[:4])})]}],
                criteria, ["면적 정수 안의 층·동·수리 상태 차이와 표본 구성 변화는 남습니다."],
                checks(complex_identity="통과: 기존 정확 매핑 재사용", reporting_delay=f"통과: 기준월 {month} 제외"),
                question=QUESTIONS[direction], first_answer=f"{row['name']} {row['area']}㎡: {row['change_pct']:+.1f}%"))
    return results, meta


def topic_interest_copy(path, month, data_dir):
    """Same visitor/day distinct definition as analytics_service.topic_interest.

    Date range is pinned to this report's month end (30 days), never wall-clock
    time. immutable=1 prevents journal/SHM creation on a consistent server copy.
    """
    end = date.fromisoformat(price.month_shift(month, 1) + "-01")
    start = end - timedelta(days=30)
    meta = {"status": "미집계", "start": start.isoformat(), "end_exclusive": end.isoformat(),
            "definition": "home_topic_click + ranking_view, 같은 방문자·하루 중복 제거(방문자-일)",
            "note": "노출 수가 아니라 클릭·순위 조회입니다. 날짜 간 동일 방문자도 각각 셉니다."}
    if path is None:
        return {**meta, "reason": "--analytics-db 서버 사본을 지정하지 않음"}
    path = path.resolve()
    for root in (data_dir.resolve() / "analytics", (ROOT / "data").resolve() / "analytics"):
        if path.is_relative_to(root):
            raise ValueError("개발 PC의 data/analytics DB는 사용할 수 없습니다. 별도 서버 사본을 지정하세요.")
    if not path.is_file():
        return {**meta, "reason": "지정한 서버 분석 DB 사본 없음"}
    if any(p.exists() and p.stat().st_size for p in (Path(str(path) + "-wal"), Path(str(path) + "-journal"))):
        return {**meta, "reason": "단독 DB 사본이 아님: SQLite backup으로 일관된 서버 사본 필요"}
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            marks = ",".join("?" for _ in DIRECTORY_EVENTS)
            rows = conn.execute("SELECT path, COUNT(DISTINCT visitor_hash || '|' || day) FROM event "
                f"WHERE event_type IN ({marks}) AND day >= ? AND day < ? AND path IS NOT NULL GROUP BY path",
                (*DIRECTORY_EVENTS, start.isoformat(), end.isoformat())).fetchall()
    except sqlite3.Error as exc:
        return {**meta, "reason": f"서버 사본 조회 실패: {exc}"}
    finally:
        if "conn" in locals():
            conn.close()
    counts = dict(rows)
    topics = [{"topic": key, "question": QUESTIONS[key], "path": f"/rankings/{slug}",
               "visitor_days": counts.get(f"/rankings/{slug}", 0)} for key, slug, *_ in TOPICS]
    topics.sort(key=lambda r: (-r["visitor_days"], r["topic"]))
    return {**meta, "status": "집계", "source": str(path), "topics": topics,
            "low_interest": [r["topic"] for r in topics if r["visitor_days"] <= 1],
            "caution": "관심 0~1은 노출 기회나 집계 기간이 부족한 결과일 수 있습니다."}


def candidate_order(row):
    return (-row["impact_complex_count"], -row["metrics"].get("increase", 0),
            row["metrics"].get("price_rank", 0), row["kind"], row["title"], row["id"])


def recommendations(candidates):
    selected, kinds = [], set()
    for row in candidates:
        if not row.get("question") or row["kind"] in kinds:
            continue
        selected.append({k: row[k] for k in ("id", "kind", "question", "first_answer", "criteria", "risks", "checks")})
        if "change_kind" in row:
            selected[-1]["change_kind"] = row["change_kind"]
        kinds.add(row["kind"])
        if len(selected) == 5:
            break
    return selected


def render_report(report):
    candidates = report["candidates"]
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = [f"# {report['data_month']} 월간 홈 아이템 스카우트", "",
             f"총 **{len(candidates):,}개 후보**. 영향 단지 수가 큰 순서이며 첫 화면에는 상위 10개만 표시합니다.",
             "시설 추가·소실은 데이터에서 발견한 후보입니다. 실제 신설·폐업은 검증 대기입니다.", "",
             "| 순서 | 후보 | 영향 단지 |", "|---:|---|---:|"]
    for i, row in enumerate(candidates[:10], 1):
        lines.append(f"| {i} | {cell(row['title'])} | {row['impact_complex_count']:,} |")
    lines += ["", f"- TOP 5 변동: **{report['comparison']['top5']['status']}** — {report['comparison']['top5'].get('reason', '직전 월 사본과 비교')}",
              f"- 질문 인기: **{report['analytics']['status']}** — {report['analytics'].get('reason', '서버 사본의 클릭·조회 집계')}",
              "- 동 단위 학원 증가: 이번 달 미비교. 주소 집계 사본을 저장해 다음 달 비교 기준으로 사용합니다.",
              "- 상세 수치·영향 단지·근거 행·점검 결과: [candidates.json](candidates.json)", "",
              "<details>", "<summary>질문 제안·산정 기준·위험 요소·변화 주제 설정</summary>", ""]
    for row in report["recommendations"]:
        lines += [f"### {row['question']}", "", f"1위 답 후보: {row['first_answer']}", ""]
        lines.extend(f"- {name}: {value}" for name, value in row["criteria"])
        lines += ["", "위험 요소: " + " / ".join(row["risks"]), ""]
        if row.get("change_kind"):
            lines += ["`CHANGE_KINDS` 제안(사용자 선택 후 구현, 아이콘은 기존 `CHANGE_ICONS` 키):", "", "```json",
                      encoded(row["change_kind"]).strip(), "```", ""]
    lines += ["</details>", "", "<details>", "<summary>비교 범위·점검 결과·질문 인기</summary>", "",
              "## 비교 기준", "", "- 보고서 기준월과 원천 수집일은 다릅니다. 기준월 라벨을 시설 개업월로 해석하지 않습니다.",
              f"- 현재 데이터: `{report['inputs']['data_dir']}`", f"- 직전 자료: `{report['inputs']['prev_dir'] or '없음'}`",
              f"- 가격: {report['price_meta']['recent_start']}~{report['price_meta']['recent_end']} 대 {report['price_meta']['prev_start']}~{report['price_meta']['prev_end']}",
              f"- 가격 비교 가능 단지·면적 조합: {report['price_meta']['compared']:,}, 직거래 제외 {report['price_meta']['direct_excluded']:,}건", "",
              "## 필수 점검", "",
              "1. 기관명 공백을 제거한 뒤 비교합니다(중앙보훈·한일·안암·양지병원 사례).",
              "2. 직전 달에 없던 단지 키와 코드가 바뀐 단지는 시설 변화에서 제외합니다(목동성원 사례).",
              "3. 반올림 거리 대신 개수 컬럼을 우선합니다. 개수에 맞는 항목이 없으면 제외합니다.",
              "4. 가격은 신고 기한 30일을 고려해 기준월을 제외합니다(2026-09 부분 신고 사례).",
              "5. 지하철은 양쪽에 canonical_line·station_key를 적용하고 기존 역의 반경 변화를 제외합니다.", "",
              "| 영역 | 상태 | 비교 단지 / 제외 |", "|---|---|---|"]
    for key, meta in report["comparison"].items():
        lines.append(f"| {key} | {meta['status']} | {meta.get('compared_complexes', '—')} / {meta.get('excluded_complexes', '—')} |")
    lines += ["", "### 질문 인기", "", f"기간(KST): {report['analytics']['start']} 이상 ~ {report['analytics']['end_exclusive']} 미만.",
              "같은 방문자의 하루 반복을 1로 세는 방문자-일입니다. 노출 수나 기간 전체 순방문자 수가 아닙니다.", ""]
    if report["analytics"]["status"] == "집계":
        for row in report["analytics"]["topics"]:
            lines.append(f"- {row['question']}: {row['visitor_days']} 방문자-일" + (" (저관심·집계 기회 확인)" if row["visitor_days"] <= 1 else ""))
    else:
        lines.append("미집계: " + report["analytics"]["reason"] + ". 0건으로 간주하지 않습니다.")
    lines += ["", "</details>", "", "<details>", "<summary>전체 후보 목록</summary>", "",
              "| 순서 | 후보 | 영향 단지 | 후보 ID |", "|---:|---|---:|---|"]
    for i, row in enumerate(candidates, 1):
        lines.append(f"| {i} | {cell(row['title'])} | {row['impact_complex_count']} | {row['id']} |")
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def validate_outputs(paths, protected_dirs, inputs):
    for path in paths:
        resolved = path.resolve()
        if any(resolved.is_relative_to(root.resolve()) for root in protected_dirs if root):
            raise ValueError(f"출력은 data·백업 디렉터리 밖이어야 합니다: {path}")
        for source in inputs:
            if source and (resolved == source.resolve() or
                           (resolved.exists() and source.exists() and resolved.samefile(source))):
                raise ValueError(f"출력이 입력 파일과 충돌합니다: {path}")


def write_copy(path, contents):
    """Atomically preserve the exact source bytes, including its newline format."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_report(data_dir, prev_dir, month, rankings_path, previous_path, analytics_db):
    current = read_json(rankings_path)
    if current.get("data_month") != month:
        raise ValueError("현재 home_rankings.json 기준월이 --data-month와 다릅니다. 재빌드하지 말고 올바른 사본을 지정하세요.")
    home.validate_rankings(current)
    previous = read_json(previous_path) if previous_path.is_file() else None
    current_master_path = data_dir / "apartment/seoul_apartments.csv"
    previous_master_path = prev_dir / "apartment/seoul_apartments.csv" if prev_dir else None
    if prev_dir and not previous_master_path.is_file():
        previous_master_path = prev_dir / "seoul_apartments.csv"
    masters = master_rows(current_master_path)
    old_masters = master_rows(previous_master_path) if previous_master_path and previous_master_path.is_file() else None
    master = {master_key(r): r for r in masters}
    ac = baseline(data_dir / "baseline/academy_baseline.csv", ()) or {}
    sub = baseline(data_dir / "baseline/subway_baseline.csv", ()) or {}
    served = {k for k in set(ac) & set(sub) & set(master)
              if not ac[k].get("duplicate_key") and not sub[k].get("duplicate_key")}
    if old_masters is None:
        stable = set()  # do not claim master-identity validation without a previous master
    else:
        old_by_code = {r["k-아파트코드"]: master_key(r) for r in old_masters}
        stable = {k for k, r in master.items() if old_by_code.get(r["k-아파트코드"]) == k} & served
    candidates, comparison = [], {}
    for kind, spec in FACILITIES.items():
        now_path = data_dir / f"baseline/{spec[1]}_baseline.csv"
        old_path = prev_dir / f"baseline/{spec[1]}_baseline.csv" if prev_dir else None
        rows, meta = facility_candidates(kind, now_path, old_path, stable)
        if old_masters is None:
            meta = {"status": "미비교", "reason": "직전 단지 마스터 없음"}
        candidates.extend(rows)
        comparison[kind] = meta
    rows, comparison["academy_growth"] = academy_candidates(data_dir / "baseline/academy_baseline.csv",
        prev_dir / "baseline/academy_baseline.csv" if prev_dir else None, stable)
    if old_masters is None:
        comparison["academy_growth"] = {"status": "미비교", "reason": "직전 단지 마스터 없음"}
    candidates.extend(rows)
    rows, comparison["new_complex"] = new_complex_candidates(masters, old_masters, current_master_path, previous_master_path, month)
    candidates.extend(rows)
    rows, comparison["top5"] = rank_changes(current, previous, rankings_path, previous_path)
    candidates.extend(rows)
    rows, price_meta = price_candidates(data_dir, master, served, month)
    candidates.extend(rows)
    candidates.sort(key=candidate_order)
    report = {"schema_version": 1, "data_month": month,
              "inputs": {"data_dir": str(data_dir.resolve()), "prev_dir": str(prev_dir.resolve()) if prev_dir else None,
                         "rankings": str(rankings_path.resolve()), "previous_rankings": str(previous_path.resolve()),
                         "source_dates": current.get("sources", {})},
              "comparison": comparison, "price_meta": price_meta,
              "analytics": topic_interest_copy(analytics_db, month, data_dir),
              "candidates": candidates, "recommendations": recommendations(candidates)}
    return report, academy_address_snapshot(data_dir / "academy/academy_geocoded.csv", month)


def main(argv=None):
    parser = argparse.ArgumentParser(description="월간 홈 아이템 후보를 읽기 전용으로 조사합니다.")
    parser.add_argument("--data-month", required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--prev-dir", type=Path, help="갱신 전 baseline/·단지 마스터가 있는 백업 폴더")
    parser.add_argument("--rankings", type=Path, help="현재 기준월 home_rankings.json")
    parser.add_argument("--previous-rankings", type=Path, help="직전 월 사본(기본: 출력 폴더의 직전 월)")
    parser.add_argument("--analytics-db", type=Path, help="서버에서 받은 독립된 읽기 전용 SQLite 사본(로컬 개발 DB 금지)")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/home-scout")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", args.data_month):
            raise ValueError("--data-month는 YYYY-MM 형식이어야 합니다.")
        date.fromisoformat(args.data_month + "-01")
        if args.prev_dir and not args.prev_dir.is_dir():
            raise ValueError("--prev-dir 폴더가 없습니다.")
        rankings = args.rankings or args.data_dir / "derived/home_rankings.json"
        previous = args.previous_rankings or args.output_root / price.month_shift(args.data_month, -1) / "home_rankings.json"
        folder = args.output_root / args.data_month
        outputs = [folder / name for name in ("candidates.json", "report.md", "home_rankings.json",
                   "home_rankings.snapshot.json", "academy_address_counts.json")]
        inputs = [rankings, previous, home.snapshot_path(rankings), args.analytics_db]
        validate_outputs(outputs, [args.data_dir, ROOT / "data", args.prev_dir], inputs)
        report, academy_copy = build_report(args.data_dir, args.prev_dir, args.data_month, rankings, previous, args.analytics_db)
        texts = {outputs[0]: encoded(report), outputs[1]: render_report(report),
                 outputs[4]: encoded(academy_copy)}
        copies = {outputs[2]: rankings.read_bytes()}
        sidecar = home.snapshot_path(rankings)
        if sidecar.is_file():
            copies[outputs[3]] = sidecar.read_bytes()
        else:
            # Explicit absence prevents a stale same-month sidecar being mistaken for this run's snapshot.
            texts[outputs[3]] = encoded({"data_month": args.data_month, "status": "미보관", "reason": "원본 snapshot 없음"})
        folder.mkdir(parents=True, exist_ok=True)
        for path, text in texts.items():
            home.write_atomic(path, text)
        for path, contents in copies.items():
            write_copy(path, contents)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(f"완료: {folder / 'report.md'} (후보 {len(report['candidates'])}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

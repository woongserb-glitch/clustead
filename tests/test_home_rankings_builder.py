"""Verify the offline builder against the unmodified handover oracle and edge cases."""
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_home_rankings as builder
from scripts import home_price_trend as price_trend

# 인계 기준 답(compute_home_preview.py)에는 가격 추이 주제가 없다.
# 국민평형 가격 조건은 2026-10-01 사용자 결정으로 최근 6개월 평균으로 바뀌어 기준 답과 다르다.
ORACLE_TOPICS = tuple(t for t in builder.TOPICS if not t.startswith("price_") and t != "value_combo")
from services.home_billboard_service import validate_rankings


def write_csv(path, rows, encoding="utf-8-sig"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def er_items(count, names=("응급A", "응급B", "응급C")):
    """1km 안 응급실 count 곳 + 반경 밖 1곳 (거리 오름차순이 아니게 섞는다)."""
    items = [{"name": "원거리병원", "distance": 2500}] + [
        {"name": name, "distance": 100 * (n + 1)} for n, name in enumerate(names[:count])]
    return json.dumps(items, ensure_ascii=False)


def dong_name(n):
    """한글 동 이름(숫자로 시작하는 '60동'은 건물 동 번호로 보고 제외하므로 픽스처에서 쓰지 않는다)."""
    return "가나다라마바사아자차"[n % 10] + "가나다라마바사"[n // 10] + "동"


@pytest.fixture(autouse=True)
def no_raw_workbooks(monkeypatch):
    """빌더 테스트는 국토부 원본 엑셀 없이 돈다(직거래 키는 빈 집합)."""
    monkeypatch.setattr(price_trend, "load_direct_trade_keys", lambda raw_dir, years: set())


@pytest.fixture
def dataset(tmp_path):
    """More than fifty rows, boundary filters, stable ties and malformed dong data."""
    data = tmp_path / "data"
    rows = {name: [] for name in builder.BASELINE_COLUMNS}
    schools, summaries = [], []  # the handover oracle still reads these; the builder no longer does
    trades, mappings = [], []
    masters = []
    for i in range(70):
        ident = {"name": f"단지{70-i:02}", "gu": "가구", "dong": "가동"}
        masters.append({"k-아파트코드": f"code-{i}", "k-아파트명": ident["name"],
                        "주소(시군구)": ident["gu"], "주소(읍면동)": ident["dong"],
                        "k-전체세대수": [299, 300, 999, 1000][i] if i < 4 else 1000,
                        "k-사용검사일-사용승인일": "2026-09-15"})
        metrics = {
            "academy_baseline": {"exam_count": 100 - i // 3, "math_count": 10, "english_count": 5,
                                 "academy_count_500m": i % 3, "academy_count_1000m": 1000 - i},
            "subway_baseline": {"nearest_subway_distance": 501 if i == 6 else 500 if i == 7 else 400,
                                "nearest_subway_name": "가역", "subway_line_count_500m": 3 - i % 3,
                                "subway_station_count_500m": 5 - i % 5,
                                "subway_items_500m_json": json.dumps([{"name": "가역", "lines": ["2호선", "경의중앙선", "1호선"][:3 - i % 3]}],
                                                                     ensure_ascii=False)},
            "cafe_baseline": {"스타벅스_count_500m": 3, "nearest_스타벅스_distance": "" if i == 8 else 100 + i % 3},
            "convenience_baseline": {brand + "_count_500m": 1 for brand in builder.BRANDS},
            "nightlife_baseline": {"nightlife_count_500m": "" if i == 9 else 1 if i == 10 else 0,
                                   "nightlife_nearest_any_distance": "" if i == 11 else 0 if i == 12 else 1000 + i // 2},
            "medical_baseline": {"emergency_count_1km": 3 - i % 2, "nearest_superior_hospital_distance": 200 + i % 3,
                                 "nearest_superior_hospital_name": "종합병원",
                                 "emergency_items_json": er_items(3 - i % 2)},
        }
        schools.append({**ident, "assigned_elementary_school": "나초"})
        # 인계 기준 답은 2025.1~ 평균(transaction_summary)을 읽고, 빌더는 최근 6개월 실거래를 읽는다.
        summaries.append({**ident, "avg_trade_amount_84": 100000 if i == 4 else "" if i == 5 else 99999})
        if i != 5:  # 가격 없음
            trades += [{"transaction_type": "trade", "gu": "가구", "dong": "가동", "apartment_name": ident["name"],
                        "road_address": f"{ident['name']}로 1", "contract_date": f"2026-0{month}-10", "area_m2": "84.9",
                        "floor": str(month), "trade_price_manwon": "100000" if i == 4 else "99999"}
                       for month in (4, 5, 6)]
        mappings.append({"livefit_name": ident["name"], "gu": "가구", "dong": "가동", "transaction_apt_name": ident["name"],
                         "transaction_road_address": f"{ident['name']}로 1", "verified": "Y"})
        for name in rows:
            if name == "subway_baseline" and i == 69:
                continue  # common academy/subway key set is intentional
            rows[name].append({**ident, **metrics[name], "unused_poi_json": '[{"ignored":true}]'})
    for name, values in rows.items():
        write_csv(data / "baseline" / f"{name}.csv", values)
    write_csv(data / "baseline/school_zone_baseline.csv", schools)
    write_csv(data / "baseline/transaction_summary.csv", summaries)
    write_csv(data / "apartment/seoul_apartments.csv", masters, "cp949")
    academies = []
    for i in range(60):
        for course in ("수학", "영어"):
            academies.append({"등록상태명": "개원", "도로명상세주소": f"도로 ({dong_name(60-i)}, 건물)",
                              "행정구역명": "가구" if i < 30 else "나구", "학원명": "가학원", "교습과정명": course})
    academies.extend([
        {"등록상태명": "개원", "도로명상세주소": "주소에 법정동 없음", "행정구역명": "가구", "학원명": "학원", "교습과정명": "보습"},
        {"등록상태명": "개원", "도로명상세주소": "도로 (가동)", "행정구역명": "", "학원명": "학원", "교습과정명": "영어"},
        {"등록상태명": "폐원", "도로명상세주소": "도로 (가동)", "행정구역명": "가구", "학원명": "학원", "교습과정명": "영어"},
        {"등록상태명": "개원", "도로명상세주소": "도로 (가동)", "행정구역명": "가구", "학원명": "학원", "교습과정명": "미술"},
    ])
    write_csv(data / "academy/academy_geocoded.csv", academies)
    write_csv(data / "transactions/transaction_master.csv", trades)
    write_csv(data / "transactions/apartment_transaction_mapping.csv", mappings)
    # The reference dynamically imports its classifier relative to REPO.
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/build_academy_baseline.py", tmp_path / "scripts/build_academy_baseline.py")
    return data


def run_oracle(data, monkeypatch, prev_master=None):
    script = ROOT / "outputs/clustead-home-billboard/compute_home_preview.py"
    spec = importlib.util.spec_from_file_location("home_preview_oracle", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REPO", data.parent)
    output = data.parent / "oracle.json"
    argv = [str(script), "--output", str(output)]
    if prev_master:
        argv.extend(["--prev-master", str(prev_master)])
    monkeypatch.setattr(sys, "argv", argv)
    module.main()
    return json.loads(output.read_text(encoding="utf-8"))


def csv_fingerprints(data):
    return {str(p.relative_to(data)): hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*.csv")}


def test_top_five_exactly_matches_unmodified_reference(dataset, monkeypatch):
    before = csv_fingerprints(dataset)
    actual = builder.build_rankings(dataset, data_month="2026-09")
    expected = run_oracle(dataset, monkeypatch)
    for key in ORACLE_TOPICS:
        # 노선 이름(line_names)은 기준 답 이후에 더한 표시용 필드다.
        assert [{k: v for k, v in r.items() if k != "line_names"} for r in actual[key][:5]] == expected[key], key
    for key in ("quiet_pool", "dong_academy_meta", "new_complexes"):
        assert actual[key] == expected[key], key
    assert len(actual["academy"]) == len(actual["dong_academy"]) == 50
    assert len(actual["quiet"]) == len(actual["value_combo"]) == 50
    assert actual["convenience"][0]["name"] == "단지70"  # never use name as a new tie breaker
    assert actual["dong_academy"][0]["dong"] == dong_name(60)
    assert actual["dong_academy_meta"] == {"counted": 120, "no_dong": 2}
    assert csv_fingerprints(dataset) == before
    validate_rankings(actual)


def test_thresholds_and_missing_values_keep_reference_filters(dataset):
    actual = builder.build_rankings(dataset, data_month="2026-09")
    combo = {row["name"] for row in actual["value_combo"]}
    assert {"단지69", "단지68", "단지67", "단지63"} <= combo  # 300hh / 999hh / 1,000hh / exactly 500m
    assert not {"단지70", "단지66", "단지65", "단지64"} & combo  # 299hh / price10억 / missing price / 501m
    assert actual["value_combo_pool"] == 65
    assert actual["quiet_pool"] == 62  # 69 common keys minus 3 small + four invalid nightlife values
    quiet = {row["name"] for row in actual["quiet"]}
    assert not {"단지70", "단지69", "단지68", "단지61", "단지60", "단지59", "단지58"} & quiet


def test_delta_raw_comparison_and_future_snapshot_without_old_csv(dataset, monkeypatch, tmp_path):
    master = list(builder.csv_rows(dataset / "apartment/seoul_apartments.csv", "cp949", builder.MASTER_COLUMNS))
    medical_columns = ("name", "gu", "dong", *builder.BASELINE_COLUMNS["medical_baseline"])
    medical = list(builder.csv_rows(dataset / "baseline/medical_baseline.csv", columns=medical_columns))
    old_master = tmp_path / "previous-master.csv"
    old_medical = tmp_path / "previous-medical.csv"
    write_csv(old_master, master[:-1], "cp949")
    previous = [dict(r) for r in medical]
    previous[0].update(emergency_count_1km=2, emergency_items_json=er_items(2))        # 단지70: 응급C 신규
    previous[1].update(emergency_items_json=er_items(2, ("응급 A", "응급B")))          # 띄어쓰기만 다름: 신규 아님
    previous[2].update(name="옛이름단지", emergency_count_1km=0, emergency_items_json="[]")  # 이름 바뀐 단지: 비교 제외
    write_csv(old_medical, previous[:-1])  # 마지막 단지는 신규 등록이라 new_complexes 에만 나온다
    actual = builder.build_rankings(dataset, data_month="2026-09", prev_master=old_master, prev_medical=old_medical)
    expected = run_oracle(dataset, monkeypatch, old_master)
    assert actual["new_complexes"] == expected["new_complexes"]
    assert actual["er_changes"] == [{"name": "단지70", "gu": "가구", "dong": "가동", "hospital": "응급C", "distance": 300}]
    assert actual["changes_meta"] == {"master_compared": True, "er_compared": True}
    assert builder.er_place("서울특별시 강서구 양천로 600, 파인블루빌딩 지하1층 (등촌동)") == ("강서구", "등촌동")
    assert builder.er_place("서울특별시 종로구 대학로 101 (연건동, 서울대학교병원)") == ("종로구", "연건동")
    old_master.unlink()
    old_medical.unlink()
    again = builder.build_rankings(dataset, data_month="2026-09", previous=actual)
    assert again["new_complexes"] == actual["new_complexes"]
    assert again["er_changes"] == actual["er_changes"]
    assert again["changes_meta"] == actual["changes_meta"]
    # Next month compares against the stored snapshot: 단지67 gains 응급D.
    medical[3].update(emergency_count_1km=4, emergency_items_json=er_items(4, ("응급A", "응급B", "응급C", "응급D")))
    write_csv(dataset / "baseline/medical_baseline.csv", medical)
    next_month = builder.build_rankings(dataset, data_month="2026-10", previous=again)
    assert next_month["new_complexes"] == []
    assert next_month["er_changes"] == [{"name": "단지67", "gu": "가구", "dong": "가동", "hospital": "응급C", "distance": 300},
                                        {"name": "단지67", "gu": "가구", "dong": "가동", "hospital": "응급D", "distance": 400}]
    assert [h["name"] for h in next_month["er_hospitals"]] == ["응급C", "응급D"]
    assert next_month["changes_meta"] == {"master_compared": True, "er_compared": True, "previous_month": "2026-09"}


def test_unknown_dates_and_uncompared_deltas_are_not_inferred(dataset):
    result = builder.build_rankings(dataset, data_month="2026-09", source_dates={"subway": {"source_updated_at": "2026-09-22"}})
    assert all(source["collected_at"] is None for source in result["sources"].values())
    assert result["changes_meta"] == {"master_compared": False, "er_compared": False}
    # 수집일은 화면용 정의에 쓰지 않는다(사용자 결정). collected_at 은 sources 에만 남는다.
    assert "수집" not in json.dumps(result["definitions"], ensure_ascii=False)
    for topic in (*builder.TOPICS, "changes"):
        labels = [r[0] for r in result["definitions"][topic]]
        # 산정 기준은 기준점·반경·방식·출처만(사용자 결정). 동 단위·변경 주제는 반경이 없다.
        assert set(labels) <= {"기준점", "반경", "방식", "출처"} and {"기준점", "방식", "출처"} <= set(labels)
        assert "해당 없음" not in json.dumps(result["definitions"][topic], ensure_ascii=False)
    assert "최근 6개월(2026.03~2026.08)" in str(result["definitions"]["value_combo"])
    assert "학군" not in json.dumps(result, ensure_ascii=False)
    future = builder.build_rankings(dataset, data_month="2026-10")
    assert "최근 6개월(2026.04~2026.09)" in str(future["definitions"]["value_combo"])  # window follows the data month


def test_collection_dates_accept_file_or_json_and_validate(tmp_path):
    metadata = {"sources": {"academy": {"collected_at": "2026-10-01", "evidence": "collection log"}}}
    file = tmp_path / "sources.json"
    file.write_text(json.dumps(metadata), encoding="utf-8")
    assert builder.load_sources(file) == builder.load_sources(json.dumps(metadata))
    assert builder.load_sources(file)["academy"]["collected_at"] == "2026-10-01"
    with pytest.raises(ValueError):
        builder.load_sources({"academy": "2026-02-30"})
    with pytest.raises(ValueError):
        builder.load_sources({"academy": "2026-9-1"})


def test_previous_snapshot_must_be_adjacent_month(dataset):
    with pytest.raises(ValueError, match="immediately previous month"):
        builder.build_rankings(dataset, data_month="2026-09", previous={"data_month": "2026-07"})


def test_cli_writes_only_output_and_preserves_delta_on_rerun(dataset, tmp_path):
    before = csv_fingerprints(dataset)
    target = tmp_path / "derived/home_rankings.json"
    argv = ["--data-dir", str(dataset), "--output", str(target), "--data-month", "2026-09"]
    builder.main(argv)
    saved = json.loads(target.read_text(encoding="utf-8"))
    saved["er_changes"] = [{"name": "단지70", "gu": "가구", "dong": "가동", "hospital": "응급C", "distance": 300}]
    saved["changes_meta"]["er_compared"] = True
    target.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    builder.main(argv)
    rebuilt = json.loads(target.read_text(encoding="utf-8"))
    assert rebuilt["er_changes"] == saved["er_changes"]
    assert rebuilt["changes_meta"]["er_compared"] is True
    assert csv_fingerprints(dataset) == before
    assert not target.with_name(target.name + ".tmp").exists()
    validate_rankings(rebuilt)


# --- 가격 추이 (scripts/home_price_trend.py) ------------------------------------------

def price_master(name, households=500, sale="분양", operation="의무"):
    return {"k-아파트명": name, "k-전체세대수": str(households),
            price_trend.SALE_TYPE_COLUMN: sale, price_trend.OPERATION_COLUMN: operation}


def trades(name, road, month, prices, area="84.97"):
    return [{"transaction_type": "trade", "gu": "가구", "dong": "가동", "apartment_name": name, "road_address": road,
             "contract_date": f"{month}-{day + 1:02d}", "area_m2": area, "floor": str(day + 1),
             "trade_price_manwon": str(price), "bonbun": "1", "bubun": ""}
            for day, price in enumerate(prices)]


def test_price_windows_skip_the_partially_reported_data_month():
    assert price_trend.windows("2026-09") == ("2025-09", "2026-02", "2026-03", "2026-08")
    assert price_trend.windows("2026-01") == ("2025-01", "2025-06", "2025-07", "2025-12")


def test_price_trend_filters_rental_ambiguous_direct_and_small_samples():
    names = ("오른단지", "내린단지", "임대단지", "기타단지", "소단지", "표본부족", "동명A", "동명B")
    masters = {(n, "가구", "가동"): price_master(n) for n in names}
    masters[("임대단지", "가구", "가동")] = price_master("임대단지", sale="임대")
    masters[("기타단지", "가구", "가동")] = price_master("기타단지", sale="기타")
    masters[("소단지", "가구", "가동")] = price_master("소단지", households=299)
    mapping = [{"livefit_name": n, "gu": "가구", "dong": "가동", "transaction_apt_name": n, "transaction_road_address": f"{n}로 1",
                "verified": "Y"} for n in names[:6]]
    # 동명A/동명B 가 같은 거래명·도로명에 걸리면 어느 단지인지 모르므로 버린다.
    mapping += [{"livefit_name": n, "gu": "가구", "dong": "가동", "transaction_apt_name": "동명", "transaction_road_address": "동명로 1",
                 "verified": "Y"} for n in ("동명A", "동명B")]
    rows = []
    for n in ("오른단지", "임대단지", "기타단지", "소단지"):
        rows += trades(n, f"{n}로 1", "2025-10", [100000] * 5) + trades(n, f"{n}로 1", "2026-05", [120000] * 5)
    rows += trades("내린단지", "내린단지로 1", "2025-10", [100000] * 5) + trades("내린단지", "내린단지로 1", "2026-05", [90000] * 5)
    rows += trades("표본부족", "표본부족로 1", "2025-10", [100000] * 4) + trades("표본부족", "표본부족로 1", "2026-05", [150000] * 9)
    rows += trades("동명", "동명로 1", "2025-10", [100000] * 5) + trades("동명", "동명로 1", "2026-05", [200000] * 5)
    # 직거래 한 건(최근 기간의 아주 높은 값)은 빠져야 한다. 기준월(2026-09) 거래는 세지 않는다.
    rows += trades("오른단지", "오른단지로 1", "2026-06", [999999])
    rows += trades("오른단지", "오른단지로 1", "2026-09", [1] * 5)
    direct = {price_trend.trade_identity(rows[-6])}
    collected, stats = price_trend.collect_trades(rows, mapping, masters, set(masters), "2025-09", "2026-08", direct)
    up, down, meta = price_trend.build_price_trend(collected, stats, masters, set(masters), "2026-09", 50)
    assert [(r["name"], r["change_pct"], r["area"], r["prev_n"], r["recent_n"]) for r in up] == [("오른단지", 20.0, 84, 5, 5)]
    assert [(r["name"], r["change_pct"]) for r in down] == [("내린단지", -10.0)]
    assert meta["direct_excluded"] == 1 and meta["ambiguous"] == 10 and meta["compared"] == 2
    assert (meta["prev_start"], meta["recent_end"]) == ("2025-09", "2026-08")


def test_price_trend_keeps_one_area_per_complex():
    masters = {("한단지", "가구", "가동"): price_master("한단지")}
    mapping = [{"livefit_name": "한단지", "gu": "가구", "dong": "가동", "transaction_apt_name": "한단지",
                "transaction_road_address": "한단지로 1", "verified": "Y"}]
    rows = (trades("한단지", "한단지로 1", "2025-10", [100000] * 5, "59.9") + trades("한단지", "한단지로 1", "2026-05", [110000] * 5, "59.9")
            + trades("한단지", "한단지로 1", "2025-10", [100000] * 5) + trades("한단지", "한단지로 1", "2026-05", [130000] * 5))
    collected, stats = price_trend.collect_trades(rows, mapping, masters, set(masters), "2025-09", "2026-08", set())
    up, _, meta = price_trend.build_price_trend(collected, stats, masters, set(masters), "2026-09", 50)
    assert meta["compared"] == 2
    assert [(r["area"], r["change_pct"]) for r in up] == [(84, 30.0)]


def test_value_combo_uses_recent_six_month_84_average_and_subway_line_names(dataset):
    actual = builder.build_rankings(dataset, data_month="2026-09")
    row = next(r for r in actual["value_combo"] if r["name"] == "단지69")
    assert (row["price84"], row["price84_n"]) == (99999, 3)  # 4~6월 3건 모두 최근 6개월 안
    # 최근 6개월 밖(기준월 포함)의 거래만 있으면 가격 조건에서 빠진다.
    later = builder.build_rankings(dataset, data_month="2027-01")
    assert later["value_combo"] == [] and later["value_combo_pool"] == 0
    lines = {r["name"]: r["line_names"] for r in actual["subway"]}
    assert lines["단지70"] == ["1호선", "2호선", "경의중앙선"]  # 숫자 노선 먼저, 그다음 이름순
    assert all(len(r["line_names"]) == r["lines"] for r in actual["subway"])


def test_legal_dong_parsing_skips_building_names_and_uses_address_gu():
    from services.address_dong import gu_from_address, legal_dong_from_address
    cases = {
        ", 5층 (대치동, 미도상가)": "대치동", " (미도상가)": "", "(대치동, 청실상가동)": "대치동",
        "(1202동, 화곡동)": "화곡동", ", 2층 (연희동,(주)희훈)": "연희동", ", 405호 (장지동, 대진플라자(Ⅱ))": "장지동",
        " 106호 (진관동102, 은평뉴타운)": "진관동", "(종로2가)": "종로2가", "(상도1동)": "상도1동",
        ", 우성7차아파트상가동 203호 (일원동,운동시설(수영장))": "일원동", "주소에 법정동 없음": "",
    }
    for address, expected in cases.items():
        assert legal_dong_from_address(address) == expected, address
    assert gu_from_address("서울특별시 서초구 서초대로 1") == "서초구"
    assert gu_from_address("주소 없음") == ""

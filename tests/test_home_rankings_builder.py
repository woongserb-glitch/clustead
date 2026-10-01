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
from services.home_billboard_service import validate_rankings


def write_csv(path, rows, encoding="utf-8-sig"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def dataset(tmp_path):
    """More than fifty rows, boundary filters, stable ties and malformed dong data."""
    data = tmp_path / "data"
    rows = {name: [] for name in builder.BASELINE_COLUMNS}
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
                                "subway_station_count_500m": 5 - i % 5},
            "cafe_baseline": {"스타벅스_count_500m": 3, "nearest_스타벅스_distance": "" if i == 8 else 100 + i % 3},
            "convenience_baseline": {brand + "_count_500m": 1 for brand in builder.BRANDS},
            "nightlife_baseline": {"nightlife_count_500m": "" if i == 9 else 1 if i == 10 else 0,
                                   "nightlife_nearest_any_distance": "" if i == 11 else 0 if i == 12 else 1000 + i // 2},
            "medical_baseline": {"emergency_count_1km": 3 - i % 2, "nearest_superior_hospital_distance": 200 + i % 3,
                                 "nearest_superior_hospital_name": "종합병원"},
            "transaction_summary": {"avg_trade_amount_84": 100000 if i == 4 else "" if i == 5 else 99999},
            "school_zone_baseline": {"assigned_elementary_school": "가초 (적용시기: 2026.9)" if i == 0 else "나초"},
        }
        for name in rows:
            if name == "subway_baseline" and i == 69:
                continue  # common academy/subway key set is intentional
            rows[name].append({**ident, **metrics[name], "unused_poi_json": '[{"ignored":true}]'})
    for name, values in rows.items():
        write_csv(data / "baseline" / f"{name}.csv", values)
    write_csv(data / "apartment/seoul_apartments.csv", masters, "cp949")
    academies = []
    for i in range(60):
        for course in ("수학", "영어"):
            academies.append({"등록상태명": "개원", "도로명상세주소": f"도로 ({60-i}동, 건물)",
                              "행정구역명": "가구" if i < 30 else "나구", "학원명": "가학원", "교습과정명": course})
    academies.extend([
        {"등록상태명": "개원", "도로명상세주소": "주소에 법정동 없음", "행정구역명": "가구", "학원명": "학원", "교습과정명": "보습"},
        {"등록상태명": "개원", "도로명상세주소": "도로 (가동)", "행정구역명": "", "학원명": "학원", "교습과정명": "영어"},
        {"등록상태명": "폐원", "도로명상세주소": "도로 (가동)", "행정구역명": "가구", "학원명": "학원", "교습과정명": "영어"},
        {"등록상태명": "개원", "도로명상세주소": "도로 (가동)", "행정구역명": "가구", "학원명": "학원", "교습과정명": "미술"},
    ])
    write_csv(data / "academy/academy_geocoded.csv", academies)
    # The reference dynamically imports its classifier relative to REPO.
    (tmp_path / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/build_academy_baseline.py", tmp_path / "scripts/build_academy_baseline.py")
    return data


def run_oracle(data, monkeypatch, prev_master=None, prev_school=None):
    script = ROOT / "outputs/clustead-home-billboard/compute_home_preview.py"
    spec = importlib.util.spec_from_file_location("home_preview_oracle", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REPO", data.parent)
    output = data.parent / "oracle.json"
    argv = [str(script), "--output", str(output)]
    if prev_master:
        argv.extend(["--prev-master", str(prev_master)])
    if prev_school:
        argv.extend(["--prev-school", str(prev_school)])
    monkeypatch.setattr(sys, "argv", argv)
    module.main()
    return json.loads(output.read_text(encoding="utf-8"))


def csv_fingerprints(data):
    return {str(p.relative_to(data)): hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*.csv")}


def test_top_five_exactly_matches_unmodified_reference(dataset, monkeypatch):
    before = csv_fingerprints(dataset)
    actual = builder.build_rankings(dataset, data_month="2026-09")
    expected = run_oracle(dataset, monkeypatch)
    for key in builder.TOPICS:
        assert actual[key][:5] == expected[key], key
    for key in ("value_combo_pool", "quiet_pool", "dong_academy_meta", "new_complexes", "school_changes"):
        assert actual[key] == expected[key], key
    assert len(actual["academy"]) == len(actual["dong_academy"]) == 50
    assert len(actual["quiet"]) == len(actual["value_combo"]) == 50
    assert actual["convenience"][0]["name"] == "단지70"  # never use name as a new tie breaker
    assert actual["dong_academy"][0]["dong"] == "60동"
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
    school = list(builder.csv_rows(dataset / "baseline/school_zone_baseline.csv", columns=("name", "gu", "dong", "assigned_elementary_school")))
    old_master = tmp_path / "previous-master.csv"
    old_school = tmp_path / "previous-school.csv"
    write_csv(old_master, master[:-1], "cp949")
    school[0]["assigned_elementary_school"] = "가초 (적용시기: 2025.9)"
    school[1]["assigned_elementary_school"] = "이전초"
    write_csv(old_school, school)
    actual = builder.build_rankings(dataset, data_month="2026-09", prev_master=old_master, prev_school=old_school)
    expected = run_oracle(dataset, monkeypatch, old_master, old_school)
    assert actual["new_complexes"] == expected["new_complexes"]
    # Oracle's set iteration has no stable display order; compare membership and every value.
    normalize = lambda rows: sorted(({k: v for k, v in r.items() if k != "dong"} for r in rows), key=lambda r: r["name"])
    assert normalize(actual["school_changes"]) == normalize(expected["school_changes"])
    assert len(actual["school_changes"]) == 2
    annotation_only = next(r for r in actual["school_changes"] if r["name"] == "단지70")
    assert annotation_only["from"] == annotation_only["to"] == "가초"  # raw change retained before display cleaning
    assert all(r["dong"] == "가동" for r in actual["school_changes"])
    old_master.unlink()
    old_school.unlink()
    again = builder.build_rankings(dataset, data_month="2026-09", previous=actual)
    assert again["new_complexes"] == actual["new_complexes"]
    assert again["school_changes"] == actual["school_changes"]
    assert again["changes_meta"] == actual["changes_meta"]
    # Next month uses stored raw names and codes, including an annotation-only change.
    school[0]["assigned_elementary_school"] = "가초 (적용시기: 2026.10)"
    school[1]["assigned_elementary_school"] = "나초"
    write_csv(dataset / "baseline/school_zone_baseline.csv", school)
    next_month = builder.build_rankings(dataset, data_month="2026-10", previous=again)
    assert next_month["new_complexes"] == []
    assert len(next_month["school_changes"]) == 1
    assert next_month["school_changes"][0]["name"] == "단지70"
    assert next_month["changes_meta"] == {"master_compared": True, "school_compared": True, "previous_month": "2026-09"}


def test_unknown_dates_and_uncompared_deltas_are_not_inferred(dataset):
    result = builder.build_rankings(dataset, data_month="2026-09", source_dates={"subway": {"source_updated_at": "2026-09-22"}})
    assert all(source["collected_at"] is None for source in result["sources"].values())
    assert result["changes_meta"] == {"master_compared": False, "school_compared": False}
    assert "수집일 기록 없음" in str(result["definitions"]["subway"])
    for topic in (*builder.TOPICS, "changes"):
        labels = {r[0] for r in result["definitions"][topic]}
        assert {"기준점", "반경", "방식", "동률", "출처와 수집일"} <= labels
    assert "2025.1~2026.9" in str(result["definitions"]["value_combo"])
    assert "학군" not in json.dumps(result, ensure_ascii=False)
    future = builder.build_rankings(dataset, data_month="2026-10")
    assert "2025.1~2026.9" in str(future["definitions"]["value_combo"])  # publication month never infers coverage


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
    saved["school_changes"] = [{"name": "단지70", "gu": "가구", "dong": "가동", "from": "전초", "to": "가초"}]
    saved["changes_meta"]["school_compared"] = True
    target.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    builder.main(argv)
    rebuilt = json.loads(target.read_text(encoding="utf-8"))
    assert rebuilt["school_changes"] == saved["school_changes"]
    assert rebuilt["changes_meta"]["school_compared"] is True
    assert csv_fingerprints(dataset) == before
    assert not target.with_name(target.name + ".tmp").exists()
    validate_rankings(rebuilt)

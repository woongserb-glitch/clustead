"""Scout regression tests: false discoveries, reproducibility and read-only inputs."""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import scout_home_items as scout


KEY = ("가아파트", "가구", "가동")


def write_csv(path, rows, encoding="utf-8-sig"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def facility_row(kind, items, count=None, key=KEY):
    spec = scout.FACILITIES[kind]
    return {**scout.label(key), spec[2]: str(len(items) if count is None else count),
            spec[3]: json.dumps(items, ensure_ascii=False)}


def station(name, lines, distance=100):
    return {"name": name, "lines": lines, "distance": distance}


def test_subway_aliases_and_seoul_group_are_not_openings_or_closures(tmp_path):
    old = [station("서울역", ["1호선", "경부선"]), station("서울", ["광역급행철도"], 150),
           station("이촌(국립중앙박물관)", ["경원선", "과천선"], 250)]
    now = [station("서울역", ["1호선", "GTX-A"]), station("이촌", ["경의중앙선", "4호선"], 250)]
    before = write_csv(tmp_path / "before.csv", [facility_row("subway", old)])
    after = write_csv(tmp_path / "after.csv", [facility_row("subway", now)])
    candidates, meta = scout.facility_candidates("subway", after, before, {KEY})
    assert candidates == []
    assert meta["compared_complexes"] == 1
    before_index = scout.facility_index(scout.baseline(before, (scout.FACILITIES["subway"][2], scout.FACILITIES["subway"][3])), "subway")[0]
    assert before_index[KEY]["서울"]["lines"] == ["1호선", "GTX-A"]
    assert before_index[KEY]["이촌"]["lines"] == ["4호선", "경의중앙선"]


def test_subway_regrouping_radius_change_is_not_a_new_station(tmp_path):
    old = facility_row("subway", [], 0)
    old["subway_items_json"] = json.dumps([station("서울", ["광역급행철도"], 510)])
    now = facility_row("subway", [station("서울역", ["GTX-A"], 490)])
    before = write_csv(tmp_path / "before.csv", [old])
    after = write_csv(tmp_path / "after.csv", [now])
    candidates, meta = scout.facility_candidates("subway", after, before, {KEY})
    assert candidates == []
    assert meta["subway_existing_station_radius_changes_excluded"] == 1


def test_new_station_is_kept(tmp_path):
    before = write_csv(tmp_path / "before.csv", [facility_row("subway", [])])
    after = write_csv(tmp_path / "after.csv", [facility_row("subway", [station("신설역", ["1호선"])])])
    rows, _ = scout.facility_candidates("subway", after, before, {KEY})
    assert rows[0]["metrics"]["facility_name"] == "신설"
    assert rows[0]["impact_complex_count"] == 1


def test_emergency_spaces_new_complex_and_rounded_boundary(tmp_path):
    old_items = [{"name": "중앙 보훈 병원", "distance": 300}]
    current_items = [{"name": "중앙보훈병원", "distance": 300}, {"name": "경계병원", "distance": 1000}]
    new_key = ("이름바뀐단지", "가구", "가동")
    before = write_csv(tmp_path / "before.csv", [facility_row("emergency", old_items)])
    after = write_csv(tmp_path / "after.csv", [facility_row("emergency", current_items, count=1),
                                               facility_row("emergency", current_items, key=new_key)])
    rows, meta = scout.facility_candidates("emergency", after, before, {KEY, new_key})
    assert rows == []
    assert meta["excluded_complexes"] == 1


def test_facility_disappearance_evidence_and_unique_impact(tmp_path):
    keys = [KEY, ("나아파트", "가구", "가동")]
    before = write_csv(tmp_path / "before.csv", [facility_row("emergency", [{"name": "한일 병원", "distance": 200}], key=k) for k in keys])
    after = write_csv(tmp_path / "after.csv", [facility_row("emergency", [], key=k) for k in keys])
    rows, _ = scout.facility_candidates("emergency", after, before, set(keys))
    assert len(rows) == 1
    assert rows[0]["impact_complex_count"] == 2
    assert rows[0]["metrics"]["direction"] == "removed"
    assert len(rows[0]["evidence"]) == 4
    assert rows[0]["change_kind"]["icon"] == "cross"


def test_incomplete_facility_list_is_not_a_closure(tmp_path):
    before = write_csv(tmp_path / "before.csv", [facility_row("mart", [{"name": "마트", "distance": 100}])])
    after = write_csv(tmp_path / "after.csv", [facility_row("mart", [], count=1)])
    rows, meta = scout.facility_candidates("mart", after, before, {KEY})
    assert rows == []
    assert len(meta["invalid_current"]) == 1


def test_duplicate_old_complex_key_is_excluded_and_reported(tmp_path):
    row = facility_row("emergency", [{"name": "병원", "distance": 100}])
    before = write_csv(tmp_path / "before.csv", [row, row])
    after = write_csv(tmp_path / "after.csv", [facility_row("emergency", [])])
    rows, meta = scout.facility_candidates("emergency", after, before, {KEY})
    assert rows == []
    assert meta["compared_complexes"] == 0
    assert "중복 단지 키" in meta["invalid_previous"][0]["reason"]


def test_analytics_requires_explicit_server_copy_and_preserves_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTEAD_ANALYTICS_DB", str(tmp_path / "local.db"))
    assert scout.topic_interest_copy(None, "2026-09", tmp_path / "data")["status"] == "미집계"
    db = tmp_path / "server-copy.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE event(event_type TEXT, day TEXT, visitor_hash TEXT, path TEXT)")
        conn.executemany("INSERT INTO event VALUES(?, ?, ?, ?)", [
            ("home_topic_click", "2026-09-01", "a", "/rankings/starbucks"),
            ("ranking_view", "2026-09-01", "a", "/rankings/starbucks"),
            ("ranking_view", "2026-09-02", "a", "/rankings/starbucks"),
            ("ranking_view", "2026-09-02", "b", "/rankings/starbucks"),
            ("ranking_view", "2026-08-31", "c", "/rankings/starbucks"),
            ("ranking_view", "2026-10-01", "c", "/rankings/starbucks"),
            ("page_view", "2026-09-02", "d", "/rankings/starbucks"),
        ])
    before = db.read_bytes()
    actual = scout.topic_interest_copy(db, "2026-09", tmp_path / "data")
    assert actual["status"] == "집계"
    assert actual["topics"][0]["visitor_days"] == 3
    assert db.read_bytes() == before
    assert not Path(str(db) + "-shm").exists()
    assert not Path(str(db) + "-wal").exists()
    assert "visitor_hash" not in json.dumps(actual)
    with pytest.raises(ValueError, match="개발 PC"):
        scout.topic_interest_copy(tmp_path / "data/analytics/analytics.db", "2026-09", tmp_path / "data")


def test_missing_corrupt_and_wal_analytics_are_unavailable(tmp_path):
    db = tmp_path / "server.db"
    assert scout.topic_interest_copy(db, "2026-09", tmp_path / "data")["status"] == "미집계"
    db.write_text("not a DB")
    assert scout.topic_interest_copy(db, "2026-09", tmp_path / "data")["status"] == "미집계"
    Path(str(db) + "-wal").write_bytes(b"uncheckpointed")
    assert "일관된" in scout.topic_interest_copy(db, "2026-09", tmp_path / "data")["reason"]


def test_top5_requires_previous_month_and_handles_entries_and_exits(tmp_path):
    row = lambda name: {"name": name, "gu": "가구", "dong": "가동", "count": 1}
    now = {"data_month": "2026-09", "starbucks": [row("나"), row("신규")]}
    old = {"data_month": "2026-08", "starbucks": [row("가"), row("나")]}
    path = tmp_path / "rankings.json"
    assert scout.rank_changes(now, None, path, path)[1]["status"] == "미비교"
    assert scout.rank_changes(now, now, path, path)[1]["status"] == "미비교"
    result, _ = scout.rank_changes(now, old, path, path)
    assert result[0]["impact_complex_count"] == 3
    moved = result[0]["metrics"]["moved_rows"]
    assert next(r for r in moved if r["name"] == "신규")["before_rank"] is None


def test_academy_growth_uses_1km_total_and_saves_addresses(tmp_path):
    row = {**scout.label(KEY), "academy_count_1000m": "10"}
    old = write_csv(tmp_path / "old.csv", [row])
    now = write_csv(tmp_path / "now.csv", [{**row, "academy_count_1000m": "12"}])
    candidates, _ = scout.academy_candidates(now, old, {KEY})
    assert candidates[0]["metrics"] == {"before": 10, "after": 12, "increase": 2}
    academy = {"등록상태명": "개원", "학원지정번호": "id", "학원명": "수학학원", "교습과정명": "수학",
               "행정구역명": "가구", "도로명상세주소": "길 1 (가동)"}
    raw = write_csv(tmp_path / "raw.csv", [academy, academy, {**academy, "학원지정번호": "closed", "등록상태명": "폐원"}])
    saved = scout.academy_address_snapshot(raw, "2026-09")
    assert saved["dong_counts"][0]["total"] == 1
    assert saved["duplicate_rows_excluded"] == 1
    assert saved["source_rows"][0]["address"] == "길 1 (가동)"


def test_output_paths_protect_data_backup_and_input(tmp_path):
    data, backup = tmp_path / "data", tmp_path / "backup"
    with pytest.raises(ValueError):
        scout.validate_outputs([data / "derived/report.md"], [data, backup], [])
    with pytest.raises(ValueError):
        scout.validate_outputs([backup / "2026-09/report.md"], [data, backup], [])
    source = tmp_path / "source.json"
    with pytest.raises(ValueError):
        scout.validate_outputs([source], [data], [source])


def test_cli_monthly_copies_determinism_and_top10(tmp_path, monkeypatch):
    data, out = tmp_path / "data", tmp_path / "reports"
    rankings = data / "derived/home_rankings.json"
    rankings.parent.mkdir(parents=True)
    rankings.write_bytes(b'{\n"data_month":"2026-09"\n}\n')
    sidecar = scout.home.snapshot_path(rankings)
    sidecar.write_text('{"snapshot":{"master_codes":["code"]}}', encoding="utf-8")
    rows = [scout.candidate("test", n, f"후보 {n}", [scout.label((str(i), "가구", "가동")) for i in range(n)],
                             {}, [], [], [], scout.checks()) for n in range(12)]
    rows.sort(key=scout.candidate_order)
    previous_paths = []
    def build(data_dir, prev_dir, month, ranks, previous, analytics):
        previous_paths.append(previous)
        return {"data_month": month, "inputs": {"data_dir": str(data), "prev_dir": None},
                "comparison": {"top5": {"status": "미비교"}}, "price_meta": {"recent_start": "2026-03", "recent_end": "2026-08",
                "prev_start": "2025-09", "prev_end": "2026-02", "compared": 0, "direct_excluded": 0},
                "analytics": scout.topic_interest_copy(None, month, data), "candidates": rows, "recommendations": []}, {"data_month": month}
    monkeypatch.setattr(scout, "build_report", build)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*.json")}
    argv = ["--data-month", "2026-09", "--data-dir", str(data), "--output-root", str(out)]
    assert scout.main(argv) == 0
    outputs = {p.name: p.read_bytes() for p in (out / "2026-09").iterdir()}
    assert scout.main(argv) == 0
    assert outputs == {p.name: p.read_bytes() for p in (out / "2026-09").iterdir()}
    assert outputs["home_rankings.json"] == rankings.read_bytes()
    assert outputs["home_rankings.snapshot.json"] == sidecar.read_bytes()
    assert "academy_address_counts.json" in outputs
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob("*.json")}
    report_front = outputs["report.md"].decode().split("<details>")[0]
    assert len([line for line in report_front.splitlines() if re_rank_line(line)]) == 10
    assert previous_paths[0] == out / "2026-08/home_rankings.json"
    argv[1] = "2026-10"
    scout.main(argv)
    assert previous_paths[-1] == out / "2026-09/home_rankings.json"


def re_rank_line(line):
    return line.startswith("| ") and line.split("|")[1].strip().isdigit()


def test_price_candidates_reuse_approved_functions(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(scout.price, "load_direct_trade_keys", lambda *_: {("direct",)})
    monkeypatch.setattr(scout.home, "csv_rows", lambda *_: iter([]))
    monkeypatch.setattr(scout.price, "collect_trades", lambda *args: (calls.append(args) or [], {}))
    monkeypatch.setattr(scout.price, "build_price_trend", lambda *args: ([], [], {"unchanged_definition": True}))
    result, meta = scout.price_candidates(tmp_path, {}, set(), "2026-09")
    assert result == []
    assert meta["unchanged_definition"]
    assert calls[0][-3:] == ("2025-09", "2026-08", {("direct",)})

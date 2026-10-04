"""Startup readiness is a cached load snapshot, not a request-time data scan."""

import copy
import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")


@pytest.fixture
def runtime(monkeypatch):
    import app
    from services import preload_service as preload

    monkeypatch.setattr(preload, "DATA_LOAD_STATUS", copy.deepcopy(preload.DATA_LOAD_STATUS))
    monkeypatch.setattr(preload, "REQUIRED_DATA", preload.REQUIRED_DATA)
    monkeypatch.setattr(preload, "DATA_LOAD_COMPLETE", preload.DATA_LOAD_COMPLETE)
    return app, preload


def test_current_local_data_is_ready(runtime):
    app, preload = runtime
    assert set(preload.REQUIRED_DATA) == {
        "apartment_data", *(attr for _, attr in app.RANKING_SOURCES.values())
    }
    assert preload.DATA_LOAD_STATUS["apartment_data"]["rows"] == len(app.apartment_data)
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_empty_required_baseline_is_degraded(runtime, monkeypatch):
    app, preload = runtime
    monkeypatch.setattr(preload, "subway_baseline_data", [])
    # Simulate the startup/reload recorder seeing an empty in-memory result.
    preload.record_data_load("subway_baseline_data")
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json == {"status": "degraded", "missing": ["subway_baseline_data"]}


@pytest.mark.parametrize("offset,status", [(-1, 503), (0, 200)])
def test_ninety_five_percent_boundary(runtime, monkeypatch, offset, status):
    app, preload = runtime
    count = math.ceil(preload.DATA_LOAD_STATUS["apartment_data"]["rows"] * 0.95) + offset
    monkeypatch.setattr(preload, "subway_baseline_data", [{}] * count)
    preload.record_data_load("subway_baseline_data")
    assert app.app.test_client().get("/healthz").status_code == status


def test_optional_load_failure_only_warns(runtime, monkeypatch):
    app, preload = runtime
    monkeypatch.setattr(preload, "school_data", [])
    preload.record_data_load("school_data", FileNotFoundError("test missing school data"))
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "warnings": ["school_data"]}
    monkeypatch.setattr(preload, "school_data", [{}])
    preload.record_data_load("school_data")
    assert app.app.test_client().get("/healthz").json == {"status": "ok"}


def test_empty_apartments_after_startup_is_degraded_not_loading(runtime, monkeypatch):
    app, preload = runtime
    monkeypatch.setattr(preload, "apartment_data", [])
    preload.record_data_load("apartment_data")
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json == {"status": "degraded", "missing": ["apartment_data"]}


def test_unfinished_startup_is_loading(runtime, monkeypatch):
    app, preload = runtime
    monkeypatch.setattr(preload, "DATA_LOAD_COMPLETE", False)
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json == {"status": "loading"}


def test_health_does_not_open_files_or_query_database(runtime, monkeypatch):
    app, preload = runtime

    def forbidden(*args, **kwargs):
        pytest.fail("healthz must use the startup registry only")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(preload, "_baseline_conn", forbidden)
    monkeypatch.setattr(preload, "record_data_load", forbidden)
    for _ in range(3):
        assert app.app.test_client().get("/healthz").json == {"status": "ok"}


def test_sqlite_read_failure_is_recorded_without_csv_fallback(runtime, monkeypatch):
    import sqlite3
    app, preload = runtime

    def broken():
        raise sqlite3.DatabaseError("test malformed database")

    monkeypatch.setattr(preload, "academy_baseline_data", preload._SqliteBaseline("academy"))
    monkeypatch.setattr(preload, "_baseline_conn", broken)
    preload.record_data_load("academy_baseline_data")
    response = app.app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json["missing"] == ["academy_baseline_data"]
    assert preload.DATA_LOAD_STATUS["academy_baseline_data"]["rows"] == 0


def test_missing_sqlite_column_is_degraded_even_with_enough_rows(runtime, monkeypatch):
    import sqlite3
    app, preload = runtime
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE academy (name TEXT)")
        count = preload.DATA_LOAD_STATUS["apartment_data"]["rows"]
        connection.executemany("INSERT INTO academy VALUES (?)", [("test",)] * count)
        monkeypatch.setattr(preload, "_baseline_conn", lambda: connection)
        monkeypatch.setattr(preload, "academy_baseline_data", preload._SqliteBaseline("academy"))
        preload.record_data_load("academy_baseline_data", columns=("name", "gu", "dong"))
        assert preload.DATA_LOAD_STATUS["academy_baseline_data"]["rows"] == count
        response = app.app.test_client().get("/healthz")
        assert response.status_code == 503
        assert response.json["missing"] == ["academy_baseline_data"]
    finally:
        connection.close()


def test_initialize_records_swallowed_empty_and_raised_optional_failures(runtime, monkeypatch):
    app, preload = runtime
    # Exercise the real coordinator without rerunning loaders or altering data.
    for name in preload.DATA_LOAD_STATUS:
        monkeypatch.setattr(preload, f"load_{name}", lambda: None)
    monkeypatch.setattr(preload, "subway_baseline_data", [])

    def fail_school():
        raise OSError("test school load failure")

    monkeypatch.setattr(preload, "load_school_data", fail_school)
    preload.initialize_data(app.RANKING_SOURCES)
    assert preload.data_health() == ({"status": "loading"}, 503)
    preload.finish_data_loading()
    assert preload.data_health() == ({
        "status": "degraded", "missing": ["subway_baseline_data"], "warnings": ["school_data"],
    }, 503)


def test_require_sqlite_fails_before_any_loader(runtime, monkeypatch, tmp_path):
    app, preload = runtime
    monkeypatch.setattr(preload, "_BASELINE_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setenv("CLUSTEAD_REQUIRE_SQLITE_BASELINE", "1")
    monkeypatch.setattr(preload, "load_cctv_data", lambda: pytest.fail("must fail before loading"))
    with pytest.raises(RuntimeError, match="CSV memory fallback is disabled"):
        preload.initialize_data(app.RANKING_SOURCES)


@pytest.mark.parametrize("flag", [None, "0"])
def test_local_backend_allows_missing_database(runtime, monkeypatch, tmp_path, flag):
    _, preload = runtime
    monkeypatch.setattr(preload, "_BASELINE_DB_PATH", str(tmp_path / "missing.db"))
    if flag is None:
        monkeypatch.delenv("CLUSTEAD_REQUIRE_SQLITE_BASELINE", raising=False)
    else:
        monkeypatch.setenv("CLUSTEAD_REQUIRE_SQLITE_BASELINE", flag)
    assert preload.select_baseline_backend() is False

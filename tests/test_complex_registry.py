"""재건축 옛 단지 301, 재건축 진행 중 안내, 현장 통용명 표기·검색."""

import csv
import os
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")

from services import complex_registry  # noqa: E402


def _lifecycle(status):
    with complex_registry.LIFECYCLE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return [r for r in csv.DictReader(handle) if r["status"] == status]


@pytest.fixture
def app_module(monkeypatch):
    import app

    monkeypatch.setitem(app.app.config, "TESTING", True)
    monkeypatch.setattr(app.limiter, "enabled", False)
    monkeypatch.setattr(app.analytics_service, "track", lambda *a, **kw: None)
    return app


def test_rebuilt_successors_exist_and_old_complexes_left_master(app_module):
    live = {(a["name"], a["gu"], a["dong"]) for a in app_module.apartment_data}
    rebuilt = _lifecycle("rebuilt")
    assert rebuilt
    for row in rebuilt:
        assert (row["successor_name"], row["successor_gu"], row["successor_dong"]) in live, row["successor_name"]
        assert (row["name"], row["gu"], row["dong"]) not in live, row["name"]


def test_rebuilt_old_address_redirects_to_successor(app_module):
    client = app_module.app.test_client()
    for row in _lifecycle("rebuilt"):
        old = app_module.apartment_detail_path(row["name"], row["gu"], row["dong"])
        response = client.get(old + "?src=explore", follow_redirects=False)
        assert response.status_code == 301, old
        location = unquote(response.headers["Location"])
        assert location.startswith(f"/apartments/{row['successor_gu']}/{row['successor_dong']}/{row['successor_name']}")
        assert "src=explore" in location
        # /result?apartment= 진입도 같은 곳으로 보낸다.
        legacy = client.get("/result", query_string={"apartment": row["name"], "gu": row["gu"], "dong": row["dong"]})
        assert legacy.status_code == 301
        assert unquote(legacy.headers["Location"]) == location.split("?")[0]


def test_rebuilding_complex_shows_notice(app_module):
    client = app_module.app.test_client()
    live = {(a["name"], a["gu"], a["dong"]) for a in app_module.apartment_data}
    rows = [r for r in _lifecycle("rebuilding") if (r["name"], r["gu"], r["dong"]) in live]
    assert rows
    for row in rows:
        html = client.get(app_module.apartment_detail_path(row["name"], row["gu"], row["dong"])).get_data(as_text=True)
        assert "재건축 진행 중인 단지입니다" in html, row["name"]
        if row["planned_name"]:
            assert row["planned_name"] in html


def test_common_name_shown_and_searchable(app_module):
    client = app_module.app.test_client()
    name, gu, dong = "압구정한양3단지", "강남구", "압구정동"
    assert complex_registry.common_name(name, gu, dong) == "한양5차"
    html = client.get(app_module.apartment_detail_path(name, gu, dong)).get_data(as_text=True)
    assert "현장에서는 <strong>한양5차</strong>" in html
    assert "<title>압구정한양3단지(한양5차) 생활환경 분석" in html
    items = client.get("/api/search/apartments", query_string={"q": "한양5차"}).get_json()["items"]
    assert any(i["value"] == name and i["gu"] == gu for i in items)


def test_plain_complex_has_no_notice_or_common_name(app_module):
    html = app_module.app.test_client().get(
        app_module.apartment_detail_path("헬리오시티", "송파구", "가락동")
    ).get_data(as_text=True)
    assert "재건축 진행 중인 단지입니다" not in html
    assert "result-common-name" not in html

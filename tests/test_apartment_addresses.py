"""Canonical detail URLs must identify one complex and never redirect to themselves."""

import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")


@pytest.fixture
def detail_app(monkeypatch):
    import app

    monkeypatch.setitem(app.app.config, "TESTING", True)
    monkeypatch.setattr(app.limiter, "enabled", False)
    monkeypatch.setattr(app.analytics_service, "track", lambda *a, **kw: None)
    return app


def path(module, name="헬리오시티아파트", gu="송파구", dong="가락동"):
    return module.apartment_detail_path(name, gu, dong)


def test_every_canonical_address_renders_without_redirect(detail_app):
    client = detail_app.app.test_client()
    assert len(detail_app.apartment_data) >= 2800
    for apartment in detail_app.apartment_data:
        url = path(detail_app, apartment["name"], apartment["gu"], apartment["dong"])
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 200, (url, response.status_code, response.location)
        assert "Location" not in response.headers, url
        response.close()


@pytest.mark.parametrize("route,gu,dong", [
    (route, gu, dong)
    for route in ("detail", "result")
    for gu, dong in (("없는구", "없는동"), ("없는구", "가락동"), ("송파구", "없는동"))
] + [("result", "", "")])
def test_wrong_address_redirects_once_and_preserves_query(detail_app, route, gu, dong):
    query = "src=a%2Fb&src=second&empty=&q=%ED%95%9C+%EA%B8%80&x=%2f"
    if route == "detail":
        url = path(detail_app, gu=gu, dong=dong)
    else:
        url = "/result"
        query = urlencode({"apartment": "헬리오시티", "gu": gu, "dong": dong}) + "&" + query
    client = detail_app.app.test_client()
    response = client.get(url + "?" + query)
    assert response.status_code == 301
    assert response.headers["Location"] == path(detail_app) + "?" + query
    follow = client.get(response.headers["Location"])
    assert follow.status_code == 200
    assert "Location" not in follow.headers


@pytest.mark.parametrize("route", ["detail", "result"])
def test_all_duplicate_names_with_wrong_address_are_not_guessed(detail_app, route):
    by_name = defaultdict(list)
    for apartment in detail_app.apartment_data:
        by_name[detail_app.clean_text(apartment["name"])].append(apartment)
    duplicates = {name: rows for name, rows in by_name.items() if len(rows) > 1}
    assert {"우리유앤미", "코오롱하늘채아파트", "신동아아파트"} <= duplicates.keys()
    client = detail_app.app.test_client()
    for name, rows in duplicates.items():
        # Even a real dong must not override a conflicting gu.
        for dong in ("없는동", rows[0]["dong"]):
            url = (path(detail_app, name, "없는구", dong) if route == "detail" else
                   "/result?" + urlencode({"apartment": name, "gu": "없는구", "dong": dong}))
            response = client.get(url)
            assert response.status_code == 404, (name, dong, response.status_code)
            assert "Location" not in response.headers


def test_partial_name_redirects_only_on_permanent_route(detail_app):
    client = detail_app.app.test_client()
    response = client.get(path(detail_app, name="헬리오시") + "?src=search")
    assert response.status_code == 301
    assert response.location == path(detail_app) + "?src=search"
    for query in ({"apartment": "헬리오시"},
                  {"apartment": "헬리오시", "gu": "송파구", "dong": "가락동"},
                  {"apartment": "우리유앤미"}):
        response = client.get("/result?" + urlencode(query))
        assert response.status_code == 200
        assert "Location" not in response.headers


def test_clean_text_equivalent_address_does_not_loop(detail_app):
    response = detail_app.app.test_client().get(
        "/apartments/%20송파구%20/%20가락동%20/%20헬리오시티아파트%20")
    assert response.status_code == 200
    assert "Location" not in response.headers


@pytest.mark.parametrize("route", ["detail", "result"])
def test_unknown_name_is_404(detail_app, route):
    url = (path(detail_app, name="존재하지않는단지_000") if route == "detail" else
           "/result?" + urlencode({"apartment": "존재하지않는단지_000", "gu": "송파구", "dong": "가락동"}))
    assert detail_app.app.test_client().get(url).status_code == 404

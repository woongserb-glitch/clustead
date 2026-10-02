"""운영 안정성 보강(2026-10-02, docs/review/2026-10-ops-review.md #3·#4·#9·#10·#11) 회귀 테스트.

이상한 입력이 500 을 내지 않는지, 카카오 오류 응답이 '0건'으로 캐시되지 않는지,
관리자 토큰이 쿠키로 바뀌고 로그에서 가려지는지 확인한다.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.parametrize("status, payload", [
    (429, {"errorType": "RequestThrottled", "message": "limit"}),
    (401, {"errorType": "AccessDeniedError", "message": "bad key"}),
    (200, {"errorType": "Unexpected"}),  # 성공 상태라도 documents 가 없으면 실패
])
def test_kakao_error_response_is_not_an_empty_success(monkeypatch, status, payload):
    from services import kakao_local_service as kakao

    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.setattr(kakao.requests, "get", lambda *a, **k: _FakeResponse(status, payload))
    ok, pois = kakao._fetch_category("cafe", 37.5, 127.0)
    assert (ok, pois) == (False, [])
    ok, pois = kakao._fetch_keyword("스타벅스", 37.5, 127.0, 500, "CE7", "cafe")
    assert (ok, pois) == (False, [])
    assert kakao.count_category_exact("convenience", 37.5, 127.0, 500) is None


def test_kakao_real_zero_result_is_still_success(monkeypatch):
    from services import kakao_local_service as kakao

    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    payload = {"documents": [], "meta": {"is_end": True, "total_count": 0}}
    monkeypatch.setattr(kakao.requests, "get", lambda *a, **k: _FakeResponse(200, payload))
    assert kakao._fetch_category("cafe", 37.5, 127.0) == (True, [])


@pytest.fixture(scope="module")
def app_module():
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.limiter.enabled = False
    return app_module


@pytest.mark.parametrize("body", ["[1]", "1", '"hello"', "true"])
def test_home_click_rejects_non_object_json(app_module, body):
    client = app_module.app.test_client()
    resp = client.post("/api/home-click", data=body, content_type="application/json")
    assert resp.status_code == 204


def test_explore_share_with_lone_surrogate_is_ignored(app_module):
    client = app_module.app.test_client()
    # base64 of {"gu":"\ud800"} — 짝 없는 surrogate
    resp = client.get("/explore?q=eyJndSI6Ilx1ZDgwMCJ9")
    assert resp.status_code == 200


@pytest.fixture
def admin_client(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "FLASK_DEBUG", False)
    monkeypatch.setattr(app_module, "ADMIN_TOKEN", "secret-test-token")
    return app_module.app.test_client()


@pytest.mark.parametrize("bbox", [
    "nan,127,38,128", "-inf,127,38,128", "1e100,127,1e101,128", "37,127,inf,128",
])
def test_admin_grid_rejects_non_finite_bbox(admin_client, bbox):
    resp = admin_client.get(f"/admin/grid/cells?layer=cctv&bbox={bbox}",
                            headers={"X-Admin-Token": "secret-test-token"})
    assert resp.status_code == 400


def test_admin_token_in_url_becomes_cookie(admin_client):
    resp = admin_client.get("/admin/grid?admin_token=secret-test-token")
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert "admin_token" not in resp.headers["Location"]
    assert "clustead_admin=" in resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in resp.headers.get("Set-Cookie", "")

    follow = admin_client.get(resp.headers["Location"])
    assert follow.status_code == 200
    assert follow.headers.get("Cache-Control") == "private, no-store"


def test_admin_wrong_token_is_hidden(admin_client):
    assert admin_client.get("/admin/grid?admin_token=wrong").status_code == 404
    admin_client.set_cookie("clustead_admin", "wrong", path="/admin")
    assert admin_client.get("/admin/grid").status_code == 404


def test_log_path_masks_admin_token(app_module):
    with app_module.app.test_request_context("/admin/grid?admin_token=secret-test-token&layer=cctv"):
        logged = app_module._loggable_path()
    assert "secret-test-token" not in logged
    assert "layer=cctv" in logged

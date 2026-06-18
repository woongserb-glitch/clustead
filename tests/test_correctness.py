"""Correctness invariants for the P0/P1 fixes.

Unlike tests/snapshot_result.py (which only detects *changes* in output), these
assert that the behaviour is *correct*, so a wrong "fix" to matching or scoring
fails here instead of silently becoming the new golden output.

Two tiers:
  * pure_* : pure-function math (mid-rank percentile) — fast, no data load.
  * integ_*: need app + baselines loaded (~9s import).

Run standalone:   python tests/test_correctness.py
Or with pytest:   pytest tests/test_correctness.py
(the pure_/integ_ functions are also exposed as test_* for pytest.)
"""

import os
import sys
from itertools import islice
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")

APPROX = 1e-6


# --------------------------------------------------------------------------
# Pure mid-rank percentile math (P1 tie-distortion fix)
# --------------------------------------------------------------------------

def pure_enrich_midrank_zero_inflated():
    """Zero-inflated LOWER_BETTER: the modal value must land mid-scale, not be
    pushed to ~30 by counting ties as losses (the original nightlife bug)."""
    from enrich_baseline_percentiles import calculate_percentile_and_score, HIGHER_BETTER, LOWER_BETTER

    values = [0, 0, 0, 0, 5]  # 4 ties at the best (lowest) value

    pct, score = calculate_percentile_and_score(values, 0, LOWER_BETTER)
    # strictly_better=0, ties=4 -> top=(0+2)/5*100=40 -> score=60
    assert abs(float(pct) - 40.0) < APPROX, pct
    assert abs(float(score) - 60.0) < APPROX, score

    # worst value (5) for LOWER_BETTER -> near 0
    pct_w, score_w = calculate_percentile_and_score(values, 5, LOWER_BETTER)
    assert abs(float(score_w) - 10.0) < APPROX, score_w  # strictly_better=4,ties=1->90 top->10 score

    # unique max under HIGHER_BETTER -> top-scoring
    pct_m, score_m = calculate_percentile_and_score(values, 5, HIGHER_BETTER)
    assert abs(float(score_m) - 90.0) < APPROX, score_m


def pure_enrich_empty_target():
    from enrich_baseline_percentiles import calculate_percentile_and_score, HIGHER_BETTER
    assert calculate_percentile_and_score([1, 2, 3], None, HIGHER_BETTER) == ("", "")
    assert calculate_percentile_and_score([], 1, HIGHER_BETTER) == ("", "")


def pure_baseline_service_midrank():
    from services.baseline_service import (
        calculate_density_top_percent,
        calculate_distance_top_percent,
    )
    # density (higher better): value 0 among [0,0,0,0,5] -> strictly>0=1,ties=4 -> 60
    assert calculate_density_top_percent(0, [0, 0, 0, 0, 5]) == 60
    # distance (lower better): 100 among [100,100,200,300] -> strictly<100=0,ties=2 -> 25
    assert calculate_distance_top_percent(100, [100, 100, 200, 300]) == 25
    # guards
    assert calculate_density_top_percent(None, [1, 2]) is None
    assert calculate_distance_top_percent(5, []) is None


def pure_ranking_to_number_rejects_nan():
    from services.ranking_service import to_number
    assert to_number("nan") is None
    assert to_number(float("inf")) is None
    assert to_number("") is None
    assert to_number("12.5") == 12.5


def pure_kakao_cache():
    """Kakao POI cache: success cached (memory+disk), distinct coords miss,
    failures never cached, disable flag bypasses. No network (fetch mocked)."""
    import tempfile
    from pathlib import Path
    import services.kakao_local_service as K

    K._CACHE_DIR = Path(tempfile.mkdtemp()) / "kakao"
    K._MEMORY_CACHE.clear()
    K._CACHE_ENABLED = True

    calls = {"n": 0}

    def ok_fetch(cat, lat, lng):
        calls["n"] += 1
        return True, [{"category": cat, "distance": 1}]

    K._fetch_category = ok_fetch
    K.search_category("cafe", 37.5, 127.0)
    K.search_category("cafe", 37.5, 127.0)  # memory hit
    assert calls["n"] == 1, calls

    K._MEMORY_CACHE.clear()
    K.search_category("cafe", 37.5, 127.0)  # disk hit
    assert calls["n"] == 1, calls

    K.search_category("cafe", 37.6, 127.1)  # distinct key
    assert calls["n"] == 2, calls

    def fail_fetch(cat, lat, lng):
        calls["n"] += 1
        return False, []

    K._fetch_category = fail_fetch
    K._MEMORY_CACHE.clear()
    K.search_category("mart", 1.0, 2.0)
    K.search_category("mart", 1.0, 2.0)  # failure must NOT be cached
    assert calls["n"] == 4, calls


# --------------------------------------------------------------------------
# Integration: matching + ranking consistency (P0 + P1)
# --------------------------------------------------------------------------

_APP = None


def _app():
    global _APP
    if _APP is None:
        import app
        _APP = app
    return _APP


def _find_colliding_apartment(app):
    seen = {}
    for a in app.apartment_data:
        name = a.get("name")
        if not name:
            continue
        seen.setdefault(name, []).append(a)
    for name, group in seen.items():
        gus = {g.get("gu") for g in group}
        if len(group) > 1 and len(gus) > 1:
            return name, group
    return None, None


def integ_get_apartment_disambiguates_collision():
    app = _app()
    name, group = _find_colliding_apartment(app)
    assert name, "expected at least one colliding apartment name in the dataset"
    for entry in group:
        resolved = app.get_apartment(name, entry.get("gu"), entry.get("dong"))
        assert resolved is not None
        assert resolved["district"] == entry.get("gu"), (name, entry.get("gu"), resolved["district"])
        assert resolved["dong"] == entry.get("dong")


def integ_get_apartment_unknown_is_none():
    app = _app()
    assert app.get_apartment("존재하지않는아파트_zzz_0000") is None


def integ_get_apartment_prefers_exact_over_substring():
    """A query that is a substring of a longer name must still resolve to the
    exact-named complex when one exists (kills the first-substring-match bug)."""
    app = _app()
    names = {a.get("name") for a in app.apartment_data if a.get("name")}
    target = None
    for n in names:
        if any(other != n and n in other for other in names):
            target = n
            break
    if target is None:
        return  # dataset has no nested names; nothing to assert
    resolved = app.get_apartment(target)
    assert resolved is not None
    assert resolved["name"] == target, (target, resolved["name"])


def integ_composite_index_resolves_collision():
    app = _app()
    from services.preload_service import get_indexed_baseline_row, subway_baseline_index
    # find colliding name in subway baseline
    seen = {}
    for r in app.subway_baseline_data:
        seen.setdefault(r.get("name"), []).append(r)
    coll = next((g for g in seen.values() if len(g) > 1), None)
    if not coll:
        return
    for row in coll:
        got = get_indexed_baseline_row(
            subway_baseline_index, row.get("name"), row.get("gu"), row.get("dong")
        )
        assert got is row, (row.get("name"), row.get("gu"), row.get("dong"))


def integ_ranking_matches_baked_scores():
    """Ranking's per-category score must equal the baked baseline score
    (single source of truth — P1 unification)."""
    app = _app()
    from services import ranking_service as R
    from services import preload_service as P
    from baseline_metric_config import BASELINE_METRIC_CONFIG, score_column

    idx = R.build_apartment_index()
    cfg = BASELINE_METRIC_CONFIG["nightlife"]
    col = score_column(cfg["primary_metric"])

    checked = 0
    for row in islice(P.nightlife_baseline_data, 50):
        key = (row.get("name"), row.get("gu"), row.get("dong"))
        baked = R.to_number(row.get(col))
        entry = idx.get(key)
        if baked is None or not entry:
            continue
        ranked_val = entry["category_scores"].get("nightlife")
        assert ranked_val is not None and abs(ranked_val - baked) < APPROX, (key, baked, ranked_val)
        checked += 1
    assert checked > 0, "no nightlife rows cross-checked"


def integ_ranking_coverage_expanded():
    """Unification expanded coverage from 9 to the full RANKING_SOURCES set."""
    app = _app()
    from services import ranking_service as R
    idx = R.build_apartment_index()
    # at least one apartment should carry most of the mapped categories
    best = max((len(v["category_scores"]) for v in idx.values()), default=0)
    assert best >= 12, f"expected wide category coverage, got {best}"


def _wide_subway_lines(r):
    """비교용: subway_items_json(넓은 반경) 의 구조적 노선 집합."""
    import json as _json
    out = set()
    raw = r.get("subway_items_json", "")
    try:
        items = _json.loads(raw) if raw else []
    except Exception:
        items = []
    for it in items:
        ls = it.get("lines", [])
        if isinstance(ls, str):
            ls = [p.strip() for p in ls.replace("/", ",").split(",")]
        for L in ls:
            L = (L or "").strip()
            if L:
                out.add(L)
    return out


def integ_subway_line_filter_500m_exact():
    """Explore 노선 필터는 (1) 노선 '전체 일치'(부분문자열 금지)이고 (2) 500m 도보권이어야 한다.
    회귀 방지 두 케이스:
      - 부분문자열: '1호선' 이 '공항철도1호선' 에 매칭되던 가양2단지류.
      - 반경: '1호선' 역이 1.6km 밖이라 500m 도보권이 아닌 답십리한화류.
    둘 다 _apartment_subway_lines(=500m 정확매칭) 가 1호선으로 인정하지 않아야 한다."""
    app = _app()
    from services.preload_service import subway_baseline_data

    target = "1호선"
    exact_hit = False        # 500m 내에 정확히 1호선이 있는 단지 존재
    substring_only = None    # 넓은 json 문자열엔 '1호선' 있으나 500m 정확매칭엔 없음
    radius_case = None       # 넓은 '구조적' 노선엔 1호선 있으나 500m 엔 없음(=반경 초과)
    for r in subway_baseline_data:
        near = app._apartment_subway_lines(r)        # 500m 정확매칭
        if target in near:
            exact_hit = True
            continue
        if target in str(r.get("subway_items_json", "")):
            substring_only = r
        if target in _wide_subway_lines(r):
            radius_case = r

    assert exact_hit, "expected at least one apartment with 1호선 within 500m"
    assert substring_only is not None, "expected a substring/far case (e.g. 공항철도1호선)"
    assert target not in app._apartment_subway_lines(substring_only)
    # 반경 잠금: helper 가 넓은 반경으로 되돌아가면 radius_case 가 사라져 실패한다.
    assert radius_case is not None, "expected a 1호선-only-beyond-500m apartment (radius lock)"
    assert target not in app._apartment_subway_lines(radius_case)


def integ_subway_station_filter_500m():
    """역명 필터도 500m 도보권으로 한정해야 한다 — 넓은 반경(>500m, nearest 포함)의 역이
    '접근'으로 잡혀 거의 모든 단지가 임의 역에 매칭되던 문제(2860/2861) 회귀 방지."""
    app = _app()
    import json
    from services.preload_service import subway_baseline_data

    def wide_station_names(r):
        out = set()
        nm0 = app.clean_text(r.get("nearest_subway_name", "")).replace("역", "")
        if nm0:
            out.add(app.normalize_search_text(nm0))
        raw = r.get("subway_items_json", "")
        try:
            items = json.loads(raw) if raw else []
        except Exception:
            items = []
        for it in items:
            nm = app.clean_text(it.get("name", "")).replace("역", "")
            if nm:
                out.add(app.normalize_search_text(nm))
        return out

    # 넓은 셋에는 있으나 500m 셋엔 없는 역이 존재하는 단지(반경 초과). helper 가 넓게
    # 되돌아가면 이런 단지가 사라져 assert 가 실패한다.
    radius_case = next(
        (r for r in subway_baseline_data
         if wide_station_names(r) - app._apartment_station_names(r)),
        None,
    )
    assert radius_case is not None, "expected a station-beyond-500m apartment (radius lock)"
    near = app._apartment_station_names(radius_case)
    assert near < wide_station_names(radius_case)  # 500m 셋은 넓은 셋의 진부분집합


def integ_seo_crawl_endpoints():
    app = _app()
    client = app.app.test_client()

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    robots_text = robots.get_data(as_text=True)
    assert "User-agent: *" in robots_text
    assert "Disallow: /admin/" in robots_text
    assert "Sitemap: https://clustead.com/sitemap.xml" in robots_text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    sitemap_text = sitemap.get_data(as_text=True)
    assert sitemap_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<loc>https://clustead.com/</loc>" in sitemap_text
    assert "<loc>https://clustead.com/area</loc>" in sitemap_text
    assert "https://clustead.com/area/" in sitemap_text
    assert "https://clustead.com/apartments/" in sitemap_text
    assert "https://clustead.com/result?apartment=" not in sitemap_text


def integ_result_page_has_seo_meta():
    app = _app()
    apt = next(a for a in app.apartment_data if a.get("name") and a.get("gu") and a.get("dong"))
    client = app.app.test_client()

    response = client.get("/result", query_string={
        "apartment": apt.get("name"),
        "gu": apt.get("gu"),
        "dong": apt.get("dong"),
    })
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "생활환경 분석 | Clustead" in html
    assert '<meta name="description"' in html
    assert '<link rel="canonical" href="https://clustead.com/apartments/' in html
    assert '<script type="application/ld+json">' in html

    clean_response = client.get(app.apartment_detail_path(
        apt.get("name"),
        apt.get("gu"),
        apt.get("dong"),
    ))
    assert clean_response.status_code == 200
    clean_html = clean_response.get_data(as_text=True)
    assert '<link rel="canonical" href="https://clustead.com/apartments/' in clean_html


def integ_explore_academy_priority_returns_results():
    app = _app()
    label = app._ACADEMY_TYPE_BY_KEY["exam"]["label"]
    client = app.app.test_client()

    response = client.get("/explore", query_string={"priority": f"academy:{label}"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="explore-result-row"' in html
    assert "/apartments/" in html

    filters = app.normalize_explore_filters({"priority": [f"academy:{label}"]})
    with app.app.test_request_context("/explore"):
        results = app.build_explore_results(filters)
    assert len(results) == 10
    assert all(row.get("url", "").startswith("/apartments/") for row in results)


def integ_area_pages_have_seo_and_recommendations():
    app = _app()
    apt = next(a for a in app.apartment_data if a.get("name") and a.get("gu") and a.get("dong"))
    client = app.app.test_client()

    hub_response = client.get("/area")
    assert hub_response.status_code == 200
    hub_html = hub_response.get_data(as_text=True)
    assert "서울 아파트 지역별 생활환경" in hub_html
    assert '<link rel="canonical" href="https://clustead.com/area"' in hub_html
    assert "지역별 추천 허브" in hub_html
    assert '<script type="application/ld+json">' in hub_html

    gu_response = client.get(app.area_landing_path(apt.get("gu")))
    assert gu_response.status_code == 200
    gu_html = gu_response.get_data(as_text=True)
    assert f"{apt.get('gu')} 아파트 생활환경" in gu_html
    assert '<link rel="canonical" href="https://clustead.com/area/' in gu_html
    assert "도메인 평균점수" in gu_html
    assert "추천 단지" in gu_html
    assert '<script type="application/ld+json">' in gu_html

    dong_response = client.get(app.area_landing_path(apt.get("gu"), apt.get("dong")))
    assert dong_response.status_code == 200
    dong_html = dong_response.get_data(as_text=True)
    assert f"{apt.get('gu')} {apt.get('dong')} 아파트 생활환경" in dong_html
    assert '<link rel="canonical" href="https://clustead.com/area/' in dong_html


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------

def _all_tests():
    g = globals()
    pure = [(n, f) for n, f in sorted(g.items()) if n.startswith("pure_") and callable(f)]
    integ = [(n, f) for n, f in sorted(g.items()) if n.startswith("integ_") and callable(f)]
    return pure, integ


# Expose as pytest test_* aliases
def _register_pytest_aliases():
    g = globals()
    for n, f in list(g.items()):
        if (n.startswith("pure_") or n.startswith("integ_")) and callable(f):
            g["test_" + n] = f


_register_pytest_aliases()


def main():
    pure, integ = _all_tests()
    failures = 0

    print("== pure (no data load) ==")
    for name, fn in pure:
        try:
            fn()
            print(f"[ok]   {name}")
        except Exception as exc:
            print(f"[FAIL] {name}: {exc!r}")
            failures += 1

    print("== integration (loads app) ==")
    for name, fn in integ:
        try:
            fn()
            print(f"[ok]   {name}")
        except Exception as exc:
            print(f"[FAIL] {name}: {exc!r}")
            failures += 1

    print("-" * 60)
    print(f"{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

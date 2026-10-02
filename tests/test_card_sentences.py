"""카드 설명 문장 회귀(2026-10-02 데이터 정합성 검토 D3·D4·D7, D2 문장).

개수가 0일 때 '0곳이 있습니다' 대신 '없습니다'로, 로딩 중처럼 읽히는 문구는 쓰지 않는다.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")


@pytest.fixture(scope="module")
def A():
    import app
    return app


def card(key, count, label, radius, **extra):
    return {"key": key, "count": count, "label": label, "radius": radius, "pois": [], **extra}


@pytest.mark.parametrize("summary, expected", [
    (card("warehouse_mart", 0, "📦 창고형마트", 5000), "반경 5,000m 내 창고형마트는 없습니다."),
    (card("super_mart", 0, "🏪 슈퍼마켓", 500), "반경 500m 내 슈퍼마켓은 없습니다."),
    (card("pharmacy", 0, "💊 약국", 500), "반경 500m 내 약국은 없습니다."),
])
def test_zero_count_says_none(A, summary, expected):
    assert A.build_category_evidence(summary) == expected


def test_zero_count_keeps_nearest_sentence(A):
    summary = card("general-hospital", 0, "🏥 종합병원", 3000,
                   nearest_poi={"label": "강남베드로병원", "distance": 4151})
    text = A.build_category_evidence(summary)
    assert text.startswith("반경 3,000m 내 종합병원은 없습니다.")
    assert "강남베드로병원" in text and "0곳" not in text


def test_nonzero_count_unchanged(A):
    text = A.build_category_evidence(card("warehouse_mart", 2, "📦 창고형마트", 5000))
    assert text == "반경 5,000m 내 창고형마트 2곳이 있습니다."


def test_hangang_outside_radius(A):
    text = A.build_category_evidence(card("hangang", 0, "🌊 한강공원", 3000))
    assert text == "반경 3,000m 안에 한강공원이 없습니다."


def test_fire_station_outside_radius_mentions_nearest(A):
    summary = card("fire-station", 0, "🚒 119안전센터/구조대", 1500,
                   nearest_poi={"label": "삼성119안전센터", "distance": 2100})
    text = A.build_category_evidence(summary)
    assert text.startswith("반경 1,500m 안에 119안전센터·구조대가 없습니다.")
    assert "0곳" not in text


def test_no_loading_like_wording(A):
    for summary in (card("hangang", 0, "🌊 한강공원", 3000), card("school-environment", 0, "🏫 교육환경", 1500)):
        text = A.build_category_evidence(summary)
        assert "확인합니다" not in text and "확인 중" not in text

"""단지 생애 상태(재건축)와 현장 통용명.

두 목록 모두 scripts/manual_overrides/ 의 승인 CSV 를 읽는다. 마스터(K-apt)에는
없는 정보라 데이터 폴더가 아니라 저장소에 둔다.

- complex_lifecycle_approved.csv
    rebuilt    : 재건축이 끝나 새 단지로 바뀐 옛 단지. 옛 주소로 들어오면 새 단지로 301.
                 마스터에서도 빠진다(refresh_apartment_master / apply_complex_lifecycle).
    rebuilding : 철거·공사 중인 단지. 페이지는 두고 안내를 띄운다.
- complex_common_names_approved.csv
    마스터 이름과 현장에서 부르는 이름이 다른 단지(예: 압구정한양3단지 → 한양5차).
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "scripts" / "manual_overrides"
LIFECYCLE_CSV = _DIR / "complex_lifecycle_approved.csv"
COMMON_NAMES_CSV = _DIR / "complex_common_names_approved.csv"


def _key_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(name, gu, dong):
    return (_key_text(name), _key_text(gu), _key_text(dong))


def _read(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _lifecycle():
    by_key, by_name = {}, {}
    for row in _read(LIFECYCLE_CSV):
        key = _key(row.get("name"), row.get("gu"), row.get("dong"))
        by_key[key] = row
        by_name.setdefault(key[0], []).append(row)
    return by_key, by_name


@lru_cache(maxsize=1)
def _common_names():
    return {
        _key(row.get("name"), row.get("gu"), row.get("dong")): _key_text(row.get("common_name"))
        for row in _read(COMMON_NAMES_CSV)
        if _key_text(row.get("common_name"))
    }


def lifecycle_entry(name, gu="", dong=""):
    """(이름, 구, 동) 의 재건축 상태 행. 구·동이 없으면 이름이 유일할 때만 찾는다."""
    by_key, by_name = _lifecycle()
    name, gu, dong = _key(name, gu, dong)
    if gu and dong:
        return by_key.get((name, gu, dong))
    rows = [r for r in by_name.get(name, []) if not gu or _key_text(r.get("gu")) == gu]
    return rows[0] if len(rows) == 1 else None


def rebuilt_successor(name, gu="", dong=""):
    """재건축이 끝난 옛 단지면 새 단지의 (이름, 구, 동), 아니면 None."""
    row = lifecycle_entry(name, gu, dong)
    if not row or row.get("status") != "rebuilt":
        return None
    return _key(row.get("successor_name"), row.get("successor_gu"), row.get("successor_dong"))


def rebuilding_notice(name, gu="", dong=""):
    """철거·공사 중인 단지면 {"planned_name": ...}, 아니면 None."""
    row = lifecycle_entry(name, gu, dong)
    if not row or row.get("status") != "rebuilding":
        return None
    return {"planned_name": _key_text(row.get("planned_name"))}


def common_name(name, gu="", dong=""):
    return _common_names().get(_key(name, gu, dong), "")


def common_name_index():
    """{(이름, 구, 동): 통용명} — 검색에서 통용명으로도 찾게 할 때 쓴다."""
    return dict(_common_names())

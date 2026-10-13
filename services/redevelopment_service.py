"""단지별 건축물대장 요약(용적률·건폐율)과 재건축 진행 단계.

원천(분기 갱신, docs/MONTHLY_UPDATE.md 11-1):
- data/apartment/building_registry.csv      scripts/fetch_building_registry.py (국토부 건축물대장)
- data/redevelopment/complex_redevelopment.csv scripts/build_redevelopment.py (서울시 정비사업 추진현황)
파일이 없으면 조용히 빈 값(화면에서 해당 칸이 빠진다).
"""
import csv
import os
import re
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "data", "apartment", "building_registry.csv")
LINKS = os.path.join(ROOT, "data", "redevelopment", "complex_redevelopment.csv")
RAW_DIR = os.path.join(ROOT, "data", "redevelopment", "raw")

# (단계 이름, 날짜 칸) — 엑셀의 '사업추진단계' 이름과 같다
STEPS = [("구역지정", "designated"), ("추진위", "committee"), ("조합설립", "union"), ("건축심의", "architecture_review"),
         ("사업시행", "project_approval"), ("관리처분", "management_disposal"), ("착공", "construction_start")]


def _key(name, gu, dong):
    return tuple(re.sub(r"\s+", " ", str(p or "")).strip() for p in (name, gu, dong))


def _read(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


@lru_cache(maxsize=1)
def _registry():
    return {_key(r["name"], r["gu"], r["dong"]): r for r in _read(REGISTRY)}


@lru_cache(maxsize=1)
def _links():
    return {_key(r["name"], r["complex_gu"], r["complex_dong"]): r for r in _read(LINKS)}


@lru_cache(maxsize=1)
def basis_month():
    """원본 파일 이름의 기준월(seoul_redevelopment_2606.xlsx → '2026년 6월')."""
    try:
        files = sorted(f for f in os.listdir(RAW_DIR) if re.match(r"seoul_redevelopment_\d{4}\.xlsx$", f))
    except OSError:
        return ""
    if not files:
        return ""
    yymm = re.search(r"(\d{2})(\d{2})", files[-1])
    return f"20{yymm.group(1)}년 {int(yymm.group(2))}월" if yymm else ""


def floor_area(name, gu, dong):
    """{'vl_rat': 204.2, 'bc_rat': 20.1, 'source': 'registry'|'parcel'|…, 'max_floor': 14} 또는 None."""
    r = _registry().get(_key(name, gu, dong))
    if not r or r.get("status") != "ok" or not r.get("vl_rat"):
        return None
    try:
        out = {"vl_rat": float(r["vl_rat"]), "bc_rat": float(r["bc_rat"]) if r.get("bc_rat") else None,
               "source": r.get("ratio_source") or "", "max_floor": int(float(r["max_floor"])) if r.get("max_floor") else None}
    except ValueError:
        return None
    return out


def _dot(date):
    return date.replace("-", ".") if date else ""


def redevelopment(name, gu, dong):
    """재건축 진행 단계 — 화면용 dict 또는 None."""
    r = _links().get(_key(name, gu, dong))
    if not r or not r.get("stage"):
        return None
    current = next((i for i, (label, _) in enumerate(STEPS) if label == r["stage"]), None)
    steps = []
    for i, (label, col) in enumerate(STEPS):
        steps.append({"label": label, "date": _dot(r.get(col) or ""),
                      "state": "done" if current is not None and i < current else ("current" if i == current else "todo")})
    relocation = ""
    if r.get("relocation_start"):
        relocation = f"이주 {_dot(r['relocation_start'])}" + (f" ~ {_dot(r['relocation_end'])}" if r.get("relocation_end") else "")
    units = r.get("units_total") or ""
    return {"zone": r.get("zone", ""), "type": r.get("type", ""), "stage": r["stage"], "steps": steps,
            "relocation": relocation, "units_total": units if units not in ("", "0") else "",
            "households_before": r.get("households_before") if r.get("households_before") not in ("", "0") else "",
            "basis": r.get("basis") or basis_month()}

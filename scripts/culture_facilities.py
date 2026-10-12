"""문화생활 baseline 에 붙는 고정 시설 지표 — 도서관, 박물관·미술관(2026-10-12 추가).

문화생활 카드(서울시 공공서비스예약 행사)는 매달 30% 가까이 바뀌는 행사 목록이라, 위치가 고정된 시설
두 가지를 같은 영역에 더한다(사용자 결정: 문화생활 영역 등급에 반영).

도서관   등급 = 가장 가까운 공공도서관(구립 등, 서울 열린데이터 216곳)까지 거리(가까울수록 좋음).
         작은도서관(브이월드 LT_P_SMALLLIBRARY, 서울 약 920곳, 64% 사립 — 단지 안 문고 포함)은
         개수·목록으로만 보여 준다(개수로 등급을 매기면 단지 문고가 많은 대단지가 부풀려진다).
박물관·미술관  등급 = 가장 가까운 곳까지 거리(브이월드 LT_P_DGMUSEUMART, 서울 약 240곳).

동별 원칙(scripts/dong_points): 거리 지표는 중간 동, 목록은 어느 동이든 반경 안을 합치고
거리는 가장 가까운 동 기준(+ dong_count).
"""
import csv
import json
import math
from pathlib import Path

from scripts.dong_points import GridIndex, load_dong_points, median_low, points_for

BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_LIBRARY_PATH = BASE_DIR / "data" / "culture" / "public_libraries.csv"
SMALL_LIBRARY_PATH = BASE_DIR / "data" / "derived" / "vworld" / "LT_P_SMALLLIBRARY.geojson"
MUSEUM_PATH = BASE_DIR / "data" / "derived" / "vworld" / "LT_P_DGMUSEUMART.geojson"

LIBRARY_LIST_M = 1000
MUSEUM_LIST_M = 2000
FAR_M = 100000

COLUMNS = [
    "nearest_public_library_name", "nearest_public_library_distance",
    "public_library_count_1km", "small_library_count_1km", "library_items_json",
    "nearest_museum_name", "nearest_museum_distance", "museum_count_2km", "museum_items_json",
    "library_basis", "library_dong_count",
]


def _hav(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _seoul_points(path, name_key, addr_key, subtype_fn):
    if not path.exists():
        print(f"[CULTURE] 원천 없음(건너뜀): {path}")
        return []
    out = []
    for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
        p = f.get("properties") or {}
        if not str(p.get(addr_key) or "").startswith("서울"):
            continue
        try:
            lng, lat = f["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"name": str(p.get(name_key) or "").strip(), "lat": float(lat), "lng": float(lng),
                    "subtype": subtype_fn(p), "address": str(p.get(addr_key) or "").strip(), "props": p})
    return out


def load_facilities():
    public = []
    if PUBLIC_LIBRARY_PATH.exists():
        for r in csv.DictReader(PUBLIC_LIBRARY_PATH.open(encoding="utf-8-sig")):
            public.append({"name": r["name"], "lat": float(r["lat"]), "lng": float(r["lng"]), "subtype": "공공도서관",
                           "address": r.get("address", ""), "op_time": r.get("op_time", ""), "closed": r.get("closed", "")})
    else:
        print(f"[CULTURE] 원천 없음(건너뜀): {PUBLIC_LIBRARY_PATH}")
    small = _seoul_points(SMALL_LIBRARY_PATH, "lbr_name", "addr",
                          lambda p: "작은도서관(공립)" if p.get("category") == "공립" else "작은도서관(사립)")
    museum = _seoul_points(MUSEUM_PATH, "mus_nam", "new_adr", lambda p: {
        "국립": "국립", "공립": "공립", "사립": "사립", "대학": "대학"}.get(p.get("mus_typ"), "기타"))
    for m in museum:
        fee = str(m["props"].get("adt_fee") or "").strip()
        m["fee"] = "무료" if fee in ("0", "") else f"성인 {int(float(fee)):,}원" if fee.replace(".", "").isdigit() else ""
        m.pop("props")
    for s in small:
        s.pop("props")
    print(f"[CULTURE] 공공도서관 {len(public)} · 작은도서관 {len(small)} · 박물관·미술관 {len(museum)}")
    return public, small, museum


class FacilityCalculator:
    def __init__(self):
        self.public, self.small, self.museum = load_facilities()
        self.public_idx = GridIndex(self.public)
        self.small_idx = GridIndex(self.small)
        self.museum_idx = GridIndex(self.museum)
        self.dong_points = load_dong_points()

    @staticmethod
    def _nearest(points, items, index, search_m):
        """점마다 가장 가까운 시설 (거리, 시설). search_m 안에 없으면 전체에서."""
        result = []
        for lat, lng in points:
            best = None
            for it in index.near(lat, lng, search_m):
                d = _hav(lat, lng, it["lat"], it["lng"])
                if best is None or d < best[0]:
                    best = (d, it)
            if best is None or best[0] > search_m:
                for it in items:
                    d = _hav(lat, lng, it["lat"], it["lng"])
                    if best is None or d < best[0]:
                        best = (d, it)
            result.append(best)
        return result

    @staticmethod
    def _union(points, index, radius):
        """어느 동이든 radius 안: [(가장 가까운 동 거리, 동 수, 시설)], 점마다 개수."""
        merged, counts = {}, []
        for lat, lng in points:
            n = 0
            seen = set()
            for it in index.near(lat, lng, radius):
                if id(it) in seen:
                    continue
                seen.add(id(it))
                d = _hav(lat, lng, it["lat"], it["lng"])
                if d > radius:
                    continue
                n += 1
                m = merged.get(id(it))
                if m is None:
                    merged[id(it)] = [d, 1, it]
                else:
                    m[0] = min(m[0], d)
                    m[1] += 1
            counts.append(n)
        return sorted(merged.values(), key=lambda x: (x[0], x[2]["name"])), counts

    def row(self, apartment):
        points, basis = points_for(self.dong_points, apartment["name"], apartment["gu"], apartment["dong"],
                                   apartment["lat"], apartment["lng"])
        dong = basis == "dong"

        def item(d, n, it, category):
            out = {"label": it["name"], "subtype": it["subtype"], "distance": int(round(d)),
                   "lat": round(it["lat"], 7), "lng": round(it["lng"], 7), "category": category}
            for k in ("address", "op_time", "closed", "fee"):
                if it.get(k):
                    out[k] = it[k]
            if dong:
                out["dong_count"] = n
            return out

        out = {}
        # 도서관
        near_pub = [b for b in self._nearest(points, self.public, self.public_idx, 3000) if b]
        if near_pub:
            dists = [b[0] for b in near_pub]
            mid = median_low(dists)
            votes = {}
            for d, it in near_pub:
                votes.setdefault(it["name"], []).append(d)
            top = min(votes, key=lambda k: (-len(votes[k]), min(votes[k]), k))
            out["nearest_public_library_name"] = top
            out["nearest_public_library_distance"] = int(round(mid))
        else:
            out["nearest_public_library_name"], out["nearest_public_library_distance"] = "", ""
        pub_list, pub_counts = self._union(points, self.public_idx, LIBRARY_LIST_M)
        small_list, small_counts = self._union(points, self.small_idx, LIBRARY_LIST_M)
        out["public_library_count_1km"] = median_low(pub_counts) or 0
        out["small_library_count_1km"] = median_low(small_counts) or 0
        items = [item(d, n, it, "library") for d, n, it in pub_list + small_list]
        # 1km 안에 공공도서관이 없으면 가장 가까운 곳을 목록 맨 앞에 붙인다(등급 근거가 목록에 보이게)
        if not pub_list and near_pub:
            d, it = min(near_pub, key=lambda b: b[0])
            items.insert(0, item(d, 1, it, "library"))
        items.sort(key=lambda x: (x["distance"], x["label"]))
        out["library_items_json"] = json.dumps(items, ensure_ascii=False)
        # 박물관·미술관
        near_mus = [b for b in self._nearest(points, self.museum, self.museum_idx, 3000) if b]
        if near_mus:
            votes = {}
            for d, it in near_mus:
                votes.setdefault(it["name"], []).append(d)
            out["nearest_museum_name"] = min(votes, key=lambda k: (-len(votes[k]), min(votes[k]), k))
            out["nearest_museum_distance"] = int(round(median_low([b[0] for b in near_mus])))
        else:
            out["nearest_museum_name"], out["nearest_museum_distance"] = "", ""
        mus_list, mus_counts = self._union(points, self.museum_idx, MUSEUM_LIST_M)
        out["museum_count_2km"] = median_low(mus_counts) or 0
        out["museum_items_json"] = json.dumps([item(d, n, it, "museum") for d, n, it in mus_list], ensure_ascii=False)
        out["library_basis"] = basis
        out["library_dong_count"] = len(points) if dong else 1
        return out

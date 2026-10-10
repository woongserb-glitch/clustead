"""(월간 갱신) 동별 정보: v5 동 건물마다 배정초(경계 걸침 표시), 최근접 지하철역·거리, 중학교·고교 학교군.

입력: complex_buildings_v5.jsonl(동 윤곽), 초등학교통학구역.shp(사이트와 같은 원천),
      subway_station_master.csv, 브이월드 LT_C_DMSCH/LT_C_DHSCH
출력: data/derived/vworld/dong_level.json  {"이름|구|동": {...}}
"""
import csv, json, math, re, sys, collections
import geopandas as gpd
from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
R = str(Path(__file__).resolve().parents[2]).replace("\\", "/"); V = f"{R}/data/derived/vworld"

# 마스터에 남아 있는 단지만(재건축 옛 단지 제외)
master = {(r["k-아파트명"].strip(), r["주소(시군구)"].strip(), r["주소(읍면동)"].strip())
          for r in csv.DictReader(open(f"{R}/data/apartment/seoul_apartments.csv", encoding="cp949"))}

zones = gpd.read_file(f"{R}/data/school/zone/초등학교통학구역.shp")
zones = zones[zones["EDU_UP_NM"] == "서울특별시교육청"].to_crs("EPSG:4326")
normal = zones[zones["HAKGUDO_GB"].astype(str) == "0"]
zsidx = normal.sindex
clean_zone = lambda s: str(s or "").replace("공동통학구역", "").replace("통학구역", "").strip()


def layer(name):
    d = json.load(open(f"{V}/{name}.geojson", encoding="utf-8"))
    return [(shape(f["geometry"]).buffer(0), f["properties"]["hakgudo_nm"]) for f in d["features"]
            if f["properties"].get("edu_up_nm") == "서울특별시교육청"]


MID, HIGH = layer("LT_C_DMSCH"), layer("LT_C_DHSCH")

# 역: 같은 이름은 하나로(환승역) — 노선 목록을 모은다
st = collections.defaultdict(lambda: {"lat": [], "lng": [], "lines": set()})
for enc in ("cp949", "utf-8-sig"):
    try:
        rows = list(csv.DictReader(open(f"{R}/data/subway/subway_station_master.csv", encoding=enc)))
        break
    except UnicodeDecodeError:
        continue
for r in rows:
    vals = list(r.values())
    name, line, lat, lng = vals[1], vals[2], vals[3], vals[4]
    try:
        lat, lng = float(lat), float(lng)
    except ValueError:
        continue
    if not (37.4 < lat < 37.72 and 126.7 < lng < 127.25):
        continue
    key = re.sub(r"\(.*?\)|역$", "", name).strip()
    st[key]["lat"].append(lat); st[key]["lng"].append(lng); st[key]["lines"].add(line)
STATIONS = [(k, sum(v["lat"]) / len(v["lat"]), sum(v["lng"]) / len(v["lng"])) for k, v in st.items()]


def hav(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(x))


def nearest_station(lat, lng):
    return min(((hav(lat, lng, s[1], s[2]), s[0]) for s in STATIONS))


to_m = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True).transform


def zones_of(geom):
    """건물 윤곽과 겹치는 일반 통학구역(면적 비율). 중심이 든 구역이 첫째."""
    c = geom.centroid
    out = []
    gm = transform(to_m, geom)
    for i in zsidx.query(geom):
        z = normal.iloc[int(i)]
        if not z.geometry.intersects(geom):
            continue
        share = transform(to_m, z.geometry.intersection(geom)).area / max(gm.area, 1)
        out.append((z.geometry.contains(c), share, clean_zone(z["HAKGUDO_NM"])))
    out.sort(key=lambda x: (not x[0], -x[1]))
    return out


SOUTH = {"강서구", "양천구", "영등포구", "구로구", "금천구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구"}
bank = lambda gu: "S" if gu in SOUTH else "N"
GATES = []
for g in json.load(open(f"{R}/data/derived/hangang_access_points.json", encoding="utf-8")):
    gu = next((w for w in g["address"].split() if w.endswith("구")), "")
    if gu:
        GATES.append((bank(gu), g["lat"], g["lng"], g["group"]))


def nearest_gate(lat, lng, gu):
    b = bank(gu)
    return min(((hav(lat, lng, y, x), n) for bb, y, x, n in GATES if bb == b), default=(None, ""))


def group_of(layer_, pt):
    return next((n for g, n in layer_ if g.contains(pt)), "")


sys.path.insert(0, R)
from scripts.dong_points import rejected_keys  # noqa: E402
rejected = rejected_keys()

out = {}
n_cx = 0
for line in open(f"{V}/complex_buildings_v5.jsonl", encoding="utf-8"):
    r = json.loads(line)
    k = tuple(r["key"])
    if k not in master or k in rejected:
        continue
    dongs = [b for b in r["buildings"] if b.get("label")]
    if len(dongs) < 2:
        continue
    rows_ = []
    for b in dongs:
        g = shape(b["geom"]).buffer(0)
        c = g.centroid
        zs = zones_of(g)
        school = zs[0][2] if zs else ""
        straddle = [z[2] for z in zs[1:] if z[1] >= 0.05 and z[2] != school]
        d, sname = nearest_station(c.y, c.x)
        hd, hname = nearest_gate(c.y, c.x, k[1])
        rows_.append({"dong": b["label"], "school": school, "straddle": straddle,
                      "station": sname, "station_m": round(d),
                      "hangang_gate": hname, "hangang_m": round(hd) if hd is not None else None,
                      "middle": group_of(MID, c), "high": group_of(HIGH, c)})
    schools = collections.Counter(x["school"] for x in rows_ if x["school"])
    dists = [x["station_m"] for x in rows_]
    near = collections.Counter(x["station"] for x in rows_)
    out["|".join(k)] = {
        "dongs": sorted(rows_, key=lambda x: (len(x["dong"]), x["dong"])),
        "summary": {
            "n": len(rows_),
            "schools": dict(schools.most_common()),
            "straddle_dongs": [x["dong"] for x in rows_ if x["straddle"]],
            "station_min": min(dists), "station_max": max(dists),
            "within_500": sum(1 for x in dists if x <= 500),
            "nearest_stations": dict(near.most_common()),
            "hangang_min": min((x["hangang_m"] for x in rows_ if x["hangang_m"] is not None), default=None),
            "hangang_max": max((x["hangang_m"] for x in rows_ if x["hangang_m"] is not None), default=None),
            "hangang_gates": dict(collections.Counter(x["hangang_gate"] for x in rows_ if x["hangang_gate"]).most_common()),
            "middle": sorted({x["middle"] for x in rows_ if x["middle"]}),
            "high": sorted({x["high"] for x in rows_ if x["high"]}),
        },
    }
    n_cx += 1
json.dump(out, open(f"{V}/dong_level.json", "w", encoding="utf-8"), ensure_ascii=False)
multi = sum(1 for v in out.values() if len(v["summary"]["schools"]) > 1)
spread = sum(1 for v in out.values() if v["summary"]["station_max"] - v["summary"]["station_min"] >= 300)
print(f"단지 {n_cx} | 배정초 2곳 이상으로 갈리는 단지 {multi} | 역 거리 동별 차이 300m+ {spread}")
for nm in ["헬리오시티|송파구|가락동", "잠실파크리오|송파구|신천동", "잠실엘스아파트|송파구|잠실동"]:
    if nm in out:
        print(nm, json.dumps(out[nm]["summary"], ensure_ascii=False))

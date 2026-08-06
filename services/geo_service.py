from math import radians, sin, cos, sqrt, atan2, floor, pi

EARTH_RADIUS_M = 6371000

# get_distance_m 이 쓰는 구(球) 모델에서 위도 1도의 길이. 격자 인덱스의 bounding
# box 를 거리 함수와 같은 모델로 계산해야 경계에서 후보를 흘리지 않는다.
METERS_PER_DEG_LAT = pi * EARTH_RADIUS_M / 180


def get_distance_m(lat1, lng1, lat2, lng2):
    earth_radius = EARTH_RADIUS_M

    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)

    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(d_lng / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return round(earth_radius * c)


def filter_pois_by_radius(pois, center_lat, center_lng, radius):
    filtered = []

    for poi in pois:
        
        if "lat" not in poi or "lng" not in poi:
            continue
        
        distance = get_distance_m(
            center_lat,
            center_lng,
            poi["lat"],
            poi["lng"]
        )

        if distance <= radius:
            new_poi = {
                **poi,
                "distance": distance,
            }
            filtered.append(new_poi)

    filtered.sort(key=lambda x: x["distance"])

    return filtered


class RadiusIndex:
    """반경 질의용 균일 격자 인덱스 — filter_pois_by_radius 의 전수 스캔 대체.

    문제는 스캔의 CPU 비용이 아니라 **스캔이 건드리는 메모리 양**이다. CCTV
    59,750개를 훑으면 흩어진 dict 6만 개의 페이지를 전부 만지는데, RAM 1GB
    서버에서는 그 대부분이 스왑에 밀려 있어 요청 하나가 major fault 를 수천 건
    일으킨다. 이게 상세 렌더가 로컬 0.07초 / 서버 5~42초로 갈리던 이유다.
    (2026-08-06 진단: 그 시각 CPU 98% 유휴 · iowait 70%대 · pswpin 급증.)

    위경도를 고정 크기 셀로 나눠 두고 질의 반경의 bounding box 에 겹치는 셀만
    본다. 500m 질의면 후보가 6만 개 → 수백 개로 줄고, 만지는 페이지도 같은
    비율로 준다.

    **정렬 동등성**: 원본은 입력 순서로 모은 뒤 거리로 stable sort 하므로 동점은
    입력 순서를 따른다. 셀 단위로 모으면 그 순서가 깨지므로 원본 순번을 함께
    저장해 (거리, 순번) 으로 정렬한다 — 결과 리스트가 원본과 완전히 같아야
    골든마스터가 통과한다.
    """

    # 위도 0.005° ≈ 0.55km. 실측으로 고른 값이다 — CCTV 6만 개 기준 셀을 0.02 →
    # 0.0025 로 줄여가며 재보면 0.005 까지는 질의가 크게 빨라지고(5.6s→0.9s,
    # 단지 716개 합계) 그 아래로는 셀 수만 3배가 되고 이득은 1.6배로 꺾인다.
    CELL_DEG = 0.005

    def __init__(self, pois, cell_deg=CELL_DEG):
        self._pois = pois
        self._cell_deg = cell_deg
        # 원본 목록은 load_*_data 가 clear()/extend() 로 갈아끼운다. 인덱스가
        # 그보다 낡았는지 호출부가 판별할 수 있게 만들 당시 길이를 남긴다.
        self.source_len = len(pois)

        cells = {}
        for order, poi in enumerate(pois):
            try:
                lat = float(poi["lat"])
                lng = float(poi["lng"])
            except (KeyError, TypeError, ValueError):
                # 좌표가 없거나 숫자가 아니면 원본도 건너뛰던 항목이다.
                continue

            key = (int(floor(lat / cell_deg)), int(floor(lng / cell_deg)))
            cells.setdefault(key, []).append(order)

        self._cells = cells

    def __len__(self):
        return sum(len(orders) for orders in self._cells.values())

    def candidates(self, center_lat, center_lng, radius):
        """반경 안의 (거리, 원본순번, poi) 를 원본 정렬 순서로 돌려준다.

        결과 dict 모양이 호출부마다 다르므로(버스 정류장은 자체 포맷을 만든다)
        여기서는 원본 poi 를 그대로 넘기고 조립은 호출부에 맡긴다.
        """
        cell = self._cell_deg

        lat_span = radius / METERS_PER_DEG_LAT
        # 경도 1도의 길이는 위도에 따라 줄어든다. bbox 가 모자라면 경계의 POI 를
        # 놓치므로, 밴드 안에서 극에 가장 가까운 위도(= cos 가 가장 작은 쪽)를
        # 기준으로 잡아 항상 넉넉한 쪽으로 틀리게 한다.
        worst_lat = min(abs(center_lat) + lat_span, 90.0)
        cos_lat = max(cos(radians(worst_lat)), 1e-9)
        lng_span = radius / (METERS_PER_DEG_LAT * cos_lat)

        # 부동소수점 경계와 셀 절단을 한꺼번에 덮으려고 셀 하나씩 더 본다.
        # 3x3 이 5x5 가 될 뿐이라 6만 개 스캔에 비하면 없는 비용이다.
        lat_min = int(floor((center_lat - lat_span) / cell)) - 1
        lat_max = int(floor((center_lat + lat_span) / cell)) + 1
        lng_min = int(floor((center_lng - lng_span) / cell)) - 1
        lng_max = int(floor((center_lng + lng_span) / cell)) + 1

        pois = self._pois
        cells = self._cells
        matched = []

        for lat_key in range(lat_min, lat_max + 1):
            for lng_key in range(lng_min, lng_max + 1):
                for order in cells.get((lat_key, lng_key), ()):
                    poi = pois[order]
                    try:
                        distance = get_distance_m(
                            center_lat,
                            center_lng,
                            poi["lat"],
                            poi["lng"],
                        )
                    except Exception:
                        continue

                    if distance <= radius:
                        matched.append((distance, order, poi))

        matched.sort(key=lambda item: (item[0], item[1]))
        return matched

    def within(self, center_lat, center_lng, radius):
        """filter_pois_by_radius 와 같은 결과(거리 병합 + 거리순)를 돌려준다."""
        return [
            {**poi, "distance": distance}
            for distance, _order, poi in self.candidates(
                center_lat, center_lng, radius
            )
        ]
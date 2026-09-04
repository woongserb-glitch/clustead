"""배포된 데이터가 로컬과 같은지 확인한다. 배포 직후 반드시 한 번 돌릴 것.

왜 필요한가
-----------
데이터는 git 추적 대상이 아니라 scp 로 따로 보낸다. 그래서 "무엇을 보내야
하는지" 가 코드 어디에도 없었고, 2026-09-04 하루에만 배포 누락이 세 번 났다.

  * baseline CSV 6 종을 빠뜨림 — subway/cctv/convenience/mart/cafe/school_zone
    로더에는 SQLite 분기가 없어 CSV 를 직접 읽는데, 나머지 12 종만 보고
    "baseline.db 가 있으니 CSV 는 폴백" 이라고 판단했다. 그 결과 kakao 전량
    재수집(79분)과 지하철 동점 보정이 화면에 반영되지 않은 채 하루를 보냈다.
  * apartment_transaction_mapping.csv 를 빠뜨림 — 신규 단지의 실거래가 비고,
    개명한 단지(위례중앙푸르지오 1/2단지)가 옛 이름으로 조회됐다.
  * .new 로 올려놓고 원자적 swap 을 빠뜨림 — md5 까지 맞춰 놓고 교체를 안 했다.

셋 다 "돌려보면 바로 드러나는" 종류였다. 그래서 목록을 코드에 못박고,
서버와 md5 로 대조한다.

사용
----
    python scripts/verify_deployed_data.py              # 로컬↔서버 대조
    python scripts/verify_deployed_data.py --list       # 배포 대상만 출력
    CLUSTEAD_HOST=root@1.2.3.4 python scripts/verify_deployed_data.py

불일치가 있으면 종료 코드 1 이라 배포 스크립트의 마지막 관문으로 쓸 수 있다.
"""

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
HOST = os.getenv("CLUSTEAD_HOST", "root@211.188.48.124")
SSH_KEY = os.getenv("CLUSTEAD_SSH_KEY", str(Path.home() / ".ssh" / "clustead_deploy"))
REMOTE_DIR = os.getenv("CLUSTEAD_REMOTE_DIR", "/root/clustead")

# 런타임이 실제로 읽는 파일. 주석은 "왜 필요한가" 를 적는다 — 지우려는 사람이
# 판단할 수 있어야 한다.
REQUIRED_FILES = [
    ("data/baseline.db", "baseline 21 종의 SQLite 백엔드. 대부분의 카테고리가 여기서 읽힌다"),
    ("data/apartment/seoul_apartments.csv", "단지 마스터. 모든 화면의 기준"),
    # 아래 6 종은 로더에 SQLite 분기가 없어 CSV 를 직접 읽는다(self-check 로 확인).
    ("data/baseline/subway_baseline.csv", "load_subway_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/cctv_baseline.csv", "load_cctv_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/convenience_baseline.csv", "load_convenience_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/mart_baseline.csv", "load_mart_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/cafe_baseline.csv", "load_cafe_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/school_zone_baseline.csv", "load_school_zone_baseline_data 가 CSV 를 직접 읽음"),
    ("data/baseline/transaction_summary.csv", "실거래 요약(transaction_service)"),
    ("data/bus/seoul_bus_stops.csv", "버스 정류장 preload"),
    ("data/bus/seoul_bus_routes.csv", "버스 노선 preload"),
    ("data/cctv/national_cctv.csv", "CCTV 지도 preload"),
    ("data/park/park.csv", "공원 preload"),
    ("data/school/school.csv", "학교 preload"),
    ("data/transactions/transaction_master.csv", "실거래 원장"),
    ("data/transactions/apartment_transaction_mapping.csv", "단지↔실거래 매핑(load_batch_mapping)"),
    ("data/grid.db", "격자 지도"),
]

REQUIRED_DIRS = [
    ("data/transactions/detail_index", "단지별 실거래 상세 샤드"),
]

# baseline.db 가 있으면 SQLite 로 읽으므로 보낼 필요가 없는 것들. 서버에 있어도
# 쓰이지 않으니 디스크만 차지한다(2026-09-04 기준 412MB).
NOT_REQUIRED = [
    "academy", "medical", "ev_charger", "shopping", "culture", "bus",
    "commercial", "bike", "fire_station", "nightlife", "hangang", "park",
]

# 로더 이름 → 배포 대상 파일. self-check 가 이 대응을 확인한다.
LOADER_TO_FILE = {
    "load_subway_baseline_data": "data/baseline/subway_baseline.csv",
    "load_cctv_baseline_data": "data/baseline/cctv_baseline.csv",
    "load_convenience_baseline_data": "data/baseline/convenience_baseline.csv",
    "load_mart_baseline_data": "data/baseline/mart_baseline.csv",
    "load_cafe_baseline_data": "data/baseline/cafe_baseline.csv",
    "load_school_zone_baseline_data": "data/baseline/school_zone_baseline.csv",
}


def md5_file(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_fingerprint(path):
    """디렉터리는 '파일명 크기' 목록의 해시로 비교한다(내용까지 읽으면 너무 느리다)."""
    entries = sorted(
        f"{p.name} {p.stat().st_size}" for p in Path(path).iterdir() if p.is_file()
    )
    return hashlib.md5("\n".join(entries).encode()).hexdigest(), len(entries)


def self_check():
    """목록이 코드와 어긋났는지 본다.

    preload_service 의 load_*_baseline_data 중 함수 앞부분에 _USE_SQLITE_BASELINE
    분기가 없는 것 = CSV 를 직접 읽는 것. 그 집합이 LOADER_TO_FILE 과 다르면
    코드가 바뀐 것이므로 이 파일도 고쳐야 한다.
    """
    src = (BASE_DIR / "services" / "preload_service.py").read_text(encoding="utf-8")
    csv_backed = set()
    for match in re.finditer(r"^def (load_\w*?baseline\w*?_data)\(\):\n(.*?)(?=^def |\Z)", src, re.S | re.M):
        name, body = match.group(1), match.group(2)
        if "_USE_SQLITE_BASELINE" not in body[:400]:
            csv_backed.add(name)

    expected = set(LOADER_TO_FILE)
    if csv_backed == expected:
        print(f"  [self-check] CSV 를 직접 읽는 로더 {len(csv_backed)}개 — 목록과 일치")
        return True

    print("  [self-check] *** 목록이 코드와 어긋났습니다 ***")
    for name in sorted(csv_backed - expected):
        print(f"      코드에는 있는데 목록에 없음: {name}  -> REQUIRED_FILES 에 추가할 것")
    for name in sorted(expected - csv_backed):
        print(f"      목록에만 있음(이제 SQLite 사용): {name}  -> 목록에서 빼도 됨")
    return False


def remote_hashes(paths, dirs):
    """서버에서 md5 를 한 번에 받아온다."""
    lines = []
    for path, _ in paths:
        lines.append(
            f'if [ -f "{path}" ]; then echo "F $(md5sum "{path}" | cut -d\' \' -f1) {path}"; '
            f'else echo "F MISSING {path}"; fi'
        )
    for path, _ in dirs:
        lines.append(
            f'if [ -d "{path}" ]; then '
            f'echo "D $(ls -l "{path}" | awk \'{{print $9, $5}}\' | grep -v \'^ \' | sort | md5sum | cut -d\' \' -f1) '
            f'$(ls "{path}" | wc -l) {path}"; else echo "D MISSING 0 {path}"; fi'
        )
    script = f"cd {REMOTE_DIR} && " + " ; ".join(lines)
    out = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=25", HOST, script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        print(f"  ssh 실패: {out.stderr.strip()[:200]}")
        return None
    return out.stdout.splitlines()


def main():
    args = sys.argv[1:]
    print(f"배포 대상 파일 {len(REQUIRED_FILES)}개 + 디렉터리 {len(REQUIRED_DIRS)}개")
    ok_selfcheck = self_check()

    if "--list" in args:
        print("\n[보내야 하는 것]")
        for path, why in REQUIRED_FILES + REQUIRED_DIRS:
            size = 0
            p = BASE_DIR / path
            if p.is_dir():
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            elif p.exists():
                size = p.stat().st_size
            print(f"  {size / 1048576:8.1f}MB  {path}\n              {why}")
        print("\n[보낼 필요 없는 것] baseline.db 가 있으면 SQLite 로 읽는다")
        print("  " + ", ".join(f"{k}_baseline.csv" for k in NOT_REQUIRED))
        return 0 if ok_selfcheck else 1

    print("\n로컬 해시 계산 중...")
    local = {}
    for path, _ in REQUIRED_FILES:
        p = BASE_DIR / path
        local[path] = md5_file(p) if p.exists() else "MISSING"
    local_dirs = {}
    for path, _ in REQUIRED_DIRS:
        p = BASE_DIR / path
        local_dirs[path] = dir_fingerprint(p) if p.is_dir() else ("MISSING", 0)

    print("서버 해시 수집 중...")
    lines = remote_hashes(REQUIRED_FILES, REQUIRED_DIRS)
    if lines is None:
        return 2

    same = diff = missing = 0
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "F":
            _, digest, path = parts[0], parts[1], parts[2]
            mine = local.get(path)
            if digest == "MISSING" or mine == "MISSING":
                print(f"  없음   {path}")
                missing += 1
            elif digest == mine:
                same += 1
            else:
                print(f"  다름   {path}\n           로컬 {mine[:12]} / 서버 {digest[:12]}")
                diff += 1
        elif parts[0] == "D":
            _, digest, count, path = parts[0], parts[1], parts[2], parts[3]
            mine, mine_count = local_dirs.get(path, ("MISSING", 0))
            if digest == "MISSING":
                print(f"  없음   {path}/")
                missing += 1
            elif int(count) != mine_count:
                print(f"  다름   {path}/  로컬 {mine_count}개 / 서버 {count}개")
                diff += 1
            else:
                same += 1

    print(f"\n일치 {same} / 다름 {diff} / 없음 {missing}")
    if diff or missing:
        print("→ 위 파일을 서버로 보내고 .new 에서 원자적으로 swap 한 뒤 앱을 재시작하세요.")
    if not ok_selfcheck:
        print("→ self-check 실패: 코드가 바뀌었으니 이 스크립트의 목록도 고치세요.")
    return 0 if (diff == 0 and missing == 0 and ok_selfcheck) else 1


if __name__ == "__main__":
    sys.exit(main())

"""raw 데이터 갱신 후 baseline 전체 체인을 한 번에 실행하는 단일 진입점.

build_all_baselines(모든 baseline CSV 재생성)
  → enrich_baseline_percentiles(percentile/score 컬럼)
  → build_baseline_sqlite(앱이 읽는 data/baseline.db)
  → validate_baselines(정합성 점검)

배경: update_data_pipeline.py 와 build_all_baselines.py 는 'CSV 빌드'까지만
수행하고 enrich/sqlite/재시작은 하지 않는다. 그 단계를 빠뜨리면 CSV 는 갱신돼도
라이브 앱의 baseline.db 가 옛날 데이터로 남는다. 개별 수정사항(예: 버스 노선
컬럼·광역 분류)은 build 스크립트에 들어 있으므로, 이 체인을 거치면 자동 반영된다.

사용:
    python scripts/rebuild_data_full.py                # 전체(모든 baseline)
    python scripts/rebuild_data_full.py --skip-build   # 이미 CSV가 최신일 때
                                                       # enrich→sqlite→validate만

배포(데이터는 git 비추적): 로컬에서 실행 후 data/baseline.db(또는 변경된
*_baseline.csv)를 서버로 전송하고 컨테이너를 재시작한다. 서버에서 직접 돌릴
때는 build_baseline_sqlite 가 stdlib만 쓰므로 가능하나, build_all_baselines 는
pandas(빌드 의존)와 네트워크(academy 지오코딩)가 필요하다.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def step(name, cmd):
    print("\n" + "=" * 64, flush=True)
    print(f"[STEP] {name}", flush=True)
    print("=" * 64, flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["PYTHONUNBUFFERED"] = "1"
    started = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    elapsed = time.time() - started
    if result.returncode != 0:
        print(f"\n[FAIL] {name} (exit {result.returncode}, {elapsed:.0f}s)", flush=True)
        sys.exit(result.returncode)
    print(f"[OK] {name} ({elapsed:.0f}s)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build", action="store_true",
        help="CSV 재빌드를 건너뛰고 enrich→sqlite→validate만 실행",
    )
    args = parser.parse_args()

    # enrich/validate 는 sys.path[0]=scripts 가 필요(베어 import)하므로 -m 이 아닌
    # 파일 경로로 실행한다. build_all_baselines 는 패키지 임포트라 -m 으로 실행.
    if not args.skip_build:
        step("build all baselines (CSV 재생성)",
             [sys.executable, "-m", "scripts.build_all_baselines"])
    step("enrich percentiles",
         [sys.executable, str(ROOT / "scripts" / "enrich_baseline_percentiles.py")])
    step("build baseline.db (SQLite)",
         [sys.executable, str(ROOT / "scripts" / "build_baseline_sqlite.py")])
    step("validate baselines",
         [sys.executable, str(ROOT / "scripts" / "validate_baselines.py")])

    print("\n" + "=" * 64, flush=True)
    print("[DONE] 전체 baseline 체인 완료 — data/baseline.db 갱신됨.", flush=True)
    print("배포: 변경된 data/baseline.db(또는 *_baseline.csv) 를 서버로 전송하고", flush=True)
    print("      컨테이너를 재시작해야 라이브에 반영된다.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

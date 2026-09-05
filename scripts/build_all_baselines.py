import sys
import time
import runpy

from scripts.baseline_config import (
    BASELINE_JOBS
)


print("=" * 60)
print("CLUSTEAD BASELINE BUILD START")
print("=" * 60)

start_time = time.time()

success_count = 0
fail_count = 0

for key, job in BASELINE_JOBS.items():

    print("\n")
    print("-" * 60)

    print(f"[BUILD] {key}")
    print(f"[DESC] {job['description']}")
    print(f"[SOURCE] {job['source']}")

    try:

        job_start = time.time()

        runpy.run_module(
            job["builder"],
            run_name="__main__"
        )

        elapsed = round(
            time.time() - job_start,
            2
        )

        print(
            f"[SUCCESS] {key} "
            f"({elapsed} sec)"
        )

        success_count += 1

    except Exception as e:

        print(
            f"[FAILED] {key} : {e}"
        )

        fail_count += 1

print("\n")
print("=" * 60)

total_elapsed = round(
    time.time() - start_time,
    2
)

print("CLUSTEAD BASELINE BUILD COMPLETE")

print(f"[SUCCESS COUNT] {success_count}")
print(f"[FAIL COUNT] {fail_count}")

print(f"[TOTAL TIME] {total_elapsed} sec")

print("=" * 60)

# 실패가 있으면 반드시 0 이 아닌 코드로 끝낸다. 지금까지는 실패 건수를 찍고도
# 정상 종료해서, 상위 rebuild_data_full 이 성공으로 보고 enrich -> sqlite ->
# validate 로 넘어갔다. 그 sqlite 단계는 기존 DB 를 먼저 지우므로, 조용한 실패가
# 멀쩡한 baseline.db 를 나쁜 CSV 로 갈아치우는 데까지 이어질 수 있었다.
if fail_count:
    print(f"[EXIT] {fail_count}개 빌더가 실패해 종료코드 1 로 끝냅니다.")
    sys.exit(1)

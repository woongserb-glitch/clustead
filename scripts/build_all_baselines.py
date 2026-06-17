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

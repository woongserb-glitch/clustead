"""Golden-master (characterization) test for the /result page.

The result page is assembled by ~13 near-identical build_X/apply_X functions
with no unit tests. Before refactoring that duplication we pin the CURRENT
rendered HTML for a diverse set of apartments, then assert byte-identical
output after each refactor step. Kakao is forced off so rendering is
deterministic (no live network).

Usage:
    python tests/snapshot_result.py save     # capture golden HTML (run BEFORE refactor)
    python tests/snapshot_result.py check     # compare current output to golden
"""

import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# Fixed preference vector so the recommendation block is deterministic too.
FIXED_PREFS = {
    "subway": 5, "bus": 3, "bike": 2, "mart": 4, "convenience": 3,
    "ev-charger": 1, "cafe": 4, "hospital": 3, "pharmacy": 2, "park": 4,
    "hangang": 3, "culture": 3, "academy": 2, "cctv": 3, "fire-station": 2,
    "nightlife": 1, "commercial": 3, "shopping": 3,
}


def select_apartments(app, limit=8):
    """Deterministic, data-derived selection: 헬리오시티 + first apartment of
    each gu (sorted). No hard-coded names, so it survives data refreshes."""
    by_gu = {}
    for a in app.apartment_data:
        gu = a.get("gu")
        if gu and a.get("name") and gu not in by_gu:
            by_gu[gu] = a

    picks = [("헬리오시티", "송파구", "가락동")]
    for gu in sorted(by_gu):
        a = by_gu[gu]
        picks.append((a["name"], a["gu"], a["dong"]))
        if len(picks) > limit:
            break

    # de-dup, preserve order
    out = []
    for p in picks:
        if p not in out:
            out.append(p)
    return out


def slug(name, gu, dong):
    raw = f"{name}|{gu}|{dong}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def render(client, name, gu, dong):
    from urllib.parse import urlencode
    params = {"apartment": name, "gu": gu, "dong": dong, **FIXED_PREFS}
    resp = client.get("/result?" + urlencode(params))
    return resp.status_code, resp.data


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    import app
    client = app.app.test_client()
    apartments = select_apartments(app)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    failures = 0
    for name, gu, dong in apartments:
        status, data = render(client, name, gu, dong)
        path = GOLDEN_DIR / f"{slug(name, gu, dong)}.html"
        label = f"{name} ({gu} {dong})"

        if status != 200:
            print(f"[FAIL] {label}: HTTP {status}")
            failures += 1
            continue

        if mode == "save":
            path.write_bytes(data)
            print(f"[save] {label}: {len(data)} bytes -> {path.name}")
        else:
            if not path.exists():
                print(f"[FAIL] {label}: no golden file ({path.name}); run 'save' first")
                failures += 1
                continue
            golden = path.read_bytes()
            if golden == data:
                print(f"[ok]   {label}: identical ({len(data)} bytes)")
            else:
                print(f"[DIFF] {label}: golden={len(golden)}b current={len(data)}b")
                failures += 1

    print("-" * 60)
    if mode == "check":
        print(f"{'PASS' if failures == 0 else 'FAIL'}: {failures} difference(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

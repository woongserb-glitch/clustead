"""Profile Explore request combinations.

This is an operational profiling helper, not part of the web runtime. It loads
the Flask app once, exercises request-producing Home/Explore filter
combinations, and prints the slowest requests with timing breakdowns.
"""

from __future__ import annotations

import argparse
import cProfile
import csv
import itertools
import json
import os
import pstats
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("CLUSTEAD_ANALYTICS", "0")
os.environ.setdefault("CLUSTEAD_KAKAO_RESULT_MODE", "off")
os.environ.setdefault("CLUSTEAD_PRELOAD_VERBOSE", "0")

import app as app_module  # noqa: E402
from services import preload_service  # noqa: E402


@dataclass
class Metrics:
    db_ms: float = 0.0
    baseline_ms: float = 0.0
    template_ms: float = 0.0
    _baseline_depth: int = 0


CURRENT: Metrics | None = None


def add_ms(field: str, value: float) -> None:
    if CURRENT is not None:
        setattr(CURRENT, field, getattr(CURRENT, field) + value)


def timed_baseline(fn):
    def wrapper(*args, **kwargs):
        global CURRENT
        metrics = CURRENT
        if metrics is None:
            return fn(*args, **kwargs)
        outer = metrics._baseline_depth == 0
        metrics._baseline_depth += 1
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            metrics._baseline_depth -= 1
            if outer:
                metrics.baseline_ms += elapsed

    return wrapper


def timed_generator_baseline(fn, *, count_as_db=False):
    def wrapper(*args, **kwargs):
        global CURRENT
        metrics = CURRENT
        if metrics is None:
            yield from fn(*args, **kwargs)
            return
        outer = metrics._baseline_depth == 0
        metrics._baseline_depth += 1
        start = time.perf_counter()
        try:
            yield from fn(*args, **kwargs)
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            metrics._baseline_depth -= 1
            if outer:
                metrics.baseline_ms += elapsed
            if count_as_db:
                metrics.db_ms += elapsed

    return wrapper


def install_instrumentation():
    original = {}

    def patch(obj, name, replacement):
        original[(obj, name)] = getattr(obj, name)
        setattr(obj, name, replacement)

    for name in (
        "get_indexed_baseline_row",
        "_academy_subtype_lookup",
        "_subtype_lookup",
        "_derived_category_stats",
        "_baseline_metric_lookup",
        "_transaction_price_lookup",
        "_bus_route_lookup",
        "_bus_routes_by_type",
        "_assigned_elementary_lookup",
        "_midhigh_school_coords",
    ):
        patch(app_module, name, timed_baseline(getattr(app_module, name)))

    patch(
        app_module,
        "iter_baseline_columns",
        timed_generator_baseline(app_module.iter_baseline_columns, count_as_db=True),
    )

    sqlite_get = preload_service._SqliteBaseline.get

    def timed_sqlite_get(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return sqlite_get(self, *args, **kwargs)
        finally:
            add_ms("db_ms", (time.perf_counter() - start) * 1000)

    patch(preload_service._SqliteBaseline, "get", timed_sqlite_get)

    render_template = app_module.render_template

    def timed_render_template(*args, **kwargs):
        start = time.perf_counter()
        try:
            return render_template(*args, **kwargs)
        finally:
            add_ms("template_ms", (time.perf_counter() - start) * 1000)

    patch(app_module, "render_template", timed_render_template)
    return original


def restore_instrumentation(original):
    for (obj, name), value in reversed(list(original.items())):
        setattr(obj, name, value)


def priority_items():
    graph = app_module.build_home_graph()
    domain_by_category = {}
    for domain in graph:
        for category in domain.get("categories", []):
            if category.get("kind") == "priority":
                domain_by_category[category["key"]] = domain["key"]

    items = []
    for category, cfg in app_module.SUBTYPE_SEARCH_CONFIG.items():
        for subtype in cfg["subtypes"]:
            items.append({
                "domain": domain_by_category.get(category, ""),
                "category": category,
                "category_label": cfg["label"],
                "subtype": subtype,
                "priority": f"{category}:{subtype}",
            })
    return items


def sample_non_priority_cases():
    cases = []

    lines = app_module.get_subway_line_options()
    if lines:
        cases.append({
            "kind": "category_sample",
            "domain": "transport",
            "category": "subway_line",
            "label": f"subway line={lines[0]}",
            "params": {"line": lines[0]},
        })

    station_index = app_module.get_subway_line_station_index()
    stations = sorted({station for values in station_index.values() for station in values})
    if stations:
        cases.append({
            "kind": "category_sample",
            "domain": "transport",
            "category": "subway",
            "label": f"station={stations[0]}",
            "params": {"station": stations[0]},
        })

    assigned = sorted({name for name in app_module._assigned_elementary_lookup().values() if name})
    if assigned:
        cases.append({
            "kind": "category_sample",
            "domain": "education",
            "category": "assigned_elementary",
            "label": f"assigned_elementary={assigned[0]}",
            "params": {"assigned_elementary": assigned[0]},
        })

    schools = []
    seen = set()
    for row in app_module.school_data:
        if row.get("subtype") not in ("middle", "high"):
            continue
        name = app_module.clean_text(row.get("name", ""))
        if name and name not in seen:
            seen.add(name)
            schools.append(name)
    schools.sort()
    if schools:
        cases.append({
            "kind": "category_sample",
            "domain": "education",
            "category": "school",
            "label": f"school={schools[0]}",
            "params": {"school": schools[0]},
        })

    routes_by_type = app_module._bus_routes_by_type()
    routes = sorted({route for routes in routes_by_type.values() for route in routes})
    if routes:
        cases.append({
            "kind": "category_sample",
            "domain": "transport",
            "category": "bus",
            "label": f"bus_route={routes[0]}",
            "params": {"bus_route": routes[0]},
        })

    cases.append({
        "kind": "category_sample",
        "domain": "safety",
        "category": "no_nightlife",
        "label": "no_nightlife=1",
        "params": {"no_nightlife": "1"},
    })

    return cases


def build_cases(max_pair_cases: int | None = None):
    items = priority_items()
    cases = []

    for item in items:
        cases.append({
            "kind": "priority_single",
            "domain": item["domain"],
            "category": item["category"],
            "label": f"{item['category_label']} / {item['subtype']}",
            "params": {"priority": item["priority"]},
        })

    pairs = itertools.combinations(items, 2)
    if max_pair_cases is not None:
        pairs = itertools.islice(pairs, max_pair_cases)
    for a, b in pairs:
        cases.append({
            "kind": "priority_pair",
            "domain": "+".join(sorted({a["domain"], b["domain"]})),
            "category": f"{a['category']}+{b['category']}",
            "label": f"{a['category_label']}:{a['subtype']} + {b['category_label']}:{b['subtype']}",
            "params": {"priority": [a["priority"], b["priority"]]},
        })

    by_category = {}
    for item in items:
        by_category.setdefault(item["category"], []).append(item)
    for category, group in by_category.items():
        cases.append({
            "kind": "category_bundle",
            "domain": group[0]["domain"],
            "category": category,
            "label": f"{group[0]['category_label']} all subtypes",
            "params": {"priority": [item["priority"] for item in group]},
        })

    by_domain = {}
    for item in items:
        if item["domain"]:
            by_domain.setdefault(item["domain"], []).append(item)
    for domain, group in by_domain.items():
        cases.append({
            "kind": "domain_bundle",
            "domain": domain,
            "category": "*",
            "label": f"{domain} all priority leaves",
            "params": {"priority": [item["priority"] for item in group]},
        })

    cases.extend(sample_non_priority_cases())
    return cases


def query_string(params):
    return urlencode(params, doseq=True)


def sort_ms_from_profile(profile):
    stats = pstats.Stats(profile)
    total = 0.0
    for func, data in stats.stats.items():
        name = func[2]
        if "sort" in name:
            total += data[3] * 1000
    return total


def run_case(client, case, repeats=1, profile_sort=True):
    samples = []
    url = "/explore?" + query_string(case["params"])
    for _ in range(repeats):
        metrics = Metrics()
        profile = cProfile.Profile() if profile_sort else None
        global CURRENT
        CURRENT = metrics
        start = time.perf_counter()
        if profile is not None:
            profile.enable()
        response = client.get(url)
        if profile is not None:
            profile.disable()
        total_ms = (time.perf_counter() - start) * 1000
        CURRENT = None
        samples.append({
            "status": response.status_code,
            "bytes": len(response.data),
            "total_ms": total_ms,
            "db_ms": metrics.db_ms,
            "baseline_ms": metrics.baseline_ms,
            "sort_ms": sort_ms_from_profile(profile) if profile is not None else 0.0,
            "template_ms": metrics.template_ms,
        })
    return samples


def aggregate_samples(samples):
    # Use the last sample after warmup-like repeat effects, but keep max total.
    if len(samples) == 1:
        return samples[0]
    last = samples[-1]
    return {**last, "max_total_ms": max(s["total_ms"] for s in samples)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-pair-cases", type=int, default=None)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--no-cprofile", action="store_true")
    args = parser.parse_args()

    # Warm import-time scenarios are already built by app import. Warm common option
    # caches too so request timings focus on Explore result generation/rendering.
    app_module.get_subway_line_station_index()
    app_module._assigned_elementary_lookup()
    app_module._bus_routes_by_type()

    cases = build_cases(args.max_pair_cases)
    client = app_module.app.test_client()
    original = install_instrumentation()
    rows = []
    try:
        for index, case in enumerate(cases, 1):
            samples = run_case(client, case, repeats=args.repeats, profile_sort=not args.no_cprofile)
            result = aggregate_samples(samples)
            rows.append({
                "rank": None,
                "index": index,
                "kind": case["kind"],
                "domain": case["domain"],
                "category": case["category"],
                "label": case["label"],
                "query": query_string(case["params"]),
                **result,
            })
    finally:
        restore_instrumentation(original)

    rows.sort(key=lambda row: row["total_ms"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "case_count": len(rows),
        "top": rows[:args.top],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

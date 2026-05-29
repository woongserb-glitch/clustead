import argparse
import csv
import os
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
REGISTRY_DIR = BASE_DIR / "data" / "registry"
DATA_SOURCES_PATH = REGISTRY_DIR / "data_sources.json"
SOURCE_STATUS_PATH = REGISTRY_DIR / "source_status.json"
UPDATE_LOG_PATH = REGISTRY_DIR / "update_log.json"
PIPELINE_RUN_DIR = REGISTRY_DIR / "pipeline_runs"
RAW_BACKUP_DIR = BASE_DIR / "data" / "raw_backup"

PIPELINE_RUN_DIR.mkdir(parents=True, exist_ok=True)
RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=True)


UPDATED_STATUSES = {"first_check", "update_available", "checked_no_remote_date"}


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


SEOUL_OPEN_DATA_CSV_DOWNLOAD_URL = (
    "https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do"
)

SEOUL_OPEN_DATA_API_URL = "http://openapi.seoul.go.kr:8088"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def count_csv_rows(path):
    if not path or not path.exists() or path.suffix.lower() != ".csv":
        return None

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return max(sum(1 for _ in file) - 1, 0)
    except Exception:
        return None


def get_baseline_path(source):
    baseline_path = source.get("baseline_path")
    if not baseline_path:
        return None

    return BASE_DIR / baseline_path


def get_raw_path(source):
    raw_path = (
        source.get("raw_path")
        or source.get("local_raw_path")
        or source.get("target_path")
    )
    if not raw_path:
        return None

    return BASE_DIR / raw_path


def get_baseline_meta_path(baseline_path):
    return baseline_path.with_name(f"{baseline_path.stem}.meta.json")


def read_baseline_meta(baseline_path):
    if not baseline_path:
        return {}

    return load_json(get_baseline_meta_path(baseline_path), {})


def write_baseline_meta(baseline_path, metadata):
    if not baseline_path:
        return

    save_json(get_baseline_meta_path(baseline_path), metadata)


def update_baseline_build_meta(source, result):
    baseline_path = get_baseline_path(source)
    if not baseline_path or result.get("build_status") != "success":
        return

    build_logs = [
        log for log in result.get("build_logs", [])
        if log.get("status") == "success"
    ]
    if not build_logs:
        return

    metadata = read_baseline_meta(baseline_path)
    raw_path = get_raw_path(source)

    metadata.update({
        "source_key": result.get("key") or get_source_key(source),
        "baseline_generated_at": result.get("build_finished_at"),
        "baseline_build_script": ", ".join(log.get("script", "") for log in build_logs if log.get("script")),
        "baseline_build_status": result.get("build_status"),
        "baseline_build_elapsed_seconds": result.get("build_elapsed_seconds"),
        "baseline_output": str(baseline_path.relative_to(BASE_DIR)),
        "baseline_row_count": count_csv_rows(baseline_path),
        "raw_path": str(raw_path.relative_to(BASE_DIR)) if raw_path else "",
        "raw_source_rows": count_csv_rows(raw_path) if raw_path else None,
        "updated_by": "build",
    })

    write_baseline_meta(baseline_path, metadata)


def attach_build_summary(result, source):
    build_logs = [
        log for log in result.get("build_logs", [])
        if log.get("status") not in ["no_build_scripts", "missing_script"]
    ]

    baseline_path = get_baseline_path(source)
    if baseline_path:
        result["baseline_output"] = str(baseline_path.relative_to(BASE_DIR))

    if not build_logs:
        return

    result["build_script"] = ", ".join(
        log.get("script", "") for log in build_logs if log.get("script")
    )
    result["build_started_at"] = build_logs[0].get("started_at")
    result["build_finished_at"] = build_logs[-1].get("finished_at")
    result["build_elapsed_seconds"] = round(
        sum(float(log.get("elapsed_seconds") or 0) for log in build_logs),
        1,
    )

    update_baseline_build_meta(source, result)
    if result.get("baseline_output"):
        print(f"[BUILD OUTPUT] {result['baseline_output']}", flush=True)
    if result.get("build_elapsed_seconds") is not None:
        print(f"[BUILD SUMMARY] elapsed={result['build_elapsed_seconds']}s", flush=True)


def detect_provider(url):
    url = str(url or "")

    if "data.seoul.go.kr" in url or "datafile.seoul.go.kr" in url:
        return "seoul_open_data"

    if "data.go.kr" in url:
        return "public_data_portal"

    if "file.localdata.go.kr" in url:
        return "localdata_file"

    return "unknown"


def request_with_retry(method, url, *, headers=None, data=None, params=None, timeout=25, retries=2):
    last_error = None
    merged_headers = dict(DEFAULT_HEADERS)

    if headers:
        merged_headers.update(headers)

    for attempt in range(retries + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=merged_headers,
                data=data,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.2 * (attempt + 1))

    raise last_error


def sanitize_error_text(text):
    return re.sub(
        r"([?&](?:serviceKey|ServiceKey)=)[^&\s]+",
        r"\1***",
        str(text or ""),
    )


def extract_date_from_text(text):
    text = str(text or "")

    patterns = [
        r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
        r"(20\d{2})(\d{2})(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    return None


def pick_remote_date_from_page(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    labels = [
        "데이터갱신일",
        "데이터 갱신일",
        "메타정보수정일",
        "메타정보 수정일",
        "수정일",
        "최종수정일",
        "최종 수정일",
        "변경일",
        "갱신일",
    ]

    for label in labels:
        idx = text.find(label)
        if idx < 0:
            continue

        nearby = text[idx: idx + 120]
        date_value = extract_date_from_text(nearby)

        if date_value:
            return date_value

    return extract_date_from_text(text)


def fetch_remote_metadata(source):
    if source.get("check_mode") == "manual":
        return {
            "status": "manual_check",
            "provider": source.get("provider"),
            "checked_at": now_iso(),
        }

    url = (
        source.get("source_page_url")
        or source.get("dataset_url")
        or source.get("api_meta_url")
    )
    provider = source.get("provider") or source.get("source_provider") or detect_provider(url)

    if not url:
        return {
            "status": "missing_source_url",
            "provider": provider,
            "error": "source_page_url 또는 api_meta_url이 data_sources.json에 없습니다.",
            "checked_at": now_iso(),
        }

    try:
        response = request_with_retry("GET", url)
        remote_updated_at = pick_remote_date_from_page(response.text)

        return {
            "status": "ok",
            "provider": provider,
            "remote_updated_at": remote_updated_at,
            "checked_at": now_iso(),
        }

    except Exception as exc:
        return {
            "status": "check_failed",
            "provider": provider,
            "error": str(exc),
            "checked_at": now_iso(),
        }


def get_source_key(source):
    return source.get("key") or source.get("name") or source.get("source_page_url")


def get_raw_path(source):
    raw_path = (
        source.get("raw_path")
        or source.get("local_raw_path")
        or source.get("target_path")
    )

    if not raw_path:
        return None

    return BASE_DIR / raw_path


def get_provider(source):
    return (
        source.get("provider")
        or source.get("source_provider")
        or detect_provider(source.get("source_page_url") or source.get("download_url"))
    )


def extract_oa_id(source):
    for key in ["inf_id", "infId", "dataset_id", "source_page_url", "dataset_url"]:
        value = str(source.get(key, "") or "")
        match = re.search(r"OA-\d+", value)

        if match:
            return match.group(0)

    return None


def build_seoul_open_data_download_config(source):
    if source.get("openapi_service"):
        return {
            "method": "SEOUL_OPEN_API",
            "service": source.get("openapi_service"),
            "page_size": int(source.get("page_size", 1000)),
            "service_key_env": source.get("service_key_env", "SEOUL_OPEN_DATA_KEY"),
        }

    # 서울 열린데이터광장은 미리보기 CSV 다운로드가 보통 아래 POST endpoint + infId payload 구조다.
    # Network Payload 예:
    # srvType=S, infId=OA-16096, serviceKind=1
    oa_id = extract_oa_id(source)

    if not oa_id:
        return None

    return {
        "method": "POST",
        "url": source.get("download_url") or SEOUL_OPEN_DATA_CSV_DOWNLOAD_URL,
        "data": {
            "srvType": source.get("srvType", "S"),
            "infId": oa_id,
            "serviceKind": str(source.get("serviceKind", "1")),
            "pageNo": str(source.get("pageNo", "1")),
        },
    }


def build_public_data_portal_download_config(source):
    # 공공데이터포털은 파일 직접 URL이면 download_url을 우선 사용한다.
    # API형 데이터는 api_download_url + service_key가 있는 경우만 자동 수집한다.
    if source.get("download_url"):
        return {
            "method": source.get("download_method", "GET").upper(),
            "url": source.get("download_url"),
            "params": source.get("download_params") or {},
            "data": source.get("download_data") or None,
        }

    api_url = source.get("api_download_url") or source.get("api_url")
    service_key = source.get("service_key") or source.get("api_key")
    service_key_env = source.get("service_key_env")

    if not service_key and service_key_env:
        service_key = os.getenv(service_key_env)

    if isinstance(service_key, str) and service_key.startswith("$"):
        service_key = os.getenv(service_key[1:])

    if service_key:
        service_key = unquote(str(service_key))

    if api_url and service_key:
        params = dict(source.get("api_params") or {})
        params.setdefault("serviceKey", service_key)
        params.setdefault("pageNo", "1")
        params.setdefault("numOfRows", source.get("num_of_rows", "10000"))
        params.setdefault("type", source.get("response_type", "json"))

        return {
            "method": "GET",
            "url": api_url,
            "params": params,
            "data": None,
        }

    return None


def build_localdata_file_download_config(source):
    if not source.get("download_url"):
        return None

    return {
        "method": source.get("download_method", "GET").upper(),
        "url": source.get("download_url"),
        "params": source.get("download_params") or {},
        "data": source.get("download_data") or None,
    }


def build_download_config(source):
    if source.get("download_config"):
        return source.get("download_config")

    provider = get_provider(source)

    if provider == "seoul_open_data":
        return build_seoul_open_data_download_config(source)

    if provider == "public_data_portal":
        return build_public_data_portal_download_config(source)

    if provider == "localdata_file":
        return build_localdata_file_download_config(source)

    if source.get("download_url"):
        return {
            "method": source.get("download_method", "GET").upper(),
            "url": source.get("download_url"),
            "params": source.get("download_params") or {},
            "data": source.get("download_data") or None,
        }

    return None


def backup_existing_file(path):
    if not path or not path.exists():
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = RAW_BACKUP_DIR / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = backup_dir / path.name
    shutil.copy2(path, backup_path)

    return str(backup_path.relative_to(BASE_DIR))


def extract_seoul_open_api_rows(payload, service):
    if not isinstance(payload, dict):
        return [], 0

    body = payload.get(service)

    if not isinstance(body, dict):
        for value in payload.values():
            if isinstance(value, dict) and ("row" in value or "list_total_count" in value):
                body = value
                break

    if not isinstance(body, dict):
        return [], 0

    rows = body.get("row") or []
    total = body.get("list_total_count") or len(rows)

    try:
        total = int(total)
    except Exception:
        total = len(rows)

    if isinstance(rows, dict):
        rows = [rows]

    return rows, total


def download_seoul_open_data_api(source, raw_path, config):
    service = config.get("service")
    service_key_env = config.get("service_key_env") or "SEOUL_OPEN_DATA_KEY"
    service_key = os.getenv(service_key_env) or os.getenv("SEOUL_OPEN_DATA_API_KEY")
    page_size = int(config.get("page_size") or 1000)

    if not service:
        return {
            "download_status": "missing_openapi_service",
            "error": "openapi_service is required for Seoul Open API download.",
        }

    if not service_key:
        return {
            "download_status": "missing_service_key",
            "error": f"{service_key_env} is required for Seoul Open API download.",
        }

    rows = []
    total_count = None
    start = 1

    try:
        while True:
            end = start + page_size - 1
            url = f"{SEOUL_OPEN_DATA_API_URL}/{service_key}/json/{service}/{start}/{end}/"
            response = request_with_retry(
                "GET",
                url,
                headers={"Referer": source.get("source_page_url", "https://data.seoul.go.kr/")},
                timeout=60,
                retries=2,
            )
            page_rows, total = extract_seoul_open_api_rows(response.json(), service)

            if total_count is None:
                total_count = total

            if not page_rows:
                break

            rows.extend(page_rows)

            if len(rows) >= total_count:
                break

            start = end + 1

        if not rows:
            return {
                "download_status": "download_failed",
                "error": "Seoul Open API returned no rows.",
            }

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = backup_existing_file(raw_path)

        fieldnames = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)

        with raw_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return {
            "download_status": "downloaded",
            "raw_path": str(raw_path.relative_to(BASE_DIR)),
            "backup_path": backup_path,
            "rows": len(rows),
            "downloaded_at": now_iso(),
        }

    except Exception as exc:
        response = getattr(exc, "response", None)
        response_text = ""

        if response is not None:
            try:
                response_text = response.text[:800]
            except Exception:
                response_text = ""

        return {
            "download_status": "download_failed",
            "error": sanitize_error_text(exc),
            "status_code": getattr(response, "status_code", None),
            "response_text_head": sanitize_error_text(response_text),
        }


def download_raw_data(source):
    raw_path = get_raw_path(source)

    if not raw_path:
        return {
            "download_status": "missing_raw_path",
            "error": "raw_path/local_raw_path/target_path가 없습니다.",
        }

    config = build_download_config(source)

    if not config:
        return {
            "download_status": "no_download_url",
            "error": "download_url 또는 자동 생성 가능한 다운로드 설정이 없습니다.",
        }

    method = str(config.get("method", "GET")).upper()

    if method == "SEOUL_OPEN_API":
        return download_seoul_open_data_api(source, raw_path, config)

    url = config.get("url")
    params = config.get("params") or None
    data = config.get("data") or None

    if not url:
        return {
            "download_status": "missing_download_url",
            "error": "download config에 url이 없습니다.",
        }

    headers = dict(DEFAULT_HEADERS)

    if get_provider(source) == "seoul_open_data":
        headers.update({
            "Origin": "https://data.seoul.go.kr",
            "Referer": source.get("source_page_url", "https://data.seoul.go.kr/"),
        })
    elif get_provider(source) == "localdata_file":
        headers.update({
            "Origin": "https://file.localdata.go.kr",
            "Referer": source.get("download_page_url")
            or source.get("source_page_url")
            or "https://file.localdata.go.kr/",
            "Accept": "text/csv,application/octet-stream,*/*",
        })

    try:
        response = request_with_retry(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
            timeout=60,
            retries=2,
        )

        content = response.content
        text_head = content[:500].decode(response.encoding or "utf-8", errors="ignore").lower()
        content_type = response.headers.get("Content-Type", "").lower()

        if not content or len(content) < 100:
            return {
                "download_status": "download_failed",
                "error": "응답 파일 크기가 너무 작습니다.",
            }

        if "<html" in text_head or "javascript" in text_head or "alert(" in text_head:
            return {
                "download_status": "download_failed",
                "error": "CSV/rawdata response was an HTML error page, so it was not saved.",
                "content_type": content_type,
                "bytes": len(content),
            }

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = backup_existing_file(raw_path)

        raw_path.write_bytes(content)

        return {
            "download_status": "downloaded",
            "raw_path": str(raw_path.relative_to(BASE_DIR)),
            "backup_path": backup_path,
            "bytes": len(content),
            "downloaded_at": now_iso(),
        }

    except Exception as exc:
        response = getattr(exc, "response", None)
        response_text = ""

        if response is not None:
            try:
                response_text = response.text[:800]
            except Exception:
                response_text = ""

        return {
            "download_status": "download_failed",
            "error": sanitize_error_text(exc),
            "status_code": getattr(response, "status_code", None),
            "response_text_head": sanitize_error_text(response_text),
        }


def run_build_scripts(source):
    logs = []
    scripts = source.get("build_scripts", [])

    if not scripts:
        return [{
            "status": "no_build_scripts",
            "message": "data_sources.json??build_scripts媛 ?놁뒿?덈떎.",
        }]

    for script in scripts:
        script_path = BASE_DIR / script

        if not script_path.exists():
            logs.append({
                "script": script,
                "status": "missing_script",
            })
            continue

        env = dict(os.environ)
        env["PYTHONPATH"] = (
            str(BASE_DIR)
            if not env.get("PYTHONPATH")
            else str(BASE_DIR) + os.pathsep + env["PYTHONPATH"]
        )
        env["PYTHONUNBUFFERED"] = "1"

        print("-" * 60, flush=True)
        print(f"[BUILD START] {script}", flush=True)
        started_at = time.time()
        started_iso = now_iso()
        output_lines = []

        process = subprocess.Popen(
            [sys.executable, "-u", str(script_path)],
            cwd=str(BASE_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            for line in process.stdout:
                print(line, end="", flush=True)
                output_lines.append(line)

            returncode = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            print(f"\n[BUILD INTERRUPTED] {script}", flush=True)
            raise

        elapsed_seconds = round(time.time() - started_at, 1)
        finished_iso = now_iso()
        status = "success" if returncode == 0 else "failed"
        print(f"[BUILD END] {script} - {status} ({elapsed_seconds}s)", flush=True)

        output = "".join(output_lines)
        logs.append({
            "script": script,
            "status": status,
            "returncode": returncode,
            "started_at": started_iso,
            "finished_at": finished_iso,
            "elapsed_seconds": elapsed_seconds,
            "stdout": output[-2000:],
            "stderr": "",
        })

    return logs


def summarize_build_status(build_logs):
    if not build_logs:
        return "not_run"

    statuses = [log.get("status") for log in build_logs]

    if any(status in ["failed", "missing_script"] for status in statuses):
        return "failed"

    if all(status == "no_build_scripts" for status in statuses):
        return "no_build_scripts"

    return "success"


def compare_status(source_key, metadata, previous_status):
    remote_updated_at = metadata.get("remote_updated_at")
    previous_remote = previous_status.get(source_key, {}).get("remote_updated_at")

    if metadata.get("status") != "ok":
        return metadata.get("status")

    if not remote_updated_at:
        return "checked_no_remote_date"

    if not previous_remote:
        return "first_check"

    if remote_updated_at != previous_remote:
        return "update_available"

    return "up_to_date"


def print_check_result(source, result):
    print("=" * 60)
    print(f"[CHECK] {source.get('name', source.get('key'))}")
    print(f"  - provider: {result.get('provider')}")

    for key in [
        "status",
        "action_status",
        "previous_remote_updated_at",
        "remote_updated_at",
        "download_status",
        "build_status",
        "build_elapsed_seconds",
        "baseline_output",
        "error",
    ]:
        if result.get(key):
            print(f"  - {key}: {result.get(key)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--download-updated", action="store_true")
    parser.add_argument("--download-all", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--rebuild-updated", action="store_true")
    parser.add_argument("--rebuild-all", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    registry = load_json(DATA_SOURCES_PATH, {"sources": []})
    previous_status = load_json(SOURCE_STATUS_PATH, {})
    new_status = dict(previous_status)

    run_results = []

    for source in registry.get("sources", []):
        source_key = get_source_key(source)

        if args.build_only:
            result = {
                "key": source_key,
                "name": source.get("name"),
                "provider": get_provider(source),
                "status": "build_only",
                "action_status": "baseline_rebuild_requested",
                "download_status": "skipped_build_only",
                "checked_at": now_iso(),
            }
            result["build_logs"] = run_build_scripts(source)
            result["build_status"] = summarize_build_status(result["build_logs"])
            attach_build_summary(result, source)
            if result["build_status"] == "success":
                result["action_status"] = "baseline_rebuilt"

            print_check_result(source, result)
            run_results.append(result)
            continue

        metadata = fetch_remote_metadata(source)
        status = compare_status(source_key, metadata, previous_status)

        result = {
            "key": source_key,
            "name": source.get("name"),
            "provider": metadata.get("provider") or get_provider(source),
            "status": status,
            "previous_remote_updated_at": previous_status.get(source_key, {}).get("remote_updated_at"),
            "remote_updated_at": metadata.get("remote_updated_at"),
            "checked_at": metadata.get("checked_at") or now_iso(),
        }

        if metadata.get("error"):
            result["error"] = metadata.get("error")

        if args.check_only:
            result["action_status"] = "checked_only"
            result["download_status"] = "skipped_check_only"
            result["build_status"] = "skipped_check_only"

        should_download = (
            not args.check_only
            and (
                args.download_all
                or status in UPDATED_STATUSES
            )
            and status != "manual_check"
        )

        if args.download_only and not should_download:
            # download-only는 업데이트 대상만 다운로드한다.
            pass

        if should_download:
            download_result = download_raw_data(source)
            result.update(download_result)
            if result.get("download_status") == "downloaded":
                result["action_status"] = "raw_downloaded"
            if args.download_only:
                result["build_status"] = "skipped_download_only"

        if args.download_only and not should_download and not args.check_only:
            result["download_status"] = "skipped_not_updated"
            result["build_status"] = "skipped_download_only"
            result["action_status"] = (
                "up_to_date_no_action"
                if status == "up_to_date"
                else "download_only_no_action"
            )

        should_rebuild = (
            not args.check_only
            and not args.download_only
            and (
                args.rebuild_all
                or (
                    status in UPDATED_STATUSES
                    and result.get("download_status") == "downloaded"
                )
            )
            and status != "manual_check"
        )

        if should_rebuild:
            result["build_logs"] = run_build_scripts(source)
            result["build_status"] = summarize_build_status(result["build_logs"])
            attach_build_summary(result, source)
            if result["build_status"] == "success":
                result["action_status"] = "baseline_rebuilt"
        elif (
            not args.check_only
            and not args.download_only
            and status in UPDATED_STATUSES
            and status != "manual_check"
        ):
            result["build_status"] = "skipped_download_not_success"
            result["action_status"] = "baseline_rebuild_skipped"
        elif (
            not args.check_only
            and not args.download_only
            and not result.get("build_status")
        ):
            result["build_status"] = "skipped_up_to_date"
            result["action_status"] = (
                result.get("action_status")
                or "up_to_date_no_action"
            )

        print_check_result(source, result)
        run_results.append(result)

        # check_failed/manual_check 등은 기존 remote 날짜를 덮어쓰지 않는다.
        should_update_status = (
            not args.check_only
            and
            metadata.get("status") == "ok"
            and not (
                should_download
                and result.get("download_status") != "downloaded"
            )
        )

        if should_update_status:
            new_status[source_key] = {
                "remote_updated_at": metadata.get("remote_updated_at"),
                "last_checked_at": result.get("checked_at"),
                "provider": result.get("provider"),
                "name": source.get("name"),
            }

    save_json(SOURCE_STATUS_PATH, new_status)
    save_json(UPDATE_LOG_PATH, run_results)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_report_path = PIPELINE_RUN_DIR / f"update_check_{stamp}.json"
    save_json(run_report_path, run_results)

    print("=" * 60)
    print(f"[완료] 최신자료 점검/배치 로그 저장: {UPDATE_LOG_PATH}")
    print(f"[완료] 실행 리포트 저장: {run_report_path}")


if __name__ == "__main__":
    main()

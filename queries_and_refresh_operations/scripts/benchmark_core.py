"""Shared execution and result-writing code for TigerGraph query benchmarks."""

from __future__ import annotations

import csv
import json
import statistics
import time
from urllib.parse import quote, urlencode
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from query_specs import (
    PROJECT_ROOT,
    RUNS,
    TRIM_EACH_SIDE,
    QuerySpec,
    api_parameters,
    file_sha256,
)


DEFAULT_HOST = "http://localhost:14240"
DEFAULT_GRAPH = "TPCH_G"
POLL_INTERVAL_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 60
QUERY_TIMEOUT_SECONDS = 60 * 60
OUTPUT_ROOT = PROJECT_ROOT / "results" / "query_benchmarks"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def submit_and_wait(
    *,
    host: str,
    graph: str,
    installed_query: str,
    parameters: dict[str, str],
) -> tuple[str, float]:
    encoded_parameters = urlencode(parameters, quote_via=quote)
    response = requests.get(
        f"{host}/restpp/query/{graph}/{installed_query}?{encoded_parameters}",
        headers={"GSQL-ASYNC": "true"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    submitted = response.json()
    if submitted.get("error"):
        raise RuntimeError(f"TigerGraph submission failed: {submitted}")

    request_id = submitted.get("requestid")
    if not request_id:
        raise RuntimeError(f"No requestid returned: {submitted}")

    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{host}/restpp/query_status",
            params={"graph_name": graph, "requestid": request_id},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        status_response.raise_for_status()
        status_data = status_response.json()
        if status_data.get("error"):
            raise RuntimeError(f"query_status failed: {status_data}")

        results = status_data.get("results", [])
        if results:
            info = results[0]
            status = info.get("status")
            if status == "success":
                elapsed = info.get("elapsedTime")
                if elapsed is None:
                    raise RuntimeError(
                        f"No elapsedTime returned for {request_id}: {info}"
                    )
                return request_id, float(elapsed)
            if status in {"failed", "aborted", "timeout", "expired"}:
                raise RuntimeError(f"Query {request_id} ended with {status}: {info}")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Query {request_id} did not finish within {QUERY_TIMEOUT_SECONDS} seconds"
    )


def make_run_directory(spec: QuerySpec, scale: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    variant_root = OUTPUT_ROOT
    if spec.variant != "current":
        variant_root = variant_root / spec.variant.replace("-", "_")
    run_dir = (
        variant_root
        / f"sf{scale}"
        / "graph"
        / f"q{spec.number:02d}"
        / timestamp
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_benchmark(
    *,
    spec: QuerySpec,
    scale: str,
    schedule: list[dict[str, str]],
    host: str = DEFAULT_HOST,
    graph: str = DEFAULT_GRAPH,
) -> Path:
    if len(schedule) != RUNS or RUNS <= 2 * TRIM_EACH_SIDE:
        raise ValueError("Invalid run count or trimming configuration")

    run_dir = make_run_directory(spec, scale)
    parameter_fields = list(schedule[0].keys())
    write_csv(run_dir / "parameters.csv", parameter_fields, schedule)

    manifest = {
        "status": "running",
        "query": spec.code.upper(),
        "installed_query": spec.installed_query,
        "scale_factor": scale,
        "semantics": "graph",
        "semantic_status": spec.semantic_status,
        "query_variant": spec.variant,
        "note": spec.note,
        "host": host,
        "graph": graph,
        "runs": RUNS,
        "trim_each_side": TRIM_EACH_SIDE,
        "timing_metric": "TigerGraph query_status.elapsedTime",
        "query_file": str(spec.query_file),
        "query_file_sha256": file_sha256(spec.query_file),
        "parameter_source": str(spec.canonical_parameter_file),
        "parameter_source_sha256": file_sha256(spec.canonical_parameter_file),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(run_dir / "manifest.json", manifest)

    raw_rows: list[dict[str, Any]] = []
    raw_fields = parameter_fields + ["request_id", "elapsed_ms", "kept", "status"]

    try:
        for index, parameter_row in enumerate(schedule, start=1):
            request_id, elapsed_ms = submit_and_wait(
                host=host,
                graph=graph,
                installed_query=spec.installed_query,
                parameters=api_parameters(spec, parameter_row),
            )
            raw_row: dict[str, Any] = dict(parameter_row)
            raw_row.update(
                {
                    "request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "kept": "",
                    "status": "success",
                }
            )
            raw_rows.append(raw_row)
            write_csv(run_dir / "raw.csv", raw_fields, raw_rows)
            print(
                f"{spec.code.upper()} run {index:02d}/{RUNS}: "
                f"{elapsed_ms:g} ms"
            )

        ranked = sorted(
            range(len(raw_rows)), key=lambda item: raw_rows[item]["elapsed_ms"]
        )
        kept_indexes = set(ranked[TRIM_EACH_SIDE:-TRIM_EACH_SIDE])
        for index, row in enumerate(raw_rows):
            row["kept"] = "true" if index in kept_indexes else "false"
        write_csv(run_dir / "raw.csv", raw_fields, raw_rows)

        kept_times = [
            row["elapsed_ms"]
            for index, row in enumerate(raw_rows)
            if index in kept_indexes
        ]
        summary = {
            "query": spec.code.upper(),
            "installed_query": spec.installed_query,
            "scale_factor": scale,
            "semantics": "graph",
            "semantic_status": spec.semantic_status,
            "query_variant": spec.variant,
            "total_runs": RUNS,
            "trim_each_side": TRIM_EACH_SIDE,
            "used_runs": len(kept_times),
            "mean_ms": round(statistics.fmean(kept_times), 3),
            "min_kept_ms": min(kept_times),
            "max_kept_ms": max(kept_times),
            "timing_metric": "query_status.elapsedTime",
        }
        write_csv(run_dir / "summary.csv", list(summary), [summary])

        manifest.update(
            {
                "status": "success",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "summary": summary,
            }
        )
        write_json(run_dir / "manifest.json", manifest)
        return run_dir
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "completed_runs": len(raw_rows),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(run_dir / "manifest.json", manifest)
        raise

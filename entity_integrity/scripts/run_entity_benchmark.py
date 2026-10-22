"""Run formal Entity Integrity benchmarks using query_status.elapsedTime."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


HOST = "http://localhost:14240"
GRAPH = "TPCH_G"
RUNS = 20
TRIM_EACH_SIDE = 5
POLL_INTERVAL_SECONDS = 0.05
REQUEST_TIMEOUT_SECONDS = 60
QUERY_TIMEOUT_SECONDS = 60 * 30
SUPPORTED_SCALES = ("0.01", "0.1", "1")

ENTITY_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ENTITY_ROOT / "results" / "performance_query_status"


@dataclass(frozen=True)
class EntityBenchmark:
    code: str
    query: str
    definition_file: Path
    er_key: str
    fixed_position: str


BENCHMARKS = {
    "lineitem": EntityBenchmark(
        code="lineitem",
        query="key_verification_lineitem",
        definition_file=ENTITY_ROOT / "lineitem" / "key_verification_lineitem.txt",
        er_key="({ORDERS}, {l_linenumber})",
        fixed_position="o_orderkey=1; l_linenumber=9",
    ),
    "partsupp": EntityBenchmark(
        code="partsupp",
        query="key_verification_partsupp",
        definition_file=ENTITY_ROOT / "partsupp" / "key_verification_partsupp.txt",
        er_key="({PART, SUPPLIER}, empty)",
        fixed_position="p_partkey=1; s_suppkey=1",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(benchmark: EntityBenchmark) -> None:
    if not benchmark.definition_file.is_file():
        raise FileNotFoundError(benchmark.definition_file)
    text = benchmark.definition_file.read_text(encoding="utf-8-sig")
    match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+OPENCYPHER\s+QUERY\s+(\w+)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"No query declaration in {benchmark.definition_file}")
    if match.group(1) != benchmark.query:
        raise ValueError(
            f"Query mismatch: file declares {match.group(1)!r}, "
            f"expected {benchmark.query!r}"
        )


def submit_and_wait(benchmark: EntityBenchmark, host: str, graph: str) -> tuple[str, float]:
    response = requests.get(
        f"{host}/restpp/query/{graph}/{benchmark.query}",
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
                    raise RuntimeError(f"No elapsedTime returned: {info}")
                return request_id, float(elapsed)
            if status in {"failed", "aborted", "timeout", "expired"}:
                raise RuntimeError(f"Query {request_id} ended with {status}: {info}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Query {request_id} exceeded {QUERY_TIMEOUT_SECONDS} seconds")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_one(
    benchmark: EntityBenchmark,
    scale: str,
    host: str,
    graph: str,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = (
        OUTPUT_ROOT / f"sf{scale}" / "graph" / benchmark.code / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "status": "running",
        "experiment": "entity_integrity_fixed_position_performance",
        "entity": benchmark.code.upper(),
        "query": benchmark.query,
        "scale_factor": scale,
        "semantics": "graph",
        "er_key": benchmark.er_key,
        "fixed_position": benchmark.fixed_position,
        "runs": RUNS,
        "trim_each_side": TRIM_EACH_SIDE,
        "timing_metric": "TigerGraph query_status.elapsedTime",
        "db_hits": "not available; not reported",
        "definition_file": str(benchmark.definition_file),
        "definition_sha256": sha256(benchmark.definition_file),
        "host": host,
        "graph": graph,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(output_dir / "manifest.json", manifest)

    raw_rows: list[dict[str, Any]] = []
    raw_fields = ["run", "request_id", "elapsed_ms", "kept", "status"]
    try:
        for run_number in range(1, RUNS + 1):
            request_id, elapsed_ms = submit_and_wait(benchmark, host, graph)
            raw_rows.append(
                {
                    "run": run_number,
                    "request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "kept": "",
                    "status": "success",
                }
            )
            write_csv(output_dir / "raw.csv", raw_fields, raw_rows)
            print(
                f"{benchmark.code.upper()} run {run_number:02d}/{RUNS}: "
                f"{elapsed_ms:g} ms"
            )

        ranked = sorted(
            range(len(raw_rows)), key=lambda index: raw_rows[index]["elapsed_ms"]
        )
        kept_indexes = set(ranked[TRIM_EACH_SIDE:-TRIM_EACH_SIDE])
        for index, row in enumerate(raw_rows):
            row["kept"] = "true" if index in kept_indexes else "false"
        write_csv(output_dir / "raw.csv", raw_fields, raw_rows)

        kept_times = [
            row["elapsed_ms"]
            for index, row in enumerate(raw_rows)
            if index in kept_indexes
        ]
        summary = {
            "entity": benchmark.code.upper(),
            "query": benchmark.query,
            "scale_factor": scale,
            "semantics": "graph",
            "total_runs": RUNS,
            "trim_each_side": TRIM_EACH_SIDE,
            "used_runs": len(kept_times),
            "mean_ms": round(statistics.fmean(kept_times), 3),
            "min_kept_ms": min(kept_times),
            "max_kept_ms": max(kept_times),
            "timing_metric": "query_status.elapsedTime",
        }
        write_csv(output_dir / "summary.csv", list(summary), [summary])
        manifest.update(
            {
                "status": "success",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "summary": summary,
            }
        )
        write_json(output_dir / "manifest.json", manifest)
        return output_dir
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "completed_runs": len(raw_rows),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        write_json(output_dir / "manifest.json", manifest)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run formal TigerGraph Entity Integrity performance benchmarks."
    )
    selection = result.add_mutually_exclusive_group(required=True)
    selection.add_argument("--entity", choices=tuple(BENCHMARKS))
    selection.add_argument("--all", action="store_true")
    result.add_argument("--scale", required=True, choices=SUPPORTED_SCALES)
    result.add_argument("--host", default=HOST)
    result.add_argument("--graph", default=GRAPH)
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate query files without contacting TigerGraph or writing results.",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    names = list(BENCHMARKS) if args.all else [args.entity]
    for name in names:
        benchmark = BENCHMARKS[name]
        validate(benchmark)
        if args.dry_run:
            print(
                f"{benchmark.code.upper()}: query={benchmark.query}, "
                f"metric=query_status.elapsedTime, file={benchmark.definition_file}"
            )
            continue
        output_dir = run_one(benchmark, args.scale, args.host, args.graph)
        print(f"{benchmark.code.upper()} results: {output_dir}")
    if args.dry_run:
        print("Dry-run passed; TigerGraph was not contacted and no results were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

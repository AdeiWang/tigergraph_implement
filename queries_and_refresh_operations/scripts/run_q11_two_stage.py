"""Run scalable two-stage Q11 with two openCypher queries and Python orchestration."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

from benchmark_core import DEFAULT_GRAPH, DEFAULT_HOST, submit_and_wait, write_csv, write_json
from query_specs import PROJECT_ROOT, RUNS, TRIM_EACH_SIDE, get_spec, load_parameter_schedule

THRESHOLD_QUERY = "q11_threshold_tigergraph"
VALUES_QUERY = "q11_values_tigergraph"
OUTPUT_ROOT = PROJECT_ROOT / "results" / "query_benchmarks_final" / "two-stage"


def payload(host: str, graph: str, query: str, parameters: dict[str, str]) -> dict[str, Any]:
    encoded = urlencode(parameters, quote_via=quote)
    response = requests.get(
        f"{host}/restpp/query/{graph}/{query}?{encoded}", timeout=3600
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data)
    return data


def scalar(data: Any, field: str) -> float:
    if isinstance(data, dict):
        if field in data:
            return float(data[field])
        for value in data.values():
            try:
                return scalar(value, field)
            except KeyError:
                pass
    elif isinstance(data, list):
        for value in data:
            try:
                return scalar(value, field)
            except KeyError:
                pass
    raise KeyError(field)


def rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in data.get("results", []):
        for value in block.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                result.extend(value)
    return result


def trimmed(values: list[float]) -> dict[str, Any]:
    kept = sorted(values)[TRIM_EACH_SIDE:-TRIM_EACH_SIDE]
    return {
        "total_runs": len(values),
        "trim_each_side": TRIM_EACH_SIDE,
        "used_runs": len(kept),
        "mean_ms": round(statistics.fmean(kept), 3),
        "min_kept_ms": min(kept),
        "max_kept_ms": max(kept),
    }


def run(scale: str, host: str, graph: str, runs: int) -> Path:
    schedule = load_parameter_schedule(get_spec(11), scale)[:runs]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = OUTPUT_ROOT / f"sf{scale}" / "graph" / "q11" / stamp
    outputs = out / "final_outputs"
    outputs.mkdir(parents=True)
    raw: list[dict[str, Any]] = []

    for index, row in enumerate(schedule, 1):
        first = {"selected_nation": row["selected_nation"], "fraction": row["fraction"]}
        round_start = time.perf_counter()
        id1, t1 = submit_and_wait(
            host=host, graph=graph, installed_query=THRESHOLD_QUERY, parameters=first
        )
        threshold = scalar(payload(host, graph, THRESHOLD_QUERY, first), "threshold")
        second = {"selected_nation": row["selected_nation"], "threshold": format(threshold, ".17g")}
        id2, t2 = submit_and_wait(
            host=host, graph=graph, installed_query=VALUES_QUERY, parameters=second
        )
        final = rows(payload(host, graph, VALUES_QUERY, second))
        # Detached timed calls do not return result rows, so the two queries are
        # executed synchronously a second time to materialise and validate the
        # final output.  This wall-clock interval therefore includes four
        # database calls and is not a one-pass end-to-end Q11 measurement.
        round_wall_ms = (time.perf_counter() - round_start) * 1000.0
        normalized = [
            {"partkey": int(item["partkey"]), "value": float(item["value"])}
            for item in final
        ]
        write_csv(outputs / f"run_{index:02d}.csv", ["partkey", "value"], normalized)
        raw.append({
            "run": index,
            "position": row.get("position", ""),
            "selected_nation": row["selected_nation"],
            "fraction": row["fraction"],
            "threshold": threshold,
            "threshold_request_id": id1,
            "values_request_id": id2,
            "threshold_elapsed_ms": t1,
            "values_elapsed_ms": t2,
            "database_elapsed_ms": t1 + t2,
            "round_wall_ms": round(round_wall_ms, 3),
            "result_rows": len(normalized),
        })
        print(
            f"Q11 two-stage run {index:02d}/{runs}: db={t1 + t2:g} ms, "
            f"round-wall={round_wall_ms:.3f} ms, rows={len(normalized)}"
        )

    db = trimmed([float(item["database_elapsed_ms"]) for item in raw]) if runs == RUNS else {}
    round_wall = trimmed([float(item["round_wall_ms"]) for item in raw]) if runs == RUNS else {}
    summary = {
        "query": "Q11",
        "scale_factor": scale,
        "variant": "two-stage",
        "installed_queries": f"{THRESHOLD_QUERY}+{VALUES_QUERY}",
        **{f"database_{key}": value for key, value in db.items()},
        **{f"round_wall_{key}": value for key, value in round_wall.items()},
        "primary_comparison_metric": "database_mean_ms",
        "database_timing_metric": "sum of two query_status.elapsedTime values",
        "python_orchestration": "passes threshold between two openCypher queries and saves complete output",
        "round_wall_scope": (
            "two detached timed calls plus two repeated synchronous calls used "
            "to retrieve threshold and output; not a one-pass end-to-end metric"
        ),
        "formal": runs == RUNS,
    }
    write_csv(out / "parameters.csv", list(schedule[0]), schedule)
    write_csv(out / "raw.csv", list(raw[0]), raw)
    write_csv(out / "summary.csv", list(summary), [summary])
    write_json(out / "manifest.json", summary)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=("0.01", "0.1", "1"), required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--runs", type=int, choices=(1, RUNS), default=RUNS)
    args = parser.parse_args()
    print(run(args.scale, args.host, args.graph, args.runs))


if __name__ == "__main__":
    main()

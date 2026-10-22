"""Run final Q21/Q22 benchmarks and materialize complete CSV results."""

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
from query_specs import PROJECT_ROOT, RUNS, TRIM_EACH_SIDE

ROOT = PROJECT_ROOT / "queries_and_refresh_operations"
OUTPUT_ROOT = PROJECT_ROOT / "results" / "query_benchmarks_final"
Q22_FIELDS = ("code1", "code2", "code3", "code4", "code5", "code6", "code7")
Q22_NEO4J_COMPATIBLE_CODES = ("25", "23", "11", "14", "13", "30", "28")


def load_schedule(number: int) -> list[dict[str, str]]:
    path = PROJECT_ROOT / "results" / f"q{number}" / f"q{number}_benchmark_parameter_order.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != RUNS:
        raise ValueError(f"Expected {RUNS} rows in {path}, found {len(rows)}")
    return rows


def synchronous_rows(host: str, graph: str, query: str, params: dict[str, str]) -> list[dict[str, Any]]:
    encoded = urlencode(params, quote_via=quote)
    response = requests.get(
        f"{host}/restpp/query/{graph}/{query}?{encoded}", timeout=600
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data)
    rows: list[dict[str, Any]] = []
    for block in data.get("results", []):
        for value in block.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                rows.extend(value)
    return rows


def finalize_q21(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    final = []
    for row in rows:
        numwait = int(row["candidate_plus_flag"]) - int(row["bad_plus_flag"])
        if numwait > 0:
            final.append({"supplier_name": row["supplier_name"], "numwait": numwait})
    return sorted(final, key=lambda row: (-row["numwait"], row["supplier_name"]))


def finalize_q22(
    customers: list[dict[str, Any]], ordered: list[dict[str, Any]]
) -> tuple[float, list[dict[str, Any]]]:
    positive = [float(row["acctbal"]) for row in customers if float(row["acctbal"]) > 0.0]
    average = statistics.fmean(positive)
    ordered_ids = {int(row["customer_key"]) for row in ordered}
    grouped: dict[str, list[float]] = {}
    for row in customers:
        balance = float(row["acctbal"])
        if balance > average and int(row["customer_key"]) not in ordered_ids:
            grouped.setdefault(str(row["cntrycode"]), []).append(balance)
    final = [
        {
            "cntrycode": code,
            "numcust": len(values),
            "totalacctbal": f"{sum(values):.2f}",
        }
        for code, values in sorted(grouped.items())
    ]
    return average, final


def trimmed_summary(times: list[float]) -> dict[str, Any]:
    ranked = sorted(times)
    kept = ranked[TRIM_EACH_SIDE:-TRIM_EACH_SIDE]
    return {
        "total_runs": len(times),
        "trim_each_side": TRIM_EACH_SIDE,
        "used_runs": len(kept),
        "mean_ms": round(statistics.fmean(kept), 3),
        "min_kept_ms": min(kept),
        "max_kept_ms": max(kept),
    }


def run_q21(variant: str, scale: str, host: str, graph: str) -> Path:
    query = f"q21_tigergraph_{variant.replace('-', '_')}"
    schedule = load_schedule(21)
    out = OUTPUT_ROOT / variant / f"sf{scale}" / "graph" / "q21" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    outputs = out / "final_outputs"
    outputs.mkdir(parents=True)
    raw: list[dict[str, Any]] = []
    for index, row in enumerate(schedule, 1):
        params = {"selected_nation": row["selected_nation"]}
        request_id, elapsed = submit_and_wait(host=host, graph=graph, installed_query=query, parameters=params)
        final = finalize_q21(synchronous_rows(host, graph, query, params))
        # Official TPC-H Q21 returns at most the first 100 rows. The Neo4j
        # reference workload has no LIMIT, so keep that variant unchanged.
        if variant == "tpch-corrected":
            final = final[:100]
        write_csv(outputs / f"run_{index:02d}.csv", ["supplier_name", "numwait"], final)
        raw.append({"run": index, **params, "request_id": request_id, "elapsed_ms": elapsed})
        print(f"Q21 {variant} run {index:02d}/{RUNS}: {elapsed:g} ms, rows={len(final)}")
    times = [float(row["elapsed_ms"]) for row in raw]
    summary = {"query": "Q21", "scale_factor": scale, "variant": variant, "installed_query": query, **trimmed_summary(times), "timing_metric": "query_status.elapsedTime", "postprocessing_timed": False}
    write_csv(out / "raw.csv", list(raw[0]), raw)
    write_csv(out / "summary.csv", list(summary), [summary])
    write_json(out / "manifest.json", summary)
    return out


def run_q22(variant: str, scale: str, host: str, graph: str) -> Path:
    schedule = load_schedule(22)
    out = OUTPUT_ROOT / variant / f"sf{scale}" / "graph" / "q22" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    outputs = out / "final_outputs"
    outputs.mkdir(parents=True)
    raw: list[dict[str, Any]] = []
    for index, row in enumerate(schedule, 1):
        if variant == "neo4j-compatible":
            params = dict(zip(Q22_FIELDS, Q22_NEO4J_COMPATIBLE_CODES))
        else:
            params = {field: row[field] for field in Q22_FIELDS}
        id1, t1 = submit_and_wait(host=host, graph=graph, installed_query="q22_customers_tigergraph", parameters=params)
        id2, t2 = submit_and_wait(host=host, graph=graph, installed_query="q22_order_customers_tigergraph", parameters=params)
        end_to_end_start = time.perf_counter()
        customers = synchronous_rows(host, graph, "q22_customers_tigergraph", params)
        ordered = synchronous_rows(host, graph, "q22_order_customers_tigergraph", params)
        average, final = finalize_q22(customers, ordered)
        end_to_end_ms = (time.perf_counter() - end_to_end_start) * 1000.0
        write_csv(outputs / f"run_{index:02d}.csv", ["cntrycode", "numcust", "totalacctbal"], final)
        raw.append({"run": index, **params, "customers_request_id": id1, "orders_request_id": id2, "customers_elapsed_ms": t1, "orders_elapsed_ms": t2, "database_elapsed_ms": t1 + t2, "end_to_end_ms": round(end_to_end_ms, 3), "positive_average_balance": round(average, 6)})
        print(f"Q22 {variant} run {index:02d}/{RUNS}: db={t1 + t2:g} ms, end-to-end={end_to_end_ms:.3f} ms, rows={len(final)}")
    database_times = [float(row["database_elapsed_ms"]) for row in raw]
    end_to_end_times = [float(row["end_to_end_ms"]) for row in raw]
    db_summary = trimmed_summary(database_times)
    e2e_summary = trimmed_summary(end_to_end_times)
    summary = {"query": "Q22", "scale_factor": scale, "variant": variant, "installed_queries": "q22_customers_tigergraph+q22_order_customers_tigergraph", **{f"database_{key}": value for key, value in db_summary.items()}, **{f"end_to_end_{key}": value for key, value in e2e_summary.items()}, "primary_comparison_metric": "end_to_end_mean_ms", "database_timing_metric": "sum of query_status.elapsedTime", "code_selection": "inferred first-seven Neo4j scan order" if variant == "neo4j-compatible" else "official TPC-H fixed codes", "postprocessing_in_end_to_end": True}
    write_csv(out / "raw.csv", list(raw[0]), raw)
    write_csv(out / "summary.csv", list(summary), [summary])
    write_json(out / "manifest.json", summary)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", choices=("21", "22", "both"), default="both")
    parser.add_argument("--q21-variant", choices=("neo4j-compatible", "tpch-corrected", "both"), default="both")
    parser.add_argument("--q22-variant", choices=("neo4j-compatible", "tpch-corrected", "both"), default="neo4j-compatible")
    parser.add_argument("--scale", choices=("0.01", "0.1", "1"), default="0.01")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    args = parser.parse_args()
    if args.query in {"21", "both"}:
        variants = ("neo4j-compatible", "tpch-corrected") if args.q21_variant == "both" else (args.q21_variant,)
        for variant in variants:
            print(run_q21(variant, args.scale, args.host, args.graph))
    if args.query in {"22", "both"}:
        variants = ("neo4j-compatible", "tpch-corrected") if args.q22_variant == "both" else (args.q22_variant,)
        for variant in variants:
            print(run_q22(variant, args.scale, args.host, args.graph))


if __name__ == "__main__":
    main()

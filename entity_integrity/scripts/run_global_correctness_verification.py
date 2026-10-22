"""Run non-benchmark, whole-graph E/R-key correctness verification."""

import argparse
import csv
from datetime import datetime
from pathlib import Path

import requests


BASE_URL = "http://localhost:14240"
GRAPH = "TPCH_G"
SCALE_FACTOR = "0.01"
REQUEST_TIMEOUT = 300
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results" / "global_correctness_sf001"

CHECKS = (
    {
        "entity": "LINEITEM",
        "er_key": "({ORDERS}, {l_linenumber})",
        "query": "global_verify_lineitem",
    },
    {
        "entity": "PARTSUPP",
        "er_key": "({PART, SUPPLIER}, empty)",
        "query": "global_verify_partsupp",
    },
)


def extract_single_value(value, field):
    if isinstance(value, dict):
        if field in value:
            return value[field]
        for child in value.values():
            found = extract_single_value(child, field)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = extract_single_value(child, field)
            if found is not None:
                return found
    return None


def run_check(check, base_url, graph):
    response = requests.get(
        f"{base_url}/restpp/query/{graph}/{check['query']}",
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"{check['query']} failed: {data}")

    value = extract_single_value(data, "violation_count")
    if value is None:
        raise RuntimeError(
            f"{check['query']} did not return violation_count: {data}"
        )

    violation_count = int(value)
    return violation_count, "PASS" if violation_count == 0 else "FAIL"


def write_results(rows, timestamp, output_dir, scale_tag):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"global_correctness_sf{scale_tag}_{timestamp}.csv"
    fields = (
        "timestamp",
        "scale_factor",
        "semantics",
        "entity",
        "er_key",
        "query",
        "violation_count",
        "status",
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default=SCALE_FACTOR, choices=("0.01", "0.1", "1"))
    parser.add_argument("--host", default=BASE_URL)
    parser.add_argument("--graph", default=GRAPH)
    args = parser.parse_args()
    scale_tag = args.scale.replace(".", "")
    output_dir = Path(__file__).resolve().parent.parent / "results" / f"global_correctness_sf{scale_tag}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows = []

    for check in CHECKS:
        violation_count, status = run_check(check, args.host, args.graph)
        row = {
            "timestamp": timestamp,
            "scale_factor": args.scale,
            "semantics": "graph",
            "entity": check["entity"],
            "er_key": check["er_key"],
            "query": check["query"],
            "violation_count": violation_count,
            "status": status,
        }
        rows.append(row)
        print(
            f"{check['entity']}: violation_count={violation_count}, status={status}"
        )

    output_path = write_results(rows, timestamp, output_dir, scale_tag)
    print(f"Results saved to: {output_path}")

    failed = [row for row in rows if row["status"] != "PASS"]
    if failed:
        raise SystemExit("Global entity-integrity verification failed.")


if __name__ == "__main__":
    main()

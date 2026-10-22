"""Shared runner for graph-semantics referential-integrity benchmarks."""

import csv
import argparse
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests


BASE_URL = "http://localhost:14240"
GRAPH = "TPCH_G"
PERCENTAGES = [0.001, 0.01, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0]
RUNS = 20
OUTLIERS = 5
POLL_INTERVAL = 0.05
REQUEST_TIMEOUT = 60
RANDOM_SEED = 20260921
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ChainConfig:
    code: str
    description: str
    entity_name: str
    entity_count: int
    key_name: str
    expected_min_key: int
    expected_max_key: int
    scale_factor: str = "0.01"

    @property
    def activate_query(self):
        return f"ri_{self.code}_activate_gsql"

    @property
    def update_query(self):
        return f"ri_{self.code}_update"

    @property
    def deactivate_query(self):
        return f"ri_{self.code}_deactivate_gsql"

    @property
    def result_dir(self):
        scale_tag = self.scale_factor.replace(".", "")
        return SCRIPT_DIR.parent / "results" / f"{self.code}_sf{scale_tag}"


def run_query_sync(query_name, params=None):
    response = requests.get(
        f"{BASE_URL}/restpp/query/{GRAPH}/{query_name}",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"Query '{query_name}' failed:\n{data}")
    return data


def extract_single_value(data, field):
    if isinstance(data, dict):
        if field in data:
            return data[field]
        for value in data.values():
            found = extract_single_value(value, field)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = extract_single_value(value, field)
            if found is not None:
                return found
    return None


def submit_timed_update(config):
    response = requests.get(
        f"{BASE_URL}/restpp/query/{GRAPH}/{config.update_query}",
        headers={"GSQL-ASYNC": "true"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error") or not data.get("requestid"):
        raise RuntimeError(f"Detached update submission failed:\n{data}")
    return data["requestid"]


def wait_for_elapsed_time(request_id):
    while True:
        response = requests.get(
            f"{BASE_URL}/restpp/query_status",
            params={"graph_name": GRAPH, "requestid": request_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(f"query_status failed for {request_id}:\n{data}")
        results = data.get("results", [])
        if not results:
            time.sleep(POLL_INTERVAL)
            continue
        info = results[0]
        status = info.get("status")
        if status == "success":
            if info.get("elapsedTime") is None:
                raise RuntimeError(f"No elapsedTime for {request_id}:\n{info}")
            return info["elapsedTime"]
        if status in {"failed", "aborted", "timeout", "expired"}:
            raise RuntimeError(f"Query {request_id} ended as {status}:\n{info}")
        time.sleep(POLL_INTERVAL)


def checked_count(data, field, expected, operation):
    value = extract_single_value(data, field)
    if value is None or int(value) != expected:
        raise RuntimeError(
            f"{operation} count mismatch: expected {expected}, got {value}; response={data}"
        )
    return int(value)


def activate(config, offset, n):
    data = run_query_sync(
        config.activate_query,
        {"offset_value": offset, "limit_value": n},
    )
    return checked_count(data, "activated_count", n, "Activation")


def restore(config, expected_n):
    data = run_query_sync(config.update_query)
    return checked_count(data, "updated_count", expected_n, "Restore")


def deactivate(config, expected_n):
    data = run_query_sync(config.deactivate_query)
    return checked_count(data, "deactivated_count", expected_n, "Deactivation")


def emergency_cleanup(config, expected_n=None):
    print("\nAttempting emergency cleanup...")
    if expected_n is not None:
        try:
            restore(config, expected_n)
            print("  Restore attempt completed.")
        except Exception as exc:
            print(f"  Restore cleanup warning: {exc}")
    try:
        run_query_sync(config.deactivate_query)
        print("  Deactivation attempt completed.")
    except Exception as exc:
        print(f"  Deactivation cleanup warning: {exc}")


def validate_settings(config):
    if RUNS <= 0 or OUTLIERS < 0 or 2 * OUTLIERS >= RUNS:
        raise ValueError("Require RUNS > 2 * OUTLIERS >= 0.")
    if config.entity_count <= 0:
        raise ValueError("entity_count must be positive.")
    if any(not 0 < percentage <= 1 for percentage in PERCENTAGES):
        raise ValueError("Every percentage must be in (0, 1].")


def trim_times(values):
    ordered = sorted(values)
    return ordered if OUTLIERS == 0 else ordered[OUTLIERS:-OUTLIERS]


def percentage_text(fraction):
    """Return a stable human/CSV percentage without losing 0.1%."""
    value = fraction * 100
    return str(int(value)) if value.is_integer() else f"{value:g}"


def update_count(entity_count, fraction):
    """Map a requested fraction to a runnable integer vertex count.

    A non-zero experiment must update at least one vertex. The effective
    percentage is recorded separately because small sf=0.01 entity sets
    cannot represent every requested percentage exactly (notably Sc 0.1%).
    """
    return max(1, round(entity_count * fraction))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_benchmark(config):
    validate_settings(config)
    rng = random.Random(RANDOM_SEED)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_rows = []
    summary_rows = []

    print("=" * 68)
    print(f"Experiment: {config.code.upper()} ({config.description})")
    print(f"Semantics: Graph | Scale factor: sf={config.scale_factor}")
    print(f"{config.entity_name}_COUNT={config.entity_count}, RUNS={RUNS}, OUTLIERS={OUTLIERS}")
    print("=" * 68)

    for percentage in PERCENTAGES:
        n = update_count(config.entity_count, percentage)
        requested_percentage = percentage_text(percentage)
        effective_percentage = n * 100 / config.entity_count
        max_offset = config.entity_count - n
        raw_times = []
        print(
            f"\n{requested_percentage}% requested | n={n} | "
            f"effective={effective_percentage:g}%"
        )

        for run_number in range(1, RUNS + 1):
            offset = 0 if max_offset == 0 else rng.randint(0, max_offset)
            request_id = None
            print(f"  run {run_number:02d}/{RUNS} offset={offset} n={n}", end="", flush=True)
            try:
                activate(config, offset, n)
                request_id = submit_timed_update(config)
                elapsed_ms = wait_for_elapsed_time(request_id)
                restore(config, n)
                deactivate(config, n)
            except Exception:
                print(" -> FAILED")
                emergency_cleanup(config, n)
                raise

            raw_times.append(elapsed_ms)
            raw_rows.append({
                "percentage": requested_percentage,
                "effective_percentage": f"{effective_percentage:g}",
                "n": n,
                "run": run_number,
                "offset": offset,
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            })
            print(f" -> {elapsed_ms} ms")

        retained = trim_times(raw_times)
        mean_ms = sum(retained) / len(retained)
        summary_rows.append({
            "percentage": requested_percentage,
            "effective_percentage": f"{effective_percentage:g}",
            "n": n,
            "runs": RUNS,
            "outliers_each_side": OUTLIERS,
            "retained_runs": len(retained),
            "mean_ms": round(mean_ms, 3),
            "retained_times_ms": " ".join(str(value) for value in retained),
        })
        print(f"  retained={retained}\n  trimmed mean={mean_ms:.3f} ms")

    scale_tag = config.scale_factor.replace(".", "")
    raw_path = config.result_dir / f"{config.code}_sf{scale_tag}_raw_{timestamp}.csv"
    summary_path = config.result_dir / f"{config.code}_sf{scale_tag}_summary_{timestamp}.csv"
    write_csv(
        raw_path,
        ["percentage", "effective_percentage", "n", "run", "offset", "request_id", "elapsed_ms"],
        raw_rows,
    )
    write_csv(
        summary_path,
        ["percentage", "effective_percentage", "n", "runs", "outliers_each_side", "retained_runs", "mean_ms", "retained_times_ms"],
        summary_rows,
    )

    print("\nFINAL SUMMARY")
    for row in summary_rows:
        print(
            f"{row['percentage']:>4}% requested | "
            f"effective={row['effective_percentage']:>7}% | "
            f"n={row['n']:5d} | mean={row['mean_ms']:.3f} ms"
        )
    print(f"Raw results: {raw_path}\nSummary: {summary_path}")
    print(
        f"Final check required: active_count=0, negative_count=0, "
        f"min_{config.key_name}={config.expected_min_key}, "
        f"max_{config.key_name}={config.expected_max_key}"
    )
    return raw_path, summary_path


SCALE_CONFIGS = {
    "0.01": {
        "cc": (1500, 1500), "oc": (15000, 60000),
        "pc": (2000, 2000), "sc": (100, 100),
    },
    "0.1": {
        "cc": (15000, 15000), "oc": (150000, 600000),
        "pc": (20000, 20000), "sc": (1000, 1000),
    },
    "1": {
        "cc": (150000, 150000), "oc": (1500000, 6000000),
        "pc": (200000, 200000), "sc": (10000, 10000),
    },
}

CHAIN_METADATA = {
    "cc": ("CUSTOMER -> ORDERS", "CUSTOMER", "custkey"),
    "oc": ("ORDERS -> LINEITEM", "ORDERS", "orderkey"),
    "pc": ("PART -> PARTSUPP -> LINEITEM", "PART", "partkey"),
    "sc": ("SUPPLIER -> PARTSUPP -> LINEITEM", "SUPPLIER", "suppkey"),
}


def main():
    global BASE_URL, GRAPH
    parser = argparse.ArgumentParser(description="Run graph referential-integrity benchmarks.")
    parser.add_argument("--chain", required=True, choices=tuple(CHAIN_METADATA))
    parser.add_argument("--scale", required=True, choices=tuple(SCALE_CONFIGS))
    parser.add_argument("--host", default=BASE_URL)
    parser.add_argument("--graph", default=GRAPH)
    args = parser.parse_args()
    BASE_URL, GRAPH = args.host, args.graph
    count, maximum = SCALE_CONFIGS[args.scale][args.chain]
    description, entity, key = CHAIN_METADATA[args.chain]
    run_benchmark(ChainConfig(
        code=args.chain, description=description, entity_name=entity,
        entity_count=count, key_name=key, expected_min_key=1,
        expected_max_key=maximum, scale_factor=args.scale,
    ))


if __name__ == "__main__":
    main()

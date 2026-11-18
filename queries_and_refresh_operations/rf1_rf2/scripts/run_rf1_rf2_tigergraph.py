"""Run isolated RF1/RF2 Graph experiments with installed openCypher queries."""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

HOST = "http://localhost:14241"
GRAPH = "TPCH_RF_G"
CUSTOMER_COUNT = 1_500
PARTSUPP_COUNT = 8_000
OUTPUT_LABEL = "sf001_graph"
SEED = 20260923
FORMAL_RUNS = 20
FORMAL_ORDERS_BY_SCALE = {"0.01": 15, "0.1": 150, "1": 1_500}
TRIM = 5
STATUS_READ_RETRIES = 5
QUERY_DEADLINE_SECONDS = 900
SUBMISSION_TIMEOUT_SECONDS = 300
RECOVERY_DELAYS_SECONDS = (10, 20, 40)
# Recovery delays are outside the formal database elapsed-time metric.
OPERATION_RETRY_DELAYS_SECONDS: tuple[int, ...] = (15, 30, 60)
OPERATION_RETRY_EVENTS: list[dict[str, object]] = []
SESSION = requests.Session()
SESSION.mount("http://", HTTPAdapter(pool_connections=4, pool_maxsize=4))
RAW_FIELDS = [
    "run",
    "orders",
    "lineitems",
    "rf1_query_count",
    "rf2_query_count",
    "rf1_elapsed_ms",
    "rf2_elapsed_ms",
    "operation_retry_count",
    "operation_retry_wait_seconds",
    "rf1_correctness_passed",
    "rf2_correctness_passed",
]

PROFILES = {
    "0.01": {"host": "http://localhost:14241", "customers": 1_500, "partsupp": 8_000, "output": "sf001_graph"},
    "0.1": {"host": "http://localhost:14242", "customers": 15_000, "partsupp": 80_000, "output": "sf01_graph"},
    "1": {"host": "http://localhost:14245", "customers": 150_000, "partsupp": 800_000, "output": "sf1_graph"},
}


def run_query_once(name: str, params: dict[str, object]) -> float:
    """Submit one timed database operation and return only a successful elapsed time."""
    response = SESSION.get(
        f"{HOST}/restpp/query/{GRAPH}/{name}",
        params=params,
        headers={"GSQL-ASYNC": "true"},
        timeout=SUBMISSION_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error") or not data.get("requestid"):
        raise RuntimeError(data)
    request_id = data["requestid"]
    deadline = time.monotonic() + QUERY_DEADLINE_SECONDS
    read_failures = 0
    poll_count = 0
    while time.monotonic() < deadline:
        try:
            status_response = SESSION.get(
                f"{HOST}/restpp/query_status",
                params={"graph_name": GRAPH, "requestid": request_id},
                timeout=60,
            )
            status_response.raise_for_status()
            status = status_response.json()
            read_failures = 0
        except (requests.ReadTimeout, requests.ConnectionError):
            read_failures += 1
            if read_failures > STATUS_READ_RETRIES:
                raise
            time.sleep(min(2 ** (read_failures - 1), 30))
            continue
        if status.get("error"):
            raise RuntimeError(status)
        if status.get("results"):
            item = status["results"][0]
            if item.get("status") == "success":
                return float(item["elapsedTime"])
            if item.get("status") in {"failed", "aborted", "timeout", "expired"}:
                raise RuntimeError(item)
        poll_count += 1
        time.sleep(min(0.1 * (2 ** min(poll_count // 5, 3)), 1.0))
    raise TimeoutError(f"{name}: request {request_id} exceeded the query deadline")


def run_query(name: str, params: dict[str, object]) -> float:
    """Retry one idempotent RF operation without restarting the whole round.

    The RF queries create fixed vertex/edge identifiers or delete a fixed order-key
    range, so repeating an operation after an uncertain REST response is safe. Failed
    attempts and recovery delays are not included in the reported database time.
    """
    last_error: Exception | None = None
    attempts = len(OPERATION_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            return run_query_once(name, params)
        except (requests.Timeout, requests.ConnectionError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            delay = OPERATION_RETRY_DELAYS_SECONDS[attempt]
            OPERATION_RETRY_EVENTS.append(
                {
                    "query": name,
                    "attempt": attempt + 1,
                    "wait_seconds": delay,
                    "error": str(exc),
                    "recorded_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            print(
                f"{name} transient operation failure on attempt {attempt + 1}: {exc}; "
                f"retrying after {delay}s",
                flush=True,
            )
            time.sleep(delay)
    raise TimeoutError(
        f"{name} failed after {attempts} operation attempts: {last_error}"
    ) from last_error


def run_support_query(name: str, params: dict[str, object]) -> dict[str, object]:
    """Run an untimed GSQL support query used only for correctness or recovery."""
    response = SESSION.get(
        f"{HOST}/restpp/query/{GRAPH}/{name}",
        params=params,
        timeout=600,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error") or not data.get("results"):
        raise RuntimeError(data)
    return data["results"][0]


def get_vertex(vertex_type: str, vertex_id: str) -> dict[str, object] | None:
    response = SESSION.get(
        f"{HOST}/restpp/graph/{GRAPH}/vertices/{vertex_type}/{vertex_id}",
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        return None
    results = data.get("results", [])
    return results[0] if results else None


def delete_vertex(vertex_type: str, vertex_id: str) -> None:
    """Delete a test vertex by Technical ID; used only for recovery."""
    response = SESSION.delete(
        f"{HOST}/restpp/graph/{GRAPH}/vertices/{vertex_type}/{vertex_id}",
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error") and data.get("code") != "601":
        raise RuntimeError(data)


def edge_targets(vertex_type: str, vertex_id: str) -> set[tuple[str, str]]:
    response = SESSION.get(
        f"{HOST}/restpp/graph/{GRAPH}/edges/{vertex_type}/{vertex_id}",
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        return set()
    return {(item["e_type"], str(item["to_id"])) for item in data.get("results", [])}


def verify_created(batch: list[dict[str, object]]) -> dict[str, object]:
    order_vertices = order_edges = line_vertices = order_line_edges = partsupp_edges = 0
    failures: list[str] = []
    invalid_vertices: set[tuple[str, str]] = set()
    for order in batch:
        order_id = str(order["order_id"])
        customer_id = str(order["customer_id"])
        order_vertex = get_vertex("RF_ORDERS", order_id)
        if order_vertex:
            order_vertices += 1
            actual_key = int(order_vertex.get("attributes", {}).get("o_orderkey", 0))
            if actual_key != int(order["order_key"]):
                failures.append(
                    f"wrong order key {order_id}: expected {order['order_key']}, got {actual_key}"
                )
                invalid_vertices.add(("RF_ORDERS", order_id))
        else:
            failures.append(f"missing order {order_id}")
            invalid_vertices.add(("RF_ORDERS", order_id))
        if ("RF_ORDERS_CUSTOMER", customer_id) in edge_targets("RF_ORDERS", order_id):
            order_edges += 1
        else:
            failures.append(f"missing {order_id}->customer {customer_id}")
            invalid_vertices.add(("RF_ORDERS", order_id))
        for line in order["lines"]:
            line_id = str(line["line_id"])
            partsupp_id = str(line["partsupp_id"])
            line_vertex = get_vertex("RF_LINEITEM", line_id)
            if line_vertex:
                line_vertices += 1
                actual_number = int(line_vertex.get("attributes", {}).get("l_linenumber", 0))
                if actual_number != int(line["line_number"]):
                    failures.append(
                        f"wrong line number {line_id}: expected {line['line_number']}, got {actual_number}"
                    )
                    invalid_vertices.add(("RF_LINEITEM", line_id))
            else:
                failures.append(f"missing lineitem {line_id}")
                invalid_vertices.add(("RF_LINEITEM", line_id))
            targets = edge_targets("RF_LINEITEM", line_id)
            if ("RF_LINEITEM_ORDERS", order_id) in targets:
                order_line_edges += 1
            else:
                failures.append(f"missing {line_id}->order {order_id}")
                invalid_vertices.add(("RF_LINEITEM", line_id))
            if ("RF_LINEITEM_PARTSUPP", partsupp_id) in targets:
                partsupp_edges += 1
            else:
                failures.append(f"missing {line_id}->partsupp {partsupp_id}")
                invalid_vertices.add(("RF_LINEITEM", line_id))
    expected_lines = sum(len(order["lines"]) for order in batch)
    return {
        "passed": not failures,
        "expected_orders": len(batch),
        "actual_order_vertices": order_vertices,
        "actual_order_customer_edges": order_edges,
        "expected_lineitems": expected_lines,
        "actual_lineitem_vertices": line_vertices,
        "actual_lineitem_order_edges": order_line_edges,
        "actual_lineitem_partsupp_edges": partsupp_edges,
        "invalid_vertices": [
            {"vertex_type": vertex_type, "vertex_id": vertex_id}
            for vertex_type, vertex_id in sorted(invalid_vertices)
        ],
        "failures": failures,
    }


def verify_deleted(batch: list[dict[str, object]]) -> dict[str, object]:
    remaining_orders = [str(o["order_id"]) for o in batch if get_vertex("RF_ORDERS", str(o["order_id"]))]
    remaining_lines = [
        str(line["line_id"])
        for order in batch
        for line in order["lines"]
        if get_vertex("RF_LINEITEM", str(line["line_id"]))
    ]
    return {
        "passed": not remaining_orders and not remaining_lines,
        "remaining_order_count": len(remaining_orders),
        "remaining_lineitem_count": len(remaining_lines),
        "remaining_orders": remaining_orders,
        "remaining_lineitems": remaining_lines,
    }


def verify_created_batch(batch: list[dict[str, object]]) -> dict[str, object]:
    """Verify a large RF1 round with aggregate counts and a small exact sample."""
    expected_lines = sum(len(order["lines"]) for order in batch)
    min_key = min(int(order["order_key"]) for order in batch)
    max_key = max(int(order["order_key"]) for order in batch)
    counts = run_support_query(
        "rf_verify_batch",
        {"min_order_key": min_key, "max_order_key": max_key},
    )
    failures: list[str] = []
    expected = {
        "order_count": len(batch),
        "order_customer_edges": len(batch),
        "lineitem_count": expected_lines,
        "lineitem_order_edges": expected_lines,
        "lineitem_partsupp_edges": expected_lines,
    }
    for name, value in expected.items():
        actual = int(counts.get(name, -1))
        if actual != value:
            failures.append(f"{name}: expected {value}, got {actual}")

    sample_indexes = sorted(
        {0, len(batch) // 4, len(batch) // 2, (3 * len(batch)) // 4, len(batch) - 1}
    )
    sample = verify_created([batch[index] for index in sample_indexes])
    failures.extend(f"sample: {message}" for message in sample["failures"])
    return {
        "passed": not failures,
        "verification_mode": "aggregate counts plus five exact sampled orders",
        "expected_orders": len(batch),
        "actual_order_vertices": int(counts.get("order_count", -1)),
        "actual_order_customer_edges": int(counts.get("order_customer_edges", -1)),
        "expected_lineitems": expected_lines,
        "actual_lineitem_vertices": int(counts.get("lineitem_count", -1)),
        "actual_lineitem_order_edges": int(counts.get("lineitem_order_edges", -1)),
        "actual_lineitem_partsupp_edges": int(counts.get("lineitem_partsupp_edges", -1)),
        "sampled_order_count": len(sample_indexes),
        "invalid_vertices": sample["invalid_vertices"],
        "failures": failures,
    }


def verify_deleted_batch(batch: list[dict[str, object]]) -> dict[str, object]:
    """Verify that no objects connected to the round's order-key range remain."""
    min_key = min(int(order["order_key"]) for order in batch)
    max_key = max(int(order["order_key"]) for order in batch)
    counts = run_support_query(
        "rf_verify_batch",
        {"min_order_key": min_key, "max_order_key": max_key},
    )
    remaining_orders = int(counts.get("order_count", -1))
    remaining_lines = int(counts.get("lineitem_count", -1))
    return {
        "passed": remaining_orders == 0 and remaining_lines == 0,
        "verification_mode": "aggregate order-key-range check",
        "remaining_order_count": remaining_orders,
        "remaining_lineitem_count": remaining_lines,
        "remaining_orders": [],
        "remaining_lineitems": [],
    }


def batch_key_range(run_no: int, orders_per_run: int) -> tuple[int, int]:
    """Return the business-key range reserved for one formal round."""
    start = 1_800_000_000 + run_no * 10_000
    return start, start + orders_per_run - 1


def range_counts(run_no: int, orders_per_run: int) -> dict[str, object]:
    min_key, max_key = batch_key_range(run_no, orders_per_run)
    return run_support_query(
        "rf_verify_batch",
        {"min_order_key": min_key, "max_order_key": max_key},
    )


def range_is_clean(counts: dict[str, object]) -> bool:
    return int(counts.get("order_count", -1)) == 0 and int(
        counts.get("lineitem_count", -1)
    ) == 0


def cleanup_range(run_no: int, orders_per_run: int) -> dict[str, object]:
    min_key, max_key = batch_key_range(run_no, orders_per_run)
    return run_support_query(
        "rf_cleanup_batch",
        {"min_order_key": min_key, "max_order_key": max_key},
    )


def ensure_clean_start(run_no: int, orders_per_run: int) -> None:
    """Prevent a resumed round from inheriting objects from an interrupted attempt."""
    counts = range_counts(run_no, orders_per_run)
    if range_is_clean(counts):
        return
    cleanup_range(run_no, orders_per_run)
    time.sleep(10)
    counts = range_counts(run_no, orders_per_run)
    if not range_is_clean(counts):
        raise RuntimeError(
            f"run {run_no} key range is not clean before RF1: {counts}"
        )


def recover_interrupted_cycle(run_no: int, orders_per_run: int) -> None:
    """Repeat delayed cleanup because a timed-out request may finish after the client exits."""
    last_error: Exception | None = None
    for delay in RECOVERY_DELAYS_SECONDS:
        time.sleep(delay)
        try:
            cleanup_range(run_no, orders_per_run)
            last_error = None
        except Exception as exc:  # recovery must not hide the original workload error
            last_error = exc
    try:
        counts = range_counts(run_no, orders_per_run)
        if not range_is_clean(counts):
            print(f"WARNING: recovery left objects for run {run_no}: {counts}")
    except Exception as exc:
        last_error = exc
    if last_error is not None:
        print(f"WARNING: recovery verification failed for run {run_no}: {last_error}")


def one_cycle(run_no: int, orders_per_run: int, rng: random.Random) -> tuple[dict[str, object], dict[str, object]]:
    retry_event_start = len(OPERATION_RETRY_EVENTS)
    batch: list[dict[str, object]] = []
    rf1_ms = 0.0
    rf2_ms = 0.0
    fallback_vertices: list[dict[str, str]] = []
    cycle_completed = False
    prefix = f"RF_{datetime.now():%Y%m%d%H%M%S%f}_{run_no:02d}"
    try:
        ensure_clean_start(run_no, orders_per_run)
        for order_no in range(orders_per_run):
            order_id = f"{prefix}_O_{order_no:03d}"
            order_key = 1_800_000_000 + run_no * 10_000 + order_no
            customer_id = f"C{rng.randint(1, CUSTOMER_COUNT):06d}"
            lines: list[dict[str, str]] = []
            rf1_ms += run_query("rf1_create_order", {"order_id": order_id, "order_key": order_key})
            rf1_ms += run_query("rf1_create_order_customer_edge", {"o": order_id, "c": customer_id})
            order_record = {
                "order_id": order_id,
                "order_key": order_key,
                "customer_id": customer_id,
                "lines": lines,
            }
            batch.append(order_record)
            line_count = rng.randint(1, 6)
            for line_no in range(1, line_count + 1):
                line_id = f"{prefix}_L_{order_no:03d}_{line_no}"
                partsupp_id = f"PS{rng.randint(1, PARTSUPP_COUNT):06d}"
                lines.append(
                    {
                        "line_id": line_id,
                        "partsupp_id": partsupp_id,
                        "line_number": line_no,
                    }
                )
                rf1_ms += run_query("rf1_create_lineitem", {"lineitem_id": line_id, "line_number": line_no})
                rf1_ms += run_query("rf1_create_lineitem_order_edge", {"l": line_id, "o": order_id})
                rf1_ms += run_query("rf1_create_lineitem_partsupp_edge", {"l": line_id, "ps": partsupp_id})

        after_rf1 = (
            verify_created_batch(batch)
            if orders_per_run >= 100
            else verify_created(batch)
        )
        if not after_rf1["passed"]:
            fallback_vertices = list(after_rf1["invalid_vertices"])
            raise RuntimeError(f"RF1 correctness failed: {after_rf1}")

        for order in batch:
            order_key = int(order["order_key"])
            rf2_ms += run_query("rf2_delete_lineitems", {"order_key": order_key})
            rf2_ms += run_query("rf2_delete_order", {"order_key": order_key})
        after_rf2 = (
            verify_deleted_batch(batch)
            if orders_per_run >= 100
            else verify_deleted(batch)
        )
        if not after_rf2["passed"]:
            raise RuntimeError(f"RF2 correctness failed: {after_rf2}")
        cycle_completed = True
    finally:
        # Recovery is outside timing and runs only after an interrupted cycle.
        if not cycle_completed:
            recover_interrupted_cycle(run_no, orders_per_run)
        for vertex in fallback_vertices:
            try:
                delete_vertex(str(vertex["vertex_type"]), str(vertex["vertex_id"]))
            except Exception:
                pass
    line_count = sum(len(order["lines"]) for order in batch)
    recovery_events = OPERATION_RETRY_EVENTS[retry_event_start:]
    row = {
        "run": run_no,
        "orders": orders_per_run,
        "lineitems": line_count,
        "rf1_query_count": 2 * orders_per_run + 3 * line_count,
        "rf2_query_count": 2 * orders_per_run,
        "rf1_elapsed_ms": rf1_ms,
        "rf2_elapsed_ms": rf2_ms,
        "operation_retry_count": len(recovery_events),
        "operation_retry_wait_seconds": sum(
            int(event["wait_seconds"]) for event in recovery_events
        ),
        "rf1_correctness_passed": after_rf1["passed"],
        "rf2_correctness_passed": after_rf2["passed"],
    }
    return row, {
        "run": run_no,
        "after_rf1": after_rf1,
        "after_rf2": after_rf2,
        "operation_recovery": {
            "retry_count": len(recovery_events),
            "wait_seconds": sum(int(event["wait_seconds"]) for event in recovery_events),
            "events": recovery_events,
        },
    }


def advance_rng(rng: random.Random, orders_per_run: int, run_count: int) -> None:
    """Advance the seeded workload plan without submitting database queries."""
    for _ in range(run_count):
        for _ in range(orders_per_run):
            rng.randint(1, CUSTOMER_COUNT)
            line_count = rng.randint(1, 6)
            for _ in range(line_count):
                rng.randint(1, PARTSUPP_COUNT)


def write_checkpoint(
    out: Path,
    rows: list[dict[str, object]],
    correctness: list[dict[str, object]],
    metadata: dict[str, object],
    status: str,
    error: str | None = None,
) -> None:
    """Persist completed rounds so an interrupted batch can be resumed."""
    with (out / "raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (out / "correctness.json").write_text(
        json.dumps(correctness, indent=2) + "\n", encoding="utf-8"
    )
    progress = dict(metadata)
    progress.update(
        {
            "status": status,
            "completed_runs": [int(row["run"]) for row in rows],
            "next_run": (max(int(row["run"]) for row in rows) + 1) if rows else metadata["start_run"],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    if error:
        progress["error"] = error
    (out / "progress.json").write_text(
        json.dumps(progress, indent=2) + "\n", encoding="utf-8"
    )


def load_checkpoint(out: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw_path = out / "raw.csv"
    correctness_path = out / "correctness.json"
    if not raw_path.exists() or not correctness_path.exists():
        raise FileNotFoundError(f"Resume directory is missing checkpoint files: {out}")
    with raw_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.setdefault("operation_retry_count", "0")
        row.setdefault("operation_retry_wait_seconds", "0")
    correctness = json.loads(correctness_path.read_text(encoding="utf-8"))
    return rows, correctness


def build_summary(
    args: argparse.Namespace,
    rows: list[dict[str, object]],
    orders: int,
    planned_total_runs: int,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "scale_factor": args.scale,
        "host": HOST,
        "graph": GRAPH,
        "seed": args.seed,
        "completed_runs": len(rows),
        "planned_total_runs": planned_total_runs,
        "orders_per_run": orders,
        "customer_id_range": CUSTOMER_COUNT,
        "partsupp_id_range": PARTSUPP_COUNT,
        "workload_plan": (
            "scale-dependent orders; seeded 1--6 lineitems per order"
            if args.formal
            else "one-order smoke test"
        ),
    }
    if not rows:
        return summary
    summary["all_rf1_correctness_passed"] = all(
        str(row["rf1_correctness_passed"]).lower() == "true" for row in rows
    )
    summary["all_rf2_correctness_passed"] = all(
        str(row["rf2_correctness_passed"]).lower() == "true" for row in rows
    )
    rf1_counts = [int(row["rf1_query_count"]) for row in rows]
    rf2_counts = [int(row["rf2_query_count"]) for row in rows]
    summary["rf1_query_count"] = {
        "total": sum(rf1_counts),
        "mean_per_run": statistics.mean(rf1_counts),
        "min_per_run": min(rf1_counts),
        "max_per_run": max(rf1_counts),
    }
    summary["rf2_query_count"] = {
        "total": sum(rf2_counts),
        "mean_per_run": statistics.mean(rf2_counts),
    }
    run_numbers = sorted(int(row["run"]) for row in rows)
    complete_formal_series = (
        args.formal
        and len(rows) == FORMAL_RUNS
        and run_numbers == list(range(1, FORMAL_RUNS + 1))
    )
    summary["formal_series_complete"] = complete_formal_series
    if complete_formal_series:
        for field in ("rf1_elapsed_ms", "rf2_elapsed_ms"):
            values = sorted(float(row[field]) for row in rows)
            summary[field.replace("_elapsed_ms", "_trimmed_mean_ms")] = statistics.mean(
                values[TRIM:-TRIM]
            )
    return summary


def main() -> None:
    global HOST, CUSTOMER_COUNT, PARTSUPP_COUNT, OUTPUT_LABEL
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--formal",
        action="store_true",
        help="20 runs; orders per run scale as 15/150/1500 for SF 0.01/0.1/1",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--scale", choices=tuple(PROFILES), default="0.01")
    parser.add_argument(
        "--runs",
        type=int,
        help="Runs in this invocation; defaults to 20 with --formal and 1 otherwise",
    )
    parser.add_argument("--start-run", type=int, default=1)
    parser.add_argument(
        "--resume-dir",
        type=Path,
        help="Existing checkpoint directory to append to",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=0.0,
        help="Stop before the next round if the output drive has less free space",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=0,
        help="Wait before the workload so recently started TigerGraph services can stabilise",
    )
    parser.add_argument(
        "--warmup-orders",
        type=int,
        default=0,
        help="Run and verify an untimed disposable warm-up cycle before the requested runs",
    )
    parser.add_argument(
        "--between-runs-seconds",
        type=int,
        default=0,
        help="Untimed cooldown after each completed round except the final requested round",
    )
    parser.add_argument(
        "--round-retries",
        type=int,
        default=0,
        help="Retry an interrupted round after cleanup; failed attempts are not recorded",
    )
    args = parser.parse_args()
    if args.runs is not None and args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.start_run < 1:
        parser.error("--start-run must be at least 1")
    if args.settle_seconds < 0:
        parser.error("--settle-seconds cannot be negative")
    if args.warmup_orders < 0:
        parser.error("--warmup-orders cannot be negative")
    if args.between_runs_seconds < 0:
        parser.error("--between-runs-seconds cannot be negative")
    if args.round_retries < 0:
        parser.error("--round-retries cannot be negative")
    profile = PROFILES[args.scale]
    HOST = str(profile["host"])
    CUSTOMER_COUNT = int(profile["customers"])
    PARTSUPP_COUNT = int(profile["partsupp"])
    OUTPUT_LABEL = str(profile["output"])
    runs = args.runs if args.runs is not None else (FORMAL_RUNS if args.formal else 1)
    orders = FORMAL_ORDERS_BY_SCALE[args.scale] if args.formal else 1
    end_run = args.start_run + runs - 1
    if args.formal and end_run > FORMAL_RUNS:
        parser.error(f"Formal run numbers must stay within 1--{FORMAL_RUNS}")

    if args.resume_dir:
        out = args.resume_dir.resolve()
        rows, correctness = load_checkpoint(out)
        existing_runs = {int(row["run"]) for row in rows}
        overlap = existing_runs.intersection(range(args.start_run, end_run + 1))
        if overlap:
            parser.error(f"Requested runs already exist in checkpoint: {sorted(overlap)}")
        expected_previous = set(range(1, args.start_run))
        if args.formal and existing_runs != expected_previous:
            parser.error(
                "Resume checkpoint must contain every preceding formal run exactly once; "
                f"found {sorted(existing_runs)}, expected {sorted(expected_previous)}"
            )
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out = Path(__file__).resolve().parents[1] / "results" / OUTPUT_LABEL / stamp
        out.mkdir(parents=True)
        rows = []
        correctness = []

    rng = random.Random(args.seed)
    advance_rng(rng, orders, args.start_run - 1)
    metadata: dict[str, object] = {
        "scale_factor": args.scale,
        "seed": args.seed,
        "orders_per_run": orders,
        "start_run": args.start_run,
        "end_run": end_run,
        "min_free_gb": args.min_free_gb,
        "settle_seconds": args.settle_seconds,
        "warmup_orders": args.warmup_orders,
        "between_runs_seconds": args.between_runs_seconds,
        "round_retries": args.round_retries,
    }
    write_checkpoint(out, rows, correctness, metadata, "running")
    try:
        if args.settle_seconds:
            time.sleep(args.settle_seconds)
        if args.warmup_orders:
            warmup_rng = random.Random(args.seed ^ 0x5F3759DF)
            one_cycle(0, args.warmup_orders, warmup_rng)
        for run_no in range(args.start_run, end_run + 1):
            free_gb = shutil.disk_usage(out.anchor).free / (1024**3)
            if free_gb < args.min_free_gb:
                raise RuntimeError(
                    f"Free disk space {free_gb:.1f} GB is below the "
                    f"{args.min_free_gb:.1f} GB safety threshold before run {run_no}"
                )
            rng_state = rng.getstate()
            for attempt in range(args.round_retries + 1):
                try:
                    row, check = one_cycle(run_no, orders, rng)
                    break
                except (requests.Timeout, requests.ConnectionError, TimeoutError) as exc:
                    if attempt >= args.round_retries:
                        raise
                    print(
                        f"run {run_no} transient failure on attempt {attempt + 1}: {exc}; "
                        "retrying the same workload plan"
                    )
                    rng.setstate(rng_state)
                    time.sleep(max(args.between_runs_seconds, 60))
            rows.append(row)
            correctness.append(check)
            write_checkpoint(out, rows, correctness, metadata, "running")
            if args.between_runs_seconds and run_no < end_run:
                time.sleep(args.between_runs_seconds)
    except Exception as exc:
        write_checkpoint(out, rows, correctness, metadata, "interrupted", str(exc))
        print(out)
        raise

    summary = build_summary(args, rows, orders, FORMAL_RUNS if args.formal else runs)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    write_checkpoint(out, rows, correctness, metadata, "completed")
    print(out)


if __name__ == "__main__":
    main()

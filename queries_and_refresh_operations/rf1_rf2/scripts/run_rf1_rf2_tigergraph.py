"""Run isolated RF1/RF2 Graph experiments with installed openCypher queries."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests

HOST = "http://localhost:14241"
GRAPH = "TPCH_RF_G"
CUSTOMER_COUNT = 1_500
PARTSUPP_COUNT = 8_000
OUTPUT_LABEL = "sf001_graph"
SEED = 20260923
FORMAL_RUNS = 20
FORMAL_ORDERS = 15
TRIM = 5

PROFILES = {
    "0.01": {"host": "http://localhost:14241", "customers": 1_500, "partsupp": 8_000, "output": "sf001_graph"},
    "0.1": {"host": "http://localhost:14242", "customers": 15_000, "partsupp": 80_000, "output": "sf01_graph"},
    "1": {"host": "http://localhost:14245", "customers": 150_000, "partsupp": 800_000, "output": "sf1_graph"},
}


def run_query(name: str, params: dict[str, object]) -> float:
    response = requests.get(
        f"{HOST}/restpp/query/{GRAPH}/{name}",
        params=params,
        headers={"GSQL-ASYNC": "true"},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error") or not data.get("requestid"):
        raise RuntimeError(data)
    request_id = data["requestid"]
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        status = requests.get(
            f"{HOST}/restpp/query_status",
            params={"graph_name": GRAPH, "requestid": request_id},
            timeout=60,
        ).json()
        if status.get("error"):
            raise RuntimeError(status)
        if status.get("results"):
            item = status["results"][0]
            if item.get("status") == "success":
                return float(item["elapsedTime"])
            if item.get("status") in {"failed", "aborted", "timeout", "expired"}:
                raise RuntimeError(item)
        time.sleep(0.05)
    raise TimeoutError(name)


def get_vertex(vertex_type: str, vertex_id: str) -> dict[str, object] | None:
    response = requests.get(
        f"{HOST}/restpp/graph/{GRAPH}/vertices/{vertex_type}/{vertex_id}",
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        return None
    results = data.get("results", [])
    return results[0] if results else None


def edge_targets(vertex_type: str, vertex_id: str) -> set[tuple[str, str]]:
    response = requests.get(
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
    for order in batch:
        order_id = str(order["order_id"])
        customer_id = str(order["customer_id"])
        if get_vertex("RF_ORDERS", order_id):
            order_vertices += 1
        else:
            failures.append(f"missing order {order_id}")
        if ("RF_ORDERS_CUSTOMER", customer_id) in edge_targets("RF_ORDERS", order_id):
            order_edges += 1
        else:
            failures.append(f"missing {order_id}->customer {customer_id}")
        for line in order["lines"]:
            line_id = str(line["line_id"])
            partsupp_id = str(line["partsupp_id"])
            if get_vertex("RF_LINEITEM", line_id):
                line_vertices += 1
            else:
                failures.append(f"missing lineitem {line_id}")
            targets = edge_targets("RF_LINEITEM", line_id)
            if ("RF_LINEITEM_ORDERS", order_id) in targets:
                order_line_edges += 1
            else:
                failures.append(f"missing {line_id}->order {order_id}")
            if ("RF_LINEITEM_PARTSUPP", partsupp_id) in targets:
                partsupp_edges += 1
            else:
                failures.append(f"missing {line_id}->partsupp {partsupp_id}")
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


def line_counts_for_total(total: int, orders: int) -> list[int]:
    if not orders <= total <= 6 * orders:
        raise ValueError(f"Cannot distribute {total} lineitems over {orders} orders")
    counts = [1] * orders
    remaining = total - orders
    index = 0
    while remaining:
        if counts[index] < 6:
            counts[index] += 1
            remaining -= 1
        index = (index + 1) % orders
    return counts


def sf001_formal_lineitem_plan() -> list[int]:
    root = Path(__file__).resolve().parents[1] / "results" / "sf001_graph"
    for directory in sorted(root.iterdir(), reverse=True):
        raw = directory / "raw.csv"
        if raw.is_file():
            with raw.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            if len(rows) == FORMAL_RUNS:
                return [int(row["lineitems"]) for row in rows]
    raise FileNotFoundError("No 20-run sf=0.01 RF workload plan was found")


def one_cycle(run_no: int, orders_per_run: int, rng: random.Random, planned_lineitems: int | None = None) -> tuple[dict[str, object], dict[str, object]]:
    batch: list[dict[str, object]] = []
    rf1_ms = 0.0
    rf2_ms = 0.0
    prefix = f"RF_{datetime.now():%Y%m%d%H%M%S%f}_{run_no:02d}"
    planned_counts = line_counts_for_total(planned_lineitems, orders_per_run) if planned_lineitems is not None else None
    try:
        for order_no in range(orders_per_run):
            order_id = f"{prefix}_O_{order_no:03d}"
            order_key = 1_800_000_000 + run_no * 10_000 + order_no
            customer_id = f"C{rng.randint(1, CUSTOMER_COUNT):06d}"
            lines: list[dict[str, str]] = []
            rf1_ms += run_query("rf1_create_order", {"order_id": order_id, "order_key": order_key})
            rf1_ms += run_query("rf1_create_order_customer_edge", {"o": order_id, "c": customer_id})
            line_count = planned_counts[order_no] if planned_counts is not None else rng.randint(1, 6)
            for line_no in range(1, line_count + 1):
                line_id = f"{prefix}_L_{order_no:03d}_{line_no}"
                partsupp_id = f"PS{rng.randint(1, PARTSUPP_COUNT):06d}"
                lines.append({"line_id": line_id, "partsupp_id": partsupp_id})
                rf1_ms += run_query("rf1_create_lineitem", {"lineitem_id": line_id, "line_number": line_no})
                rf1_ms += run_query("rf1_create_lineitem_order_edge", {"l": line_id, "o": order_id})
                rf1_ms += run_query("rf1_create_lineitem_partsupp_edge", {"l": line_id, "ps": partsupp_id})
            batch.append({"order_id": order_id, "order_key": order_key, "customer_id": customer_id, "lines": lines})

        after_rf1 = verify_created(batch)
        if not after_rf1["passed"]:
            raise RuntimeError(f"RF1 correctness failed: {after_rf1}")

        for order in batch:
            order_key = int(order["order_key"])
            rf2_ms += run_query("rf2_delete_lineitems", {"order_key": order_key})
            rf2_ms += run_query("rf2_delete_order", {"order_key": order_key})
        after_rf2 = verify_deleted(batch)
        if not after_rf2["passed"]:
            raise RuntimeError(f"RF2 correctness failed: {after_rf2}")
    finally:
        # Recovery is outside timing and makes interrupted runs rerunnable.
        for order in batch:
            order_key = int(order["order_key"])
            try:
                run_query("rf2_delete_lineitems", {"order_key": order_key})
                run_query("rf2_delete_order", {"order_key": order_key})
            except Exception:
                pass
    line_count = sum(len(order["lines"]) for order in batch)
    row = {
        "run": run_no,
        "orders": orders_per_run,
        "lineitems": line_count,
        "rf1_query_count": 2 * orders_per_run + 3 * line_count,
        "rf2_query_count": 2 * orders_per_run,
        "rf1_elapsed_ms": rf1_ms,
        "rf2_elapsed_ms": rf2_ms,
        "rf1_correctness_passed": after_rf1["passed"],
        "rf2_correctness_passed": after_rf2["passed"],
    }
    return row, {"run": run_no, "after_rf1": after_rf1, "after_rf2": after_rf2}


def main() -> None:
    global HOST, CUSTOMER_COUNT, PARTSUPP_COUNT, OUTPUT_LABEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--formal", action="store_true", help="20 runs x 15 orders; default is a 1-order smoke run")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--scale", choices=tuple(PROFILES), default="0.01")
    args = parser.parse_args()
    profile = PROFILES[args.scale]
    HOST = str(profile["host"])
    CUSTOMER_COUNT = int(profile["customers"])
    PARTSUPP_COUNT = int(profile["partsupp"])
    OUTPUT_LABEL = str(profile["output"])
    runs, orders = (FORMAL_RUNS, FORMAL_ORDERS) if args.formal else (1, 1)
    rng = random.Random(args.seed)
    lineitem_plan = sf001_formal_lineitem_plan() if args.formal and args.scale != "0.01" else [None] * runs
    completed = [one_cycle(i, orders, rng, lineitem_plan[i - 1]) for i in range(1, runs + 1)]
    rows = [item[0] for item in completed]
    correctness = [item[1] for item in completed]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = Path(__file__).resolve().parents[1] / "results" / OUTPUT_LABEL / stamp
    out.mkdir(parents=True)
    with (out / "raw.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary: dict[str, object] = {"scale_factor": args.scale, "host": HOST, "graph": GRAPH, "seed": args.seed, "runs": runs, "orders_per_run": orders, "customer_id_range": CUSTOMER_COUNT, "partsupp_id_range": PARTSUPP_COUNT, "workload_plan": "sf=0.01 formal lineitem totals" if args.formal and args.scale != "0.01" else "generated from seed"}
    summary["all_rf1_correctness_passed"] = all(bool(row["rf1_correctness_passed"]) for row in rows)
    summary["all_rf2_correctness_passed"] = all(bool(row["rf2_correctness_passed"]) for row in rows)
    summary["rf1_query_count"] = {
        "total": sum(int(row["rf1_query_count"]) for row in rows),
        "mean_per_run": statistics.mean(int(row["rf1_query_count"]) for row in rows),
        "min_per_run": min(int(row["rf1_query_count"]) for row in rows),
        "max_per_run": max(int(row["rf1_query_count"]) for row in rows),
    }
    summary["rf2_query_count"] = {
        "total": sum(int(row["rf2_query_count"]) for row in rows),
        "mean_per_run": statistics.mean(int(row["rf2_query_count"]) for row in rows),
    }
    if args.formal:
        for field in ("rf1_elapsed_ms", "rf2_elapsed_ms"):
            values = sorted(float(row[field]) for row in rows)
            summary[field.replace("_elapsed_ms", "_trimmed_mean_ms")] = statistics.mean(values[TRIM:-TRIM])
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "correctness.json").write_text(json.dumps(correctness, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()

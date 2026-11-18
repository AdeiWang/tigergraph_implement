"""Run reversible positive controls for the two global E/R-key detectors."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = PROJECT_ROOT / "entity_integrity" / "results" / "positive_control"
PARTSUPP_ID = "__ei_positive_control_partsupp__"
LINEITEM_ID = "__ei_positive_control_lineitem__"


def call(host: str, graph: str, query: str, **parameters: object) -> dict[str, Any]:
    response = requests.get(
        f"{host}/restpp/query/{graph}/{query}",
        params={key: str(value) for key, value in parameters.items()},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"{query} failed: {payload}")
    return payload


def violation_count(host: str, graph: str, query: str) -> int:
    payload = call(host, graph, query)

    def find(value: object) -> object | None:
        if isinstance(value, dict):
            if "violation_count" in value:
                return value["violation_count"]
            for child in value.values():
                found = find(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = find(child)
                if found is not None:
                    return found
        return None

    result = find(payload.get("results", []))
    if result is None:
        raise RuntimeError(f"Unexpected {query} response: {payload}")
    return int(result)


def cleanup(host: str, graph: str) -> None:
    call(host, graph, "ei_pc_delete_lineitem_gsql", test_id=LINEITEM_ID)
    call(host, graph, "ei_pc_delete_partsupp_gsql", test_id=PARTSUPP_ID)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:14240")
    parser.add_argument("--graph", default="TPCH_G")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = RESULT_ROOT / timestamp
    output.mkdir(parents=True, exist_ok=False)
    observations: list[dict[str, object]] = []

    def record(entity: str, stage: str, count: int) -> None:
        observations.append(
            {"entity": entity, "stage": stage, "violation_count": count}
        )

    status = "failed"
    error = ""
    try:
        cleanup(args.host, args.graph)

        partsupp_base = violation_count(
            args.host, args.graph, "global_verify_partsupp"
        )
        record("PartSupp", "baseline", partsupp_base)
        call(
            args.host,
            args.graph,
            "ei_pc_create_partsupp_gsql",
            test_id=PARTSUPP_ID,
        )
        partsupp_injected = violation_count(
            args.host, args.graph, "global_verify_partsupp"
        )
        record("PartSupp", "duplicate_injected", partsupp_injected)
        if partsupp_injected <= partsupp_base:
            raise AssertionError("PartSupp detector did not report the injected duplicate")
        call(
            args.host,
            args.graph,
            "ei_pc_delete_partsupp_gsql",
            test_id=PARTSUPP_ID,
        )
        partsupp_restored = violation_count(
            args.host, args.graph, "global_verify_partsupp"
        )
        record("PartSupp", "cleanup", partsupp_restored)
        if partsupp_restored != partsupp_base:
            raise AssertionError("PartSupp count did not return to baseline")

        lineitem_base = violation_count(
            args.host, args.graph, "global_verify_lineitem"
        )
        record("Lineitem", "baseline", lineitem_base)
        call(
            args.host,
            args.graph,
            "ei_pc_create_lineitem_gsql",
            test_id=LINEITEM_ID,
        )
        lineitem_injected = violation_count(
            args.host, args.graph, "global_verify_lineitem"
        )
        record("Lineitem", "duplicate_injected", lineitem_injected)
        if lineitem_injected <= lineitem_base:
            raise AssertionError("Lineitem detector did not report the injected duplicate")
        call(
            args.host,
            args.graph,
            "ei_pc_delete_lineitem_gsql",
            test_id=LINEITEM_ID,
        )
        lineitem_restored = violation_count(
            args.host, args.graph, "global_verify_lineitem"
        )
        record("Lineitem", "cleanup", lineitem_restored)
        if lineitem_restored != lineitem_base:
            raise AssertionError("Lineitem count did not return to baseline")
        status = "pass"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        cleanup_error = ""
        try:
            cleanup(args.host, args.graph)
        except Exception as exc:
            cleanup_error = f"{type(exc).__name__}: {exc}"

        with (output / "observations.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["entity", "stage", "violation_count"]
            )
            writer.writeheader()
            writer.writerows(observations)

        manifest = {
            "status": status,
            "host": args.host,
            "graph": args.graph,
            "detectors": "installed openCypher global verification queries",
            "test_mutations": "GSQL correctness-only setup and cleanup queries",
            "test_ids": {"partsupp": PARTSUPP_ID, "lineitem": LINEITEM_ID},
            "duplicated_components": {
                "partsupp": ["P000001", "S000002"],
                "lineitem": ["O000001", "line_number=1", "PS006208"],
            },
            "error": error,
            "cleanup_error": cleanup_error,
            "observations": observations,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

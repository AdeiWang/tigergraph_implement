"""Unified command-line entry point for TigerGraph TPC-H Q1-Q22 benchmarks."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmark_core import DEFAULT_GRAPH, DEFAULT_HOST, OUTPUT_ROOT, run_benchmark
from query_specs import (
    RANDOM_SEED,
    RUNS,
    SPECS,
    SUPPORTED_SCALES,
    TRIM_EACH_SIDE,
    file_sha256,
    get_spec,
    load_parameter_schedule,
    validate_spec,
)


TWO_STAGE_Q11_QUERIES = (
    "q11_threshold_tigergraph",
    "q11_values_tigergraph",
)


def parse_query_list(value: str) -> list[int]:
    try:
        numbers = [int(part.strip().lower().removeprefix("q")) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Queries must be comma-separated numbers, for example 1,4,11"
        ) from exc
    invalid = [number for number in numbers if number not in SPECS]
    if invalid:
        raise argparse.ArgumentTypeError(f"Unknown query numbers: {invalid}")
    if len(numbers) != len(set(numbers)):
        raise argparse.ArgumentTypeError("Duplicate query numbers are not allowed")
    return numbers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run reproducible TigerGraph TPC-H query benchmarks."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--query", type=int, choices=range(1, 23))
    selection.add_argument("--queries", type=parse_query_list)
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--scale", required=True, choices=SUPPORTED_SCALES)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument(
        "--variant",
        choices=("current", "neo4j-compatible"),
        default="current",
        help="Use current project queries or the separate Neo4j-reference-compatible variants.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and parameters without contacting TigerGraph or writing results.",
    )
    return parser


def selected_queries(args: argparse.Namespace) -> list[int]:
    if args.all:
        return list(range(1, 23))
    if args.query is not None:
        return [args.query]
    return args.queries


def show_dry_run(number: int, scale: str, variant: str) -> None:
    if number == 11 and variant == "current":
        spec = get_spec(number, variant)
        schedule = load_parameter_schedule(spec, scale)
        print(
            "Q11: runner=two-stage, "
            f"queries={'+'.join(TWO_STAGE_Q11_QUERIES)}, "
            f"parameters={len(schedule)}, fields=selected_nation,fraction, "
            "semantic_status=formal"
        )
        print(
            "  timing=sum of two TigerGraph query_status.elapsedTime values"
        )
        print(
            "  note=Python passes the scalar threshold from stage 1 to stage 2; "
            "the historical q11_tigergraph query is not executed."
        )
        return
    spec = get_spec(number, variant)
    validate_spec(spec)
    schedule = load_parameter_schedule(spec, scale)
    print(
        f"{spec.code.upper()}: query={spec.installed_query}, "
        f"parameters={len(schedule)}, fields={','.join(spec.api_fields)}, "
        f"semantic_status={spec.semantic_status}, variant={spec.variant}"
    )
    print(f"  query_file={spec.query_file}")
    print(f"  query_sha256={file_sha256(spec.query_file)}")
    print(f"  canonical_parameters={spec.canonical_parameter_file}")
    print(f"  parameter_sha256={file_sha256(spec.canonical_parameter_file)}")
    print(
        f"  future_output={OUTPUT_ROOT / (spec.variant.replace('-', '_') if spec.variant != 'current' else '') / f'sf{scale}' / 'graph' / f'q{number:02d}' / '<timestamp>'}"
    )
    if spec.note:
        print(f"  note={spec.note}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    numbers = selected_queries(args)

    if any(number in {21, 22} for number in numbers):
        parser.error(
            "Q21 and Q22 require run_q21_q22_final.py so that their complete "
            "final CSV outputs are materialised. Exclude them from this runner."
        )

    print("TigerGraph unified query benchmark")
    print(f"scale={args.scale}, runs={RUNS}, trim_each_side={TRIM_EACH_SIDE}")
    print(f"canonical_parameter_seed={RANDOM_SEED}")

    if args.dry_run:
        for number in numbers:
            show_dry_run(number, args.scale, args.variant)
        print(f"Dry-run validation passed for {len(numbers)} queries; no files were written.")
        return 0

    for number in numbers:
        if number == 11 and args.variant == "current":
            from run_q11_two_stage import run as run_q11_two_stage

            output = run_q11_two_stage(
                scale=args.scale,
                host=args.host,
                graph=args.graph,
                runs=RUNS,
            )
            print(f"Q11 results: {output}")
            continue
        spec = get_spec(number, args.variant)
        validate_spec(spec)
        schedule = load_parameter_schedule(spec, args.scale)
        output = run_benchmark(
            spec=spec,
            scale=args.scale,
            schedule=schedule,
            host=args.host,
            graph=args.graph,
        )
        print(f"{spec.code.upper()} results: {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

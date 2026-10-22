"""Query-specific configuration for the unified Q1-Q22 benchmark runner.

The existing sf=0.01 parameter-order CSV files are treated as the canonical
workload schedule. Reusing that schedule keeps future scale-factor runs
comparable and avoids silently changing the random workload.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUERY_ROOT = PROJECT_ROOT / "queries_and_refresh_operations"
LEGACY_RESULTS_ROOT = PROJECT_ROOT / "results"
SUPPORTED_SCALES = ("0.01", "0.1", "1")
RUNS = 20
TRIM_EACH_SIDE = 5
RANDOM_SEED = 42


@dataclass(frozen=True)
class QuerySpec:
    number: int
    installed_query: str
    api_fields: tuple[str, ...]
    semantic_status: str = "formal"
    note: str = ""
    variant: str = "current"
    query_filename: str | None = None

    @property
    def code(self) -> str:
        return f"q{self.number}"

    @property
    def query_file(self) -> Path:
        filename = self.query_filename or f"{self.code}_tigergraph.txt"
        return QUERY_ROOT / self.code / filename

    @property
    def canonical_parameter_file(self) -> Path:
        return (
            LEGACY_RESULTS_ROOT
            / self.code
            / f"{self.code}_benchmark_parameter_order.csv"
        )


SPECS = {
    1: QuerySpec(1, "q1_tigergraph", ("cutoff_date",)),
    2: QuerySpec(
        2,
        "q2_tigergraph",
        ("selected_size", "selected_type", "selected_region"),
    ),
    3: QuerySpec(3, "q3_tigergraph", ("selected_segment", "selected_date")),
    4: QuerySpec(4, "q4_tigergraph", ("start_date", "end_date")),
    5: QuerySpec(
        5,
        "q5_tigergraph",
        ("selected_region", "start_date", "end_date"),
    ),
    6: QuerySpec(
        6,
        "q6_tigergraph",
        (
            "start_date",
            "end_date",
            "min_discount",
            "max_discount",
            "selected_quantity",
        ),
    ),
    7: QuerySpec(7, "q7_tigergraph", ("nation1", "nation2")),
    8: QuerySpec(
        8,
        "q8_tigergraph",
        ("selected_region", "selected_type", "selected_nation"),
    ),
    9: QuerySpec(9, "q9_tigergraph", ("selected_color",)),
    10: QuerySpec(10, "q10_tigergraph", ("start_date", "end_date")),
    11: QuerySpec(
        11,
        "q11_tigergraph",
        ("selected_nation", "fraction"),
        semantic_status="historical-single-query",
        note=(
            "The installed query named here is the historical single-query "
            "workaround. Formal Q11 execution is routed through "
            "run_q11_two_stage.py at every scale factor."
        ),
    ),
    12: QuerySpec(
        12,
        "q12_tigergraph",
        ("mode1", "mode2", "start_date", "end_date"),
    ),
    13: QuerySpec(13, "q13_tigergraph", ("word1", "word2")),
    14: QuerySpec(14, "q14_tigergraph", ("start_date", "end_date")),
    15: QuerySpec(15, "q15_tigergraph", ("start_date", "end_date")),
    16: QuerySpec(
        16,
        "q16_tigergraph",
        (
            "excluded_brand",
            "excluded_type_prefix",
            "size1",
            "size2",
            "size3",
            "size4",
            "size5",
            "size6",
            "size7",
            "size8",
        ),
    ),
    17: QuerySpec(
        17,
        "q17_tigergraph",
        ("selected_brand", "selected_container"),
    ),
    18: QuerySpec(18, "q18_tigergraph", ("quantity_threshold",)),
    19: QuerySpec(
        19,
        "q19_tigergraph",
        ("brand1", "brand2", "brand3", "qty1", "qty2", "qty3"),
        note="Uses the project's corrected official TPC-H semantics.",
    ),
    20: QuerySpec(
        20,
        "q20_tigergraph",
        ("name_prefix", "selected_nation", "start_date", "end_date"),
        note="Uses the project's corrected official TPC-H semantics.",
    ),
    21: QuerySpec(
        21,
        "q21_tigergraph_tpch_corrected",
        ("selected_nation",),
        note="Official semantics; final numwait, ordering, and LIMIT 100 are materialized by run_q21_q22_final.py.",
        variant="tpch-corrected",
        query_filename="q21_tigergraph_tpch_corrected.txt",
    ),
    22: QuerySpec(
        22,
        "q22_tigergraph",
        ("code1", "code2", "code3", "code4", "code5", "code6", "code7"),
        semantic_status="intermediate",
        note="Legacy single-query implementation. Formal Q22 uses the two-query run_q21_q22_final.py pipeline.",
    ),
}


NEO4J_COMPATIBLE_SPECS = {
    21: QuerySpec(
        21, "q21_tigergraph_neo4j_compatible", ("selected_nation",),
        semantic_status="comparison",
        note="Matches the Neo4j reference workload by omitting o_orderstatus='F'; Python materializes numwait and ordering.",
        variant="neo4j-compatible",
        query_filename="q21_tigergraph_neo4j_compatible.txt",
    ),
    2: QuerySpec(
        2, "q2_tigergraph_neo4j_compatible",
        ("selected_size", "selected_type", "selected_region"),
        semantic_status="comparison",
        note="Matches the Neo4j reference workload, including its missing second-stage minimum-cost filter.",
        variant="neo4j-compatible",
        query_filename="q2_tigergraph_neo4j_compatible.txt",
    ),
    8: QuerySpec(
        8, "q8_tigergraph_neo4j_compatible",
        ("selected_region", "selected_type", "selected_nation"),
        semantic_status="comparison",
        note="Matches the Neo4j reference traversal and ship-year grouping; market share is derived from returned numerator/denominator.",
        variant="neo4j-compatible",
        query_filename="q8_tigergraph_neo4j_compatible.txt",
    ),
    19: QuerySpec(
        19, "q19_tigergraph_neo4j_compatible",
        ("brand1", "brand2", "brand3", "qty1", "qty2", "qty3"),
        semantic_status="comparison",
        note="Matches the Neo4j reference predicates, including no p_size filters and its Q19 first-branch bounds.",
        variant="neo4j-compatible",
        query_filename="q19_tigergraph_neo4j_compatible.txt",
    ),
    20: QuerySpec(
        20, "q20_tigergraph_neo4j_compatible",
        ("name_prefix", "selected_nation", "start_date", "end_date"),
        semantic_status="comparison",
        note="Matches the Neo4j reference CONTAINS and total_qty <= 300 workload rather than official TPC-H Q20 semantics.",
        variant="neo4j-compatible",
        query_filename="q20_tigergraph_neo4j_compatible.txt",
    ),
}


def get_spec(number: int, variant: str = "current") -> QuerySpec:
    if variant == "current":
        return SPECS[number]
    if variant == "neo4j-compatible":
        try:
            return NEO4J_COMPATIBLE_SPECS[number]
        except KeyError as exc:
            raise ValueError(
                "neo4j-compatible is available only for Q2, Q8, Q19, Q20, and Q21"
            ) from exc
    raise ValueError(f"Unknown query variant: {variant}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def declared_query_signature(path: Path) -> tuple[str, tuple[str, ...]]:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+OPENCYPHER\s+QUERY\s+"
        r"(\w+)\s*\((.*?)\)\s*FOR\s+GRAPH",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"Cannot find an openCypher query declaration in {path}")
    fields = tuple(
        re.findall(
            r"(?:STRING|INT|UINT|FLOAT|DOUBLE|BOOL|DATETIME)\s+(\w+)",
            match.group(2),
            flags=re.IGNORECASE,
        )
    )
    return match.group(1), fields


def validate_spec(spec: QuerySpec) -> None:
    if not spec.query_file.is_file():
        raise FileNotFoundError(f"Query file not found: {spec.query_file}")
    if not spec.canonical_parameter_file.is_file():
        raise FileNotFoundError(
            f"Canonical parameter schedule not found: "
            f"{spec.canonical_parameter_file}"
        )
    declared, declared_fields = declared_query_signature(spec.query_file)
    if declared != spec.installed_query:
        raise ValueError(
            f"{spec.code} mismatch: file declares {declared!r}, "
            f"configuration expects {spec.installed_query!r}"
        )
    if declared_fields != spec.api_fields:
        raise ValueError(
            f"{spec.code} parameter mismatch: file declares {declared_fields}, "
            f"configuration expects {spec.api_fields}"
        )


def load_parameter_schedule(spec: QuerySpec, scale: str) -> list[dict[str, str]]:
    if scale not in SUPPORTED_SCALES:
        raise ValueError(f"Unsupported scale factor: {scale}")

    with spec.canonical_parameter_file.open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != RUNS:
        raise ValueError(
            f"{spec.canonical_parameter_file} contains {len(rows)} rows; "
            f"expected {RUNS}"
        )

    expected_runs = [str(number) for number in range(1, RUNS + 1)]
    actual_runs = [row.get("run", "") for row in rows]
    if actual_runs != expected_runs:
        raise ValueError(
            f"Unexpected run sequence in {spec.canonical_parameter_file}"
        )

    missing = [field for field in spec.api_fields if field not in rows[0]]
    if missing:
        raise ValueError(
            f"{spec.canonical_parameter_file} is missing API fields: {missing}"
        )

    # TPC-H Q11 is the only current workload parameter that changes with sf.
    if spec.number == 11:
        fraction = Decimal("0.0001") / Decimal(scale)
        fraction_text = format(fraction.normalize(), "f")
        for row in rows:
            row["fraction"] = fraction_text

    return rows


def api_parameters(spec: QuerySpec, row: dict[str, str]) -> dict[str, str]:
    return {field: row[field] for field in spec.api_fields}

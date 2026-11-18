# Formal experiment evidence

This directory contains the compact evidence set corresponding to the retained dissertation
results. It is organised by workload and scale factor.

- `queries/`: raw timings and summaries for Q1--Q22, plus retained output-validation reports.
- `entity_integrity/`: fixed-position timing records, global checks, and the reversible positive control.
- `referential_integrity/`: Cc, Oc, Pc, and Sc timing records and cleanup checks.
- `refresh/`: completed RF1/RF2 raw records, summaries, and round-level correctness reports.
- `query_source_map.csv`: source selection for each query and scale factor.
- `evidence_manifest.csv`: relative path, file size, and SHA-256 digest for each evidence file.

The query timing summary for each condition is derived from 20 repetitions by sorting the
recorded database times, removing the five fastest and five slowest observations, and taking
the mean of the remaining ten. The individual workload documentation explains any different
measurement boundary, including the multi-stage Q11 and Q22 implementations.

Generated TPC-H data, database volumes, failed attempts, retry logs, and repeated full-output
dumps are not included. The correctness reports document the checks that were retained; they
do not imply that every analytical query received independent source-data validation.

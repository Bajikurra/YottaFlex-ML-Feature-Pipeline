# YottaFlex AI — Point-in-Time ML Feature Pipeline

A locally runnable, reproducible data-engineering project that ingests synthetic transactional events, validates and quarantines bad records, calculates point-in-time customer features, publishes outputs to SQLite, and records operational metrics.

## Goals

- Prevent target leakage by computing features only from events available before the prediction timestamp.
- Keep the same feature calculation function for training and inference snapshots.
- Make reruns idempotent using deterministic keys and SQLite upserts.
- Preserve rejected rows with source row IDs and explicit reasons.
- Reconcile input, accepted, rejected, and output counts.
- Run locally with Python; no cloud account or API key is required.

## Architecture

text
Synthetic CSV generator
        |
        v
Ingestion + schema / business validation
        |                         |
        v                         v
Accepted events              rejected_records
        |
        v
Point-in-time feature builder (shared by training/inference)
        |
        v
SQLite: transactions, feature_snapshots, pipeline_runs
        |
        v
Validation report + tests + reconciliation SQL


## Data model and assumptions

### customers.csv
| Column | Type | Rules |
|---|---|---|
| customer_id | string | Required, stable customer key |
| signup_timestamp | ISO-8601 UTC timestamp | Required |

### transactions.csv
| Column | Type | Rules |
|---|---|---|
| event_id | string | Required deterministic event key |
| customer_id | string | Must exist in customers |
| event_timestamp | ISO-8601 UTC timestamp | Business event time |
| available_at | ISO-8601 UTC timestamp | When the pipeline could know the event |
| amount | decimal number | Required, finite; refunds may be negative |
| event_type | string | purchase or refund |
| source_file | string | Source lineage |

**Grain:** one row per transaction event. event_id is unique. Duplicate event IDs are rejected (first valid occurrence wins in input order). A transaction is eligible for a feature snapshot only if event_timestamp < as_of_timestamp **and** available_at < as_of_timestamp. This strict-before rule prevents same-timestamp ambiguity and excludes late-arriving events that were not yet known at prediction time.

**Feature window:** trailing 7 or 30 days, left-inclusive and right-exclusive: as_of_timestamp - window <= event_timestamp < as_of_timestamp, with available_at < as_of_timestamp. Refunds are included as signed amounts; event counts include both purchases and refunds. This is an explicit business assumption and can be changed in src/feature_pipeline/features.py.

**Target labels:** labels.csv is generated separately and is not passed to feature computation. In a real supervised-learning system, labels would be defined from outcomes in a future horizon and joined only after feature snapshots are frozen.

## Requirements

- Python 3.10+
- Dependencies: pandas, pytest

## Setup

bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt


## Quick start

Run the small reproducible dataset and pipeline:

bash
python -m feature_pipeline.cli --data-dir data/sample --db-path output/features.db --report-path output/report.json


Generate a larger deterministic dataset (100,000 transaction rows by default):

bash
python -m feature_pipeline.generate_data --out-dir data/generated --transactions 100000 --customers 5000 --seed 42
python -m feature_pipeline.cli --data-dir data/generated --db-path output/large.db --report-path output/large_report.json


Run tests:

bash
pytest -q


Inspect the SQLite database:

bash
python - <<'PY'
import sqlite3
con = sqlite3.connect("output/features.db")
for table in ("pipeline_runs", "feature_snapshots", "rejected_records"):
    print("\\n", table)
    print(con.execute(f"SELECT * FROM {table} LIMIT 5").fetchall())
con.close()
PY


## Outputs

- transactions: accepted and normalized transaction events
- feature_snapshots: one feature row per (customer_id, as_of_timestamp, feature_version)
- rejected_records: rejected input records with row ID, source file, reason, and raw JSON
- pipeline_runs: run ID, start/end timestamps, status, counts, duration, and failure reason
- JSON report: reconciliation counts and simple performance measurement

A successful run should satisfy:

input_rows = accepted_rows + rejected_rows

feature_rows = number of distinct customer/as-of snapshots generated

The report includes a source-to-target reconciliation section. A run with invalid rows can still complete with status `SUCCESS_WITH_REJECTS`; fatal processing errors are logged as `FAILED` and re-raised.

## Idempotency, retry, and backfill

- Transactions are keyed by event_id and inserted with ON CONFLICT DO UPDATE.
- Feature rows use the deterministic composite key (customer_id, as_of_timestamp, feature_version) and are upserted.
- Re-running the same files does not create duplicate transaction or feature rows. A new audit row is still written for each execution.
- If a run fails, inspect pipeline_runs.failure_reason, fix the input/configuration, and rerun. Upserts make retry safe for the same keys.
- To backfill, provide snapshots with historical as_of_timestamp values and rerun. The same point-in-time availability rules apply.
- Quarantine rows are keyed by (run_id, source_row_id) so every run's rejection evidence is preserved.

## Validation and tests

Tests cover the happy path, empty input, malformed timestamps/amounts, missing required fields, duplicate event IDs, invalid customer references, out-of-order/late events, target-label isolation, deterministic results, and idempotent reruns. The pipeline performs basic reconciliation and records elapsed time and throughput.

## Performance note

The generator supports 100,000+ rows. The current implementation favors clarity and deterministic behavior, using pandas and a per-customer feature calculation. For substantially larger data, optimize by sorting events once and using vectorized rolling-window operations or a SQL window-function implementation; benchmark before adding distributed processing.

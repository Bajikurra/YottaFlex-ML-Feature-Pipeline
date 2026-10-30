# Data dictionary

All names use `snake_case`. Timestamps are ISO-8601 with timezone offsets; normalized pipeline timestamps are UTC. IDs are stable strings.

## Source entities

- **customers** — one row per customer. Primary key: `customer_id`.
- **transactions** — one row per event. Primary key: `event_id`; foreign key: `customer_id` → customers. Amount is signed; refunds are negative.
- **labels** — one row per customer label in the synthetic example. `target_label` is intentionally isolated from feature computation.

## Target tables

- **transactions** — validated transaction records, unique by `event_id`.
- **feature_snapshots** — one row per customer, prediction timestamp, and feature version.
- **pipeline_runs** — one audit row per execution.
- **rejected_records** — rejected raw records with source location and reason.

## Feature definitions

| Feature | Definition |
|---|---|
| `txn_count_7d` | Count of eligible transaction events in `[as_of - 7 days, as_of)` |
| `txn_amount_sum_7d` | Sum of signed amounts over the 7-day window |
| `txn_count_30d` | Count of eligible transaction events in `[as_of - 30 days, as_of)` |
| `txn_amount_avg_30d` | Mean signed amount over the 30-day window; null when no eligible events |
| `last_txn_age_hours` | Hours between as-of time and latest eligible event; null when no eligible events |

Eligibility requires both `event_timestamp < as_of_timestamp` and `available_at < as_of_timestamp`. This excludes future events and events that arrived late.

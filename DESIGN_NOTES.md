# Design and trade-off notes

1. **Point-in-time correctness:** Feature calculations filter both business event time and system availability time. This is stricter than event-time-only filtering and models what the pipeline could know at prediction time.
2. **No label leakage:** `labels.csv` is not loaded by the pipeline. Labels should be joined after snapshots are frozen, using an explicit future label horizon.
3. **Training/inference parity:** both public entry points call the same pure `build_features` function to reduce transformation drift.
4. **Idempotency:** stable event IDs and composite feature keys are enforced in SQLite; upserts make retries safe.
5. **Quarantine:** rejects preserve raw input plus source row and reason. First occurrence of a duplicate key wins within a batch.
6. **Observability:** each run records status, timestamps, row counts, duration, and failure reason.
7. **Trade-off:** per-snapshot filtering is readable and sufficient for the assessment sample. For very large datasets, sort once and use vectorized rolling windows or SQL window functions.
8. **Limitations:** no scheduler, streaming processing, schema registry, distributed execution, or concurrent-run locking is implemented. These are intentionally out of scope for a 72-hour vertical slice.

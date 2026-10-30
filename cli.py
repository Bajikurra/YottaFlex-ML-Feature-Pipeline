"""Command-line runner with audit logging and reconciliation report."""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from .validation import validate_customers, validate_transactions
from .features import build_features
from .storage import connect, publish_transactions, publish_features, save_rejects

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_pipeline(data_dir, db_path, report_path, as_of=None):
    started_clock = time.perf_counter()
    run_id = str(uuid.uuid4())
    started_at = now_iso()
    con = connect(db_path)
    input_rows = accepted_rows = rejected_rows = feature_rows = 0
    status, failure = "RUNNING", None
    con.execute("INSERT INTO pipeline_runs(run_id, started_at, status) VALUES(?,?,?)", (run_id, started_at, status))
    con.commit()
    try:
        data_dir = Path(data_dir)
        customers_raw = pd.read_csv(data_dir / "customers.csv", dtype=str, keep_default_na=False)
        tx_raw = pd.read_csv(data_dir / "transactions.csv", dtype=str, keep_default_na=False)
        input_rows = len(tx_raw)
        customers, cust_rejects = validate_customers(customers_raw)
        tx, tx_rejects = validate_transactions(tx_raw, set(customers["customer_id"].tolist()))
        # Customer rejects are also traceable in quarantine; row IDs are prefixed to avoid collisions.
        rejects = cust_rejects + tx_rejects
        for r in cust_rejects:
            r["source_row_id"] = "customer:" + r["source_row_id"]
        accepted_rows = len(tx)
        rejected_rows = len(rejects)
        publish_transactions(con, tx)
        save_rejects(con, run_id, rejects)
        if as_of:
            snapshot_time = pd.to_datetime(as_of, utc=True).isoformat()
        elif not tx.empty:
            # Deterministic sample point: maximum event timestamp + one day.
            snapshot_time = (pd.to_datetime(tx["event_timestamp"], utc=True).max() + pd.Timedelta(days=1)).isoformat()
        else:
            snapshot_time = "2026-01-01T00:00:00+00:00"
        snapshots = pd.DataFrame([
            {"customer_id": cid, "as_of_timestamp": snapshot_time}
            for cid in sorted(customers["customer_id"].tolist())
        ])
        feature_df = build_features(tx, snapshots)
        feature_rows = len(feature_df)
        publish_features(con, feature_df)
        ended_at = now_iso()
        duration = time.perf_counter() - started_clock
        status = "SUCCESS_WITH_REJECTS" if rejected_rows else "SUCCESS"
        report = {
            "run_id": run_id, "status": status, "started_at": started_at, "ended_at": ended_at,
            "input_rows": input_rows, "accepted_rows": accepted_rows, "rejected_rows": rejected_rows,
            "feature_rows_this_run": feature_rows, "duration_seconds": round(duration, 6),
            "input_reconciliation_passed": input_rows == len(tx_raw),
            "transaction_reconciliation_passed": len(tx_raw) == len(tx) + len(tx_rejects),
            "note": "Customer reference rejects are separately quarantined; transaction reconciliation compares transaction input to accepted plus rejected transaction rows.",
            "features": feature_df.head(20).where(pd.notna(feature_df.head(20)), None).to_dict(orient="records")
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        con.execute("""UPDATE pipeline_runs SET ended_at=?, status=?, input_rows=?, accepted_rows=?,
                    rejected_rows=?, feature_rows=?, duration_seconds=?, failure_reason=? WHERE run_id=?""",
                    (ended_at, status, input_rows, accepted_rows, rejected_rows, feature_rows, duration, None, run_id))
        con.commit()
        return report
    except Exception as exc:
        ended_at = now_iso()
        duration = time.perf_counter() - started_clock
        con.execute("""UPDATE pipeline_runs SET ended_at=?, status='FAILED', input_rows=?, accepted_rows=?,
                    rejected_rows=?, feature_rows=?, duration_seconds=?, failure_reason=? WHERE run_id=?""",
                    (ended_at, input_rows, accepted_rows, rejected_rows, feature_rows, duration, repr(exc), run_id))
        con.commit()
        raise
    finally:
        con.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="data/sample")
    p.add_argument("--db-path", default="output/features.db")
    p.add_argument("--report-path", default="output/report.json")
    p.add_argument("--as-of", help="Optional ISO-8601 UTC prediction timestamp")
    a = p.parse_args()
    report = run_pipeline(a.data_dir, a.db_path, a.report_path, a.as_of)
    print(json.dumps({k:v for k,v in report.items() if k != "features"}, indent=2))
if __name__ == "__main__":
    main()

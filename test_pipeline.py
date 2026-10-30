import sqlite3
import pandas as pd
from feature_pipeline.features import build_features, build_training_features, build_inference_features
from feature_pipeline.validation import validate_transactions
from feature_pipeline.cli import run_pipeline

def sample_tx():
    return pd.DataFrame([
        {"event_id":"e1","customer_id":"c1","event_timestamp":"2025-01-01T00:00:00+00:00","available_at":"2025-01-01T00:01:00+00:00","amount":10.0,"event_type":"purchase","source_file":"x.csv"},
        {"event_id":"e2","customer_id":"c1","event_timestamp":"2025-01-05T00:00:00+00:00","available_at":"2025-01-05T00:01:00+00:00","amount":20.0,"event_type":"purchase","source_file":"x.csv"},
        # Event happened before as_of but arrived after it: must not leak.
        {"event_id":"late","customer_id":"c1","event_timestamp":"2025-01-06T00:00:00+00:00","available_at":"2025-01-12T00:00:00+00:00","amount":999.0,"event_type":"purchase","source_file":"x.csv"},
        # Future event: must not leak.
        {"event_id":"future","customer_id":"c1","event_timestamp":"2025-01-20T00:00:00+00:00","available_at":"2025-01-20T00:00:00+00:00","amount":500.0,"event_type":"purchase","source_file":"x.csv"},
    ])

def test_point_in_time_excludes_future_and_late_events():
    tx = sample_tx()
    snaps = pd.DataFrame([{"customer_id":"c1","as_of_timestamp":"2025-01-10T00:00:00Z"}])
    result = build_features(tx, snaps).iloc[0]
    assert result.txn_count_7d == 1
    assert result.txn_amount_sum_7d == 20.0
    assert result.txn_count_30d == 2
    assert result.txn_amount_avg_30d == 15.0

def test_training_and_inference_transformations_match():
    tx = sample_tx()
    snaps = pd.DataFrame([{"customer_id":"c1","as_of_timestamp":"2025-01-10T00:00:00Z"}])
    pd.testing.assert_frame_equal(build_training_features(tx, snaps), build_inference_features(tx, snaps))

def test_empty_input_produces_zero_count_features():
    tx = pd.DataFrame(columns=["event_id","customer_id","event_timestamp","available_at","amount","event_type","source_file"])
    snaps = pd.DataFrame([{"customer_id":"c1","as_of_timestamp":"2025-01-10T00:00:00Z"}])
    result = build_features(tx, snaps).iloc[0]
    assert result.txn_count_7d == 0
    assert result.txn_count_30d == 0
    assert result.txn_amount_sum_7d == 0

def test_validation_rejects_missing_malformed_duplicate_and_bad_reference():
    rows = pd.DataFrame([
        {"event_id":"e1","customer_id":"c1","event_timestamp":"2025-01-01T00:00:00Z","available_at":"2025-01-01T00:01:00Z","amount":"5","event_type":"purchase","source_file":"x"},
        {"event_id":"e1","customer_id":"c1","event_timestamp":"2025-01-01T00:00:00Z","available_at":"2025-01-01T00:01:00Z","amount":"5","event_type":"purchase","source_file":"x"},
        {"event_id":"e2","customer_id":"","event_timestamp":"2025-01-01T00:00:00Z","available_at":"2025-01-01T00:01:00Z","amount":"5","event_type":"purchase","source_file":"x"},
        {"event_id":"e3","customer_id":"c1","event_timestamp":"bad","available_at":"2025-01-01T00:01:00Z","amount":"5","event_type":"purchase","source_file":"x"},
        {"event_id":"e4","customer_id":"missing","event_timestamp":"2025-01-01T00:00:00Z","available_at":"2025-01-01T00:01:00Z","amount":"5","event_type":"purchase","source_file":"x"},
    ])
    accepted, rejects = validate_transactions(rows, {"c1"})
    assert len(accepted) == 1
    assert len(rejects) == 4
    assert {r["reason"] for r in rejects} >= {"duplicate_event_id","missing_required:customer_id","invalid_timestamp:event_timestamp","invalid_customer_reference"}

def make_input(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame([{"customer_id":"c1","signup_timestamp":"2024-01-01T00:00:00Z"}]).to_csv(data/"customers.csv", index=False)
    pd.DataFrame([{"event_id":"e1","customer_id":"c1","event_timestamp":"2025-01-01T00:00:00Z","available_at":"2025-01-01T00:01:00Z","amount":10,"event_type":"purchase","source_file":"transactions.csv"}]).to_csv(data/"transactions.csv", index=False)
    return data

def test_rerun_is_idempotent(tmp_path):
    data = make_input(tmp_path)
    db = tmp_path / "out.db"
    report = tmp_path / "report.json"
    run_pipeline(data, db, report, "2025-01-02T00:00:00Z")
    run_pipeline(data, db, report, "2025-01-02T00:00:00Z")
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM feature_snapshots").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0] == 2
    con.close()

def test_empty_transaction_file(tmp_path):
    data = tmp_path / "empty"
    data.mkdir()
    pd.DataFrame([{"customer_id":"c1","signup_timestamp":"2024-01-01T00:00:00Z"}]).to_csv(data/"customers.csv", index=False)
    pd.DataFrame(columns=["event_id","customer_id","event_timestamp","available_at","amount","event_type","source_file"]).to_csv(data/"transactions.csv", index=False)
    report = run_pipeline(data, tmp_path/"empty.db", tmp_path/"report.json")
    assert report["input_rows"] == 0
    assert report["accepted_rows"] == 0
    assert report["rejected_rows"] == 0

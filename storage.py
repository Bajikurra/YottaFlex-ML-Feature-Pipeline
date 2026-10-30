"""SQLite schema and idempotent publishing helpers."""
import json
import sqlite3
from pathlib import Path
import pandas as pd

def connect(db_path):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS transactions (
      event_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, event_timestamp TEXT NOT NULL,
      available_at TEXT NOT NULL, amount REAL NOT NULL, event_type TEXT NOT NULL, source_file TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS feature_snapshots (
      customer_id TEXT NOT NULL, as_of_timestamp TEXT NOT NULL, feature_version TEXT NOT NULL,
      txn_count_7d INTEGER NOT NULL, txn_amount_sum_7d REAL NOT NULL,
      txn_count_30d INTEGER NOT NULL, txn_amount_avg_30d REAL, last_txn_age_hours REAL,
      PRIMARY KEY(customer_id, as_of_timestamp, feature_version)
    );
    CREATE TABLE IF NOT EXISTS pipeline_runs (
      run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
      status TEXT NOT NULL, input_rows INTEGER DEFAULT 0, accepted_rows INTEGER DEFAULT 0,
      rejected_rows INTEGER DEFAULT 0, feature_rows INTEGER DEFAULT 0, duration_seconds REAL,
      failure_reason TEXT
    );
    CREATE TABLE IF NOT EXISTS rejected_records (
      run_id TEXT NOT NULL, source_row_id TEXT NOT NULL, source_file TEXT NOT NULL,
      reason TEXT NOT NULL, raw_record TEXT NOT NULL,
      PRIMARY KEY(run_id, source_row_id)
    );
    """)
    con.commit()
    return con

def publish_transactions(con, df):
    if df.empty: return
    con.executemany("""
      INSERT INTO transactions VALUES(?,?,?,?,?,?,?)
      ON CONFLICT(event_id) DO UPDATE SET
        customer_id=excluded.customer_id, event_timestamp=excluded.event_timestamp,
        available_at=excluded.available_at, amount=excluded.amount,
        event_type=excluded.event_type, source_file=excluded.source_file
    """, list(df[["event_id","customer_id","event_timestamp","available_at","amount","event_type","source_file"]].itertuples(index=False, name=None)))
    con.commit()

def publish_features(con, df):
    if df.empty: return
    cols = ["customer_id","as_of_timestamp","feature_version","txn_count_7d","txn_amount_sum_7d","txn_count_30d","txn_amount_avg_30d","last_txn_age_hours"]
    con.executemany("""
      INSERT INTO feature_snapshots VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(customer_id, as_of_timestamp, feature_version) DO UPDATE SET
        txn_count_7d=excluded.txn_count_7d, txn_amount_sum_7d=excluded.txn_amount_sum_7d,
        txn_count_30d=excluded.txn_count_30d, txn_amount_avg_30d=excluded.txn_amount_avg_30d,
        last_txn_age_hours=excluded.last_txn_age_hours
    """, list(df[cols].itertuples(index=False, name=None)))
    con.commit()

def save_rejects(con, run_id, rejects):
    con.executemany("INSERT OR REPLACE INTO rejected_records VALUES(?,?,?,?,?)", [
        (run_id, r["source_row_id"], r["source_file"], r["reason"], r["raw_record"]) for r in rejects
    ])
    con.commit()

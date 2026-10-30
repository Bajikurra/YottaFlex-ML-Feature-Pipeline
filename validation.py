"""Strict input validation with traceable per-row rejection reasons."""
import json
import math
import pandas as pd

TRANSACTION_COLUMNS = ["event_id", "customer_id", "event_timestamp", "available_at", "amount", "event_type", "source_file"]
CUSTOMER_COLUMNS = ["customer_id", "signup_timestamp"]
ALLOWED_TYPES = {"purchase", "refund"}

def _utc(value):
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts

def validate_customers(df: pd.DataFrame):
    missing_cols = set(CUSTOMER_COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Customer schema missing columns: {sorted(missing_cols)}")
    accepted, rejected, seen = [], [], set()
    for idx, row in df.iterrows():
        raw = row.to_dict()
        cid = str(row.get("customer_id", "")).strip()
        signup = _utc(row.get("signup_timestamp"))
        reason = None
        if not cid or cid.lower() == "nan":
            reason = "missing_required:customer_id"
        elif signup is None:
            reason = "invalid_timestamp:signup_timestamp"
        elif cid in seen:
            reason = "duplicate_customer_id"
        if reason:
            rejected.append({"source_row_id": str(idx), "source_file": "customers.csv", "reason": reason, "raw_record": json.dumps(raw, default=str)})
        else:
            seen.add(cid)
            accepted.append({"customer_id": cid, "signup_timestamp": signup})
    return pd.DataFrame(accepted, columns=CUSTOMER_COLUMNS), rejected

def validate_transactions(df: pd.DataFrame, known_customers: set[str]):
    missing_cols = set(TRANSACTION_COLUMNS) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Transaction schema missing columns: {sorted(missing_cols)}")
    accepted, rejected, seen = [], [], set()
    for idx, row in df.iterrows():
        raw = row.to_dict()
        event_id = str(row.get("event_id", "")).strip()
        customer_id = str(row.get("customer_id", "")).strip()
        event_ts = _utc(row.get("event_timestamp"))
        available_ts = _utc(row.get("available_at"))
        try:
            amount = float(row.get("amount"))
            amount_ok = math.isfinite(amount)
        except (TypeError, ValueError):
            amount, amount_ok = None, False
        event_type = str(row.get("event_type", "")).strip()
        reason = None
        if not event_id or event_id.lower() == "nan":
            reason = "missing_required:event_id"
        elif not customer_id or customer_id.lower() == "nan":
            reason = "missing_required:customer_id"
        elif event_id in seen:
            reason = "duplicate_event_id"
        elif event_ts is None:
            reason = "invalid_timestamp:event_timestamp"
        elif available_ts is None:
            reason = "invalid_timestamp:available_at"
        elif not amount_ok:
            reason = "invalid_amount"
        elif event_type not in ALLOWED_TYPES:
            reason = "invalid_event_type"
        elif customer_id not in known_customers:
            reason = "invalid_customer_reference"
        elif available_ts < event_ts:
            reason = "available_before_event_timestamp"
        if reason:
            rejected.append({"source_row_id": str(idx), "source_file": str(row.get("source_file", "transactions.csv")), "reason": reason, "raw_record": json.dumps(raw, default=str)})
        else:
            seen.add(event_id)
            accepted.append({
                "event_id": event_id, "customer_id": customer_id,
                "event_timestamp": event_ts.isoformat(), "available_at": available_ts.isoformat(),
                "amount": amount, "event_type": event_type,
                "source_file": str(row.get("source_file", "transactions.csv"))
            })
    return pd.DataFrame(accepted, columns=TRANSACTION_COLUMNS), rejected

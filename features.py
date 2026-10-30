"""Point-in-time feature computation shared by training and inference."""
import pandas as pd

FEATURE_VERSION = "v1"
WINDOWS = {"7d": pd.Timedelta(days=7), "30d": pd.Timedelta(days=30)}

def build_features(transactions: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    """Build customer snapshots using only events strictly known before as_of_timestamp.

    Feature window is [as_of - window, as_of). Late-arriving events are excluded when
    available_at >= as_of, even if their event_timestamp is earlier.
    """
    columns = ["customer_id", "as_of_timestamp", "feature_version", "txn_count_7d",
               "txn_amount_sum_7d", "txn_count_30d", "txn_amount_avg_30d", "last_txn_age_hours"]
    if snapshots.empty:
        return pd.DataFrame(columns=columns)
    tx = transactions.copy()
    if not tx.empty:
        tx["event_timestamp"] = pd.to_datetime(tx["event_timestamp"], utc=True)
        tx["available_at"] = pd.to_datetime(tx["available_at"], utc=True)
    output = []
    for _, snap in snapshots.iterrows():
        cid = str(snap["customer_id"])
        as_of = pd.to_datetime(snap["as_of_timestamp"], utc=True)
        eligible = tx[
            (tx["customer_id"] == cid)
            & (tx["event_timestamp"] < as_of)
            & (tx["available_at"] < as_of)
        ] if not tx.empty else tx
        w7 = eligible[eligible["event_timestamp"] >= as_of - WINDOWS["7d"]]
        w30 = eligible[eligible["event_timestamp"] >= as_of - WINDOWS["30d"]]
        last_age = None
        if not eligible.empty:
            last_age = round((as_of - eligible["event_timestamp"].max()).total_seconds() / 3600.0, 6)
        avg30 = None if w30.empty else round(float(w30["amount"].mean()), 6)
        output.append({
            "customer_id": cid, "as_of_timestamp": as_of.isoformat(),
            "feature_version": FEATURE_VERSION,
            "txn_count_7d": int(len(w7)),
            "txn_amount_sum_7d": round(float(w7["amount"].sum()), 6),
            "txn_count_30d": int(len(w30)),
            "txn_amount_avg_30d": avg30,
            "last_txn_age_hours": last_age
        })
    return pd.DataFrame(output, columns=columns)

def build_training_features(transactions: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    """Training entry point; deliberately delegates to the same transformation."""
    return build_features(transactions, snapshots)

def build_inference_features(transactions: pd.DataFrame, snapshots: pd.DataFrame) -> pd.DataFrame:
    """Inference entry point; deliberately delegates to the same transformation."""
    return build_features(transactions, snapshots)

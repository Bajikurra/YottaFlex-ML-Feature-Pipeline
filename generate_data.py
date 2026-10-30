"""Create deterministic synthetic source data, including labelled edge cases."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

def generate(out_dir: str | Path, transactions: int = 1000, customers: int = 100, seed: int = 42):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    customer_ids = [f"cust_{i:05d}" for i in range(customers)]
    customer_df = pd.DataFrame({
        "customer_id": customer_ids,
        "signup_timestamp": [(start - pd.Timedelta(days=int(x))).isoformat()
                              for x in rng.integers(1, 365, size=customers)]
    })
    rows = []
    for i in range(transactions):
        cust = customer_ids[int(rng.integers(0, customers))]
        event_time = start + pd.Timedelta(minutes=int(rng.integers(0, 365 * 24 * 60)))
        delay_minutes = int(rng.integers(0, 60 * 24 * 5))
        typ = "refund" if rng.random() < 0.08 else "purchase"
        amount = round(float(rng.uniform(1, 500)), 2) * (-1 if typ == "refund" else 1)
        rows.append({
            "event_id": f"evt_{i:08d}", "customer_id": cust,
            "event_timestamp": event_time.isoformat(),
            "available_at": (event_time + pd.Timedelta(minutes=delay_minutes)).isoformat(),
            "amount": amount, "event_type": typ, "source_file": "transactions.csv"
        })
    tx = pd.DataFrame(rows, columns=["event_id","customer_id","event_timestamp","available_at","amount","event_type","source_file"])
    # Deterministically inject a few negative scenarios into generated datasets with enough rows.
    if transactions >= 8:
        tx.loc[0, "event_id"] = "evt_invalid_missing_customer"
        tx.loc[0, "customer_id"] = ""
        tx.loc[1, "event_timestamp"] = "not-a-timestamp"
        tx.loc[2, "amount"] = "not-a-number"
        tx.loc[3, "customer_id"] = "cust_does_not_exist"
        tx.loc[4, "event_type"] = "unexpected_type"
        tx.loc[5, "event_id"] = tx.loc[6, "event_id"]  # duplicate key
        tx.loc[7, "available_at"] = "2024-01-01T00:00:00Z"  # out-of-order availability anomaly
    tx.to_csv(out / "transactions.csv", index=False)
    customer_df.to_csv(out / "customers.csv", index=False)
    # Labels are intentionally separate and never passed to the feature builder.
    labels = pd.DataFrame({
        "customer_id": customer_ids,
        "label_timestamp": [(start + pd.Timedelta(days=365)).isoformat()] * customers,
        "target_label": rng.integers(0, 2, size=customers)
    })
    labels.to_csv(out / "labels.csv", index=False)
    return {"customers": len(customer_df), "transactions": len(tx), "labels": len(labels)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/generated")
    p.add_argument("--transactions", type=int, default=100000)
    p.add_argument("--customers", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    print(generate(a.out_dir, a.transactions, a.customers, a.seed))
if __name__ == "__main__":
    main()

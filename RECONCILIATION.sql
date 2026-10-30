-- Run with sqlite3 output/features.db < docs/RECONCILIATION.sql
SELECT 'transactions' AS check_name, COUNT(*) AS row_count FROM transactions;
SELECT 'duplicate_event_ids' AS check_name, COUNT(*) AS duplicate_groups
FROM (SELECT event_id FROM transactions GROUP BY event_id HAVING COUNT(*) > 1);
SELECT 'feature_duplicate_keys' AS check_name, COUNT(*) AS duplicate_groups
FROM (SELECT customer_id, as_of_timestamp, feature_version
      FROM feature_snapshots
      GROUP BY customer_id, as_of_timestamp, feature_version HAVING COUNT(*) > 1);
SELECT status, COUNT(*) AS runs, SUM(input_rows) AS input_rows,
       SUM(accepted_rows) AS accepted_rows, SUM(rejected_rows) AS rejected_rows
FROM pipeline_runs GROUP BY status;
SELECT reason, COUNT(*) AS rejected_count FROM rejected_records GROUP BY reason ORDER BY rejected_count DESC;

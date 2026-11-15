# Simulated transfer sandbox

This is coursework, not a real banking service. The old transfer route used floats and committed debit, credit, and ledger steps independently.

Changes: transfers are disabled by default. A disposable staging environment may opt in with AAWCL_ENABLE_SIMULATED_TRANSFERS=1. Validations require 16-digit account ID strings and positive decimal-string amounts with up to two decimal places. Account locks are acquired in a consistent order; the sender must own the account; the debit, credit, and both log records commit together or roll back together.

Offline Python tests verify parsing and rollback behavior against a fake connection, NOT SQL Server serializability. Before even enabling a public demo, test against an isolated SQL Server schema, add idempotency keys and durable unique ledger constraints, audit all remaining account routes, and ensure credentials are rotated. Do not connect this simulator to real funds or customer information.

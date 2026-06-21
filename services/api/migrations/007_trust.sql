-- Trust ledger (#2 entailment, #3 conflicts, #4 URL liveness).
-- Per-claim entailment verdicts are now persisted to the existing (previously unused) claims table;
-- the structured trust summary (engine, supported/refuted/nei, conflicts, url health, coverage) rides
-- on the report row so the audit trail survives a reload.
alter table claims add column if not exists conflict boolean default false;
alter table reports add column if not exists trust jsonb default '{}'::jsonb;

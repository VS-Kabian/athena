-- P2-7: persist RAGAS-style faithfulness + ALCE-style citation metrics per eval run so the regression
-- gate can compare batch-over-batch. Idempotent (add column if not exists) and additive (nullable), so
-- it is safe to re-run and does not affect the existing 6-column eval_runs insert.
alter table eval_runs add column if not exists faithfulness numeric;
alter table eval_runs add column if not exists citation_recall numeric;
alter table eval_runs add column if not exists citation_precision numeric;

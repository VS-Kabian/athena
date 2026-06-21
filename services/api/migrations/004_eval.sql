create table if not exists eval_runs (
  id uuid primary key default gen_random_uuid(),
  batch text,
  topic text,
  run_id uuid,
  race_overall numeric,
  fact_risk numeric,
  quality_score int,
  created_at timestamptz default now()
);

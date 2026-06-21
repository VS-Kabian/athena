-- Hot-path indexes to avoid sequential scans as the tables grow.

-- reconcile_stale_runs() filters on (status, created_at) on every startup
create index if not exists idx_runs_status_created on research_runs(status, created_at);

-- get_run() and the report.md/.pdf routes select the latest report for a run
create index if not exists idx_reports_run on reports(run_id, created_at desc);

-- eval_runs.run_id is joined/looked up but was unindexed
create index if not exists idx_eval_runs_run on eval_runs(run_id);

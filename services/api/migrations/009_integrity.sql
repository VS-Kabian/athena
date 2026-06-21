-- 009: data-integrity hardening (audit follow-up).
-- (a) eval_runs.run_id had no foreign key -> deleting a research_runs row orphaned eval_runs rows.
--     Null out any pre-existing orphans first so the constraint can be added cleanly, then add the FK.
update eval_runs set run_id = null
  where run_id is not null and run_id not in (select id from research_runs);
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'eval_runs_run_id_fkey') then
    alter table eval_runs add constraint eval_runs_run_id_fkey
      foreign key (run_id) references research_runs(id) on delete set null;
  end if;
end $$;

-- (b) kg_entities had no dedup -> the same entity was re-inserted across runs/sources (unbounded growth).
--     A unique (run_id, norm) lets graphmem insert with ON CONFLICT DO NOTHING.
create unique index if not exists uq_kg_entities_run_norm on kg_entities(run_id, norm);

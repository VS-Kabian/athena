alter table reports add column if not exists citations jsonb default '[]'::jsonb;
alter table reports add column if not exists flagged jsonb default '[]'::jsonb;

create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists research_runs (
  id uuid primary key default gen_random_uuid(),
  topic text not null,
  params jsonb default '{}',
  status text default 'queued',
  rounds_total int default 1,
  round_current int default 0,
  quality_score int,
  created_at timestamptz default now(),
  completed_at timestamptz
);

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  url text, url_hash text, title text, domain text,
  source_type text default 'web',
  round int default 1,
  trust_score numeric, rrf_score numeric, validated boolean default false,
  raw_excerpt text,
  created_at timestamptz default now(),
  unique (run_id, url_hash)
);

create table if not exists claims (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  text text not null, verdict text default 'unverified', confidence numeric
);

create table if not exists citations (
  id uuid primary key default gen_random_uuid(),
  claim_id uuid references claims(id) on delete cascade,
  source_id uuid references sources(id) on delete cascade,
  quote text
);

create table if not exists reports (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  markdown text, quality_breakdown jsonb, created_at timestamptz default now()
);

create index if not exists idx_sources_run on sources(run_id);
create index if not exists idx_claims_run on claims(run_id);

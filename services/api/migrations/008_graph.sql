-- GraphRAG memory (Phase 3): entity-relationship triples extracted from validated sources, for
-- multi-hop reasoning and richer cross-run recall. Postgres-native (no Neo4j). Gated behind a flag
-- (settings.graphrag) — the tables exist regardless so the schema is forward-compatible.
create table if not exists kg_entities (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  name text not null,
  norm text not null,                 -- normalized name for dedup / lookup (lowercased, trimmed)
  type text default '',
  created_at timestamptz default now()
);

create table if not exists kg_relations (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  subject text not null, subject_norm text not null,
  predicate text not null,
  object text not null, object_norm text not null,
  source_url text default '',
  created_at timestamptz default now()
);

create index if not exists idx_kg_entities_norm on kg_entities(norm);
create index if not exists idx_kg_relations_subject on kg_relations(subject_norm);
create index if not exists idx_kg_relations_object on kg_relations(object_norm);
create index if not exists idx_kg_relations_run on kg_relations(run_id);

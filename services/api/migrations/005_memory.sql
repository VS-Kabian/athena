-- Cross-run long-term memory: a per-run summary embedded for semantic recall of prior research.
-- Embedding dim 384 = BAAI/bge-small-en-v1.5 (see athena/embed.py).
create table if not exists research_memory (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references research_runs(id) on delete cascade,
  topic text not null,
  summary text not null,
  embedding vector(384),
  created_at timestamptz default now()
);

-- HNSW (not ivfflat): correct recall on small tables and no list-training step. ivfflat with
-- few rows leaves empty probe lists and silently returns zero matches early in a deployment.
create index if not exists idx_memory_embedding
  on research_memory using hnsw (embedding vector_cosine_ops);
